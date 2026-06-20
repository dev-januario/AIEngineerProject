"""
Pre-Event Scheduler Service
============================
Régua de comunicação pré-evento com 3 personas.
TODAS as mensagens são geradas pelo Gemini 2.5 Flash — sem templates fixos.

  Persona A — Participante inscrito (with_companion=False)
              → Lembrete personalizado para o cargo/setor do lead

  Persona B — Participante inscrito com acompanhante (with_companion=True)
              → Lembrete personalizado + nudge para o acompanhante se inscrever

  Persona C — Acompanhante ainda não inscrito (is_companion=True, funnel_phase=COMPANION_PENDING)
              → Urgência para completar inscrição antes de fechar vagas

O job diário verifica quantos dias faltam para o evento e dispara as personas corretas.
Os dias padrão são configurados em `event.pre_event_reminder_days` (default: 30, 15, 7, 3, 1).
"""

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_until_event(event_date_str: str | None) -> int | None:
    """Calcula quantos dias faltam até a data do evento."""
    if not event_date_str:
        return None
    try:
        event_dt = date.fromisoformat(event_date_str)
        delta = (event_dt - date.today()).days
        return delta
    except ValueError:
        return None


async def _generate_ai_message(
    prompt_template: str,
    prompt_vars: dict,
    fallback: str,
) -> str:
    """
    Chama o Gemini para gerar uma mensagem personalizada.
    Retorna o fallback em caso de falha para garantir continuidade.
    """
    import google.generativeai as genai
    from app.core.config import settings
    from app.agents.prompts import SYSTEM_BASE

    genai.configure(api_key=settings._gemini_key)
    model = genai.GenerativeModel(
        model_name="gemini-3.5-flash",
        system_instruction=SYSTEM_BASE,
    )

    try:
        user_prompt = prompt_template.format(**prompt_vars)
        response = await model.generate_content_async(user_prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"[PreEvent/AI] Falha ao gerar mensagem: {e}")
        return fallback


# ── Dispatcher central ────────────────────────────────────────────────────────

async def dispatch_pre_event_for_persona(
    persona: str,
    days_remaining: int | None = None,
    force: bool = False,
) -> dict:
    """
    Dispara mensagens pré-evento geradas por IA para uma persona específica.

    Args:
        persona: "participant" | "with_companion" | "companion_pending"
        days_remaining: Dias restantes até o evento (None = calculado automaticamente)
        force: Se True, ignora verificação de dias configurados e envia para todos os leads

    Returns:
        Dict com total_sent, total_failed, leads_processed
    """
    from app.db.session import AsyncSessionLocal
    from app.models.lead import Lead, FunnelPhase
    from app.models.event import Event, EventStatus
    from app.services.notification import send_email, send_whatsapp, format_date_pt
    from app.agents.prompts import (
        PRE_EVENT_REMINDER_PARTICIPANT_PROMPT,
        PRE_EVENT_REMINDER_WITH_COMPANION_PROMPT,
        PRE_EVENT_REMINDER_COMPANION_PENDING_PROMPT,
        format_lead_context,
    )

    total_sent   = 0
    total_failed = 0
    leads_processed = []

    async with AsyncSessionLocal() as db:
        # Busca evento ativo
        event_result = await db.execute(
            select(Event).where(Event.status == EventStatus.ACTIVE).order_by(Event.id.desc())
        )
        event = event_result.scalar_one_or_none()
        if not event:
            logger.warning("[PreEvent] Nenhum evento ativo encontrado")
            return {"total_sent": 0, "total_failed": 0, "leads_processed": []}

        # Calcula dias restantes
        if days_remaining is None:
            days_remaining = _days_until_event(event.event_date)

        # Verifica se hoje é um dia de lembrete configurado (exceto em `force`)
        reminder_days = event.pre_event_reminder_days or [30, 15, 7, 3, 1]
        if not force and days_remaining is not None and days_remaining not in reminder_days:
            logger.info(
                f"[PreEvent] Persona={persona} | Hoje não é dia de lembrete "
                f"(faltam {days_remaining} dias, configurados: {reminder_days})"
            )
            return {"total_sent": 0, "total_failed": 0, "leads_processed": []}

        # Monta dados do evento para os prompts
        event_name     = event.name or "Vigil Summit 2026"
        event_date_pt  = format_date_pt(event.event_date)
        event_time     = (event.event_time or "A confirmar").replace(":", "h")
        event_location = event.location or "São Paulo, SP"
        speakers_str   = ", ".join(event.speakers) if event.speakers else "A confirmar"
        base_url       = ""  # Pode ser configurado via settings futuramente
        registration_link = f"{base_url}/#inscricao" if base_url else "vigil.ai/#inscricao"

        # Busca leads da persona
        if persona == "participant":
            leads_q = select(Lead).where(
                Lead.funnel_phase == FunnelPhase.PRE_EVENT,
                Lead.is_companion == False,      # noqa: E712
                Lead.with_companion == False,    # noqa: E712
            )
        elif persona == "with_companion":
            leads_q = select(Lead).where(
                Lead.funnel_phase == FunnelPhase.PRE_EVENT,
                Lead.is_companion == False,      # noqa: E712
                Lead.with_companion == True,     # noqa: E712
            )
        else:  # companion_pending
            leads_q = select(Lead).where(
                Lead.funnel_phase == FunnelPhase.COMPANION_PENDING,
                Lead.is_companion == True,       # noqa: E712
            )

        leads_result = await db.execute(leads_q)
        leads = leads_result.scalars().all()

        logger.info(
            f"[PreEvent] Persona={persona} | {len(leads)} lead(s) | "
            f"{days_remaining} dias restantes | IA gerando mensagens individuais"
        )

        for lead in leads:
            lead_sent   = 0
            lead_failed = 0

            try:
                # Monta contexto do lead para o prompt
                lead_ctx = format_lead_context({
                    "name":         lead.name,
                    "email":        lead.email,
                    "phone":        lead.phone,
                    "role":         lead.role or "Não informado",
                    "company":      lead.company or "Não informada",
                    "company_size": lead.company_size or "Não informado",
                    "sector":       lead.sector or "Não informado",
                    "linkedin_url": lead.linkedin_url or "Não informado",
                    "status":       lead.status.value if lead.status else "confirmed",
                    "funnel_phase": lead.funnel_phase.value if lead.funnel_phase else "pre_event",
                    "qualification_score": lead.qualification_score,
                })

                first_name  = lead.name.split()[0] if lead.name else "Participante"
                days_str    = f"{days_remaining} dia{'s' if days_remaining != 1 else ''}"

                # ── Gera mensagem via Gemini conforme persona ──────────────
                if persona == "participant":
                    body = await _generate_ai_message(
                        prompt_template=PRE_EVENT_REMINDER_PARTICIPANT_PROMPT,
                        prompt_vars={
                            "lead_context":   lead_ctx,
                            "event_name":     event_name,
                            "event_date":     event_date_pt,
                            "event_time":     event_time,
                            "event_location": event_location,
                            "speakers":       speakers_str,
                            "days_remaining": days_str,
                        },
                        fallback=(
                            f"{first_name}, o {event_name} está chegando!\n\n"
                            f"📅 {event_date_pt} às {event_time} | 📍 {event_location}\n\n"
                            f"Faltam {days_str}. Reserve na sua agenda!\n\n— Equipe Vigil.AI"
                        ),
                    )
                    subject = f"{first_name}, faltam {days_str} para o {event_name}"

                elif persona == "with_companion":
                    body = await _generate_ai_message(
                        prompt_template=PRE_EVENT_REMINDER_WITH_COMPANION_PROMPT,
                        prompt_vars={
                            "lead_context":    lead_ctx,
                            "companion_email": lead.companion_email or "seu acompanhante",
                            "event_name":      event_name,
                            "event_date":      event_date_pt,
                            "event_time":      event_time,
                            "event_location":  event_location,
                            "days_remaining":  days_str,
                        },
                        fallback=(
                            f"{first_name}, faltam {days_str} para o {event_name}!\n\n"
                            f"📅 {event_date_pt} às {event_time} | 📍 {event_location}\n\n"
                            f"Lembrete: seu acompanhante ({lead.companion_email}) "
                            f"precisa estar inscrito para garantir a entrada.\n\n— Equipe Vigil.AI"
                        ),
                    )
                    subject = f"{first_name}, faltam {days_str} para o {event_name} — você e seu acompanhante"

                else:  # companion_pending
                    # Para companion_pending, busca quem o convidou
                    inviter_name = "um participante confirmado"
                    inviter_role = ""
                    if lead.companion_of_lead_id:
                        inv_result = await db.execute(
                            select(Lead).where(Lead.id == lead.companion_of_lead_id)
                        )
                        inviter = inv_result.scalar_one_or_none()
                        if inviter:
                            inviter_name = inviter.name or inviter_name
                            inviter_role = inviter.role or ""

                    body = await _generate_ai_message(
                        prompt_template=PRE_EVENT_REMINDER_COMPANION_PENDING_PROMPT,
                        prompt_vars={
                            "companion_email":  lead.email,
                            "invited_by_name":  inviter_name,
                            "invited_by_role":  inviter_role,
                            "registration_link": registration_link,
                            "event_name":       event_name,
                            "event_date":       event_date_pt,
                            "event_time":       event_time,
                            "days_remaining":   days_str,
                        },
                        fallback=(
                            f"Olá! Você foi convidado(a) para o {event_name} por {inviter_name}.\n\n"
                            f"Faltam {days_str} e sua inscrição ainda está pendente.\n\n"
                            f"👉 Inscreva-se: {registration_link}\n\n"
                            f"📅 {event_date_pt} às {event_time}\n— Equipe Vigil.AI"
                        ),
                    )
                    subject = f"⚠️ Faltam {days_str} — Garanta sua vaga no {event_name}"

                logger.info(
                    f"[PreEvent/AI] Mensagem gerada | lead_id={lead.id} | "
                    f"persona={persona} | chars={len(body)}"
                )

                # ── Envia Email ────────────────────────────────────────────
                if lead.email:
                    email_result = await send_email(
                        email=lead.email,
                        subject=subject,
                        body=body,
                        lead_id=lead.id,
                        template_name=f"ai_pre_event_{persona}_{days_remaining}d",
                    )
                    lead.communication_log = (lead.communication_log or []) + [{
                        **email_result,
                        "channel":  "email",
                        "persona":  persona,
                        "days_before_event": days_remaining,
                        "sent_at":  datetime.now(timezone.utc).isoformat(),
                    }]
                    if email_result.get("status") in ("sent", "simulated"):
                        lead_sent += 1
                    else:
                        lead_failed += 1

                # ── Envia WhatsApp (cana preferencial para urgência alta) ──
                if lead.phone and days_remaining is not None and days_remaining <= 7:
                    wa_body = body[:500] + "\n\n— Equipe Vigil.AI" if len(body) > 500 else body
                    wa_result = await send_whatsapp(
                        phone=lead.phone,
                        message=wa_body,
                        lead_id=lead.id,
                        template_name=f"ai_pre_event_{persona}_{days_remaining}d_wa",
                    )
                    lead.communication_log = (lead.communication_log or []) + [{
                        **wa_result,
                        "channel":  "whatsapp",
                        "persona":  persona,
                        "days_before_event": days_remaining,
                        "sent_at":  datetime.now(timezone.utc).isoformat(),
                    }]
                    if wa_result.get("status") in ("sent", "simulated"):
                        lead_sent += 1
                    else:
                        lead_failed += 1

            except Exception as e:
                logger.error(f"[PreEvent] Erro ao processar lead_id={lead.id}: {e}")
                lead_failed += 1

            lead.last_contacted_at = datetime.now(timezone.utc)
            lead.contact_attempts  = (lead.contact_attempts or 0) + 1

            total_sent   += lead_sent
            total_failed += lead_failed
            leads_processed.append({
                "lead_id": lead.id,
                "name":    lead.name,
                "persona": persona,
                "sent":    lead_sent,
                "failed":  lead_failed,
            })

        await db.commit()

    logger.info(
        f"[PreEvent] ✅ Persona={persona} | "
        f"sent={total_sent} | failed={total_failed} | leads={len(leads_processed)}"
    )
    return {
        "persona":         persona,
        "days_remaining":  days_remaining,
        "total_sent":      total_sent,
        "total_failed":    total_failed,
        "leads_processed": leads_processed,
    }


async def dispatch_pre_event_all(
    days_remaining: int | None = None,
    force: bool = False,
) -> dict:
    """
    Dispara a régua pré-evento via IA para todas as 3 personas.
    Usado tanto pelo job agendado diário quanto pelo endpoint de broadcast geral.
    """
    results    = []
    total_sent = 0
    total_failed = 0

    for persona in ("participant", "with_companion", "companion_pending"):
        result = await dispatch_pre_event_for_persona(
            persona=persona,
            days_remaining=days_remaining,
            force=force,
        )
        results.append(result)
        total_sent   += result["total_sent"]
        total_failed += result["total_failed"]

    return {
        "total_sent":   total_sent,
        "total_failed": total_failed,
        "by_persona":   results,
    }


# ── Job diário ────────────────────────────────────────────────────────────────

async def _daily_pre_event_job():
    """
    Job executado diariamente pelo APScheduler.
    Verifica quais personas precisam de lembrete hoje e dispara via IA.
    """
    logger.info("📅 [PreEvent] Job diário iniciado — mensagens geradas por Gemini")
    result = await dispatch_pre_event_all(force=False)
    logger.info(
        f"📅 [PreEvent] Job diário concluído | "
        f"sent={result['total_sent']} | failed={result['total_failed']}"
    )


def register_pre_event_job(send_time: str = "09:00"):
    """
    Registra o job diário de pré-evento no APScheduler.
    Executado automaticamente no startup da aplicação.

    Args:
        send_time: Horário de disparo no formato HH:MM (ex: "09:00")
    """
    from app.services.scheduler import scheduler

    try:
        hour, minute = map(int, send_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 9, 0

    job_id = "pre_event_daily_reminder"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        _daily_pre_event_job,
        "cron",
        hour=hour,
        minute=minute,
        id=job_id,
        replace_existing=True,
        timezone="America/Sao_Paulo",
    )
    logger.info(f"📅 [PreEvent] Job diário registrado — disparo às {send_time} (Brasília)")
