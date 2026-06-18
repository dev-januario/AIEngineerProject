"""
Leads Router
============
Endpoints para o ciclo de vida completo de leads do Vigil Summit.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_funnel_for_lead, run_post_event_for_lead
from app.core.security import require_api_key
from app.db.session import get_db
from app.models.lead import FunnelPhase, Lead, LeadStatus
from app.schemas.lead import LeadCreate, LeadRead, LeadSummary, LeadUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["leads"])


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

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
        lgpd_consent=payload.lgpd_consent,
        consent_at=datetime.now(timezone.utc) if payload.lgpd_consent else None,
        status=LeadStatus.NEW,
        funnel_phase=FunnelPhase.CAPTURE,
        communication_log=[],
    )
    db.add(lead)
    await db.flush()  # Garante que o ID é gerado
    await db.refresh(lead)

    # Dispara funil de IA em background (não bloqueia a resposta HTTP)
    background_tasks.add_task(_trigger_funnel, lead)

    logger.info(f"[Route] Lead criado: id={lead.id} | email={lead.email}")
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
