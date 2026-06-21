import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LeadStatus(str, enum.Enum):
    NEW = "new"
    ENRICHED = "enriched"
    CONTACTED = "contacted"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    NO_RESPONSE = "no_response"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    FOLLOWED_UP = "followed_up"
    MEETING_BOOKED = "meeting_booked"
    OUT_OF_ICP = "out_of_icp"
    # Aguardando aprovação manual do admin (cargo intermediario: gerente, coord., especialista, etc.)
    PENDING_REVIEW = "pending_review"


class FunnelPhase(str, enum.Enum):
    CAPTURE           = "capture"
    ENRICHMENT        = "enrichment"
    PRE_EVENT         = "pre_event"
    COMPANION_PENDING = "companion_pending"  # acompanhante cujo convite foi enviado, mas ainda não se inscreveu
    POST_EVENT        = "post_event"
    CLOSED            = "closed"


class Lead(Base):
    """
    Core Lead model representing an executive registered for Vigil Summit.
    Tracks the full lifecycle from initial capture to commercial meeting booked.
    """

    __tablename__ = "leads"

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Professional Context ──────────────────────────────────────────────────
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Enrichment ────────────────────────────────────────────────────────────
    # JSON column (JSON for SQLite compat in tests, native JSON in MySQL)
    enrichment_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    qualification_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Funnel State ──────────────────────────────────────────────────────────
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="leadstatus", values_callable=lambda x: [e.value for e in x]),
        default=LeadStatus.NEW,
        nullable=False,
        index=True,
    )
    funnel_phase: Mapped[FunnelPhase] = mapped_column(
        Enum(FunnelPhase, name="funnelphase", values_callable=lambda x: [e.value for e in x]),
        default=FunnelPhase.CAPTURE,
        nullable=False,
        index=True,
    )

    # ── Communication History ─────────────────────────────────────────────────
    # List of {channel, sent_at, message_preview, status}
    communication_log: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True, default=list)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Event Context (Post-Event) ────────────────────────────────────────────
    # Notes captured during the event for personalized follow-up
    event_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    attended: Mapped[bool | None] = mapped_column(nullable=True)

    # ── Event Registration ────────────────────────────────────────────────────
    # Se o participante vai levar acompanhante (gatilho de régua de engajamento)
    with_companion: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Email do acompanhante — obrigatório quando with_companion=True; recebe notificação e link para preencher o formulário
    companion_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Tipo de vínculo com o acompanhante — somente perfis profissionais são permitidos:
    # partner | director | manager | coordinator | team_member | colleague | business_partner | guest_executive
    companion_relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Companion Flag ────────────────────────────────────────────────────────
    # True quando este lead é um acompanhante (criado a partir do companion_email de outro lead)
    # Esses leads entram na régua PRE_EVENT_COMPANION_PENDING até completarem inscrição própria
    is_companion: Mapped[bool] = mapped_column(default=False, nullable=False)
    # ID do lead principal que gerou este acompanhante (FK lógica — sem constraint para simplicidade)
    companion_of_lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── LGPD / Consent ───────────────────────────────────────────────────────
    lgpd_consent: Mapped[bool] = mapped_column(default=False, nullable=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Lead id={self.id} email={self.email!r} status={self.status}>"
