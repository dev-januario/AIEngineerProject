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

        # Templates iniciais — aditivo: verifica cada fase individualmente
        from sqlalchemy import select as _select

        seed_map = {
            TemplatePhase.CONFIRMATION: MessageTemplate(
                name="Confirmação de Inscrição",
                phase=TemplatePhase.CONFIRMATION,
                channel=TemplateChannel.BOTH,
                subject="✅ Inscrição Confirmada — {{NOME_EVENTO}}",
                body=(
                    "Olá, {{PRIMEIRO_NOME}}! 👋\n\n"
                    "Sua inscrição no {{NOME_EVENTO}} foi confirmada com sucesso!\n\n"
                    "📅 Data: {{DATA_EVENTO}}\n"
                    "🕘 Horário: {{HORA_EVENTO}}\n"
                    "📍 Local: {{LOCAL_EVENTO}}\n\n"
                    "Em breve, você receberá mais informações sobre a agenda e os painelistas.\n\n"
                    "Qualquer dúvida, é só responder essa mensagem.\n\n"
                    "Até lá! 🚀\n"
                    "Equipe Vigil.AI"
                ),
                sequence_order=1,
                is_active=True,
            ),
            TemplatePhase.POST_EVENT_ATTENDED: MessageTemplate(
                name="Pós-Evento — Presente (Agradecimento)",
                phase=TemplatePhase.POST_EVENT_ATTENDED,
                channel=TemplateChannel.BOTH,
                subject="Foi um prazer ter você no {{NOME_EVENTO}}, {{PRIMEIRO_NOME}}! 🌟",
                body=(
                    "{{PRIMEIRO_NOME}}, muito obrigado por estar com a gente no {{NOME_EVENTO}}! 👏❤️‍🔥\n\n"
                    "Foi incrível trocar experiências com profissionais como você, que "
                    "estão na linha de frente da segurança em {{EMPRESA}}.\n\n"
                    "Gostaríamos de continuar essa conversa. Que tal uma reunião de 30 minutos "
                    "para explorar como a Vigil.AI pode apoiar os desafios que debatemos no evento?\n\n"
                    "📅 Agende aqui: [LINK_CALENDÁRIO]\n\n"
                    "Abraço,\n"
                    "Equipe Vigil.AI"
                ),
                sequence_order=1,
                is_active=True,
            ),
            TemplatePhase.POST_EVENT_NO_SHOW: MessageTemplate(
                name="Pós-Evento — Ausente (Conforto)",
                phase=TemplatePhase.POST_EVENT_NO_SHOW,
                channel=TemplateChannel.BOTH,
                subject="Sentimos sua falta no {{NOME_EVENTO}}, {{PRIMEIRO_NOME}}",
                body=(
                    "{{PRIMEIRO_NOME}}, sentimos muito a sua ausência no {{NOME_EVENTO}}. 🙏\n\n"
                    "Sabemos que a agenda de {{CARGO}} na {{EMPRESA}} é corrida e imprevistos acontecem.\n\n"
                    "Os temas debatidos foram muito relevantes e gostaríamos de compartilhar "
                    "os principais insights com você. Posso te enviar o resumo do evento?\n\n"
                    "E se quiser conversar sobre como a Vigil.AI pode ajudar a sua empresa, "
                    "estamos disponíveis para uma breve conversa quando preferir.\n\n"
                    "📅 Agende um horário: [LINK_CALENDÁRIO]\n\n"
                    "Abraço,\n"
                    "Equipe Vigil.AI"
                ),
                sequence_order=1,
                is_active=True,
            ),
            TemplatePhase.POST_EVENT: MessageTemplate(
                name="Follow-up Pós-Evento — Agendamento",
                phase=TemplatePhase.POST_EVENT,
                channel=TemplateChannel.BOTH,
                subject="Foi um prazer ter você no {{NOME_EVENTO}}, {{PRIMEIRO_NOME}}!",
                body=(
                    "{{PRIMEIRO_NOME}}, foi ótimo ter você no {{NOME_EVENTO}}! 🙌\n\n"
                    "Como {{CARGO}} na {{EMPRESA}}, tenho certeza que os temas discutidos "
                    "têm aplicação direta nos seus desafios de segurança.\n\n"
                    "Que tal uma conversa de 30 minutos para explorar como a Vigil.AI "
                    "pode ajudar a sua equipe?\n\n"
                    "📅 Aqui está meu link para agendar: [LINK_CALENDÁRIO]\n\n"
                    "Abraço,\n"
                    "Equipe Vigil.AI"
                ),
                sequence_order=1,
                is_active=True,
            ),
            # ── Templates Pré-Evento: Persona A (Participante simples) ──────────
            TemplatePhase.PRE_EVENT_PARTICIPANT: [
                MessageTemplate(
                    name="Pré-Evento A — 30 dias",
                    phase=TemplatePhase.PRE_EVENT_PARTICIPANT,
                    channel=TemplateChannel.BOTH,
                    days_before_event=30,
                    subject="📅 {{NOME_EVENTO}} está chegando, {{PRIMEIRO_NOME}}!",
                    body=(
                        "{{PRIMEIRO_NOME}}, tudo bem? 👋\n\n"
                        "Faltam {{DIAS_RESTANTES}} para o {{NOME_EVENTO}} e a antecedência vale ouro!\n\n"
                        "📅 Data: {{DATA_EVENTO}}\n"
                        "🕒 Horário: {{HORA_EVENTO}}\n"
                        "📍 Local: {{LOCAL_EVENTO}}\n\n"
                        "Reserve já na sua agenda e prepare-se para um dia de conteúdo e networking com "
                        "os principais líderes de segurança do país.\n\n"
                        "Qualquer dúvida, responda esta mensagem.\n\n"
                        "Até lá! 🚀\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=1, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento A — 15 dias",
                    phase=TemplatePhase.PRE_EVENT_PARTICIPANT,
                    channel=TemplateChannel.BOTH,
                    days_before_event=15,
                    subject="🔥 {{NOME_EVENTO}} — Confira os destaques que esperam por você",
                    body=(
                        "{{PRIMEIRO_NOME}}, em {{DIAS_RESTANTES}} você terá acesso a conteúdo exclusivo!\n\n"
                        "Veja o que acontece no {{NOME_EVENTO}}:\n"
                        "- Palestras com líderes de segurança da informação\n"
                        "- Paineis sobre IA e cibersegurança\n"
                        "- Networking com CISOs, CTOs e Diretores de TI\n\n"
                        "Palestrantes confirmados:\n{{PALESTRANTES}}\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}}\n"
                        "📍 {{LOCAL_EVENTO}}\n\n"
                        "Nos vemos lá! ✌️\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=2, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento A — 7 dias",
                    phase=TemplatePhase.PRE_EVENT_PARTICIPANT,
                    channel=TemplateChannel.BOTH,
                    days_before_event=7,
                    subject="⏳ Falta 1 semana! — {{NOME_EVENTO}}",
                    body=(
                        "{{PRIMEIRO_NOME}}, falta exatamente {{DIAS_RESTANTES}} para o {{NOME_EVENTO}}!\n\n"
                        "Só um lembrete rápido:\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}}\n"
                        "📍 {{LOCAL_EVENTO}}\n\n"
                        "Confirma que está tudo certo para a sua presença?\n"
                        "Responda com 'SIM' e garantimos sua vaga na lista de confirmados. 🔐\n\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=3, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento A — 3 dias",
                    phase=TemplatePhase.PRE_EVENT_PARTICIPANT,
                    channel=TemplateChannel.WHATSAPP,
                    days_before_event=3,
                    subject=None,
                    body=(
                        "{{PRIMEIRO_NOME}}, faltam apenas {{DIAS_RESTANTES}}! 🚀\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}}\n"
                        "📍 {{LOCAL_EVENTO}}\n\n"
                        "Verifique seu transporte e os documentos de acesso. \n"
                        "Qualquer dúvida, responda aqui! 👌"
                    ),
                    sequence_order=4, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento A — 1 dia",
                    phase=TemplatePhase.PRE_EVENT_PARTICIPANT,
                    channel=TemplateChannel.WHATSAPP,
                    days_before_event=1,
                    subject=None,
                    body=(
                        "{{PRIMEIRO_NOME}}, é amanhã! 🎉\n\n"
                        "O {{NOME_EVENTO}} acontece amanhã às {{HORA_EVENTO}}.\n"
                        "📍 {{LOCAL_EVENTO}}\n\n"
                        "Durma bem, chegue cedo e prepare suas perguntas.\n"
                        "Mal podemos esperar para see você! 🙌\n\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=5, is_active=True,
                ),
            ],
            # ── Templates Pré-Evento: Persona B (Com Acompanhante) ────────────
            TemplatePhase.PRE_EVENT_WITH_COMPANION: [
                MessageTemplate(
                    name="Pré-Evento B — 30 dias",
                    phase=TemplatePhase.PRE_EVENT_WITH_COMPANION,
                    channel=TemplateChannel.BOTH,
                    days_before_event=30,
                    subject="📅 {{NOME_EVENTO}} está chegando — você e seu acompanhante",
                    body=(
                        "{{PRIMEIRO_NOME}}, tudo bem? 👋\n\n"
                        "Faltam {{DIAS_RESTANTES}} para o {{NOME_EVENTO}}!\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}}\n"
                        "📍 {{LOCAL_EVENTO}}\n\n"
                        "Lembre-se: seu acompanhante ({{NOME_ACOMPANHANTE}}) precisa realizar "
                        "a inscrição própria para garantir a vaga dele(a). "
                        "Se ainda não fez, dá uma forcinha! 😉\n\n"
                        "Qualquer dúvida, responda esta mensagem.\n\n"
                        "Até lá! 🚀\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=1, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento B — 15 dias",
                    phase=TemplatePhase.PRE_EVENT_WITH_COMPANION,
                    channel=TemplateChannel.BOTH,
                    days_before_event=15,
                    subject="🔥 {{NOME_EVENTO}} em {{DIAS_RESTANTES}} — você e seu convidado(a)!",
                    body=(
                        "{{PRIMEIRO_NOME}}, em {{DIAS_RESTANTES}} a gente se encontra no {{NOME_EVENTO}}!\n\n"
                        "Palestrantes confirmados:\n{{PALESTRANTES}}\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}} | 📍 {{LOCAL_EVENTO}}\n\n"
                        "👥 Lembrete: verifique se {{NOME_ACOMPANHANTE}} já completou a inscrição. "
                        "Sem inscrição confirmada, a entrada pode ser negada na porta.\n\n"
                        "Nos vemos lá! ✌️\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=2, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento B — 7 dias",
                    phase=TemplatePhase.PRE_EVENT_WITH_COMPANION,
                    channel=TemplateChannel.BOTH,
                    days_before_event=7,
                    subject="⏳ 1 semana! — {{NOME_EVENTO}} — Confirme você e seu acompanhante",
                    body=(
                        "{{PRIMEIRO_NOME}}, {{DIAS_RESTANTES}} para o {{NOME_EVENTO}}!\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}} | 📍 {{LOCAL_EVENTO}}\n\n"
                        "Por favor, confirme a presença respondendo 'SIM'.\n"
                        "E não esqueça de perguntar a {{NOME_ACOMPANHANTE}} se já finalizou o cadastro. 👍\n\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=3, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento B — 3 dias",
                    phase=TemplatePhase.PRE_EVENT_WITH_COMPANION,
                    channel=TemplateChannel.WHATSAPP,
                    days_before_event=3,
                    subject=None,
                    body=(
                        "{{PRIMEIRO_NOME}}, apenas {{DIAS_RESTANTES}}! 🚀\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}} | 📍 {{LOCAL_EVENTO}}\n\n"
                        "Lembrete final: {{NOME_ACOMPANHANTE}} está inscrito(a)? 😉 Garanta que sim!"
                    ),
                    sequence_order=4, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento B — 1 dia",
                    phase=TemplatePhase.PRE_EVENT_WITH_COMPANION,
                    channel=TemplateChannel.WHATSAPP,
                    days_before_event=1,
                    subject=None,
                    body=(
                        "{{PRIMEIRO_NOME}}, é amanhã! 🎉\n"
                        "{{NOME_EVENTO}} — {{HORA_EVENTO}} | {{LOCAL_EVENTO}}\n\n"
                        "Você e {{NOME_ACOMPANHANTE}} estão prontos? 🙌 "
                        "Mal podemos esperar para receber vocês!\n\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=5, is_active=True,
                ),
            ],
            # ── Templates Pré-Evento: Persona C (Acompanhante não inscrito) ───
            TemplatePhase.PRE_EVENT_COMPANION_PENDING: [
                MessageTemplate(
                    name="Pré-Evento C — 7 dias",
                    phase=TemplatePhase.PRE_EVENT_COMPANION_PENDING,
                    channel=TemplateChannel.EMAIL,
                    days_before_event=7,
                    subject="⚠️ Sua vaga no {{NOME_EVENTO}} ainda não está garantida",
                    body=(
                        "Olá, {{PRIMEIRO_NOME}}!\n\n"
                        "Você foi convidado(a) para o {{NOME_EVENTO}} e faltam apenas {{DIAS_RESTANTES}}!\n\n"
                        "Sua inscrição ainda não foi concluída. "
                        "Sem ela, sua entrada no evento não estará garantida.\n\n"
                        "👉 Inscreva-se agora: {{LINK_INSCRICAO}}\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}}\n"
                        "📍 {{LOCAL_EVENTO}}\n\n"
                        "Não perca esta oportunidade!\n\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=1, is_active=True,
                ),
                MessageTemplate(
                    name="Pré-Evento C — 3 dias",
                    phase=TemplatePhase.PRE_EVENT_COMPANION_PENDING,
                    channel=TemplateChannel.EMAIL,
                    days_before_event=3,
                    subject="🚨 Última chance! Garanta sua vaga no {{NOME_EVENTO}}",
                    body=(
                        "{{PRIMEIRO_NOME}}, é agora ou nunca! ⏰\n\n"
                        "Faltam apenas {{DIAS_RESTANTES}} para o {{NOME_EVENTO}} "
                        "e sua inscrição ainda está pendente.\n\n"
                        "As vagas são limitadas e podem esgotar a qualquer momento.\n"
                        "👉 Complete sua inscrição agora: {{LINK_INSCRICAO}}\n\n"
                        "📅 {{DATA_EVENTO}} às {{HORA_EVENTO}} | 📍 {{LOCAL_EVENTO}}\n\n"
                        "Não perca!\n"
                        "Equipe Vigil.AI"
                    ),
                    sequence_order=2, is_active=True,
                ),
            ],
        }

        added = 0
        for phase, templates in seed_map.items():
            r = await db.execute(
                _select(MessageTemplate.id)
                .where(MessageTemplate.phase == phase)
                .limit(1)
            )
            if r.scalar_one_or_none() is None:
                if isinstance(templates, list):
                    for tpl in templates:
                        db.add(tpl)
                        added += 1
                else:
                    db.add(templates)
                    added += 1
        if added:
            logger.info(f"✅ {added} template(s) adicionado(s) ao seed")

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
    logger.info(f"🔑 Anthropic configurado: {'Sim' if settings.anthropic_api_key else 'NÃO (configure .env)'}")
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
2. **Enriquecimento** — Qualifica automaticamente com dados públicos (Claude 3.5 Sonnet)
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
            "anthropic_configured": bool(settings.anthropic_api_key),
            "smtp_configured": bool(settings.smtp_user),
            "twilio_configured": bool(settings.twilio_account_sid),
        }
    )


# ── Static Files ─────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "admin").mkdir(exist_ok=True)

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
