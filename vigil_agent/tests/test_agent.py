"""
Agent Unit Tests
================
Testes unitários para os componentes do LangGraph agent e serviços.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.enrichment import (
    calculate_qualification_score,
    enrich_lead_profile,
    _score_to_tier,
)
from app.agents.prompts import format_lead_context, format_enrichment_context


# ── Enrichment Service ────────────────────────────────────────────────────────

class TestQualificationScore:
    """Testa a lógica de scoring ICP."""

    def test_ciso_financeiro_grande_empresa(self):
        """CISO em empresa financeira grande deve ter score máximo."""
        score = calculate_qualification_score(
            role="CISO",
            company_size="1000+",
            sector="Financeiro",
            has_linkedin=True,
        )
        assert score >= 0.90, f"Score esperado >= 0.90, obtido: {score}"

    def test_cto_tecnologia(self):
        """CTO em empresa de tecnologia deve ser bem qualificado."""
        score = calculate_qualification_score(
            role="CTO",
            company_size="500-1000",
            sector="Tecnologia",
            has_linkedin=False,
        )
        assert score >= 0.75

    def test_empresa_pequena_desconta_score(self):
        """Empresa pequena deve ter score menor que empresa grande com mesmo cargo."""
        score_pequena = calculate_qualification_score(
            role="CISO",
            company_size="50",  # Abaixo do threshold
            sector="Financeiro",
            has_linkedin=True,
        )
        score_grande = calculate_qualification_score(
            role="CISO",
            company_size="1000+",
            sector="Financeiro",
            has_linkedin=True,
        )
        # Empresa pequena deve ter score MENOR que empresa grande
        assert score_pequena < score_grande
        # E não deve atingir tier A
        assert score_pequena < 0.85

    def test_cargo_generico_score_medio(self):
        """Cargo genérico (Analista) deve ter score médio/baixo."""
        score = calculate_qualification_score(
            role="Analista de TI",
            company_size="500-1000",
            sector="Financeiro",
            has_linkedin=False,
        )
        assert 0.0 < score < 0.75

    def test_sem_dados_retorna_score_valido(self):
        """Ausência de dados não deve gerar erro, apenas score baixo."""
        score = calculate_qualification_score(
            role=None,
            company_size=None,
            sector=None,
            has_linkedin=False,
        )
        assert 0.0 <= score <= 1.0

    def test_score_maximo_e_um(self):
        """Score não deve ultrapassar 1.0."""
        score = calculate_qualification_score(
            role="CISO",
            company_size="1000+",
            sector="Financeiro",
            has_linkedin=True,
        )
        assert score <= 1.0

    @pytest.mark.parametrize("score,expected_tier", [
        (0.90, "A"),
        (0.75, "B"),
        (0.60, "C"),
        (0.40, "D"),
    ])
    def test_tier_mapping(self, score: float, expected_tier: str):
        """Score deve mapear corretamente para tier A/B/C/D."""
        assert _score_to_tier(score) == expected_tier


class TestEnrichLeadProfile:
    """Testa o serviço de enriquecimento assíncrono."""

    @pytest.mark.asyncio
    async def test_enrichment_retorna_estrutura_esperada(self):
        """O enriquecimento deve retornar todos os campos esperados."""
        result = await enrich_lead_profile(
            email="carlos@techcorp.com.br",
            name="Carlos Mendes",
            company="TechCorp",
            role="CISO",
            company_size="500-1000",
            sector="Financeiro",
            linkedin_url="https://linkedin.com/in/carlos",
        )

        assert "enriched_at" in result
        assert "company" in result
        assert "professional" in result
        assert "security_interests" in result
        assert "qualification" in result
        assert "personalization_hooks" in result

        qual = result["qualification"]
        assert "score" in qual
        assert "tier" in qual
        assert "fits_icp" in qual
        assert 0.0 <= qual["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_enrichment_ciso_financeiro_fits_icp(self):
        """CISO em empresa financeira deve passar no filtro ICP."""
        result = await enrich_lead_profile(
            email="ciso@banco.com.br",
            name="Ana Lima",
            company="Banco Nacional",
            role="CISO",
            company_size="1000+",
            sector="Financeiro",
            linkedin_url="https://linkedin.com/in/ana-lima",
        )
        assert result["qualification"]["fits_icp"] is True
        assert result["qualification"]["tier"] in ["A", "B"]

    @pytest.mark.asyncio
    async def test_enrichment_sem_linkedin(self):
        """Enriquecimento deve funcionar sem LinkedIn."""
        result = await enrich_lead_profile(
            email="teste@empresa.com",
            name="João Silva",
            company=None,
            role=None,
            company_size=None,
            sector=None,
            linkedin_url=None,
        )
        assert isinstance(result, dict)
        assert result["professional"]["linkedin_active"] is False

    @pytest.mark.asyncio
    async def test_personalization_hooks_gerados(self):
        """Hooks de personalização devem conter campos para templates."""
        result = await enrich_lead_profile(
            email="diretor@saude.com.br",
            name="Maria Costa",
            company="HealthCorp",
            role="Diretor de TI",
            company_size="200-500",
            sector="Saúde",
            linkedin_url=None,
        )
        hooks = result["personalization_hooks"]
        assert "first_name" in hooks
        assert hooks["first_name"] == "Maria"
        assert "event_value_prop" in hooks
        assert "role_context" in hooks


# ── Prompts ───────────────────────────────────────────────────────────────────

class TestPromptFormatters:
    """Testa formatadores de contexto para os prompts."""

    def test_format_lead_context(self):
        lead = {
            "name": "Carlos Mendes",
            "email": "carlos@empresa.com",
            "role": "CISO",
            "company": "TechCorp",
            "sector": "Financeiro",
            "status": "new",
            "funnel_phase": "capture",
            "qualification_score": 0.88,
        }
        ctx = format_lead_context(lead)
        assert "Carlos Mendes" in ctx
        assert "CISO" in ctx
        assert "Financeiro" in ctx
        assert "0.88" in ctx

    def test_format_enrichment_context_vazio(self):
        """Context vazio não deve levantar erro."""
        ctx = format_enrichment_context({})
        assert "não disponíveis" in ctx.lower() or ctx

    def test_format_enrichment_context_completo(self):
        enrichment = {
            "qualification": {"tier": "A", "score": 0.92},
            "professional": {"decision_maker": True, "seniority_level": "C-Level / VP"},
            "security_interests": ["Zero Trust", "LGPD"],
            "personalization_hooks": {
                "event_value_prop": "debate sobre Zero Trust para o setor Financeiro"
            },
        }
        ctx = format_enrichment_context(enrichment)
        assert "A" in ctx
        assert "Zero Trust" in ctx
        assert "C-Level" in ctx


# ── Agent Graph ───────────────────────────────────────────────────────────────

class TestAgentNodes:
    """Testa nós individuais do grafo LangGraph (sem Claude real)."""

    @pytest.mark.asyncio
    async def test_node_enrich_lead(self):
        """Nó de enriquecimento deve atualizar estado corretamente."""
        from app.agents.graph import node_enrich_lead, AgentState

        state: AgentState = {
            "lead_id": 1,
            "lead_email": "test@empresa.com",
            "lead_name": "Test User",
            "lead_phone": "+5511999999999",
            "lead_role": "CISO",
            "lead_company": "TestCorp",
            "lead_company_size": "500-1000",
            "lead_sector": "Financeiro",
            "lead_linkedin": "https://linkedin.com/in/test",
            "enrichment_data": None,
            "qualification_score": None,
            "fits_icp": False,
            "current_phase": "capture",
            "current_status": "new",
            "contact_attempts": 0,
            "communication_log": [],
            "inbound_message": None,
            "attended": None,
            "event_notes": None,
            "last_action": "",
            "error": None,
        }

        result = await node_enrich_lead(state)

        assert result["enrichment_data"] is not None
        assert result["qualification_score"] is not None
        assert result["current_phase"] == "enrichment"
        assert result["current_status"] == "enriched"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_node_score_and_route_icp_ok(self):
        """Lead qualificado deve ser roteado para pré-evento."""
        from app.agents.graph import node_score_and_route, AgentState

        state: AgentState = {
            "lead_id": 1,
            "lead_email": "test@empresa.com",
            "lead_name": "Test",
            "lead_phone": None,
            "lead_role": "CISO",
            "lead_company": "Corp",
            "lead_company_size": "1000+",
            "lead_sector": "Financeiro",
            "lead_linkedin": None,
            "enrichment_data": {},
            "qualification_score": 0.88,
            "fits_icp": True,
            "current_phase": "enrichment",
            "current_status": "enriched",
            "contact_attempts": 0,
            "communication_log": [],
            "inbound_message": None,
            "attended": None,
            "event_notes": None,
            "last_action": "",
            "error": None,
        }

        result = await node_score_and_route(state)
        assert result["current_phase"] == "pre_event"

    @pytest.mark.asyncio
    async def test_node_score_and_route_out_of_icp(self):
        """Lead fora do ICP deve ser fechado."""
        from app.agents.graph import node_score_and_route, AgentState

        state: AgentState = {
            "lead_id": 2,
            "lead_email": "junior@empresa.com",
            "lead_name": "Junior Dev",
            "lead_phone": None,
            "lead_role": "Estagiário",
            "lead_company": "Startup",
            "lead_company_size": "10",
            "lead_sector": "Tech",
            "lead_linkedin": None,
            "enrichment_data": {},
            "qualification_score": 0.25,
            "fits_icp": False,
            "current_phase": "enrichment",
            "current_status": "enriched",
            "contact_attempts": 0,
            "communication_log": [],
            "inbound_message": None,
            "attended": None,
            "event_notes": None,
            "last_action": "",
            "error": None,
        }

        result = await node_score_and_route(state)
        assert result["current_phase"] == "closed"
        assert result["current_status"] == "out_of_icp"
