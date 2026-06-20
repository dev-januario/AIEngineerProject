"""
Scheduler Service
=================
APScheduler para disparos temporais controlados pelo admin.

- Disparo imediato: admin clica em "Encerrar Evento"
- Disparo agendado: admin define horário de encerramento
- Disparo de teste: 3 minutos após encerramento (configurável por evento)
"""

import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

# Scheduler global (singleton)
scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={"coalesce": True, "max_instances": 1},
    timezone="America/Sao_Paulo",
)


def start_scheduler():
    """Inicia o scheduler no startup da aplicação."""
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Scheduler APScheduler iniciado")

    # Job: polling de emails inbound (respostas de leads)
    _register_imap_polling()


def _register_imap_polling():
    """Registra (ou re-registra) o job de IMAP polling no scheduler."""
    from app.core.config import settings
    from app.services.imap_poller import poll_inbox_for_replies

    job_id = "imap_inbox_polling"
    interval = settings.imap_poll_interval_seconds

    if not settings.smtp_user or not settings.smtp_password:
        logger.info("[Scheduler] SMTP não configurado — IMAP polling desativado")
        return

    # Remove job antigo se existir
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        poll_inbox_for_replies,
        "interval",
        seconds=interval,
        id=job_id,
        replace_existing=True,
        next_run_time=None,  # não executa imediatamente no startup, aguarda o primeiro intervalo
    )
    logger.info(f"📬 [Scheduler] IMAP polling registrado — intervalo: {interval}s")


def stop_scheduler():
    """Para o scheduler no shutdown da aplicação."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🛑 Scheduler APScheduler encerrado")


async def _dispatch_post_event_sequence():
    """
    Job executado após encerramento do evento.
    Envia mensagens personalizadas com base na presença do lead:
      - attended=True  → templates POST_EVENT_ATTENDED (agradecimento)
      - attended!=True → templates POST_EVENT_NO_SHOW  (conforto / sentimos sua falta)
      - fallback       → templates POST_EVENT genéricos
    """
    from app.db.session import AsyncSessionLocal
    from app.models.lead import Lead, FunnelPhase, LeadStatus
    from app.models.event import Event, EventStatus
    from app.models.message_template import MessageTemplate, TemplatePhase, TemplateChannel
    from app.services.notification import (
        send_email, send_whatsapp, NotificationChannel,
        render_template_vars, build_template_vars
    )
    from sqlalchemy import select

    logger.info("🔔 [Scheduler] Disparando régua pós-evento personalizada...")

    async with AsyncSessionLocal() as db:
        # Busca evento encerrado (ou ativo como fallback)
        event_result = await db.execute(
            select(Event).where(Event.status == EventStatus.ENDED).order_by(Event.ended_at.desc())
        )
        event = event_result.scalar_one_or_none()
        if not event:
            event_result = await db.execute(select(Event).order_by(Event.id.desc()))
            event = event_result.scalar_one_or_none()

        event_dict = {
            "name": event.name if event else "Vigil Summit",
            "event_date": event.event_date if event else None,
            "event_time": event.event_time if event else None,
            "location": event.location if event else None,
            "speakers": event.speakers if event else [],
        } if event else {}

        # Carrega todos os templates pós-evento de uma só vez
        tpl_result = await db.execute(
            select(MessageTemplate).where(
                MessageTemplate.phase.in_([
                    TemplatePhase.POST_EVENT,
                    TemplatePhase.POST_EVENT_ATTENDED,
                    TemplatePhase.POST_EVENT_NO_SHOW,
                ]),
                MessageTemplate.is_active == True,
            ).order_by(MessageTemplate.sequence_order)
        )
        all_templates = tpl_result.scalars().all()

        attended_tpls = [t for t in all_templates if t.phase == TemplatePhase.POST_EVENT_ATTENDED][:1]
        no_show_tpls  = [t for t in all_templates if t.phase == TemplatePhase.POST_EVENT_NO_SHOW][:1]
        generic_tpls  = [t for t in all_templates if t.phase == TemplatePhase.POST_EVENT][:1]

        if not all_templates:
            logger.warning("[Scheduler] Nenhum template pós-evento encontrado")
            return

        # Busca todos os leads não-fechados
        leads_result = await db.execute(
            select(Lead).where(
                Lead.funnel_phase.in_([
                    FunnelPhase.PRE_EVENT, FunnelPhase.POST_EVENT,
                    FunnelPhase.CAPTURE, FunnelPhase.ENRICHMENT,
                ])
            )
        )
        leads = leads_result.scalars().all()
        logger.info(f"[Scheduler] Pós-evento para {len(leads)} leads")

        for lead in leads:
            try:
                # Seleciona templates conforme presença confirmada via QR Code
                if lead.attended is True:
                    templates = attended_tpls or generic_tpls
                    persona = "presente"
                else:
                    templates = no_show_tpls or generic_tpls
                    persona = "ausente"

                if not templates:
                    logger.warning(f"[Scheduler] Nenhum template para lead_id={lead.id} ({persona})")
                    continue

                lead_dict = {"name": lead.name, "role": lead.role, "company": lead.company}
                vars_ = build_template_vars(lead_dict, event_dict)

                for tpl in templates:
                    rendered_body = render_template_vars(tpl.body, vars_)

                    if tpl.channel in (TemplateChannel.EMAIL, TemplateChannel.BOTH):
                        if lead.email:
                            subject = render_template_vars(tpl.subject or "Vigil Summit — Follow-up", vars_)
                            result = await send_email(
                                email=lead.email, subject=subject,
                                body=rendered_body, lead_id=lead.id, template_name=tpl.name,
                            )
                            lead.communication_log = (lead.communication_log or []) + [{
                                **result, "channel": "email", "template": tpl.name,
                                "sent_at": datetime.now(timezone.utc).isoformat(),
                            }]

                    if tpl.channel in (TemplateChannel.WHATSAPP, TemplateChannel.BOTH):
                        if lead.phone:
                            result = await send_whatsapp(
                                phone=lead.phone, message=rendered_body,
                                lead_id=lead.id, template_name=tpl.name,
                            )
                            lead.communication_log = (lead.communication_log or []) + [{
                                **result, "channel": "whatsapp", "template": tpl.name,
                                "sent_at": datetime.now(timezone.utc).isoformat(),
                            }]

                lead.funnel_phase = FunnelPhase.POST_EVENT
                lead.last_contacted_at = datetime.now(timezone.utc)
                logger.info(f"[Scheduler] Pós-evento — lead_id={lead.id} | presença={persona}")

            except Exception as e:
                logger.error(f"[Scheduler] Erro pós-evento lead_id={lead.id}: {e}")

        await db.commit()
        logger.info("✅ [Scheduler] Régua pós-evento personalizada concluída")


def schedule_post_event(delay_minutes: int = 3, run_at: datetime | None = None):
    """
    Agenda o disparo da régua pós-evento.

    Args:
        delay_minutes: Minutos de delay a partir de agora (padrão 3 para teste).
        run_at: Datetime exato para disparar (sobrescreve delay_minutes se fornecido).
    """
    job_id = "post_event_sequence"

    # Remove job anterior se existir
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if run_at:
        trigger_time = run_at
    else:
        trigger_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

    scheduler.add_job(
        _dispatch_post_event_sequence,
        "date",
        run_date=trigger_time,
        id=job_id,
        replace_existing=True,
    )

    logger.info(f"📅 [Scheduler] Pós-evento agendado para {trigger_time.isoformat()}")
    return trigger_time


def get_next_post_event_run() -> datetime | None:
    """Retorna o próximo disparo agendado do pós-evento, se houver."""
    job = scheduler.get_job("post_event_sequence")
    if job and job.next_run_time:
        return job.next_run_time
    return None
