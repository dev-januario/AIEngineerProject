from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator, model_validator

from app.models.lead import FunnelPhase, LeadStatus


# Vínculos profissionais permitidos para acompanhantes
COMPANION_PROFESSIONAL_RELATIONSHIPS = {
    "partner",           # Sócio
    "director",          # Diretor
    "manager",           # Gerente
    "coordinator",       # Coordenador
    "team_member",       # Membro da equipe
    "colleague",         # Colega / colaborador
    "business_partner",  # Parceiro de negócios
    "guest_executive",   # Executivo convidado
}


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
    companion_email: str | None = Field(None, description="Email do acompanhante (obrigatório quando with_companion=True)")
    companion_relationship: str | None = Field(
        None,
        description=(
            "Vínculo profissional com o acompanhante. Somente perfis corporativos são aceitos. "
            "Valores permitidos: partner, director, manager, coordinator, "
            "team_member, colleague, business_partner, guest_executive"
        ),
    )
    lgpd_consent: bool = Field(False, description="Consentimento LGPD obrigatório")

    @model_validator(mode="after")
    def check_lgpd_consent(self) -> "LeadBase":
        if not self.lgpd_consent:
            raise ValueError("Consentimento LGPD é obrigatório para processamento dos dados.")
        return self

    @model_validator(mode="after")
    def check_companion_email(self) -> "LeadBase":
        if self.with_companion and not self.companion_email:
            raise ValueError("O email do acompanhante é obrigatório quando 'with_companion' é verdadeiro.")
        return self

    @model_validator(mode="after")
    def check_companion_relationship(self) -> "LeadBase":
        """Rejeita vínculos pessoais (amigo, cônjuge, familiar). Apenas perfis profissionais são aceitos."""
        if self.with_companion and self.companion_relationship:
            if self.companion_relationship not in COMPANION_PROFESSIONAL_RELATIONSHIPS:
                allowed = ", ".join(sorted(COMPANION_PROFESSIONAL_RELATIONSHIPS))
                raise ValueError(
                    f"Vínculo '{self.companion_relationship}' não é permitido. "
                    f"O Vigil Summit aceita apenas acompanhantes com vínculo profissional. "
                    f"Valores válidos: {allowed}"
                )
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
    companion_email: str | None
    companion_relationship: str | None
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
