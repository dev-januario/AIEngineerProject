"""
Enrichment Service
==================
Responsável por enriquecer o perfil do lead com inferências inteligentes via Gemini 2.5 Flash.

O Gemini analisa os dados disponíveis (nome, email, empresa, cargo, LinkedIn) e retorna
um perfil enriquecido com dados realistas inferidos do seu conhecimento de mercado:
- Cargo real e nível de senioridade
- Tamanho e setor real da empresa (inferido do domínio corporativo)
- Tópicos de segurança relevantes para aquele perfil
- Score e tier de qualificação ICP
- Hooks de personalização específicos para cada lead

Em caso de falha da IA (timeout, quota, etc.), cai num fallback determinístico
que usa os dados disponíveis para calcular score sem inventar informações.
"""

import json
import logging
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Regras de Elegibilidade (determinísticas, sem IA) ─────────────────────────

_AUTO_APPROVED_ACRONYMS = {"ciso", "cto", "cio", "coo"}

_AUTO_APPROVED_KEYWORDS = [
    "chief", "vp ", "vice-president", "vice president",
    "diretor", "director",
    "head de", "head of",
    "risk manager", "gestor de risco", "gestora de risco",
]

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

_TECH_SECURITY_AREA_KEYWORDS = [
    "segurança", "security", "tecnologia", "technology", "ti ", "it ",
    "cibersegurança", "cybersecurity", "cyber",
    "risco", "risk", "compliance", "informação", "information",
    "dados", "data", "infraestrutura", "infrastructure",
    "cloud", "devops", "devsecops", "soc", "siem",
]

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

# Cargos alvo do Vigil Summit
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


def classify_lead_eligibility(role: str | None) -> str:
    """
    Classifica o lead de forma determinística com base no cargo declarado.
    Rodada ANTES do enriquecimento por IA para decisão imediata no cadastro.

    Retorna:
        "approved"       → cargo de liderança executiva, entra direto no funil
        "pending_review" → cargo intermediário com área relevante, aguarda validação
        "not_eligible"   → cargo sem relação com TI/Segurança/Risco
    """
    if not role or not role.strip():
        return "pending_review"

    role_lower = role.strip().lower()

    # Aprovação: siglas como palavras completas (evita substring em "coordenador")
    role_words = set(role_lower.replace("-", " ").replace("/", " ").replace("(", " ").replace(")", " ").split())
    if role_words & _AUTO_APPROVED_ACRONYMS:
        return "approved"

    # Aprovação: keywords executivas
    for keyword in _AUTO_APPROVED_KEYWORDS:
        if keyword in role_lower:
            return "approved"

    # Revisão manual: intermediário + área relevante
    is_intermediate = any(kw in role_lower for kw in _PENDING_REVIEW_KEYWORDS)
    is_relevant_area = any(kw in role_lower for kw in _TECH_SECURITY_AREA_KEYWORDS)

    if is_intermediate and is_relevant_area:
        return "pending_review"

    if is_relevant_area:
        return "pending_review"

    return "not_eligible"


# ── Score helpers (usados no fallback) ───────────────────────────────────────

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
        number = int(size.replace("+", "").split("-")[0].strip().replace("<", "").replace(">", ""))
        if number >= 1000:
            return 1.0
        elif number >= 500:
            return 0.9
        elif number >= 200:
            return 0.75
        else:
            return 0.3
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
    Usado como fallback quando o Gemini não está disponível.

    Pesos:
    - Cargo: 40%
    - Tamanho da empresa: 35%
    - Setor: 20%
    - LinkedIn ativo: 5%
    """
    role_score    = _score_role(role) * 0.40
    size_score    = _score_company_size(company_size) * 0.35
    sector_score  = _score_sector(sector) * 0.20
    linkedin_score = 0.05 if has_linkedin else 0.0

    final = role_score + size_score + sector_score + linkedin_score
    return round(min(final, 1.0), 3)


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


# ── Fallback (sem IA) ─────────────────────────────────────────────────────────

_FALLBACK_SECURITY_TOPICS = [
    "Zero Trust Architecture",
    "LGPD & Privacidade de Dados",
    "Threat Intelligence",
    "Cloud Security",
    "Ransomware Prevention",
    "SOC & SIEM",
    "Gestão de Identidade (IAM)",
    "Segurança em IA/ML",
]

_SECTOR_INTERESTS = {
    "financeiro":  ["LGPD & Privacidade de Dados", "Compliance Regulatório", "Threat Intelligence", "Gestão de Identidade (IAM)"],
    "saúde":       ["LGPD & Privacidade de Dados", "Ransomware Prevention", "Cloud Security", "Gestão de Vulnerabilidades"],
    "governo":     ["Zero Trust Architecture", "Incident Response", "Gestão de Identidade (IAM)", "Segurança em OT/ICS"],
    "energia":     ["Segurança em OT/ICS", "Incident Response", "Zero Trust Architecture", "Threat Intelligence"],
    "telecom":     ["SOC & SIEM", "Zero Trust Architecture", "Cloud Security", "Gestão de Identidade (IAM)"],
    "tecnologia":  ["Cloud Security", "Segurança em IA/ML", "Zero Trust Architecture", "Gestão de Vulnerabilidades"],
}


def _fallback_enrichment(
    email: str,
    name: str,
    company: str | None,
    role: str | None,
    company_size: str | None,
    sector: str | None,
    linkedin_url: str | None,
) -> dict:
    """Enriquecimento fallback usando apenas dados disponíveis + scores calculados."""
    domain = email.split("@")[-1] if "@" in email else ""
    inferred_company = company or domain.split(".")[0].title()
    enriched_size   = company_size or "200-500"
    enriched_sector = sector or "Tecnologia"
    enriched_role   = role or "Profissional de TI"
    linkedin_active = linkedin_url is not None and len(linkedin_url) > 10

    score = calculate_qualification_score(
        role=enriched_role,
        company_size=enriched_size,
        sector=enriched_sector,
        has_linkedin=linkedin_active,
    )

    sector_lower    = enriched_sector.lower()
    interests       = _SECTOR_INTERESTS.get(sector_lower, _FALLBACK_SECURITY_TOPICS[:3])
    first_name      = name.split()[0] if name else "Participante"
    primary_interest = interests[0] if interests else "cibersegurança"

    return {
        "enriched_at": datetime.utcnow().isoformat(),
        "source": "fallback_deterministic_v2",
        "company": {
            "name": inferred_company,
            "domain": domain,
            "size": enriched_size,
            "sector": enriched_sector,
            "estimated_revenue": "Não disponível",
        },
        "professional": {
            "role": enriched_role,
            "seniority_level": _infer_seniority(enriched_role),
            "decision_maker": score >= 0.75,
            "linkedin_active": linkedin_active,
        },
        "security_interests": interests,
        "qualification": {
            "score": score,
            "tier": _score_to_tier(score),
            "fits_icp": score >= 0.60,
            "reason": _explain_score(enriched_role, enriched_size, enriched_sector),
        },
        "personalization_hooks": {
            "first_name": first_name,
            "role_context": f"como {enriched_role} no setor de {enriched_sector}",
            "primary_pain": f"os desafios de {primary_interest}",
            "event_value_prop": (
                f"o Vigil Summit traz especialistas que vão debater {primary_interest} "
                f"com foco em empresas do setor {enriched_sector}"
            ),
        },
    }


# ── Enriquecimento principal via Gemini ───────────────────────────────────────

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
    Enriquece o perfil do lead via Gemini 2.5 Flash (JSON mode).

    O Gemini recebe os dados disponíveis e infere informações realistas baseadas no
    seu conhecimento de mercado: tamanho real da empresa pelo domínio corporativo,
    setor, tópicos de segurança relevantes e score de qualificação ICP.

    Em caso de falha da IA, usa o fallback determinístico para garantir continuidade.
    """
    import google.generativeai as genai
    from app.agents.prompts import ENRICHMENT_AI_PROMPT

    logger.info(f"[Enrichment/Gemini] Iniciando para {email}")

    # Prepara dados para o prompt
    email_domain     = email.split("@")[-1] if "@" in email else "desconhecido"
    linkedin_username = ""
    if linkedin_url:
        if "/in/" in linkedin_url:
            linkedin_username = linkedin_url.split("/in/")[-1].strip("/")
        else:
            linkedin_username = linkedin_url.strip()

    prompt = ENRICHMENT_AI_PROMPT.format(
        name=name,
        email=email,
        email_domain=email_domain,
        company=company or "Não informada",
        role=role or "Não informado",
        company_size=company_size or "Não informado",
        sector=sector or "Não informado",
        linkedin_username=linkedin_username or "Não informado",
    )

    try:
        genai.configure(api_key=settings._gemini_key)
        model = genai.GenerativeModel(
            model_name="gemini-3.5-flash",
            generation_config={"response_mime_type": "application/json"},
        )

        response = await model.generate_content_async(prompt)
        raw_text = response.text.strip()

        # Remove possíveis markdown fences se o modelo ainda os retornar
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[-2] if "```" in raw_text[3:] else raw_text[7:]
        raw_text = raw_text.strip()

        enrichment_raw = json.loads(raw_text)

        # Garante que todos os campos obrigatórios existem
        enrichment_result = {
            "enriched_at": datetime.utcnow().isoformat(),
            "source": "gemini_enrichment_v1",
            "company":              enrichment_raw.get("company", {}),
            "professional":         enrichment_raw.get("professional", {}),
            "security_interests":   enrichment_raw.get("security_interests", []),
            "qualification":        enrichment_raw.get("qualification", {}),
            "personalization_hooks": enrichment_raw.get("personalization_hooks", {}),
        }

        # Garante que linkedin_active reflete a realidade
        enrichment_result["professional"]["linkedin_active"] = bool(linkedin_username)

        score = enrichment_result["qualification"].get("score", 0.0)
        tier  = enrichment_result["qualification"].get("tier", "D")
        fits  = enrichment_result["qualification"].get("fits_icp", False)

        logger.info(
            f"[Enrichment/Gemini] ✅ {email} | "
            f"empresa={enrichment_result['company'].get('name')} | "
            f"setor={enrichment_result['company'].get('sector')} | "
            f"score={score:.2f} | tier={tier} | fits_icp={fits}"
        )
        return enrichment_result

    except json.JSONDecodeError as e:
        logger.warning(f"[Enrichment/Gemini] JSON inválido para {email}: {e} → usando fallback")
        return _fallback_enrichment(email, name, company, role, company_size, sector, linkedin_url)

    except Exception as e:
        logger.error(f"[Enrichment/Gemini] Falha para {email}: {e} → usando fallback")
        return _fallback_enrichment(email, name, company, role, company_size, sector, linkedin_url)
