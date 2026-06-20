"""
Enrichment Service
==================
Responsável por enriquecer o perfil do lead com dados públicos antes de qualquer contato.

Em produção, integraria com APIs como:
- Hunter.io (verificação de email principal)
- Clearbit (cargo, tamanho da empresa)
- LinkedIn Sales Navigator (presença e atividade profissional)

Para este case, implementamos um serviço mock inteligente que simula o enriquecimento
e demonstra a lógica de qualificação de leads B2B para o Vigil Summit.
"""

import asyncio
import logging
import random
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Qualificação ──────────────────────────────────────────────────────────────

# Cargos alvo do Vigil Summit (executivos de segurança e TI)
TARGET_ROLES = {
    "ciso": 1.0,
    "cto": 0.95,
    "coo": 0.85,
    "diretor de ti": 0.90,
    "diretor de tecnologia": 0.90,
    "head de segurança": 0.90,
    "vp de tecnologia": 0.88,
    "gerente de segurança": 0.75,
    "risk manager": 0.80,
    "chief security officer": 1.0,
    "chief technology officer": 0.95,
}

# ── Regras de Elegibilidade (determinísticas, sem IA) ─────────────────────────

# Cargos que aprovam automaticamente — liderança executiva de TI/Segurança/Risco
# Siglas curtas são verificadas como PALAVRAS COMPLETAS (word boundary) para evitar
# falsos positivos: ex. 'coo' dentro de 'coordenador', 'cio' dentro de 'associação'.
_AUTO_APPROVED_ACRONYMS = {"ciso", "cto", "cio", "coo"}

_AUTO_APPROVED_KEYWORDS = [
    "chief", "vp ", "vice-president", "vice president",
    "diretor", "director",
    "head de", "head of",
    "risk manager", "gestor de risco", "gestora de risco",
]

# Cargos que entram em revisão manual — perfil intermediário, pode ou não ser elegível
_PENDING_REVIEW_KEYWORDS = [
    "gerente", "manager",
    "coordenador", "coordinator",
    "especialista", "specialist",
    "consultor", "consultant",
    "analista sênior", "senior analyst",
    "analista senior",
    "engenheiro sênior", "senior engineer",
    "arquiteto", "architect",
]

# Palavras-chave que indicam área relevante (TI, Segurança, Risco, Compliance)
_TECH_SECURITY_AREA_KEYWORDS = [
    "segurança", "security", "tecnologia", "technology", "ti ", "it ",
    "cibersegurança", "cybersecurity", "cyber",
    "risco", "risk", "compliance", "informação", "information",
    "dados", "data", "infraestrutura", "infrastructure",
    "cloud", "devops", "devSecOps", "soc", "siem",
]


def classify_lead_eligibility(role: str | None) -> str:
    """
    Classifica o lead de forma determinística com base no cargo declarado.

    Retorna:
        "approved"       → cargo de liderança executiva, entra direto no funil
        "pending_review" → cargo intermediário com área relevante, aguarda validação do admin
        "not_eligible"   → cargo sem relação com TI/Segurança/Risco ou perfil incompatível

    Essa função é síncrona e roda antes do enriquecimento assíncrono por IA.
    """
    if not role or not role.strip():
        # Sem cargo declarado → vai para revisão manual (benefício da dúvida)
        return "pending_review"

    role_lower = role.strip().lower()

    # 1. Aprovação automática: verifica siglas como palavras completas (evita substring bugs)
    role_words = set(role_lower.replace("-", " ").replace("/", " ").replace("(", " ").replace(")", " ").split())
    if role_words & _AUTO_APPROVED_ACRONYMS:
        return "approved"

    # 1b. Aprovação automática: cargo executivo por keyword substring
    for keyword in _AUTO_APPROVED_KEYWORDS:
        if keyword in role_lower:
            return "approved"

    # 2. Revisão manual: cargo intermediário + área relevante
    is_intermediate = any(kw in role_lower for kw in _PENDING_REVIEW_KEYWORDS)
    is_relevant_area = any(kw in role_lower for kw in _TECH_SECURITY_AREA_KEYWORDS)

    if is_intermediate and is_relevant_area:
        return "pending_review"

    # 3. Cargo relevante mas não executivo e não claramente intermediário → revisão
    if is_relevant_area:
        return "pending_review"

    # 4. Sem relação com a área → não elegível
    return "not_eligible"

# Setores com alta propensão à segurança digital
HIGH_VALUE_SECTORS = {
    "financeiro": 1.0,
    "saúde": 0.95,
    "governo": 0.90,
    "energia": 0.88,
    "telecom": 0.85,
    "varejo": 0.75,
    "indústria": 0.72,
    "tecnologia": 0.80,
}


def _score_role(role: str | None) -> float:
    if not role:
        return 0.5
    role_lower = role.lower()
    for key, score in TARGET_ROLES.items():
        if key in role_lower:
            return score
    return 0.5


def _score_company_size(size: str | None) -> float:
    if not size:
        return 0.5
    try:
        # Aceita formatos: "500", "500-1000", "1000+"
        number = int(size.replace("+", "").split("-")[0].strip())
        if number >= 1000:
            return 1.0
        elif number >= 500:
            return 0.9
        elif number >= 200:
            return 0.75
        else:
            return 0.3  # Abaixo do perfil alvo (200+ funcionários)
    except (ValueError, AttributeError):
        return 0.5


def _score_sector(sector: str | None) -> float:
    if not sector:
        return 0.5
    sector_lower = sector.lower()
    for key, score in HIGH_VALUE_SECTORS.items():
        if key in sector_lower:
            return score
    return 0.6


def calculate_qualification_score(
    role: str | None,
    company_size: str | None,
    sector: str | None,
    has_linkedin: bool = False,
) -> float:
    """
    Calcula score de qualificação (0.0 - 1.0) baseado no perfil ICP da Vigil.AI.
    
    Pesos:
    - Cargo: 40%  (proxy de poder de decisão)
    - Tamanho da empresa: 35%  (critério mínimo: 200 funcionários)
    - Setor: 20%  (setores com maior exposição a risco digital)
    - LinkedIn ativo: 5%  (sinal de engajamento profissional)
    """
    role_score = _score_role(role) * 0.40
    size_score = _score_company_size(company_size) * 0.35
    sector_score = _score_sector(sector) * 0.20
    linkedin_score = 0.05 if has_linkedin else 0.0

    final = role_score + size_score + sector_score + linkedin_score
    return round(min(final, 1.0), 3)


# ── Mock Data ─────────────────────────────────────────────────────────────────

MOCK_COMPANIES = {
    "techcorp": {"size": "500-1000", "sector": "Tecnologia", "revenue": "R$ 50M-100M"},
    "banco": {"size": "1000+", "sector": "Financeiro", "revenue": "R$ 500M+"},
    "saúde": {"size": "200-500", "sector": "Saúde", "revenue": "R$ 20M-50M"},
    "energy": {"size": "1000+", "sector": "Energia", "revenue": "R$ 200M+"},
}

SECURITY_TOPICS = [
    "Zero Trust Architecture",
    "LGPD & Privacidade de Dados",
    "Threat Intelligence",
    "Cloud Security",
    "Ransomware Prevention",
    "SOC & SIEM",
    "Gestão de Identidade (IAM)",
    "Segurança em IA/ML",
]


async def enrich_lead_profile(
    email: str,
    name: str,
    company: str | None,
    role: str | None,
    company_size: str | None,
    sector: str | None,
    linkedin_url: str | None,
) -> dict:
    """
    Enriquece o perfil do lead com dados públicos.
    
    Simula latência de APIs externas (~1-2s) e retorna dados estruturados
    para alimentar o agente de personalização de mensagens.
    """
    logger.info(f"[Enrichment] Iniciando enriquecimento para {email}")

    # Simula chamada async a APIs externas
    await asyncio.sleep(random.uniform(0.5, 1.5))

    # Inferência de dados da empresa a partir do email/nome
    domain = email.split("@")[-1] if "@" in email else ""
    inferred_company = company or domain.split(".")[0].title()

    # Busca dados simulados ou usa valores fornecidos
    mock_key = next(
        (k for k in MOCK_COMPANIES if k in (inferred_company or "").lower()), None
    )
    company_data = MOCK_COMPANIES.get(mock_key, {})

    enriched_size = company_size or company_data.get("size", "500-1000")
    enriched_sector = sector or company_data.get("sector", "Tecnologia")
    enriched_role = role or "Diretor de TI"

    # Tópicos de segurança de interesse (inferidos do setor)
    security_interests = random.sample(SECURITY_TOPICS, k=random.randint(2, 4))

    # Verificação de presença no LinkedIn
    linkedin_active = linkedin_url is not None and len(linkedin_url) > 10

    # Score de qualificação final
    score = calculate_qualification_score(
        role=enriched_role,
        company_size=enriched_size,
        sector=enriched_sector,
        has_linkedin=linkedin_active,
    )

    enrichment_result = {
        "enriched_at": datetime.utcnow().isoformat(),
        "source": "mock_enrichment_v1",
        "company": {
            "name": inferred_company,
            "domain": domain,
            "size": enriched_size,
            "sector": enriched_sector,
            "estimated_revenue": company_data.get("revenue", "Não disponível"),
        },
        "professional": {
            "role": enriched_role,
            "seniority_level": _infer_seniority(enriched_role),
            "decision_maker": score >= 0.75,
            "linkedin_active": linkedin_active,
        },
        "security_interests": security_interests,
        "qualification": {
            "score": score,
            "tier": _score_to_tier(score),
            "fits_icp": score >= 0.60,
            "reason": _explain_score(enriched_role, enriched_size, enriched_sector),
        },
        "personalization_hooks": _generate_hooks(
            name=name,
            role=enriched_role,
            sector=enriched_sector,
            interests=security_interests,
        ),
    }

    logger.info(
        f"[Enrichment] {email} → score={score:.2f}, tier={enrichment_result['qualification']['tier']}"
    )
    return enrichment_result


def _infer_seniority(role: str) -> str:
    role_lower = role.lower()
    if any(k in role_lower for k in ["ciso", "cto", "coo", "chief", "vp"]):
        return "C-Level / VP"
    elif any(k in role_lower for k in ["diretor", "director", "head"]):
        return "Director"
    elif any(k in role_lower for k in ["gerente", "manager"]):
        return "Manager"
    return "Specialist"


def _score_to_tier(score: float) -> str:
    if score >= 0.85:
        return "A"
    elif score >= 0.70:
        return "B"
    elif score >= 0.55:
        return "C"
    return "D"


def _explain_score(role: str | None, size: str | None, sector: str | None) -> str:
    parts = []
    if role and _score_role(role) >= 0.80:
        parts.append(f"cargo decisor ({role})")
    if size and _score_company_size(size) >= 0.75:
        parts.append(f"empresa no porte alvo ({size} funcionários)")
    if sector and _score_sector(sector) >= 0.80:
        parts.append(f"setor de alta exposição a risco ({sector})")
    return "Lead qualificado: " + ", ".join(parts) if parts else "Lead em análise"


def _generate_hooks(
    name: str, role: str, sector: str, interests: list[str]
) -> dict:
    """Gera ganchos de personalização para uso nos prompts do agente."""
    first_name = name.split()[0]
    primary_interest = interests[0] if interests else "cibersegurança"
    return {
        "first_name": first_name,
        "role_context": f"como {role} no setor de {sector}",
        "primary_pain": f"os desafios de {primary_interest}",
        "event_value_prop": (
            f"o Vigil Summit traz especialistas que vão debater {primary_interest} "
            f"com foco em empresas do setor {sector}"
        ),
    }
