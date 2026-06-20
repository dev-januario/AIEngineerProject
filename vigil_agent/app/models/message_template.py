"""
MessageTemplate Model
=====================
Templates de mensagem editáveis pelo admin com suporte a variáveis dinâmicas.

Variáveis disponíveis nos templates:
  {{NOME}}              → nome do participante
  {{PRIMEIRO_NOME}}     → primeiro nome
  {{CARGO}}             → cargo/função
  {{EMPRESA}}           → empresa
  {{DATA_EVENTO}}       → data do evento (ex.: 15/07/2026)
  {{HORA_EVENTO}}       → horário do evento (ex.: 09:00)
  {{LOCAL_EVENTO}}      → local do evento
  {{NOME_EVENTO}}       → nome do evento
  {{PALESTRANTES}}      → lista de palestrantes separada por vírgula
  {{DIAS_RESTANTES}}    → quantos dias faltam para o evento
  {{NOME_ACOMPANHANTE}} → nome/email do acompanhante (quando with_companion=True)
  {{LINK_INSCRICAO}}    → link para o acompanhante completar inscrição
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplatePhase(str, enum.Enum):
    # ── Inscrição ──────────────────────────────────────────────────────────────
    CONFIRMATION = "confirmation"

    # ── Pré-Evento ─────────────────────────────────────────────────────────────
    PRE_EVENT = "pre_event"                                # Generic / legado

    PRE_EVENT_PARTICIPANT     = "pre_event_participant"        # Persona A: participante simples
    PRE_EVENT_WITH_COMPANION  = "pre_event_with_companion"     # Persona B: participante com acompanhante
    PRE_EVENT_COMPANION_PENDING = "pre_event_companion_pending" # Persona C: acompanhante não inscrito

    # ── Pós-Evento ─────────────────────────────────────────────────────────────
    POST_EVENT          = "post_event"
    POST_EVENT_ATTENDED = "post_event_attended"   # lead esteve presente → agradecimento
    POST_EVENT_NO_SHOW  = "post_event_no_show"    # lead não foi → mensagem de conforto

    # ── Genérico ───────────────────────────────────────────────────────────────
    REPLY = "reply"


class TemplateChannel(str, enum.Enum):
    EMAIL    = "EMAIL"
    WHATSAPP = "WHATSAPP"
    BOTH     = "BOTH"


class MessageTemplate(Base):
    """Template de mensagem editável pelo painel admin."""

    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[TemplatePhase] = mapped_column(
        Enum(TemplatePhase, name="templatephase", values_callable=lambda x: [e.value for e in x]),
        nullable=False, index=True,
    )
    channel: Mapped[TemplateChannel] = mapped_column(
        Enum(TemplateChannel, name="templatechannel", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Assunto (usado só em email)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Corpo da mensagem com variáveis {{NOME}}, {{CARGO}}, etc.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Ordem de disparo dentro da fase (1 = primeiro, 2 = segundo, etc.)
    sequence_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Quantidade de dias antes do evento para disparar este template.
    # Null = sem restrição de data (usado em templates de confirmação, pós-evento, etc.)
    # Exemplos: 30, 15, 7, 3, 1
    days_before_event: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MessageTemplate id={self.id} name={self.name!r} phase={self.phase} days_before={self.days_before_event}>"
