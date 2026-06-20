"""
Broadcast Routes
================
Endpoints para envio massivo de mensagens pré-evento por persona.

POST /api/v1/admin/broadcast/pre-event/participant         → Persona A (participante simples)
POST /api/v1/admin/broadcast/pre-event/with-companion      → Persona B (participante com acompanhante)
POST /api/v1/admin/broadcast/pre-event/companion-pending   → Persona C (acompanhante não inscrito)
POST /api/v1/admin/broadcast/pre-event/all                 → Todas as 3 personas
POST /api/v1/admin/broadcast/post-event/trigger-test       → Testa régua pós-evento (compat. c/ botão existente)
GET  /api/v1/admin/broadcast/pre-event/status              → Status do job diário e próximos disparos
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/broadcast", tags=["broadcast"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class BroadcastRequest(BaseModel):
    """Opções de disparo manual. Todos os campos são opcionais."""
    force: bool = True
    """Se True (padrão no broadcast manual), ignora a restrição de `days_before_event`
    e envia todos os templates ativos da persona."""
    days_remaining: int | None = None
    """Sobrescreve o cálculo automático de dias restantes.
    Útil para testar um template específico (ex.: simular disparo de 7 dias antes)."""


class BroadcastResult(BaseModel):
    persona: str | None = None
    days_remaining: int | None = None
    total_sent: int
    total_failed: int
    leads_processed: list[dict] = []
    by_persona: list[dict] = []
    triggered_at: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_admin():
    """Importação lazy para evitar circular imports."""
    from app.api.routes.admin import get_current_admin
    return Depends(get_current_admin)


# ── Endpoints: Broadcast Pré-Evento ──────────────────────────────────────────

@router.post(
    "/pre-event/participant",
    response_model=BroadcastResult,
    summary="📣 Envio massivo — Persona A (Participantes)",
    description=(
        "Envia mensagem de alerta pré-evento para todos os participantes inscritos **sem acompanhante**. "
        "Por padrão, ignora restrições de data (`force=True`) e envia todos os templates ativos."
    ),
)
async def broadcast_participant(
    payload: BroadcastRequest = BroadcastRequest(),
    _=_get_admin(),
):
    from app.services.pre_event_scheduler import dispatch_pre_event_for_persona

    result = await dispatch_pre_event_for_persona(
        persona="participant",
        days_remaining=payload.days_remaining,
        force=payload.force,
    )
    return BroadcastResult(**result, triggered_at=datetime.now(timezone.utc).isoformat())


@router.post(
    "/pre-event/with-companion",
    response_model=BroadcastResult,
    summary="📣 Envio massivo — Persona B (Participantes com Acompanhante)",
    description=(
        "Envia alerta do evento + lembrete para ajudar o acompanhante, "
        "para todos os participantes inscritos **com acompanhante** (`with_companion=True`)."
    ),
)
async def broadcast_with_companion(
    payload: BroadcastRequest = BroadcastRequest(),
    _=_get_admin(),
):
    from app.services.pre_event_scheduler import dispatch_pre_event_for_persona

    result = await dispatch_pre_event_for_persona(
        persona="with_companion",
        days_remaining=payload.days_remaining,
        force=payload.force,
    )
    return BroadcastResult(**result, triggered_at=datetime.now(timezone.utc).isoformat())


@router.post(
    "/pre-event/companion-pending",
    response_model=BroadcastResult,
    summary="📣 Envio massivo — Persona C (Acompanhantes Não Inscritos)",
    description=(
        "Envia lembrete para completar inscrição para todos os acompanhantes "
        "cujo cadastro foi iniciado mas a inscrição ainda não foi concluída."
    ),
)
async def broadcast_companion_pending(
    payload: BroadcastRequest = BroadcastRequest(),
    _=_get_admin(),
):
    from app.services.pre_event_scheduler import dispatch_pre_event_for_persona

    result = await dispatch_pre_event_for_persona(
        persona="companion_pending",
        days_remaining=payload.days_remaining,
        force=payload.force,
    )
    return BroadcastResult(**result, triggered_at=datetime.now(timezone.utc).isoformat())


@router.post(
    "/pre-event/all",
    response_model=BroadcastResult,
    summary="📣 Envio massivo — Todas as Personas (Broadcast Geral)",
    description=(
        "Dispara a régua pré-evento completa para as 3 personas simultaneamente: "
        "participantes simples (A), com acompanhante (B) e acompanhantes não inscritos (C)."
    ),
)
async def broadcast_all(
    payload: BroadcastRequest = BroadcastRequest(),
    _=_get_admin(),
):
    from app.services.pre_event_scheduler import dispatch_pre_event_all

    result = await dispatch_pre_event_all(
        days_remaining=payload.days_remaining,
        force=payload.force,
    )
    return BroadcastResult(**result, triggered_at=datetime.now(timezone.utc).isoformat())


# ── Endpoint: Status do Job Diário ────────────────────────────────────────────

@router.get(
    "/pre-event/status",
    response_model=dict,
    summary="📊 Status da Régua Pré-Evento",
    description="Exibe o status do job diário, próximo disparo e configuração de dias de lembrete.",
)
async def pre_event_status(_=_get_admin()):
    from app.services.scheduler import scheduler
    from app.db.session import AsyncSessionLocal
    from app.models.event import Event, EventStatus
    from app.services.pre_event_scheduler import _days_until_event
    from sqlalchemy import select

    job = scheduler.get_job("pre_event_daily_reminder")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Event).where(Event.status == EventStatus.ACTIVE).order_by(Event.id.desc())
        )
        event = result.scalar_one_or_none()

    reminder_days  = event.pre_event_reminder_days if event else [30, 15, 7, 3, 1]
    send_time      = event.pre_event_send_time if event else "09:00"
    days_remaining = _days_until_event(event.event_date) if event else None

    today_triggers = days_remaining in (reminder_days or []) if days_remaining is not None else False

    return {
        "job_registered":    job is not None,
        "next_run":          job.next_run_time.isoformat() if job and job.next_run_time else None,
        "send_time":         send_time,
        "reminder_days_configured": reminder_days,
        "event_date":        event.event_date if event else None,
        "days_until_event":  days_remaining,
        "triggers_today":    today_triggers,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
    }
