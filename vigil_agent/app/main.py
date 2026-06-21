"""
Vigil.AI — Funnel Agent API
============================
FastAPI application para o funil autônomo do Vigil Summit.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import leads, webhooks
from app.api.routes.admin import router as admin_router
from app.api.routes.broadcast import router as broadcast_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.scheduler import start_scheduler, stop_scheduler

# Importa modelos para que o Alembic/SQLAlchemy os reconheça
import app.models.lead          # noqa: F401
import app.models.event         # noqa: F401
import app.models.message_template  # noqa: F401
import app.models.admin_user    # noqa: F401

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Seed inicial ───────────────────────────────────────────────────────────────

async def _seed_initial_data(db_conn):
    """Cria admin padrão, evento padrão e templates iniciais se não existirem."""
    from sqlalchemy import text, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import AsyncSessionLocal
    from app.models.admin_user import AdminUser
    from app.models.event import Event, EventStatus
    from app.models.message_template import MessageTemplate, TemplatePhase, TemplateChannel
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async with AsyncSessionLocal() as db:
        # Admin padrão
        result = await db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(AdminUser).where(
                AdminUser.username == settings.admin_default_user
            )
        )
        if not result.scalar_one_or_none():
            admin = AdminUser(
                username=settings.admin_default_user,
                hashed_password=pwd_context.hash(settings.admin_default_password),
                full_name="Administrador Vigil",
                is_active=True,
            )
            db.add(admin)
            logger.info(f"✅ Admin padrão criado: {settings.admin_default_user}")

        # Evento padrão
        result = await db.execute(__import__("sqlalchemy", fromlist=["select"]).select(Event))
        if not result.scalar_one_or_none():
            event = Event(
                name="Vigil Summit — Segurança para a Era da IA",
                event_date="2026-07-15",
                event_time="09:00",
                location="São Paulo, SP — A confirmar",
                description=(
                    "Evento corporativo exclusivo voltado a CISOs, CTOs, diretores de TI "
                    "e gestores de risco. Capacidade: 120 participantes."
                ),
                speakers=["A confirmar"],
                status=EventStatus.ACTIVE,
                post_event_delay_minutes=3,
            )
            db.add(event)
            logger.info("✅ Evento padrão criado")

        # ── Prompts de instrução editáveis pelo admin ──────────────────────────
        # Cada template é um system prompt que o Gemini usa ao gerar mensagens.
        # O admin pode editar o 'body' no painel sem tocar no código.
        # Se já existem, não recria (idempotente).
        tpl_count_result = await db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(MessageTemplate)
        )
        existing_templates = tpl_count_result.scalars().all()

        # Limpa templates antigos (mensagens prontas) e insere prompts de instrução
        has_prompt_templates = any(
            "system prompt" in (t.name or "").lower() or
            "seu trabalho é gerar" in (t.body or "").lower()
            for t in existing_templates
        )

        if not has_prompt_templates:
            # Remove templates antigos se ainda existirem
            for t in existing_templates:
                await db.delete(t)
            await db.flush()

            # Insere prompts de instrução por fase
            prompt_templates = [
                MessageTemplate(
                    name="[Prompt] Confirmação de Inscrição — Aprovado",
                    phase=TemplatePhase.CONFIRMATION,
                    channel=TemplateChannel.EMAIL,
                    subject="Sua vaga no Vigil Summit está confirmada, {PRIMEIRO_NOME}",
                    body=(
                        "Seu trabalho é gerar uma mensagem de confirmação de inscrição para um lead APROVADO no Vigil Summit.\n\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "- Comece pelo primeiro nome (nunca 'Prezado')\n"
                        "- Mencione o cargo/setor do lead explicitamente\n"
                        "- Explique por que o perfil DESTE lead é exatamente o que o Vigil Summit busca\n"
                        "- Inclua data, horário e local de forma natural (não como lista)\n"
                        "- Mencione 1-2 palestrantes confirmados se disponíveis\n"
                        "- Termine com CTA para salvar na agenda\n"
                        "- Tom: caloroso, exclusivo, profissional — como carta de um colega executivo\n"
                        "- Extensão: 200-280 palavras\n"
                        "- PROIBIDO: bullets, listas, linguagem corporativa vazia, saudações genéricas"
                    ),
                    sequence_order=1,
                    is_active=True,
                ),
                MessageTemplate(
                    name="[Prompt] Inscrição em Análise",
                    phase=TemplatePhase.CONFIRMATION,
                    channel=TemplateChannel.EMAIL,
                    subject="Recebemos sua inscrição para o Vigil Summit, {PRIMEIRO_NOME}",
                    body=(
                        "Seu trabalho é gerar uma mensagem honesta informando que a inscrição está EM ANÁLISE.\n\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "- Comece pelo primeiro nome\n"
                        "- Confirme que a inscrição foi RECEBIDA com sucesso\n"
                        "- Explique gentilmente que o evento é exclusivo para líderes executivos e que o perfil está sendo avaliado\n"
                        "- Dê prazo claro: 'Nossa equipe analisará em até 48 horas úteis'\n"
                        "- Tom: transparente, respeitoso, profissional\n"
                        "- Extensão: 150-200 palavras\n"
                        "- PROIBIDO: prometer aprovação, criar expectativa de confirmação definitiva"
                    ),
                    sequence_order=2,
                    is_active=True,
                ),
                MessageTemplate(
                    name="[Prompt] Pré-Evento — Convite Inicial",
                    phase=TemplatePhase.PRE_EVENT,
                    channel=TemplateChannel.BOTH,
                    subject="Vigil Summit 2026 — Convite exclusivo para {CARGO}",
                    body=(
                        "Seu trabalho é gerar um convite personalizado para o Vigil Summit.\n\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "- Use o primeiro nome do lead\n"
                        "- Mencione cargo e setor explicitamente para mostrar que você pesquisou\n"
                        "- Conecte o evento a um problema específico do setor do lead\n"
                        "- Seja direto: peça confirmação com CTA claro ('Responda SIM' ou 'Confirmo minha vaga')\n"
                        "- WhatsApp: 150-250 palavras, conversacional\n"
                        "- Email: 300-400 palavras, mais elaborado\n"
                        "- Tom: consultivo, não vendedor. Você está CONVIDANDO um executivo, não vendendo"
                    ),
                    sequence_order=1,
                    is_active=True,
                ),
                MessageTemplate(
                    name="[Prompt] Pós-Evento — Presente (Agradecimento)",
                    phase=TemplatePhase.POST_EVENT_ATTENDED,
                    channel=TemplateChannel.EMAIL,
                    subject="Foi ótimo te ver no Vigil Summit, {PRIMEIRO_NOME}",
                    body=(
                        "Seu trabalho é gerar um follow-up comercial para quem ESTEVE PRESENTE no Vigil Summit.\n\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "- Referencie algo específico do evento (tema, painel, networking)\n"
                        "- Conecte diretamente com o problema de segurança do lead (use os interesses de security_interests)\n"
                        "- Proponha reunião/demo com valor claro para o cargo/setor do lead\n"
                        "- CTA específico: pergunte sobre disponibilidade para uma conversa de 20-30 min\n"
                        "- Tom: warm, consultivo — você está continuando uma conversa que JÁ aconteceu\n"
                        "- Extensão: 180-250 palavras\n"
                        "- PROIBIDO: linguagem genérica, começar com apenas 'Espero que tenha gostado'"
                    ),
                    sequence_order=1,
                    is_active=True,
                ),
                MessageTemplate(
                    name="[Prompt] Pós-Evento — Ausente (Recuperação)",
                    phase=TemplatePhase.POST_EVENT_NO_SHOW,
                    channel=TemplateChannel.EMAIL,
                    subject="Guardamos algo especial para você, {PRIMEIRO_NOME}",
                    body=(
                        "Seu trabalho é gerar uma mensagem de recuperação para quem NÃO COMPARECEU ao Vigil Summit.\n\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "- NÃO exponha o no-show de forma constrangedora (nunca 'Sentimos sua falta')\n"
                        "- Ofereça valor imediato: resumo exclusivo do evento ou material relevante para o setor\n"
                        "- Use o no-show como oportunidade para uma conversa direta sobre os temas do evento\n"
                        "- Proponha uma reunião de 20-30 min com agenda clara e focada no problema do lead\n"
                        "- Tom: gentil, propositivo, sem culpa nem pressão\n"
                        "- Extensão: 160-220 palavras\n"
                        "- PROIBIDO: linguagem genérica, pressão excessiva, expor o no-show"
                    ),
                    sequence_order=1,
                    is_active=True,
                ),
                MessageTemplate(
                    name="[Prompt] Resposta Inbound — Processamento",
                    phase=TemplatePhase.REPLY,
                    channel=TemplateChannel.BOTH,
                    subject=None,
                    body=(
                        "Seu trabalho é analisar uma resposta de lead e tomar a ação correta.\n\n"
                        "CENÁRIOS:\n"
                        "1. CONFIRMAÇÃO POSITIVA ('sim', 'confirmo', 'vou', 'quero'):\n"
                        "   → Atualize status para CONFIRMED, envie confirmação com detalhes do evento\n"
                        "2. DÚVIDA/PERGUNTA:\n"
                        "   → Responda objetivamente e reforce o convite com informação útil\n"
                        "3. RECUSA DEFINITIVA ('não posso', 'sem interesse'):\n"
                        "   → Agradeça, registre como DECLINED, abra porta para contato futuro\n"
                        "4. RECUSA POR AGENDA:\n"
                        "   → Registre como NO_RESPONSE por ora, sugira follow-up pós-evento\n\n"
                        "REGRAS:\n"
                        "- Tom: sempre respeitoso e consultivo\n"
                        "- Nunca seja insistente com quem recusou definitivamente\n"
                        "- Personalize a resposta usando o cargo/setor do lead"
                    ),
                    sequence_order=1,
                    is_active=True,
                ),
            ]
            for tpl in prompt_templates:
                db.add(tpl)
            logger.info(f"✅ {len(prompt_templates)} prompts de instrução criados no banco (editáveis pelo admin)")

        logger.info("✅ Seed concluído — mensagens personalizadas via Gemini ativas")

        await db.commit()




# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown do servidor."""
    logger.info("🚀 Vigil.AI Funnel Agent iniciando...")

    if settings.app_env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Tabelas verificadas/criadas (modo desenvolvimento)")
        await _seed_initial_data(None)

    # Inicia scheduler de jobs agendados
    start_scheduler()

    logger.info(f"🌍 Ambiente: {settings.app_env}")
    logger.info(f"🔑 Gemini configurado: {'Sim' if settings._gemini_key else 'NÃO (configure API_KEY_AI no .env)'}")
    logger.info(f"📧 SMTP configurado: {'Sim' if settings.smtp_user else 'NÃO (modo simulado)'}")
    logger.info(f"📱 Twilio configurado: {'Sim' if settings.twilio_account_sid else 'NÃO (modo simulado)'}")

    yield

    stop_scheduler()
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
2. **Enriquecimento** — Qualifica automaticamente com dados públicos (Gemini 3.5 Flash)
3. **Pré-Evento** — Confirmação proativa via WhatsApp/Email (meta: >70% show rate)
4. **Pós-Evento** — Follow-up personalizado para agendar reunião comercial

### Autenticação
Endpoints administrativos requerem o header `X-API-Key` ou JWT Bearer token.
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
app.include_router(admin_router, prefix="/api/v1")
app.include_router(broadcast_router, prefix="/api/v1")


# ── Health & Root ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["infra"], summary="Healthcheck")
async def health_check():
    """Verifica saúde da aplicação para load balancers e monitoramento."""
    return JSONResponse(
        content={
            "status": "healthy",
            "environment": settings.app_env,
            "gemini_configured": bool(settings._gemini_key),
            "smtp_configured": bool(settings.smtp_user),
            "twilio_configured": bool(settings.twilio_account_sid),
        }
    )


# ── Static Files ─────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "admin").mkdir(exist_ok=True)

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
