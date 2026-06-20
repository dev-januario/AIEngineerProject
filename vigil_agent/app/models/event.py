"""
Event Model
===========
Dados do evento Vigil Summit, gerenciados pelo painel admin.
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class Event(Base):
    """
    Representa um evento (ex.: Vigil Summit).
    Somente um evento pode estar ACTIVE por vez.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Vigil Summit — Segurança para a Era da IA")
    event_date: Mapped[str | None] = mapped_column(String(50), nullable=True)   # "2026-07-15"
    event_time: Mapped[str | None] = mapped_column(String(20), nullable=True)   # "09:00"
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lista de palestrantes como JSON ["João Silva", "Maria Costa"]
    speakers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)

    # Configuração da régua de pós-evento
    # Minutos após encerramento para disparar a régua (3 min por padrão = teste rápido)
    post_event_delay_minutes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Configuração da régua pré-evento
    # Lista de dias antes do evento em que serão disparados lembretes.
    # O admin pode ajustar livremente sem alterar código.
    # Padrão: [30, 15, 7, 3, 1]
    pre_event_reminder_days: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, default=lambda: [30, 15, 7, 3, 1]
    )

    # Horário de disparo diário da régua pré-evento (HH:MM, ex: "09:00")
    pre_event_send_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="eventstatus", values_callable=lambda x: [e.value for e in x]),
        default=EventStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Horário programado de encerramento (opcional)
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Horário efetivo de encerramento (preenchido quando admin clica em "Encerrar")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} name={self.name!r} status={self.status}>"
