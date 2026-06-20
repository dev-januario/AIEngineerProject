"""
Leads Router
============
Endpoints para o ciclo de vida completo de leads do Vigil Summit.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_funnel_for_lead, run_post_event_for_lead
from app.core.security import require_api_key
from app.db.session import get_db
from app.models.lead import FunnelPhase, Lead, LeadStatus
from app.schemas.lead import LeadCreate, LeadRead, LeadSummary, LeadUpdate
from app.services.enrichment import classify_lead_eligibility

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["leads"])

# Capacidade máxima do evento
EVENT_CAPACITY = 120


@router.get(
    "/spots",
    summary="Vagas disponíveis",
    description="Retorna quantas vagas ainda restam para o evento.",
)
async def get_available_spots(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(func.count()).select_from(Lead))
    total = result.scalar() or 0
    remaining = max(0, EVENT_CAPACITY - total)
    return {
        "capacity": EVENT_CAPACITY,
        "registered": total,
        "remaining": remaining,
        "is_full": remaining == 0,
    }


# ── Check-in via QR Code ──────────────────────────────────────────────────────

class CheckinRequest(BaseModel):
    email: EmailStr


@router.post(
    "/checkin",
    response_model=dict,
    summary="Confirmar presença via QR Code",
    description="Endpoint público chamado pela página de check-in. Marca o lead como presente.",
)
async def checkin_lead(
    payload: CheckinRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Lead).where(Lead.email == payload.email.lower()))
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email não encontrado. Verifique se usou o mesmo email do cadastro.",
        )

    if lead.attended is True:
        return {
            "already_checked_in": True,
            "name": lead.name,
            "message": f"Olá, {lead.name.split()[0]}! Sua presença já foi confirmada. Aproveite o evento! 🎉",
        }

    lead.attended = True
    lead.status = LeadStatus.ATTENDED
    lead.event_notes = (lead.event_notes or "") + f"\n[Check-in QR Code: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} BRT]"
    await db.commit()

    logger.info(f"[Checkin] Presença confirmada — lead_id={lead.id} | email={lead.email}")
    return {
        "already_checked_in": False,
        "name": lead.name,
        "message": f"Presença confirmada! Bem-vindo(a), {lead.name.split()[0]}! 🎉 Seu brinde está garantido.",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_lead_or_404(lead_id: int, db: AsyncSession) -> Lead:
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead não encontrado")
    return lead


async def _trigger_funnel(lead: Lead) -> None:
    """Roda o funil em background após criação do lead."""
    from app.db.session import AsyncSessionLocal
    from datetime import datetime, timezone

    lead_dict = {
        "id": lead.id,
        "email": lead.email,
        "name": lead.name,
        "phone": lead.phone,
        "role": lead.role,
        "company": lead.company,
        "company_size": lead.company_size,
        "sector": lead.sector,
        "linkedin_url": lead.linkedin_url,
        "enrichment_data": lead.enrichment_data,
        "qualification_score": lead.qualification_score,
        "status": lead.status.value,
        "funnel_phase": lead.funnel_phase.value,
        "contact_attempts": lead.contact_attempts,
        "communication_log": lead.communication_log or [],
    }

    try:
        final_state = await run_funnel_for_lead(lead_dict)

        # Persiste resultado do funil no banco
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.id == lead.id))
            db_lead = result.scalar_one_or_none()
            if db_lead:
                db_lead.enrichment_data = final_state.get("enrichment_data")
                db_lead.qualification_score = final_state.get("qualification_score")
                db_lead.status = LeadStatus(final_state.get("current_status", "new"))
                db_lead.funnel_phase = FunnelPhase(final_state.get("current_phase", "capture"))
                db_lead.contact_attempts = final_state.get("contact_attempts", 0)
                db_lead.communication_log = final_state.get("communication_log", [])
                db_lead.last_contacted_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(f"[Route] Funil concluído e salvo para lead_id={lead.id}")

    except Exception as e:
        logger.error(f"[Route] Erro no funil background para lead_id={lead.id}: {e}")

async def _send_confirmation(lead: Lead) -> None:
    """Envia confirmação imediata de inscrição via email e WhatsApp."""
    from app.db.session import AsyncSessionLocal
    from app.models.event import Event
    from app.models.message_template import MessageTemplate, TemplatePhase
    from app.services.notification import (
        notify_lead, NotificationChannel, render_template_vars, build_template_vars
    )
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Busca evento ativo
        event_result = await db.execute(select(Event).order_by(Event.id.desc()))
        event = event_result.scalar_one_or_none()
        event_dict = {
            "name": event.name if event else "Vigil Summit",
            "event_date": event.event_date if event else "A confirmar",
            "event_time": event.event_time if event else "A confirmar",
            "location": event.location if event else "A confirmar",
            "speakers": event.speakers if event else [],
        }

        # Busca template de confirmação
        tpl_result = await db.execute(
            select(MessageTemplate).where(
                MessageTemplate.phase == TemplatePhase.CONFIRMATION,
                MessageTemplate.is_active == True,
            ).order_by(MessageTemplate.sequence_order)
        )
        tpl = tpl_result.scalar_one_or_none()

        if not tpl:
            logger.warning(f"[Confirmation] Nenhum template de confirmação encontrado para lead_id={lead.id}")
            return

        vars_ = build_template_vars(
            {"name": lead.name, "role": lead.role, "company": lead.company},
            event_dict,
        )
        body = render_template_vars(tpl.body, vars_)
        subject = render_template_vars(tpl.subject or "Confirmação de Inscrição", vars_)

        log_entries = []

        # Envia email
        if lead.email:
            result = await notify_lead(
                lead_id=lead.id,
                channel=NotificationChannel.EMAIL,
                message=body,
                subject=subject,
                email=lead.email,
                template_name=tpl.name,
            )
            log_entries.append({**result, "channel": "email", "sent_at": result.get("sent_at")})

        # Envia WhatsApp
        if lead.phone:
            result = await notify_lead(
                lead_id=lead.id,
                channel=NotificationChannel.WHATSAPP,
                message=body,
                phone=lead.phone,
                template_name=tpl.name,
            )
            log_entries.append({**result, "channel": "whatsapp", "sent_at": result.get("sent_at")})

        # Salva log
        if log_entries:
            result = await db.execute(select(Lead).where(Lead.id == lead.id))
            db_lead = result.scalar_one_or_none()
            if db_lead:
                db_lead.communication_log = (db_lead.communication_log or []) + log_entries
                await db.commit()

    logger.info(f"[Confirmation] Confirmação enviada para lead_id={lead.id}")


async def _send_companion_invite(lead: Lead) -> None:
    """
    Envia email de convite ao acompanhante quando o lead registra with_companion=True.
    O acompanhante recebe um link direto para o formulário de inscrição.
    """
    if not lead.companion_email:
        return

    from app.services.notification import send_email
    from app.core.config import settings

    # Apenas vínculos profissionais são aceitos — mapeamento de valores internos para português
    relationship_labels = {
        "partner":          "sócio(a)",
        "director":         "diretor(a)",
        "manager":          "gerente",
        "coordinator":      "coordenador(a)",
        "team_member":      "membro da equipe",
        "colleague":        "colega de trabalho",
        "business_partner": "parceiro(a) de negócios",
        "guest_executive":  "executivo(a) convidado(a)",
    }
    rel_label = relationship_labels.get(lead.companion_relationship or "", "acompanhante profissional")

    # URL base do formulário — usa BASE_URL das configs ou fallback para a raiz
    base_url = getattr(settings, "base_url", "").rstrip("/") or ""
    form_url = f"{base_url}/#inscricao" if base_url else "/#inscricao"

    subject = f"Você foi convidado(a) para o Vigil Summit 2026"
    body = (
        f"Olá!\n\n"
        f"{lead.name} ({rel_label}) realizou sua inscrição no Vigil Summit 2026 "
        f"e indicou que você irá acompanhá-lo(a) no evento.\n\n"
        f"Para garantir sua vaga, é necessário que você também preencha o "
        f"formulário de inscrição. As vagas são limitadas e sua presença só é "
        f"confirmada após o preenchimento.\n\n"
        f"Acesse o link abaixo e inscreva-se agora:\n"
        f"{form_url}\n\n"
        f"— Equipe Vigil.AI"
    )

    result = await send_email(
        email=lead.companion_email,
        subject=subject,
        body=body,
        lead_id=lead.id,
        template_name="companion_invite",
    )

    logger.info(
        f"[CompanionInvite] Convite enviado para {lead.companion_email} "
        f"(lead_id={lead.id}, status={result.get('status')})"
    )

async def _create_companion_lead(lead: Lead) -> None:
    """
    Cria automaticamente um lead-acompanhante quando o participante informa `companion_email`.
    O acompanhante entra com `is_companion=True` e `funnel_phase=COMPANION_PENDING`,
    ficando na régua de lembretes para completar a inscrição própria.
    """
    if not lead.companion_email or not lead.with_companion:
        return

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # Verifica se já existe lead com esse email
        existing = await db.execute(
            select(Lead).where(Lead.email == lead.companion_email.lower())
        )
        if existing.scalar_one_or_none():
            logger.info(
                f"[CompanionLead] Acompanhante já possui cadastro próprio: {lead.companion_email}"
            )
            return

        companion = Lead(
            name=lead.companion_email.split("@")[0].replace(".", " ").title(),  # placeholder
            email=lead.companion_email.lower(),
            phone=None,
            is_companion=True,
            companion_of_lead_id=lead.id,
            with_companion=False,
            status=LeadStatus.NEW,
            funnel_phase=FunnelPhase.COMPANION_PENDING,
            communication_log=[],
            lgpd_consent=False,
        )
        db.add(companion)
        await db.commit()
        await db.refresh(companion)

    logger.info(
        f"[CompanionLead] Lead-acompanhante criado: id={companion.id} | "
        f"email={companion.email} | referenciado por lead_id={lead.id}"
    )


async def _send_not_eligible_email(lead: Lead) -> None:
    """
    Envia email de cortesia para leads classificados como 'not_eligible'.
    Tom respeitoso — informa que o evento é exclusivo sem ser grosseiro.
    O lead NÃO é apagado; permanece como out_of_icp para futuros contatos.
    """
    from app.services.notification import send_email

    first_name = lead.name.split()[0] if lead.name else "prezado(a)"
    subject = "Recebemos sua inscrição para o Vigil Summit 2026"
    body = (
        f"Olá, {first_name}!\n\n"
        f"Agradecemos seu interesse no Vigil Summit 2026 — Segurança para a Era da IA.\n\n"
        f"O Vigil Summit é um evento exclusivo para líderes de Tecnologia, Segurança da "
        f"Informação e Gestão de Riscos de médias e grandes empresas. Ao analisarmos sua "
        f"inscrição, identificamos que o perfil cadastrado (cargo: {lead.role or 'não informado'}) "
        f"não se enquadra no público-alvo desta edição.\n\n"
        f"Isso não impede que você acompanhe nossas iniciativas futuras! Manteremos seu "
        f"contato em nossa base e entraremos em contato caso surjam oportunidades "
        f"alinhadas ao seu perfil.\n\n"
        f"Caso acredite que houve algum engano ou deseje complementar suas informações, "
        f"responda este email.\n\n"
        f"Obrigado pela compreensão e até uma próxima oportunidade!\n"
        f"— Equipe Vigil.AI"
    )

    result = await send_email(
        email=lead.email,
        subject=subject,
        body=body,
        lead_id=lead.id,
        template_name="not_eligible_courtesy",
    )
    logger.info(
        f"[NotEligible] Email de cortesia enviado para lead_id={lead.id} | "
        f"status={result.get('status')}"
    )



@router.post(
    "/",
    response_model=LeadRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo lead",
    description="Recebe dados de um novo lead do formulário/landing page e dispara o funil de IA.",
)
async def create_lead(
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Verifica capacidade máxima do evento
    count_result = await db.execute(select(func.count()).select_from(Lead))
    current_count = count_result.scalar() or 0
    if current_count >= EVENT_CAPACITY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Inscrições encerradas. O evento atingiu a capacidade máxima de {EVENT_CAPACITY} participantes.",
        )

    # Verifica duplicidade de email
    existing = await db.execute(select(Lead).where(Lead.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Lead com email '{payload.email}' já existe.",
        )

    from datetime import datetime, timezone

    lead = Lead(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        role=payload.role,
        company_size=payload.company_size,
        sector=payload.sector,
        linkedin_url=payload.linkedin_url,
        with_companion=payload.with_companion,
        companion_email=payload.companion_email if payload.with_companion else None,
        companion_relationship=payload.companion_relationship if payload.with_companion else None,
        lgpd_consent=payload.lgpd_consent,
        consent_at=datetime.now(timezone.utc) if payload.lgpd_consent else None,
        status=LeadStatus.NEW,
        funnel_phase=FunnelPhase.CAPTURE,
        communication_log=[],
    )
    db.add(lead)
    await db.flush()  # Garante que o ID é gerado
    await db.refresh(lead)

    # ── Qualificação Determinística ──────────────────────────────────────────
    # Classifica imediatamente, antes de qualquer envio ou enriquecimento por IA
    eligibility = classify_lead_eligibility(payload.role)
    logger.info(f"[Route] Qualificação: lead_id={lead.id} | role='{payload.role}' | result={eligibility}")

    if eligibility == "approved":
        # Perfil executivo claro → funil roda normalmente
        lead.status = LeadStatus.NEW
        background_tasks.add_task(_send_confirmation, lead)
        background_tasks.add_task(_trigger_funnel, lead)
        if lead.with_companion and lead.companion_email:
            background_tasks.add_task(_send_companion_invite, lead)
            background_tasks.add_task(_create_companion_lead, lead)

    elif eligibility == "pending_review":
        # Perfil intermediário → aguarda aprovação manual do admin
        lead.status = LeadStatus.PENDING_REVIEW
        lead.funnel_phase = FunnelPhase.CAPTURE
        # Envia confirmação de recebimento (sem confirmar participação)
        background_tasks.add_task(_send_confirmation, lead)
        # NÃO dispara funil — admin aprova primeiro

    else:  # not_eligible
        # Sem perfil adequado → email de cortesia, sem acesso ao evento
        lead.status = LeadStatus.OUT_OF_ICP
        lead.funnel_phase = FunnelPhase.CLOSED
        background_tasks.add_task(_send_not_eligible_email, lead)

    await db.commit()
    await db.refresh(lead)

    logger.info(f"[Route] Lead criado: id={lead.id} | email={lead.email} | eligibility={eligibility}")
    return lead


@router.get(
    "/",
    response_model=list[LeadSummary],
    summary="Listar leads",
    dependencies=[Depends(require_api_key)],
)
async def list_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
    phase: FunnelPhase | None = Query(None, description="Filtrar por fase do funil"),
    status: LeadStatus | None = Query(None, alias="status", description="Filtrar por status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Lead).order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    if phase:
        query = query.where(Lead.funnel_phase == phase)
    if status:
        query = query.where(Lead.status == status)

    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/{lead_id}",
    response_model=LeadRead,
    summary="Buscar lead por ID",
    dependencies=[Depends(require_api_key)],
)
async def get_lead(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _get_lead_or_404(lead_id, db)


@router.patch(
    "/{lead_id}",
    response_model=LeadRead,
    summary="Atualizar dados do lead",
    dependencies=[Depends(require_api_key)],
)
async def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    lead = await _get_lead_or_404(lead_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead, field, value)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.post(
    "/{lead_id}/post-event",
    response_model=dict,
    summary="Disparar follow-up pós-evento",
    dependencies=[Depends(require_api_key)],
)
async def trigger_post_event(
    lead_id: int,
    attended: bool,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    event_notes: str = "",
):
    """Dispara o fluxo de follow-up pós-evento para um lead específico."""
    lead = await _get_lead_or_404(lead_id, db)

    lead_dict = {
        "id": lead.id,
        "email": lead.email,
        "name": lead.name,
        "phone": lead.phone,
        "role": lead.role,
        "company": lead.company,
        "company_size": lead.company_size,
        "sector": lead.sector,
        "enrichment_data": lead.enrichment_data,
        "qualification_score": lead.qualification_score,
        "communication_log": lead.communication_log or [],
    }

    background_tasks.add_task(run_post_event_for_lead, lead_dict, attended, event_notes)

    # Atualiza status imediatamente
    lead.attended = attended
    lead.event_notes = event_notes
    lead.funnel_phase = FunnelPhase.POST_EVENT
    await db.flush()

    return {"message": "Follow-up pós-evento disparado com sucesso", "lead_id": lead_id}
