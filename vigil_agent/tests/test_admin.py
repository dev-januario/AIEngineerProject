"""
Admin API Tests
================
Testes de integração para os endpoints administrativos (autenticação JWT, leads, qualificação).
"""

import pytest
from httpx import AsyncClient

from app.core.config import settings


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestAdminAuth:
    """Testa autenticação JWT do painel admin."""

    @pytest.mark.asyncio
    async def test_login_sucesso(self, client: AsyncClient):
        """Login com credenciais corretas deve retornar JWT."""
        response = await client.post(
            "/api/v1/admin/auth/login",
            data={
                "username": settings.admin_default_user,
                "password": settings.admin_default_password,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == settings.admin_default_user

    @pytest.mark.asyncio
    async def test_login_senha_errada(self, client: AsyncClient):
        """Login com senha incorreta deve retornar 401."""
        response = await client.post(
            "/api/v1/admin/auth/login",
            data={"username": "admin", "password": "senha_errada_123"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_usuario_inexistente(self, client: AsyncClient):
        """Login com usuário inexistente deve retornar 401."""
        response = await client.post(
            "/api/v1/admin/auth/login",
            data={"username": "usuario_fantasma", "password": "123"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_acesso_sem_token(self, client: AsyncClient):
        """Endpoint protegido sem token deve retornar 401."""
        response = await client.get("/api/v1/admin/leads")
        assert response.status_code == 401


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_admin_token(client: AsyncClient) -> str:
    """Helper: faz login e retorna o token JWT."""
    response = await client.post(
        "/api/v1/admin/auth/login",
        data={
            "username": settings.admin_default_user,
            "password": settings.admin_default_password,
        },
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    """Helper: retorna headers com Authorization Bearer."""
    return {"Authorization": f"Bearer {token}"}


# ── Leads ────────────────────────────────────────────────────────────────────

class TestAdminLeads:
    """Testa endpoints de leads no painel admin."""

    @pytest.mark.asyncio
    async def test_listar_leads(self, client: AsyncClient, sample_lead_payload: dict):
        """Admin deve conseguir listar todos os leads."""
        # Cria um lead
        await client.post("/api/v1/leads/", json={
            **sample_lead_payload,
            "email": "admin.test.list@empresa.com",
        })

        token = await _get_admin_token(client)
        response = await client.get(
            "/api/v1/admin/leads",
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        leads = response.json()
        assert isinstance(leads, list)
        assert len(leads) >= 1

    @pytest.mark.asyncio
    async def test_listar_leads_pending_only(self, client: AsyncClient):
        """Filtro pending_only deve retornar apenas leads em revisão."""
        token = await _get_admin_token(client)

        response = await client.get(
            "/api/v1/admin/leads?pending_only=true",
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        leads = response.json()
        assert isinstance(leads, list)
        # Todos devem ter status pending_review (se houver)
        for lead in leads:
            assert lead["status"] == "pending_review"


# ── Qualify Leads (approve/reject) ───────────────────────────────────────────

class TestAdminQualifyLead:
    """Testa aprovação e rejeição manual de leads."""

    @pytest.mark.asyncio
    async def test_qualificar_lead_nao_existente(self, client: AsyncClient):
        """Tentar qualificar lead inexistente deve retornar 404."""
        token = await _get_admin_token(client)
        response = await client.post(
            "/api/v1/admin/leads/99999/qualify",
            json={"action": "approve"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_qualificar_action_invalida(self, client: AsyncClient, sample_lead_payload: dict):
        """Action diferente de approve/reject deve retornar 422."""
        # Cria lead e força status pending_review
        create_resp = await client.post("/api/v1/leads/", json={
            **sample_lead_payload,
            "email": "qualify.invalid@empresa.com",
        })
        lead_id = create_resp.json()["id"]

        # Atualiza para pending_review via PATCH
        await client.patch(
            f"/api/v1/leads/{lead_id}",
            json={"status": "pending_review"},
            headers={"X-API-Key": settings.vigil_api_key},
        )

        token = await _get_admin_token(client)
        response = await client.post(
            f"/api/v1/admin/leads/{lead_id}/qualify",
            json={"action": "blah"},
            headers=_auth_headers(token),
        )
        # Pode ser 400 ou 422 dependendo do status do lead
        assert response.status_code in (400, 422)


# ── Event ────────────────────────────────────────────────────────────────────

class TestAdminEvent:
    """Testa endpoints de evento no painel admin."""

    @pytest.mark.asyncio
    async def test_obter_evento(self, client: AsyncClient):
        """Deve retornar os dados do evento ativo."""
        token = await _get_admin_token(client)
        response = await client.get(
            "/api/v1/admin/event",
            headers=_auth_headers(token),
        )
        # Pode ser 200 (se existe evento) ou 404 (sem evento no DB de teste)
        assert response.status_code in (200, 404)


# ── Templates ────────────────────────────────────────────────────────────────

class TestAdminTemplates:
    """Testa CRUD de templates de mensagem."""

    @pytest.mark.asyncio
    async def test_listar_templates(self, client: AsyncClient):
        """Deve listar templates (vazio no início)."""
        token = await _get_admin_token(client)
        response = await client.get(
            "/api/v1/admin/templates",
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_criar_template(self, client: AsyncClient):
        """Deve criar um novo template."""
        token = await _get_admin_token(client)
        payload = {
            "name": "Teste Unitário",
            "phase": "confirmation",
            "channel": "EMAIL",
            "subject": "Assunto teste",
            "body": "Corpo do template de teste",
            "sequence_order": 1,
            "is_active": True,
        }
        response = await client.post(
            "/api/v1/admin/templates",
            json=payload,
            headers=_auth_headers(token),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Teste Unitário"
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_atualizar_template(self, client: AsyncClient):
        """Deve atualizar um template existente."""
        token = await _get_admin_token(client)
        headers = _auth_headers(token)

        # Cria
        create_resp = await client.post(
            "/api/v1/admin/templates",
            json={
                "name": "Para Editar",
                "phase": "pre_event",
                "channel": "BOTH",
                "body": "Corpo original",
            },
            headers=headers,
        )
        tpl_id = create_resp.json()["id"]

        # Atualiza
        response = await client.put(
            f"/api/v1/admin/templates/{tpl_id}",
            json={
                "name": "Editado",
                "phase": "pre_event",
                "channel": "BOTH",
                "body": "Corpo editado",
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Editado"
        assert response.json()["body"] == "Corpo editado"

    @pytest.mark.asyncio
    async def test_deletar_template(self, client: AsyncClient):
        """Deve deletar um template existente."""
        token = await _get_admin_token(client)
        headers = _auth_headers(token)

        # Cria
        create_resp = await client.post(
            "/api/v1/admin/templates",
            json={
                "name": "Para Deletar",
                "phase": "confirmation",
                "channel": "EMAIL",
                "body": "Será removido",
            },
            headers=headers,
        )
        tpl_id = create_resp.json()["id"]

        # Deleta
        response = await client.delete(
            f"/api/v1/admin/templates/{tpl_id}",
            headers=headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_deletar_template_inexistente(self, client: AsyncClient):
        """Tentar deletar template que não existe deve retornar 404."""
        token = await _get_admin_token(client)
        response = await client.delete(
            "/api/v1/admin/templates/99999",
            headers=_auth_headers(token),
        )
        assert response.status_code == 404


# ── Scheduler Status ─────────────────────────────────────────────────────────

class TestAdminScheduler:
    """Testa endpoints de status do scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_status(self, client: AsyncClient):
        """Deve retornar status do scheduler."""
        token = await _get_admin_token(client)
        response = await client.get(
            "/api/v1/admin/scheduler/status",
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert "has_scheduled_job" in data
        assert "post_event_next_run" in data


# ── Companion Validation ─────────────────────────────────────────────────────

class TestCompanionValidation:
    """Testa validação de acompanhantes na inscrição."""

    @pytest.mark.asyncio
    async def test_companion_sem_email_falha(self, client: AsyncClient):
        """Acompanhante sem email deve retornar 422."""
        payload = {
            "name": "Test Companion",
            "email": "companion.test@empresa.com",
            "lgpd_consent": True,
            "with_companion": True,
            # Falta companion_email
        }
        response = await client.post("/api/v1/leads/", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_companion_vinculo_pessoal_rejeitado(self, client: AsyncClient):
        """Vínculo pessoal (amigo, cônjuge) deve ser rejeitado."""
        payload = {
            "name": "Test Personal",
            "email": "personal.bond@empresa.com",
            "lgpd_consent": True,
            "with_companion": True,
            "companion_email": "amigo@empresa.com",
            "companion_relationship": "friend",  # Vínculo pessoal
        }
        response = await client.post("/api/v1/leads/", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_companion_vinculo_profissional_aceito(self, client: AsyncClient):
        """Vínculo profissional (partner, director) deve ser aceito."""
        payload = {
            "name": "Test Professional",
            "email": "prof.bond@empresa.com",
            "lgpd_consent": True,
            "with_companion": True,
            "companion_email": "socio@empresa.com",
            "companion_relationship": "partner",
        }
        response = await client.post("/api/v1/leads/", json=payload)
        assert response.status_code == 201


# ── Available Spots ──────────────────────────────────────────────────────────

class TestAvailableSpots:
    """Testa endpoint de vagas disponíveis."""

    @pytest.mark.asyncio
    async def test_spots_retorna_valor(self, client: AsyncClient):
        """GET /leads/spots deve retornar um número de vagas."""
        response = await client.get("/api/v1/leads/spots")
        assert response.status_code == 200
        data = response.json()
        assert "remaining" in data
        assert isinstance(data["remaining"], int)
        assert data["remaining"] >= 0
        assert "capacity" in data
