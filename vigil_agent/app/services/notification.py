"""
Notification Service
====================
Abstração de envio de mensagens multicanal (WhatsApp e Email).

Implementação mock que simula os canais reais com logging detalhado.
Em produção, substituir as funções `_send_*_real` pelas integrações:
- WhatsApp: Twilio API (twilio-python)
- Email: SendGrid (sendgrid-python)

Todas as mensagens usam templates personalizados gerados pelo agente Claude.
"""

import logging
from datetime import datetime, timezone
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SIMULATED = "simulated"


# ── Templates de Mensagem ─────────────────────────────────────────────────────

PRE_EVENT_TEMPLATES = {
    "initial_invite": """
Olá, {first_name}! 👋

Sou da equipe da Vigil.AI e quero te convidar pessoalmente para o **Vigil Summit — Segurança para a Era da IA**.

Um evento exclusivo para {role_context} que quero destacar para você:
▸ {event_value_prop}
▸ 120 executivos de segurança do Brasil
▸ Formato hands-on com cases reais

📅 Data: [DATA DO EVENTO]
📍 Local: [LOCAL]

Posso confirmar sua vaga? Responda "SIM" para garantir!
""",
    "follow_up_1": """
{first_name}, tudo bem?

Vi que ainda não tive retorno sobre o Vigil Summit. Entendo que a agenda de um {role_context} é intensa! 

Mas dado {primary_pain} que vocês provavelmente enfrentam, acho que vale os 4 horas do evento.

Ainda há vagas. Posso reservar a sua?
""",
    "follow_up_2": """
{first_name}, última mensagem da minha parte!

O Vigil Summit está com as vagas quase esgotadas. 

Se segurança digital é uma prioridade pra você em 2026 — e como {role_context}, aposto que é — esse é o encontro certo.

Responda com "CONFIRMO" para garantir sua vaga VIP. 🔐
""",
    "confirmation_ack": """
✅ Perfeito, {first_name}! Sua presença no Vigil Summit está confirmada!

📋 Salva os detalhes:
📅 [DATA DO EVENTO]  
📍 [LOCAL]
🕘 Check-in a partir das 8h30

Em breve envio mais informações sobre a agenda e os speakers.

Até lá! 🚀
""",
}

POST_EVENT_TEMPLATES = {
    "follow_up_meeting": """
{first_name}, foi um prazer ter você no Vigil Summit!

Ficou na minha cabeça a conversa sobre {primary_pain}. Tenho certeza que o que discutimos tem aplicação direta no cenário da sua empresa.

Que tal uma conversa de 30 minutos para explorar como a Vigil.AI pode ajudar {role_context} a endereçar isso?

📅 Aqui está meu link para agendar: [LINK_CALENDÁRIO]

Abraço,
Equipe Vigil.AI
""",
    "no_show_recovery": """
{first_name}, sentimos sua falta no Vigil Summit!

Sei que imprevistos acontecem. Por isso, preparei um resumo exclusivo dos principais insights do evento para você:

🔐 [Material exclusivo para quem não pôde comparecer]

E como {role_context}, acredito que um bate-papo de 20 minutos sobre {primary_pain} pode ser muito mais valioso do que um evento.

Posso propor um horário?
""",
}


# ── Canal WhatsApp ────────────────────────────────────────────────────────────

async def send_whatsapp(
    phone: str,
    message: str,
    lead_id: int,
    template_name: str = "custom",
) -> dict:
    """
    Envia mensagem WhatsApp via Twilio.
    Em ambiente de desenvolvimento/mock, apenas loga a mensagem.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if not settings.twilio_account_sid or settings.twilio_account_sid.startswith("AC"):
        # Mock mode
        logger.info(
            f"[WhatsApp MOCK] → lead_id={lead_id} | phone={phone[:6]}*** | "
            f"template={template_name} | chars={len(message)}"
        )
        logger.debug(f"[WhatsApp MOCK] Mensagem:\n{message}")

        return {
            "channel": NotificationChannel.WHATSAPP,
            "status": NotificationStatus.SIMULATED,
            "sent_at": timestamp,
            "template": template_name,
            "phone": f"{phone[:4]}****",
            "message_preview": message[:80] + "..." if len(message) > 80 else message,
        }

    # Produção: integração real Twilio
    try:
        from twilio.rest import Client as TwilioClient  # type: ignore

        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = client.messages.create(
            body=message,
            from_=settings.twilio_whatsapp_from,
            to=f"whatsapp:{phone}",
        )
        logger.info(f"[WhatsApp] Enviado → SID={msg.sid} | lead_id={lead_id}")
        return {
            "channel": NotificationChannel.WHATSAPP,
            "status": NotificationStatus.SENT,
            "sent_at": timestamp,
            "template": template_name,
            "sid": msg.sid,
            "message_preview": message[:80],
        }
    except Exception as e:
        logger.error(f"[WhatsApp] Falha no envio para lead_id={lead_id}: {e}")
        return {
            "channel": NotificationChannel.WHATSAPP,
            "status": NotificationStatus.FAILED,
            "sent_at": timestamp,
            "error": str(e),
        }


# ── Canal Email ───────────────────────────────────────────────────────────────

async def send_email(
    email: str,
    subject: str,
    body: str,
    lead_id: int,
    template_name: str = "custom",
) -> dict:
    """
    Envia email via SendGrid.
    Em ambiente de desenvolvimento/mock, apenas loga a mensagem.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if not settings.sendgrid_api_key or settings.sendgrid_api_key.startswith("SG.your"):
        # Mock mode
        logger.info(
            f"[Email MOCK] → lead_id={lead_id} | to={email} | "
            f"subject={subject!r} | template={template_name}"
        )
        logger.debug(f"[Email MOCK] Corpo:\n{body}")

        return {
            "channel": NotificationChannel.EMAIL,
            "status": NotificationStatus.SIMULATED,
            "sent_at": timestamp,
            "template": template_name,
            "to": email,
            "subject": subject,
            "message_preview": body[:80] + "..." if len(body) > 80 else body,
        }

    # Produção: integração real SendGrid
    try:
        import sendgrid  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore

        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        mail = Mail(
            from_email=settings.email_from,
            to_emails=email,
            subject=subject,
            plain_text_content=body,
        )
        response = sg.send(mail)
        logger.info(f"[Email] Enviado → status={response.status_code} | lead_id={lead_id}")
        return {
            "channel": NotificationChannel.EMAIL,
            "status": NotificationStatus.SENT,
            "sent_at": timestamp,
            "template": template_name,
            "to": email,
            "subject": subject,
            "http_status": response.status_code,
        }
    except Exception as e:
        logger.error(f"[Email] Falha no envio para lead_id={lead_id}: {e}")
        return {
            "channel": NotificationChannel.EMAIL,
            "status": NotificationStatus.FAILED,
            "sent_at": timestamp,
            "error": str(e),
        }


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def notify_lead(
    lead_id: int,
    channel: NotificationChannel,
    message: str,
    subject: str = "Vigil Summit — Segurança para a Era da IA",
    phone: str | None = None,
    email: str | None = None,
    template_name: str = "custom",
) -> dict:
    """
    Dispatcher principal: roteia para o canal correto e retorna log de comunicação.
    """
    if channel == NotificationChannel.WHATSAPP:
        if not phone:
            raise ValueError("Phone é obrigatório para envio via WhatsApp")
        return await send_whatsapp(phone, message, lead_id, template_name)

    elif channel == NotificationChannel.EMAIL:
        if not email:
            raise ValueError("Email é obrigatório para envio via Email")
        return await send_email(email, subject, message, lead_id, template_name)

    raise ValueError(f"Canal desconhecido: {channel}")


def render_template(template_key: str, hooks: dict, phase: str = "pre") -> str:
    """Renderiza um template de mensagem com os hooks de personalização do lead."""
    templates = PRE_EVENT_TEMPLATES if phase == "pre" else POST_EVENT_TEMPLATES
    template = templates.get(template_key, "")
    try:
        return template.format(**hooks)
    except KeyError as e:
        logger.warning(f"[Template] Chave ausente no template {template_key!r}: {e}")
        return template
