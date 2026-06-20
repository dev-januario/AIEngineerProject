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
from email.utils import make_msgid

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


MESES_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]


def format_date_pt(date_str: str | None, time_str: str | None = None) -> str:
    """
    Converte '2026-07-15' + '09:00' → '15 de julho de 2026 às 09h00'.
    Aceita formato ISO (YYYY-MM-DD) ou strings livres.
    """
    if not date_str:
        return "A confirmar"
    try:
        parts = date_str.strip().split("-")
        if len(parts) == 3:
            dia, mes_num, ano = int(parts[2]), int(parts[1]), parts[0]
            mes_nome = MESES_PT[mes_num]
            data_formatada = f"{dia} de {mes_nome} de {ano}"
            if time_str:
                hora = time_str.strip().replace(":", "h")
                return f"{data_formatada} às {hora}"
            return data_formatada
    except Exception:
        pass
    return date_str  # fallback: retorna como veio


def build_template_vars(
    lead: dict,
    event: dict | None = None,
    days_remaining: int | None = None,
) -> dict:
    """Constrói o dicionário de variáveis para substituição no template."""
    first_name = (lead.get("name") or "").split()[0] if lead.get("name") else "Participante"
    speakers = event.get("speakers") or [] if event else []
    speakers_str = "\n- ".join(speakers) if speakers else "A confirmar"

    raw_date  = event.get("event_date")  if event else None
    raw_time  = event.get("event_time")  if event else None
    data_ptbr = format_date_pt(raw_date)   # só a data, sem horário
    hora_ptbr = (raw_time or "A confirmar").replace(":", "h") if raw_time else "A confirmar"

    # Dias restantes para o evento
    if days_remaining is not None:
        dias_str = f"{days_remaining} dia{'s' if days_remaining != 1 else ''}"
    else:
        dias_str = "em breve"

    return {
        "NOME":              lead.get("name") or "Participante",
        "PRIMEIRO_NOME":     first_name,
        "CARGO":             lead.get("role") or "Executivo",
        "EMPRESA":           lead.get("company") or "sua empresa",
        "DATA_EVENTO":       data_ptbr,
        "HORA_EVENTO":       hora_ptbr,
        "LOCAL_EVENTO":      event.get("location") or "A confirmar" if event else "A confirmar",
        "NOME_EVENTO":       event.get("name") or "Vigil Summit" if event else "Vigil Summit",
        "PALESTRANTES":      f"\n- {speakers_str}" if speakers else "A confirmar",
        "DIAS_RESTANTES":    dias_str,
        "NOME_ACOMPANHANTE": lead.get("companion_email") or "seu acompanhante",
        "LINK_INSCRICAO":    "https://vigil.ai/inscricao",  # pode ser configurado futuramente
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
        msg["Message-ID"] = make_msgid(domain="vigilai.com")
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
        import requests
        import urllib3
        from twilio.rest import Client as TwilioClient  # type: ignore
        from twilio.http.http_client import TwilioHttpClient

        # Workaround para redes corporativas com proxy SSL (ex.: Luizalabs).
        # A conexão é feita via HTTPS — apenas a verificação da cadeia de
        # certificados é ignorada (necessário quando há um proxy SSL intermediário).
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = False
        http_client = TwilioHttpClient(pool_connections=True)
        http_client.session = session

        client = TwilioClient(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            http_client=http_client,
        )
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
