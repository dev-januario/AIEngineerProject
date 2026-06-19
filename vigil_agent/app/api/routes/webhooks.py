"""
Webhooks Router
===============
Recebe eventos externos de WhatsApp (Twilio) e Email (SendGrid Inbound Parse)
com respostas dos leads e dispara o agente para processar e responder.

Endpoints:
  POST /api/v1/webhooks/inbound           — genérico (interno / testes)
  POST /api/v1/webhooks/twilio/whatsapp   — Twilio WhatsApp inbound
  POST /api/v1/webhooks/sendgrid/inbound  — SendGrid Inbound Parse (email replies)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_funnel_for_lead
from app.db.session import AsyncSessionLocal
from app.models.lead import FunnelPhase, Lead, LeadStatus
from app.schemas.lead import LeadWebhookEvent
from app.services.notification import NotificationChannel, notify_lead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Core: Processa e responde a uma mensagem inbound ──────────────────────────

async def _process_and_reply(
    lead_email: str,
    message: str,
    reply_channel: NotificationChannel,
    phone: str | None = None,
) -> None:
    """
    Background task:
      1. Busca o lead pelo email
      2. Passa a mensagem pelo agente de IA (node_process_response)
      3. Envia a resposta gerada pela IA de volta pelo mesmo canal
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.email == lead_email))
            lead = result.scalar_one_or_none()
            if not lead:
                logger.warning(f"[Webhook] Lead não encontrado para email: {lead_email}")
                return

            lead_dict = {
                "id": lead.id,
                "email": lead.email,
                "name": lead.name,
                "phone": lead.phone,
                "role": lead.role,
                "company": lead.company,
                "company_size": lead.company_size,
                "sector": lead.sector,
                "linkedin_url": lead.linkedin_url,
                "enrichment_data": lead.enrichment_data,
                "qualification_score": lead.qualification_score,
                "status": lead.status.value,
                "funnel_phase": lead.funnel_phase.value,
                "contact_attempts": lead.contact_attempts,
                "communication_log": lead.communication_log or [],
                "inbound_message": message,
            }

            try:
                from app.agents.graph import node_process_response, AgentState
                from app.services.notification import NotificationChannel as NC

                agent_state: AgentState = {
                    "lead_id": lead.id,
                    "lead_email": lead.email,
                    "lead_name": lead.name,
                    "lead_phone": lead.phone,
                    "lead_role": lead.role,
                    "lead_company": lead.company,
                    "lead_company_size": lead.company_size,
                    "lead_sector": lead.sector,
                    "lead_linkedin": lead.linkedin_url,
                    "enrichment_data": lead.enrichment_data or {},
                    "qualification_score": lead.qualification_score or 0.0,
                    "fits_icp": True,
                    "current_phase": lead.funnel_phase.value,
                    "current_status": lead.status.value,
                    "contact_attempts": lead.contact_attempts or 0,
                    "communication_log": lead.communication_log or [],
                    "inbound_message": message,
                    "attended": lead.attended,
                    "event_notes": lead.event_notes,
                    "last_action": "Iniciando processamento de resposta inbound",
                    "error": None,
                }

                final_state = await node_process_response(agent_state)

                # Atualiza status e log no banco
                lead.status     = LeadStatus(final_state.get("current_status", lead.status.value))
                lead.funnel_phase = FunnelPhase(final_state.get("current_phase", lead.funnel_phase.value))
                lead.communication_log = final_state.get("communication_log", lead.communication_log)
                lead.last_contacted_at = datetime.now(timezone.utc)
                await db.commit()

                logger.info(
                    f"[Webhook] Inbound processado lead_id={lead.id} | "
                    f"status: {lead.status} | ação: {final_state.get('last_action')}"
                )

                # O node_process_response já envia a resposta internamente por email.
                # Se o canal foi whatsapp, precisamos reenviar pelo canal correto.
                if reply_channel == NC.WHATSAPP and phone and lead.phone:
                    comm_log = final_state.get("communication_log") or []
                    if comm_log:
                        ai_reply = comm_log[-1].get("message_preview", "")
                        if ai_reply:
                            await notify_lead(
                                lead_id=lead.id,
                                channel=NC.WHATSAPP,
                                message=ai_reply,
                                phone=phone or lead.phone,
                                template_name="inbound_reply_whatsapp",
                            )

            except Exception as e:
                logger.error(f"[Webhook] Erro ao processar inbound: {e}", exc_info=True)

    except Exception as e:
        logger.warning(f"[Webhook] Background task ignorada (DB indisponível): {e}")


# ── Endpoint genérico (interno / testes) ─────────────────────────────────────

@router.post(
    "/inbound",
    summary="Receber resposta de lead via canal externo",
    description="Endpoint genérico para receber mensagens inbound de WhatsApp ou Email.",
)
async def receive_inbound_message(
    event: LeadWebhookEvent,
    background_tasks: BackgroundTasks,
):
    """
    Recebe resposta de um lead e dispara o agente de IA para processar e responder.

    Exemplo:
    ```json
    {
        "lead_email": "carlos@empresa.com",
        "channel": "email",
        "message": "Tenho uma dúvida sobre o formato do evento."
    }
    ```
    """
    logger.info(
        f"[Webhook] Resposta inbound: email={event.lead_email} | "
        f"channel={event.channel} | msg={event.message[:60]}..."
    )

    channel = (
        NotificationChannel.WHATSAPP
        if event.channel == "whatsapp"
        else NotificationChannel.EMAIL
    )

    background_tasks.add_task(
        _process_and_reply,
        str(event.lead_email),
        event.message,
        channel,
    )

    return {
        "status": "received",
        "message": "Mensagem recebida. O agente está processando e responderá em instantes.",
        "lead_email": event.lead_email,
    }


# ── Twilio WhatsApp Webhook ───────────────────────────────────────────────────

@router.post(
    "/twilio/whatsapp",
    summary="Webhook Twilio WhatsApp",
    description="Recebe mensagens inbound do WhatsApp via Twilio e responde automaticamente.",
    include_in_schema=False,
)
async def twilio_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint oficial para webhooks do Twilio WhatsApp.
    Configure em: https://console.twilio.com → Messaging → Sandbox → When a message comes in
    URL: https://seu-dominio.com/api/v1/webhooks/twilio/whatsapp
    """
    form_data = await request.form()
    phone_from = str(form_data.get("From", "")).replace("whatsapp:", "").strip()
    message    = str(form_data.get("Body", "")).strip()

    logger.info(f"[Twilio] Inbound WhatsApp: phone={phone_from[:6]}*** | msg={message[:60]}")

    if not phone_from or not message:
        return {"status": "ignored", "reason": "missing phone or message"}

    # Busca lead pelo telefone em background
    async def _find_lead_by_phone_and_reply():
        try:
            async with AsyncSessionLocal() as db:
                # Normaliza o número para busca
                phone_digits = phone_from.replace("+", "").replace(" ", "").replace("-", "")
                result = await db.execute(select(Lead))
                leads = result.scalars().all()
                # Busca por sufixo (últimos 9 dígitos) para tolerância a prefixo +55
                lead = next(
                    (
                        l for l in leads
                        if l.phone and l.phone.replace("+", "").replace(" ", "").replace("-", "").endswith(phone_digits[-9:])
                    ),
                    None,
                )
                if not lead:
                    logger.warning(f"[Twilio] Lead não encontrado para phone={phone_from[:6]}***")
                    return
                await _process_and_reply(
                    lead_email=lead.email,
                    message=message,
                    reply_channel=NotificationChannel.WHATSAPP,
                    phone=phone_from,
                )
        except Exception as e:
            logger.error(f"[Twilio] Erro ao buscar lead por phone: {e}")

    background_tasks.add_task(_find_lead_by_phone_and_reply)

    # Twilio espera status 200 vazio ou TwiML — retornamos 200 vazio
    from fastapi.responses import Response
    return Response(content="", media_type="text/xml", status_code=200)


# ── SendGrid Inbound Parse (Email Replies) ────────────────────────────────────

@router.post(
    "/sendgrid/inbound",
    summary="SendGrid Inbound Parse — respostas de email",
    description=(
        "Recebe emails inbound via SendGrid Inbound Parse e processa respostas de leads. "
        "Configure o MX do seu domínio para apontar para mx.sendgrid.net e registre "
        "este endpoint em: https://app.sendgrid.com/settings/parse"
    ),
    include_in_schema=False,
)
async def sendgrid_inbound_email(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint para SendGrid Inbound Parse.
    Quando um lead responde ao email, SendGrid faz POST aqui com os dados da mensagem.

    Campos utilizados do multipart form:
      - from: email do remetente (lead)
      - text: corpo do email em texto puro
      - html: corpo do email em HTML (fallback)
    """
    try:
        form_data = await request.form()
        from_field = str(form_data.get("from", "")).strip()
        text_body  = str(form_data.get("text", "")).strip()
        html_body  = str(form_data.get("html", "")).strip()

        # Extrai email do campo "from" (pode vir como "Nome <email@>" ou só "email@")
        if "<" in from_field and ">" in from_field:
            sender_email = from_field.split("<")[-1].replace(">", "").strip()
        else:
            sender_email = from_field

        # Prefer plain text, fallback to HTML stripped
        message = text_body or _strip_html(html_body)

        if not sender_email or not message:
            logger.warning("[SendGrid] Inbound parseado mas sem email/mensagem")
            return {"status": "ignored"}

        logger.info(
            f"[SendGrid] Inbound email de: {sender_email[:20]}... | "
            f"msg={message[:60]}..."
        )

        background_tasks.add_task(
            _process_and_reply,
            sender_email,
            message[:2000],  # limita para não sobrecarregar o agente
            NotificationChannel.EMAIL,
        )

        return {"status": "received", "from": sender_email}

    except Exception as e:
        logger.error(f"[SendGrid] Erro ao processar inbound: {e}")
        return {"status": "error", "detail": str(e)}


def _strip_html(html: str) -> str:
    """Remove tags HTML básicas para extrair texto puro."""
    import re
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:2000]
