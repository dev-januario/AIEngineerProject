from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, HttpUrl, model_validator

from app.models.lead import FunnelPhase, LeadStatus


# ── Base ──────────────────────────────────────────────────────────────────────

class LeadBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, examples=["Carlos Mendes"])
    email: EmailStr = Field(..., examples=["carlos.mendes@empresa.com.br"])
    phone: str | None = Field(None, examples=["+5511991234567"])
    company: str | None = Field(None, examples=["TechCorp Brasil"])
    role: str | None = Field(None, examples=["CISO"])
    # Campos preenchidos pela IA (enriquecimento) — opcionais no formulário
    company_size: str | None = Field(None, examples=["500-1000"])
    sector: str | None = Field(None, examples=["Financeiro"])
    linkedin_url: str | None = Field(None, examples=["https://linkedin.com/in/carlos-mendes"])
    with_companion: bool = Field(False, description="Vai levar acompanhante ao evento?")
    lgpd_consent: bool = Field(False, description="Consentimento LGPD obrigatório")

    @model_validator(mode="after")
    def check_lgpd_consent(self) -> "LeadBase":
        if not self.lgpd_consent:
            raise ValueError("Consentimento LGPD é obrigatório para processamento dos dados.")
        return self


# ── Create (entrada da API) ───────────────────────────────────────────────────

class LeadCreate(LeadBase):
    """Payload recebido ao registrar um novo lead no formulário/landing page."""
    pass


# ── Update ────────────────────────────────────────────────────────────────────

class LeadUpdate(BaseModel):
    """Campos opcionais para atualização parcial de um lead."""
    name: str | None = None
    phone: str | None = None
    company: str | None = None
    role: str | None = None
    company_size: str | None = None
    sector: str | None = None
    linkedin_url: str | None = None
    status: LeadStatus | None = None
    funnel_phase: FunnelPhase | None = None
    event_notes: str | None = None
    attended: bool | None = None


# ── Read (saída da API) ───────────────────────────────────────────────────────

class LeadRead(BaseModel):
    """Representação completa de um lead retornado pela API."""
    id: int
    name: str
    email: str
    phone: str | None
    company: str | None
    role: str | None
    company_size: str | None
    sector: str | None
    linkedin_url: str | None
    with_companion: bool
    enrichment_data: dict[str, Any] | None
    qualification_score: float | None
    status: LeadStatus
    funnel_phase: FunnelPhase
    communication_log: list[dict] | None
    last_contacted_at: datetime | None
    contact_attempts: int
    event_notes: str | None
    attended: bool | None
    lgpd_consent: bool
    consent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Summary (listagem) ────────────────────────────────────────────────────────

class LeadSummary(BaseModel):
    """Versão resumida para listagens e painéis."""
    id: int
    name: str
    email: str
    company: str | None
    role: str | None
    status: LeadStatus
    funnel_phase: FunnelPhase
    qualification_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Webhook (inbound response) ────────────────────────────────────────────────

class LeadWebhookEvent(BaseModel):
    """Evento recebido de um canal externo (WhatsApp/Email) com resposta do lead."""
    lead_email: EmailStr
    channel: str = Field(..., examples=["whatsapp", "email"])
    message: str = Field(..., examples=["Confirmo minha presença!"])
    received_at: datetime | None = None
