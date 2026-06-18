"""
Webhooks Router
===============
Recebe eventos externos de WhatsApp (Twilio) e Email (SendGrid)
com respostas dos leads para processar no agente.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_funnel_for_lead
from app.db.session import get_db
from app.models.lead import FunnelPhase, Lead, LeadStatus
from app.schemas.lead import LeadWebhookEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _process_inbound_response(lead_email: str, message: str) -> None:
    """Background task: processa resposta inbound de um lead via agente."""
    from app.db.session import AsyncSessionLocal

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
                final_state = await run_funnel_for_lead(lead_dict)
                lead.status = LeadStatus(final_state.get("current_status", lead.status.value))
                lead.funnel_phase = FunnelPhase(final_state.get("current_phase", lead.funnel_phase.value))
                lead.communication_log = final_state.get("communication_log", lead.communication_log)
                lead.last_contacted_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(
                    f"[Webhook] Resposta processada para lead_id={lead.id} | "
                    f"novo status: {lead.status}"
                )
            except Exception as e:
                logger.error(f"[Webhook] Erro ao processar resposta: {e}")
    except Exception as e:
        logger.warning(f"[Webhook] Background task ignorada (DB indisponível): {e}")


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
    Recebe resposta de um lead e dispara processamento pelo agente.
    
    Exemplo de uso:
    ```json
    {
        "lead_email": "carlos@empresa.com",
        "channel": "whatsapp",
        "message": "Confirmo minha presença!"
    }
    ```
    """
    logger.info(
        f"[Webhook] Resposta inbound recebida: "
        f"email={event.lead_email} | channel={event.channel} | "
        f"msg={event.message[:50]}..."
    )

    background_tasks.add_task(
        _process_inbound_response,
        str(event.lead_email),
        event.message,
    )

    return {
        "status": "received",
        "message": "Resposta recebida e em processamento",
        "lead_email": event.lead_email,
    }


@router.post(
    "/twilio/whatsapp",
    summary="Webhook Twilio WhatsApp (produção)",
    include_in_schema=False,
)
async def twilio_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Endpoint para receber webhooks nativos do Twilio."""
    form_data = await request.form()
    phone = str(form_data.get("From", "")).replace("whatsapp:", "")
    message = str(form_data.get("Body", ""))

    logger.info(f"[Twilio] Webhook recebido: phone={phone[:6]}*** | msg={message[:50]}")

    # Em produção: buscar lead pelo phone
    # Por ora: loga e retorna 200 para o Twilio
    return {"status": "ok"}
