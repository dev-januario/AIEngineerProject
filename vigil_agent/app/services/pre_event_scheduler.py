"""
Pre-Event Scheduler Service
============================
Régua de comunicação pré-evento com 3 personas:

  Persona A — Participante inscrito (with_companion=False)
              → Alerta do evento (data, local, agenda)

  Persona B — Participante inscrito com acompanhante (with_companion=True)
              → Alerta do evento + lembrete para ajudar o acompanhante a não esquecer

  Persona C — Acompanhante ainda não inscrito (is_companion=True, funnel_phase=COMPANION_PENDING)
              → Lembrete para completar inscrição e garantir a vaga

Os dias de antecedência dos lembretes são configurados pelo admin via `event.pre_event_reminder_days`.
Cada template tem um campo `days_before_event` que indica em qual janela deve ser disparado.
O job diário verifica automaticamente quais templates disparam hoje.
"""

import logging
from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import select

logger = logging.getLogger(__name__)


# ── Tipos ─────────────────────────────────────────────────────────────────────

Persona = Literal["participant", "with_companion", "companion_pending"]


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


def _pick_templates_for_persona(all_templates: list, phase_value: str, days_remaining: int) -> list:
    """
    Filtra templates da persona correta cujo `days_before_event` coincide
    com os dias restantes. Se não houver template exato, usa o mais próximo.
    """
    from app.models.message_template import TemplatePhase

    phase = TemplatePhase(phase_value)
    candidates = [
        t for t in all_templates
        if t.phase == phase and t.is_active
    ]

    # Match exato de dias (preferencial)
    exact = [t for t in candidates if t.days_before_event == days_remaining]
    if exact:
        return sorted(exact, key=lambda t: t.sequence_order)

    # Sem match exato: retorna todos ativos da persona (fallback para broadcast)
    return sorted(candidates, key=lambda t: t.sequence_order)


# ── Dispatcher central ────────────────────────────────────────────────────────

async def dispatch_pre_event_for_persona(
    persona: Persona,
    days_remaining: int | None = None,
    force: bool = False,
) -> dict:
    """
    Dispara mensagens pré-evento para uma persona específica.

    Args:
        persona: "participant" | "with_companion" | "companion_pending"
        days_remaining: Dias restantes até o evento (None = calculado automaticamente)
        force: Se True, ignora verificação de `days_before_event` e envia todos os templates ativos

    Returns:
        Dict com total_sent, total_failed, leads_processed
    """
    from app.db.session import AsyncSessionLocal
    from app.models.lead import Lead, FunnelPhase
    from app.models.event import Event, EventStatus
    from app.models.message_template import MessageTemplate, TemplatePhase, TemplateChannel
    from app.services.notification import (
        send_email, send_whatsapp,
        render_template_vars, build_template_vars,
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

        event_dict = {
            "name":       event.name,
            "event_date": event.event_date,
            "event_time": event.event_time,
            "location":   event.location,
            "speakers":   event.speakers or [],
        }

        # Verifica se hoje é um dia de lembrete configurado (exceto em `force`)
        reminder_days = event.pre_event_reminder_days or [30, 15, 7, 3, 1]
        if not force and days_remaining is not None and days_remaining not in reminder_days:
            logger.info(
                f"[PreEvent] Persona={persona} | Hoje não é dia de lembrete "
                f"(faltam {days_remaining} dias, configurados: {reminder_days})"
            )
            return {"total_sent": 0, "total_failed": 0, "leads_processed": []}

        # Mapeia persona → phase + filtro de leads
        PHASE_MAP: dict[Persona, str] = {
            "participant":       "pre_event_participant",
            "with_companion":    "pre_event_with_companion",
            "companion_pending": "pre_event_companion_pending",
        }
        phase_value = PHASE_MAP[persona]

        # Busca templates da persona
        tpl_result = await db.execute(
            select(MessageTemplate).where(
                MessageTemplate.phase == phase_value,
                MessageTemplate.is_active == True,
            ).order_by(MessageTemplate.days_before_event, MessageTemplate.sequence_order)
        )
        all_templates = tpl_result.scalars().all()

        if not force:
            # Filtra apenas templates do dia exato
            templates = [
                t for t in all_templates
                if t.days_before_event == days_remaining
            ]
            if not templates:
                logger.info(
                    f"[PreEvent] Persona={persona} | Nenhum template para {days_remaining} dias restantes"
                )
                return {"total_sent": 0, "total_failed": 0, "leads_processed": []}
        else:
            templates = list(all_templates)

        if not templates:
            logger.warning(f"[PreEvent] Nenhum template ativo para persona={persona}")
            return {"total_sent": 0, "total_failed": 0, "leads_processed": []}

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
            f"[PreEvent] Persona={persona} | {len(leads)} leads | "
            f"{len(templates)} template(s) | {days_remaining} dias restantes"
        )

        for lead in leads:
            lead_sent = 0
            lead_failed = 0

            lead_dict = {
                "name":            lead.name,
                "role":            lead.role,
                "company":         lead.company,
                "companion_email": lead.companion_email,
            }
            vars_ = build_template_vars(lead_dict, event_dict, days_remaining=days_remaining)

            for tpl in templates:
                rendered_body = render_template_vars(tpl.body, vars_)

                try:
                    # ── Email ──────────────────────────────────────────────────
                    if tpl.channel in (TemplateChannel.EMAIL, TemplateChannel.BOTH):
                        if lead.email:
                            subject = render_template_vars(
                                tpl.subject or f"Faltam {{{{DIAS_RESTANTES}}}} para o {{{{NOME_EVENTO}}}}!",
                                vars_
                            )
                            result = await send_email(
                                email=lead.email,
                                subject=subject,
                                body=rendered_body,
                                lead_id=lead.id,
                                template_name=tpl.name,
                            )
                            lead.communication_log = (lead.communication_log or []) + [{
                                **result,
                                "channel":  "email",
                                "template": tpl.name,
                                "persona":  persona,
                                "sent_at":  datetime.now(timezone.utc).isoformat(),
                            }]
                            if result.get("status") in ("sent", "simulated"):
                                lead_sent += 1
                            else:
                                lead_failed += 1

                    # ── WhatsApp ───────────────────────────────────────────────
                    if tpl.channel in (TemplateChannel.WHATSAPP, TemplateChannel.BOTH):
                        if lead.phone:
                            result = await send_whatsapp(
                                phone=lead.phone,
                                message=rendered_body,
                                lead_id=lead.id,
                                template_name=tpl.name,
                            )
                            lead.communication_log = (lead.communication_log or []) + [{
                                **result,
                                "channel":  "whatsapp",
                                "template": tpl.name,
                                "persona":  persona,
                                "sent_at":  datetime.now(timezone.utc).isoformat(),
                            }]
                            if result.get("status") in ("sent", "simulated"):
                                lead_sent += 1
                            else:
                                lead_failed += 1

                except Exception as e:
                    logger.error(f"[PreEvent] Erro ao enviar para lead_id={lead.id}: {e}")
                    lead_failed += 1

            lead.last_contacted_at = datetime.now(timezone.utc)
            lead.contact_attempts = (lead.contact_attempts or 0) + 1

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
        "persona":          persona,
        "days_remaining":   days_remaining,
        "total_sent":       total_sent,
        "total_failed":     total_failed,
        "leads_processed":  leads_processed,
    }


async def dispatch_pre_event_all(
    days_remaining: int | None = None,
    force: bool = False,
) -> dict:
    """
    Dispara a régua pré-evento para todas as 3 personas.
    Usado tanto pelo job agendado diário quanto pelo endpoint de broadcast geral.
    """
    results = []
    total_sent   = 0
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
    Verifica quais personas precisam de lembrete hoje e dispara.
    """
    logger.info("📅 [PreEvent] Job diário iniciado")
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
