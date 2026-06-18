"""
MessageTemplate Model
=====================
Templates de mensagem editáveis pelo admin com suporte a variáveis dinâmicas.

Variáveis disponíveis nos templates:
  {{NOME}}          → nome do participante
  {{PRIMEIRO_NOME}} → primeiro nome
  {{CARGO}}         → cargo/função
  {{EMPRESA}}       → empresa
  {{DATA_EVENTO}}   → data do evento (ex.: 15/07/2026)
  {{HORA_EVENTO}}   → horário do evento (ex.: 09:00)
  {{LOCAL_EVENTO}}  → local do evento
  {{NOME_EVENTO}}   → nome do evento
  {{PALESTRANTES}}  → lista de palestrantes separada por vírgula
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplatePhase(str, enum.Enum):
    PRE_EVENT = "pre_event"
    CONFIRMATION = "confirmation"
    POST_EVENT = "post_event"
    REPLY = "reply"


class TemplateChannel(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    BOTH = "both"


class MessageTemplate(Base):
    """Template de mensagem editável pelo painel admin."""

    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[TemplatePhase] = mapped_column(
        Enum(TemplatePhase, name="templatephase"), nullable=False, index=True
    )
    channel: Mapped[TemplateChannel] = mapped_column(
        Enum(TemplateChannel, name="templatechannel"), nullable=False
    )

    # Assunto (usado só em email)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Corpo da mensagem com variáveis {{NOME}}, {{CARGO}}, etc.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Ordem de disparo dentro da fase (1 = primeiro, 2 = segundo, etc.)
    sequence_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MessageTemplate id={self.id} name={self.name!r} phase={self.phase}>"
