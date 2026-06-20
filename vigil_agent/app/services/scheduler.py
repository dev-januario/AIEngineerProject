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

    # Job: régua pré-evento diária
    _register_pre_event_daily_job()


def _register_pre_event_daily_job():
    """Registra o job diário de lembretes pré-evento."""
    from app.services.pre_event_scheduler import register_pre_event_job

    # Tenta buscar o horário configurado no evento ativo
    # Usa "09:00" como fallback caso o banco ainda não esteja disponível no startup
    try:
        import asyncio
        from app.db.session import AsyncSessionLocal
        from app.models.event import Event, EventStatus
        from sqlalchemy import select

        async def _get_send_time() -> str:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Event).where(Event.status == EventStatus.ACTIVE).order_by(Event.id.desc())
                )
                event = result.scalar_one_or_none()
                return event.pre_event_send_time if event else "09:00"

        loop = asyncio.get_event_loop()
        if loop.is_running():
            # No contexto asyncio (lifespan), agenda com horário padrão e deixa o job atualizar depois
            send_time = "09:00"
        else:
            send_time = loop.run_until_complete(_get_send_time())
    except Exception as e:
        logger.warning(f"[Scheduler] Não foi possível buscar horário do evento: {e} — usando 09:00")
        send_time = "09:00"

    register_pre_event_job(send_time=send_time)


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
    Gera mensagens pós-evento personalizadas via Gemini para cada lead:
      - attended=True  → mensagem de agradecimento e follow-up consultivo
      - attended!=True → mensagem de conforto e re-engajamento
    Nenhum template fixo é usado — a IA gera texto único para cada perfil.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.lead import Lead, FunnelPhase, LeadStatus
    from app.agents.graph import run_post_event_for_lead
    from sqlalchemy import select

    logger.info("🔔 [Scheduler] Disparando régua pós-evento via Gemini (mensagens personalizadas)...")

    async with AsyncSessionLocal() as db:
        # Busca leads elegíveis para follow-up pós-evento
        leads_result = await db.execute(
            select(Lead).where(
                Lead.funnel_phase.in_([
                    FunnelPhase.PRE_EVENT, FunnelPhase.POST_EVENT,
                    FunnelPhase.CAPTURE, FunnelPhase.ENRICHMENT,
                ]),
                Lead.status.notin_([LeadStatus.OUT_OF_ICP]),
            )
        )
        leads = leads_result.scalars().all()
        logger.info(f"[Scheduler] Pós-evento via IA para {len(leads)} leads")

        sent = 0
        failed = 0

        for lead in leads:
            try:
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
                    "contact_attempts": lead.contact_attempts or 0,
                    "communication_log": lead.communication_log or [],
                    "attended": lead.attended,
                    "event_notes": lead.event_notes,
                }

                attended = lead.attended is True
                event_notes = lead.event_notes or ""

                # Gemini gera mensagem única baseada no perfil do lead
                final_state = await run_post_event_for_lead(
                    lead=lead_dict,
                    attended=attended,
                    event_notes=event_notes,
                )

                # Atualiza estado do lead no banco
                lead.funnel_phase = FunnelPhase.POST_EVENT
                lead.status = LeadStatus.FOLLOWED_UP
                lead.last_contacted_at = datetime.now(timezone.utc)
                comm = final_state.get("communication_log") or []
                if comm:
                    lead.communication_log = (lead.communication_log or []) + [comm[-1]]

                persona = "presente" if attended else "ausente"
                logger.info(
                    f"[Scheduler/AI] ✅ Pós-evento gerado | lead_id={lead.id} | "
                    f"persona={persona} | ação={final_state.get('last_action', '')[:60]}"
                )
                sent += 1

            except Exception as e:
                logger.error(f"[Scheduler] Erro pós-evento lead_id={lead.id}: {e}")
                failed += 1

        await db.commit()
        logger.info(
            f"✅ [Scheduler] Régua pós-evento concluída | "
            f"sent={sent} | failed={failed}"
        )



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
