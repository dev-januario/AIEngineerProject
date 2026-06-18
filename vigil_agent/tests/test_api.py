"""
API Integration Tests
======================
Testes de integração para os endpoints da Vigil.AI Funnel Agent API.
"""

import pytest
from httpx import AsyncClient

from app.core.config import settings


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Vigil.AI Funnel Agent"


# ── Lead Creation ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_lead_success(client: AsyncClient, sample_lead_payload: dict):
    """Lead completo com consentimento LGPD deve ser criado com status 201."""
    response = await client.post("/api/v1/leads/", json=sample_lead_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == sample_lead_payload["email"]
    assert data["name"] == sample_lead_payload["name"]
    assert data["status"] == "new"
    assert data["funnel_phase"] == "capture"
    assert data["lgpd_consent"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_lead_no_lgpd_consent(client: AsyncClient, sample_lead_payload_no_consent: dict):
    """Lead sem consentimento LGPD deve retornar erro 422."""
    response = await client.post("/api/v1/leads/", json=sample_lead_payload_no_consent)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("LGPD" in str(e) for e in errors)


@pytest.mark.asyncio
async def test_create_lead_duplicate_email(client: AsyncClient, sample_lead_payload: dict):
    """Tentar criar lead com email duplicado deve retornar 409."""
    # Primeiro registro
    r1 = await client.post("/api/v1/leads/", json=sample_lead_payload)
    # Segunda tentativa com mesmo email
    duplicate_payload = {**sample_lead_payload, "name": "Outro Nome"}
    r2 = await client.post("/api/v1/leads/", json=duplicate_payload)
    assert r2.status_code == 409
    assert "já existe" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_create_lead_invalid_email(client: AsyncClient):
    """Email inválido deve retornar 422."""
    payload = {
        "name": "Test User",
        "email": "not-an-email",
        "lgpd_consent": True,
    }
    response = await client.post("/api/v1/leads/", json=payload)
    assert response.status_code == 422


# ── Lead Retrieval ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_lead_requires_api_key(client: AsyncClient, sample_lead_payload: dict):
    """GET /leads/ sem API key deve retornar 401."""
    # Cria lead primeiro
    create_resp = await client.post("/api/v1/leads/", json={
        **sample_lead_payload,
        "email": "test.get@empresa.com",
    })
    assert create_resp.status_code == 201
    lead_id = create_resp.json()["id"]

    # Tenta acessar sem API key
    response = await client.get(f"/api/v1/leads/{lead_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_lead_with_api_key(client: AsyncClient, sample_lead_payload: dict):
    """GET /leads/{id} com API key válida deve retornar o lead."""
    unique_payload = {**sample_lead_payload, "email": "test.apikey@empresa.com"}
    create_resp = await client.post("/api/v1/leads/", json=unique_payload)
    assert create_resp.status_code == 201
    lead_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/v1/leads/{lead_id}",
        headers={"X-API-Key": settings.vigil_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == lead_id
    assert data["email"] == unique_payload["email"]


@pytest.mark.asyncio
async def test_get_lead_not_found(client: AsyncClient):
    """GET /leads/99999 deve retornar 404."""
    response = await client.get(
        "/api/v1/leads/99999",
        headers={"X-API-Key": settings.vigil_api_key},
    )
    assert response.status_code == 404


# ── Lead Update ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_lead(client: AsyncClient, sample_lead_payload: dict):
    """PATCH /leads/{id} deve atualizar campos parcialmente."""
    unique_payload = {**sample_lead_payload, "email": "test.update@empresa.com"}
    create_resp = await client.post("/api/v1/leads/", json=unique_payload)
    lead_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"event_notes": "Muito interessado em Zero Trust", "attended": True},
        headers={"X-API-Key": settings.vigil_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["event_notes"] == "Muito interessado em Zero Trust"
    assert data["attended"] is True


# ── Lead Listing ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_leads(client: AsyncClient, sample_lead_payload: dict):
    """GET /leads/ com API key deve retornar lista de leads."""
    # Cria alguns leads
    for i in range(3):
        await client.post("/api/v1/leads/", json={
            **sample_lead_payload,
            "email": f"list.test.{i}@empresa.com",
        })

    response = await client.get(
        "/api/v1/leads/",
        headers={"X-API-Key": settings.vigil_api_key},
    )
    assert response.status_code == 200
    leads = response.json()
    assert isinstance(leads, list)
    assert len(leads) >= 3


# ── Webhooks ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_inbound(client: AsyncClient):
    """POST /webhooks/inbound deve aceitar resposta de lead e retornar 200 imediatamente."""
    payload = {
        "lead_email": "webhook.test@empresa.com",
        "channel": "whatsapp",
        "message": "Confirmo minha presença!",
    }
    response = await client.post("/api/v1/webhooks/inbound", json=payload)
    # O endpoint deve aceitar o evento imediatamente (async background processing)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "received"
    assert data["lead_email"] == "webhook.test@empresa.com"
