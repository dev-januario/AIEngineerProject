"""
Vigil.AI — Funnel Agent API
============================
FastAPI application para o funil autônomo do Vigil Summit.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import leads, webhooks
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

# Importa modelos para que o Alembic/SQLAlchemy os reconheça
import app.models.lead  # noqa: F401

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown do servidor."""
    logger.info("🚀 Vigil.AI Funnel Agent iniciando...")

    # Cria tabelas se não existirem (dev apenas — em prod usa Alembic)
    if settings.app_env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Tabelas verificadas/criadas (modo desenvolvimento)")

    logger.info(f"🌍 Ambiente: {settings.app_env}")
    logger.info(f"🔑 Anthropic configurado: {'Sim' if settings.anthropic_api_key else 'NÃO (configure .env)'}")

    yield

    logger.info("🛑 Vigil.AI Funnel Agent encerrando...")
    await engine.dispose()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Vigil.AI — Funnel Agent API",
    description="""
## Agente de IA Autônomo para o Vigil Summit

Automatiza o funil completo de leads executivos (CISOs, CTOs, Diretores de TI)
do evento **Vigil Summit — Segurança para a Era da IA**.

### Fases do Funil
1. **Captura** — Recebe leads via formulário/landing page
2. **Enriquecimento** — Qualifica automaticamente com dados públicos (Claude 3.5 Sonnet)
3. **Pré-Evento** — Confirmação proativa via WhatsApp/Email (meta: >70% show rate)
4. **Pós-Evento** — Follow-up personalizado para agendar reunião comercial

### Autenticação
Endpoints administrativos requerem o header `X-API-Key`.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── Middlewares ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://vigil.ai"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(leads.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")


# ── Health & Root ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Vigil.AI Funnel Agent",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
    }


@app.get("/health", tags=["infra"], summary="Healthcheck")
async def health_check():
    """Verifica saúde da aplicação para load balancers e monitoramento."""
    return JSONResponse(
        content={
            "status": "healthy",
            "environment": settings.app_env,
            "anthropic_configured": bool(settings.anthropic_api_key),
        }
    )
