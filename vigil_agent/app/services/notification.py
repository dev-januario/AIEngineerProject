"""
Notification Service (SMTP + WhatsApp)
=======================================
Envio de mensagens multicanal com suporte a:
- Email via SMTP (Gmail App Password ou qualquer servidor SMTP)
- WhatsApp via Twilio Sandbox (gratuito para testes)

Templates são buscados do banco de dados e suportam variáveis {{NOME}}, etc.
"""

import logging
import re
from datetime import datetime, timezone
from enum import Enum
from string import Template

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SIMULATED = "simulated"


# ── Renderização de Templates ─────────────────────────────────────────────────

def render_template_vars(body: str, variables: dict) -> str:
    """
    Substitui variáveis {{NOME}}, {{CARGO}}, etc. no template.
    Ignora variáveis desconhecidas com aviso de log.
    """
    def replace_match(match):
        key = match.group(1).strip()
        value = variables.get(key, f"[{key}]")
        return str(value)

    return re.sub(r"\{\{([^}]+)\}\}", replace_match, body)


def build_template_vars(lead: dict, event: dict | None = None) -> dict:
    """Constrói o dicionário de variáveis para substituição no template."""
    first_name = (lead.get("name") or "").split()[0] if lead.get("name") else "Participante"
    speakers = event.get("speakers") or [] if event else []
    speakers_str = "\n- ".join(speakers) if speakers else "A confirmar"

    return {
        "NOME": lead.get("name") or "Participante",
        "PRIMEIRO_NOME": first_name,
        "CARGO": lead.get("role") or "Executivo",
        "EMPRESA": lead.get("company") or "sua empresa",
        "DATA_EVENTO": event.get("event_date") or "A confirmar" if event else "A confirmar",
        "HORA_EVENTO": event.get("event_time") or "A confirmar" if event else "A confirmar",
        "LOCAL_EVENTO": event.get("location") or "A confirmar" if event else "A confirmar",
        "NOME_EVENTO": event.get("name") or "Vigil Summit" if event else "Vigil Summit",
        "PALESTRANTES": f"\n- {speakers_str}" if speakers else "A confirmar",
    }


# ── Canal Email (SMTP) ────────────────────────────────────────────────────────

async def send_email(
    email: str,
    subject: str,
    body: str,
    lead_id: int,
    template_name: str = "custom",
) -> dict:
    """
    Envia email via SMTP (Gmail ou qualquer servidor compatível).
    Cai em modo simulado se credenciais não estão configuradas.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if not settings.smtp_user or not settings.smtp_password:
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

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.email_from_name} <{settings.smtp_user}>"
        msg["To"] = email

        # Texto puro + HTML simples
        text_part = MIMEText(body, "plain", "utf-8")
        html_body = body.replace("\n", "<br>")
        html_part = MIMEText(
            f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto'>{html_body}</body></html>",
            "html",
            "utf-8",
        )
        msg.attach(text_part)
        msg.attach(html_part)

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=True,
            username=settings.smtp_user,
            password=settings.smtp_password,
        )

        logger.info(f"[Email SMTP] ✅ Enviado → to={email} | lead_id={lead_id}")
        return {
            "channel": NotificationChannel.EMAIL,
            "status": NotificationStatus.SENT,
            "sent_at": timestamp,
            "template": template_name,
            "to": email,
            "subject": subject,
            "message_preview": body[:80],
        }

    except Exception as e:
        logger.error(f"[Email SMTP] ❌ Falha para lead_id={lead_id}: {e}")
        return {
            "channel": NotificationChannel.EMAIL,
            "status": NotificationStatus.FAILED,
            "sent_at": timestamp,
            "error": str(e),
        }


# ── Canal WhatsApp (Twilio) ───────────────────────────────────────────────────

async def send_whatsapp(
    phone: str,
    message: str,
    lead_id: int,
    template_name: str = "custom",
) -> dict:
    """
    Envia mensagem WhatsApp via Twilio (Sandbox gratuito para testes).
    Cai em modo simulado se credenciais não configuradas.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Normaliza número: garante prefixo whatsapp:+55...
    phone_normalized = phone.strip().replace(" ", "").replace("-", "")
    if not phone_normalized.startswith("+"):
        phone_normalized = "+55" + phone_normalized.lstrip("0")
    whatsapp_to = f"whatsapp:{phone_normalized}"

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.info(
            f"[WhatsApp MOCK] → lead_id={lead_id} | phone={phone_normalized[:6]}*** | "
            f"template={template_name} | chars={len(message)}"
        )
        logger.debug(f"[WhatsApp MOCK] Mensagem:\n{message}")
        return {
            "channel": NotificationChannel.WHATSAPP,
            "status": NotificationStatus.SIMULATED,
            "sent_at": timestamp,
            "template": template_name,
            "phone": f"{phone_normalized[:6]}****",
            "message_preview": message[:80] + "..." if len(message) > 80 else message,
        }

    try:
        from twilio.rest import Client as TwilioClient  # type: ignore

        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = client.messages.create(
            body=message,
            from_=settings.twilio_whatsapp_from,
            to=whatsapp_to,
        )
        logger.info(f"[WhatsApp] ✅ Enviado → SID={msg.sid} | lead_id={lead_id}")
        return {
            "channel": NotificationChannel.WHATSAPP,
            "status": NotificationStatus.SENT,
            "sent_at": timestamp,
            "template": template_name,
            "sid": msg.sid,
            "message_preview": message[:80],
        }

    except Exception as e:
        logger.error(f"[WhatsApp] ❌ Falha para lead_id={lead_id}: {e}")
        return {
            "channel": NotificationChannel.WHATSAPP,
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
    """Dispatcher principal: roteia para o canal correto."""
    if channel == NotificationChannel.WHATSAPP:
        if not phone:
            raise ValueError("Phone é obrigatório para envio via WhatsApp")
        return await send_whatsapp(phone, message, lead_id, template_name)

    elif channel == NotificationChannel.EMAIL:
        if not email:
            raise ValueError("Email é obrigatório para envio via Email")
        return await send_email(email, subject, message, lead_id, template_name)

    raise ValueError(f"Canal desconhecido: {channel}")
