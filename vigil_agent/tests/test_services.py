"""
Services Unit Tests
====================
Testes unitários para os serviços de notificação, enrichment e qualificação.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.notification import (
    render_template_vars,
    format_date_pt,
    build_template_vars,
    send_email,
    send_whatsapp,
    notify_lead,
    NotificationChannel,
    NotificationStatus,
)
from app.services.enrichment import (
    classify_lead_eligibility,
    calculate_qualification_score,
    _score_to_tier,
)


# ── Template Rendering ───────────────────────────────────────────────────────

class TestRenderTemplateVars:
    """Testa a substituição de variáveis {{VAR}} nos templates."""

    def test_substitui_variavel_simples(self):
        body = "Olá {{NOME}}, bem-vindo ao {{NOME_EVENTO}}!"
        result = render_template_vars(body, {"NOME": "Carlos", "NOME_EVENTO": "Vigil Summit"})
        assert result == "Olá Carlos, bem-vindo ao Vigil Summit!"

    def test_variavel_inexistente_mostra_placeholder(self):
        body = "Olá {{NOME}}, cargo: {{CARGO}}"
        result = render_template_vars(body, {"NOME": "Carlos"})
        assert "Carlos" in result
        assert "[CARGO]" in result

    def test_corpo_sem_variaveis(self):
        body = "Texto fixo sem variáveis"
        result = render_template_vars(body, {"NOME": "Carlos"})
        assert result == "Texto fixo sem variáveis"

    def test_variaveis_com_espacos(self):
        body = "{{ NOME }} tem cargo {{ CARGO }}"
        result = render_template_vars(body, {"NOME": "Ana", "CARGO": "CTO"})
        assert "Ana" in result
        assert "CTO" in result

    def test_corpo_vazio(self):
        result = render_template_vars("", {"NOME": "Test"})
        assert result == ""

    def test_multiplas_ocorrencias_mesma_variavel(self):
        body = "{{NOME}}, obrigado {{NOME}}!"
        result = render_template_vars(body, {"NOME": "Maria"})
        assert result == "Maria, obrigado Maria!"


# ── Date Formatting ──────────────────────────────────────────────────────────

class TestFormatDatePt:
    """Testa a formatação de datas para português brasileiro."""

    def test_data_completa(self):
        result = format_date_pt("2026-07-15")
        assert "15" in result
        assert "julho" in result
        assert "2026" in result

    def test_data_com_horario(self):
        result = format_date_pt("2026-07-15", "09:00")
        assert "09h00" in result
        assert "julho" in result

    def test_data_none(self):
        result = format_date_pt(None)
        assert result == "A confirmar"

    def test_meses_corretos(self):
        meses = [
            ("2026-01-01", "janeiro"),
            ("2026-06-15", "junho"),
            ("2026-12-31", "dezembro"),
        ]
        for date_str, expected_month in meses:
            result = format_date_pt(date_str)
            assert expected_month in result, f"Esperava {expected_month} em {result}"


# ── Build Template Variables ─────────────────────────────────────────────────

class TestBuildTemplateVars:
    """Testa a construção do dicionário de variáveis para templates."""

    def test_variaveis_basicas(self):
        lead = {"name": "Carlos Mendes", "role": "CISO", "company": "TechCorp"}
        event = {"name": "Vigil Summit", "event_date": "2026-07-15", "event_time": "09:00", "location": "São Paulo", "speakers": ["João Silva"]}
        vars = build_template_vars(lead, event)

        assert vars["NOME"] == "Carlos Mendes"
        assert vars["PRIMEIRO_NOME"] == "Carlos"
        assert vars["CARGO"] == "CISO"
        assert vars["EMPRESA"] == "TechCorp"
        assert "julho" in vars["DATA_EVENTO"]
        assert "09h00" in vars["HORA_EVENTO"]

    def test_lead_sem_dados_opcionais(self):
        lead = {"name": None, "role": None, "company": None}
        vars = build_template_vars(lead)

        assert vars["NOME"] == "Participante"
        assert vars["PRIMEIRO_NOME"] == "Participante"
        assert vars["CARGO"] == "Executivo"
        assert vars["EMPRESA"] == "sua empresa"

    def test_dias_restantes(self):
        lead = {"name": "Ana"}
        vars = build_template_vars(lead, days_remaining=3)
        assert vars["DIAS_RESTANTES"] == "3 dias"

    def test_dias_restantes_singular(self):
        lead = {"name": "Ana"}
        vars = build_template_vars(lead, days_remaining=1)
        assert vars["DIAS_RESTANTES"] == "1 dia"


# ── Lead Eligibility Classification ─────────────────────────────────────────

class TestClassifyLeadEligibility:
    """Testa a qualificação determinística de leads por cargo."""

    # Auto-aprovados
    @pytest.mark.parametrize("role", [
        "CISO", "CTO", "CIO", "COO",
        "Chief Information Security Officer",
        "Diretor de TI", "Director of Engineering",
        "VP de Tecnologia", "Vice President of Security",
        "Head de Segurança", "Head of Cybersecurity",
        "Fundador", "Co-Fundador", "Founder",
        "CEO", "CFO", "Sócio", "Partner",
        "Presidente", "Proprietário",
    ])
    def test_cargo_executivo_aprovado(self, role):
        result = classify_lead_eligibility(role)
        assert result == "approved", f"Cargo '{role}' deveria ser approved, mas foi '{result}'"

    # Revisão manual
    @pytest.mark.parametrize("role", [
        "Gerente de Segurança",
        "Coordenador de Segurança",
        "Especialista em Cibersegurança",
        "Consultor de Security",
        "Analista Sênior de Dados",
        "Arquiteto de Cloud",
        "Engenheiro Sênior de Software",
    ])
    def test_cargo_intermediario_pendente(self, role):
        result = classify_lead_eligibility(role)
        assert result == "pending_review", f"Cargo '{role}' deveria ser pending_review, mas foi '{result}'"

    # Não elegíveis
    @pytest.mark.parametrize("role", [
        "Recepcionista",
        "Auxiliar Administrativo",
        "Estagiário de RH",
        "Porteiro",
        "Motorista",
    ])
    def test_cargo_generico_nao_elegivel(self, role):
        result = classify_lead_eligibility(role)
        assert result == "not_eligible", f"Cargo '{role}' deveria ser not_eligible, mas foi '{result}'"

    # Casos limítrofes
    def test_cargo_none(self):
        assert classify_lead_eligibility(None) == "pending_review"

    def test_cargo_vazio(self):
        assert classify_lead_eligibility("") == "pending_review"

    def test_cargo_apenas_espacos(self):
        assert classify_lead_eligibility("   ") == "pending_review"

    def test_cargo_case_insensitive(self):
        """Deve normalizar letras maiúsculas/minúsculas."""
        assert classify_lead_eligibility("ciso") == "approved"
        assert classify_lead_eligibility("CISO") == "approved"
        assert classify_lead_eligibility("Ciso") == "approved"


# ── Qualification Score ──────────────────────────────────────────────────────

class TestQualificationScoreExtended:
    """Testes adicionais para o cálculo de score ICP."""

    def test_linkedin_adiciona_score(self):
        """Ter LinkedIn deve adicionar pontos ao score."""
        score_sem = calculate_qualification_score("CISO", "500-1000", "Tecnologia", False)
        score_com = calculate_qualification_score("CISO", "500-1000", "Tecnologia", True)
        assert score_com > score_sem

    def test_setor_financeiro_maior_que_varejo(self):
        """Setor financeiro deve pontuar mais que varejo."""
        score_financeiro = calculate_qualification_score("Gerente", "500-1000", "Financeiro", False)
        score_varejo = calculate_qualification_score("Gerente", "500-1000", "Varejo", False)
        assert score_financeiro >= score_varejo

    def test_score_nunca_negativo(self):
        """Score nunca deve ser negativo."""
        score = calculate_qualification_score(None, None, None, False)
        assert score >= 0.0

    @pytest.mark.parametrize("tier,min_score,max_score", [
        ("A", 0.85, 1.0),
        ("B", 0.70, 0.849),
        ("C", 0.55, 0.699),
        ("D", 0.0, 0.549),
    ])
    def test_tier_boundaries(self, tier, min_score, max_score):
        """Verifica que os limites de tier estão corretos."""
        assert _score_to_tier(min_score) == tier
        assert _score_to_tier(max_score) == tier


# ── Email Service (mock) ─────────────────────────────────────────────────────

class TestSendEmail:
    """Testa o serviço de email (modo mock quando sem credenciais)."""

    @pytest.mark.asyncio
    async def test_email_mock_sem_credenciais(self):
        """Sem SMTP configurado, deve retornar status SIMULATED."""
        with patch("app.services.notification.settings") as mock_settings:
            mock_settings.smtp_user = ""
            mock_settings.smtp_password = ""

            result = await send_email(
                email="test@empresa.com",
                subject="Teste",
                body="Corpo do email",
                lead_id=1,
                template_name="test",
            )
            assert result["status"] == NotificationStatus.SIMULATED
            assert result["to"] == "test@empresa.com"
            assert result["channel"] == NotificationChannel.EMAIL


# ── WhatsApp Service (mock) ──────────────────────────────────────────────────

class TestSendWhatsApp:
    """Testa o serviço de WhatsApp (modo mock quando sem credenciais)."""

    @pytest.mark.asyncio
    async def test_whatsapp_mock_sem_credenciais(self):
        """Sem Twilio configurado, deve retornar status SIMULATED."""
        with patch("app.services.notification.settings") as mock_settings:
            mock_settings.twilio_account_sid = ""
            mock_settings.twilio_auth_token = ""

            result = await send_whatsapp(
                phone="+5511999999999",
                message="Olá, teste!",
                lead_id=1,
                template_name="test_wa",
            )
            assert result["status"] == NotificationStatus.SIMULATED
            assert result["channel"] == NotificationChannel.WHATSAPP

    @pytest.mark.asyncio
    async def test_whatsapp_normaliza_telefone(self):
        """Deve normalizar números sem +55."""
        with patch("app.services.notification.settings") as mock_settings:
            mock_settings.twilio_account_sid = ""
            mock_settings.twilio_auth_token = ""

            result = await send_whatsapp(
                phone="11999999999",
                message="Teste normalização",
                lead_id=1,
            )
            assert result["status"] == NotificationStatus.SIMULATED
            assert "+55" in result.get("phone", "")


# ── Notify Lead Dispatcher ───────────────────────────────────────────────────

class TestNotifyLead:
    """Testa o dispatcher que roteia para o canal correto."""

    @pytest.mark.asyncio
    async def test_dispatch_email(self):
        with patch("app.services.notification.send_email", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "sent"}
            result = await notify_lead(
                lead_id=1,
                channel=NotificationChannel.EMAIL,
                message="Teste",
                email="test@test.com",
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_whatsapp(self):
        with patch("app.services.notification.send_whatsapp", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "sent"}
            result = await notify_lead(
                lead_id=1,
                channel=NotificationChannel.WHATSAPP,
                message="Teste",
                phone="+5511999999999",
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_whatsapp_sem_phone_falha(self):
        with pytest.raises(ValueError, match="Phone"):
            await notify_lead(
                lead_id=1,
                channel=NotificationChannel.WHATSAPP,
                message="Teste",
                phone=None,
            )

    @pytest.mark.asyncio
    async def test_dispatch_email_sem_email_falha(self):
        with pytest.raises(ValueError, match="Email"):
            await notify_lead(
                lead_id=1,
                channel=NotificationChannel.EMAIL,
                message="Teste",
                email=None,
            )
