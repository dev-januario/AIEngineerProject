"""
Admin Routes
============
Endpoints do painel administrativo protegidos por JWT.

POST /api/v1/admin/auth/login       → login e retorno de token JWT
GET  /api/v1/admin/event            → dados do evento ativo
PUT  /api/v1/admin/event            → atualiza dados do evento
POST /api/v1/admin/event/end        → encerra evento e agenda pós-evento
PUT  /api/v1/admin/event/schedule-end → agenda encerramento em horário específico
GET  /api/v1/admin/templates        → lista templates de mensagem
POST /api/v1/admin/templates        → cria template
PUT  /api/v1/admin/templates/{id}   → atualiza template
DELETE /api/v1/admin/templates/{id} → remove template
GET  /api/v1/admin/leads            → lista participantes com status do funil
GET  /api/v1/admin/scheduler/status → status do próximo disparo agendado
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.event import Event, EventStatus
from app.models.lead import Lead
from app.models.message_template import MessageTemplate, TemplateChannel, TemplatePhase
from app.services.scheduler import get_next_post_event_run, schedule_post_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# ── Auth ──────────────────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/admin/auth/login")

ALGORITHM = "HS256"


def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.admin_jwt_expire_minutes)
    return jwt.encode(
        {"sub": username, "exp": expire},
        settings.admin_jwt_secret,
        algorithm=ALGORITHM,
    )


async def get_current_admin(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.admin_jwt_secret, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise credentials_exception
    return user


# ── Schemas ──────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class EventUpdate(BaseModel):
    name: str | None = None
    event_date: str | None = None
    event_time: str | None = None
    location: str | None = None
    description: str | None = None
    speakers: list[str] | None = None
    post_event_delay_minutes: int | None = None


class EventRead(BaseModel):
    id: int
    name: str
    event_date: str | None
    event_time: str | None
    location: str | None
    description: str | None
    speakers: list[str] | None
    post_event_delay_minutes: int
    status: str
    scheduled_end_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class TemplateCreate(BaseModel):
    name: str
    phase: TemplatePhase
    channel: TemplateChannel
    subject: str | None = None
    body: str
    sequence_order: int = 1
    is_active: bool = True


class TemplateRead(BaseModel):
    id: int
    name: str
    phase: str
    channel: str
    subject: str | None
    body: str
    sequence_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ScheduleEndRequest(BaseModel):
    scheduled_end_at: datetime  # ISO datetime com timezone


class LeadAdminRead(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None
    company: str | None
    role: str | None
    with_companion: bool
    status: str
    funnel_phase: str
    qualification_score: float | None
    attended: bool | None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Endpoints: Auth ───────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse, summary="Login admin")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(AdminUser).where(AdminUser.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
        )

    token = _create_token(user.username)
    logger.info(f"[Admin] Login: {user.username}")
    return TokenResponse(access_token=token, username=user.username)


# ── Endpoints: Evento ─────────────────────────────────────────────────────────

async def _get_active_event(db: AsyncSession) -> Event:
    result = await db.execute(select(Event).order_by(Event.id.desc()))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Nenhum evento encontrado")
    return event


@router.get("/event", response_model=EventRead, summary="Dados do evento ativo")
async def get_event(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    return await _get_active_event(db)


@router.put("/event", response_model=EventRead, summary="Atualizar dados do evento")
async def update_event(
    payload: EventUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    event = await _get_active_event(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.flush()
    await db.refresh(event)
    logger.info("[Admin] Evento atualizado")
    return event


@router.post("/event/end", response_model=dict, summary="Encerrar evento e agendar pós-evento")
async def end_event(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    """Encerra o evento e dispara a régua pós-evento após o delay configurado."""
    event = await _get_active_event(db)
    event.status = EventStatus.ENDED
    event.ended_at = datetime.now(timezone.utc)
    await db.flush()

    run_at = schedule_post_event(delay_minutes=event.post_event_delay_minutes)

    logger.info(f"[Admin] Evento encerrado. Pós-evento agendado para {run_at.isoformat()}")
    return {
        "message": "Evento encerrado com sucesso",
        "post_event_scheduled_at": run_at.isoformat(),
        "delay_minutes": event.post_event_delay_minutes,
    }


@router.put("/event/schedule-end", response_model=dict, summary="Agendar encerramento em horário específico")
async def schedule_event_end(
    payload: ScheduleEndRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    event = await _get_active_event(db)
    event.scheduled_end_at = payload.scheduled_end_at
    await db.flush()

    # Agenda job para encerrar no horário indicado
    async def _end_at_scheduled_time():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as _db:
            res = await _db.execute(select(Event).where(Event.id == event.id))
            ev = res.scalar_one_or_none()
            if ev:
                ev.status = EventStatus.ENDED
                ev.ended_at = datetime.now(timezone.utc)
                await _db.commit()
        await _dispatch_post_event_sequence_wrapper(event.post_event_delay_minutes)

    from app.services.scheduler import scheduler
    scheduler.add_job(
        _end_at_scheduled_time,
        "date",
        run_date=payload.scheduled_end_at,
        id="scheduled_event_end",
        replace_existing=True,
    )

    logger.info(f"[Admin] Encerramento agendado para {payload.scheduled_end_at.isoformat()}")
    return {
        "message": "Encerramento agendado",
        "scheduled_end_at": payload.scheduled_end_at.isoformat(),
    }


async def _dispatch_post_event_sequence_wrapper(delay_minutes: int):
    from app.services.scheduler import schedule_post_event
    schedule_post_event(delay_minutes=delay_minutes)


class TriggerTestRequest(BaseModel):
    delay_minutes: int = 1


@router.post(
    "/scheduler/trigger-test",
    response_model=dict,
    summary="Disparar follow-up de teste (sem encerrar o evento)",
)
async def trigger_test(
    payload: TriggerTestRequest,
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    """
    Agenda o disparo da régua pós-evento para fins de teste.
    NÃO altera o status do evento nem sobrescreve nenhuma configuração.
    """
    from app.services.scheduler import schedule_post_event

    delay = max(1, payload.delay_minutes)
    run_at = schedule_post_event(delay_minutes=delay)

    logger.info(f"[Admin] Disparo de teste agendado para {run_at.isoformat()} (delay={delay} min)")
    return {
        "message": "Disparo de teste agendado com sucesso",
        "scheduled_at": run_at.isoformat(),
        "delay_minutes": delay,
    }


# ── Endpoints: Templates ──────────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateRead], summary="Listar templates")
async def list_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    result = await db.execute(
        select(MessageTemplate).order_by(MessageTemplate.phase, MessageTemplate.sequence_order)
    )
    return result.scalars().all()


@router.post("/templates", response_model=TemplateRead, status_code=201, summary="Criar template")
async def create_template(
    payload: TemplateCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    tpl = MessageTemplate(**payload.model_dump())
    db.add(tpl)
    await db.flush()
    await db.refresh(tpl)
    return tpl


@router.put("/templates/{template_id}", response_model=TemplateRead, summary="Atualizar template")
async def update_template(
    template_id: int,
    payload: TemplateCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    result = await db.execute(select(MessageTemplate).where(MessageTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tpl, field, value)
    await db.flush()
    await db.refresh(tpl)
    return tpl


@router.delete("/templates/{template_id}", response_model=dict, summary="Remover template")
async def delete_template(
    template_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    result = await db.execute(select(MessageTemplate).where(MessageTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    await db.delete(tpl)
    return {"message": "Template removido"}


# ── Endpoints: Leads ──────────────────────────────────────────────────────────

@router.get("/leads", response_model=list[LeadAdminRead], summary="Lista de participantes")
async def list_leads_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    result = await db.execute(select(Lead).order_by(Lead.created_at.desc()))
    return result.scalars().all()


# ── Endpoints: Scheduler Status ───────────────────────────────────────────────

@router.get("/scheduler/status", response_model=dict, summary="Status do scheduler")
async def scheduler_status(
    _: Annotated[AdminUser, Depends(get_current_admin)],
):
    next_run = get_next_post_event_run()
    return {
        "post_event_next_run": next_run.isoformat() if next_run else None,
        "has_scheduled_job": next_run is not None,
    }
