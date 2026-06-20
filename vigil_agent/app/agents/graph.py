"""
LangGraph Agent — Vigil Funnel Agent
=====================================
Grafo de estado que orquestra todo o ciclo de vida de um lead,
desde o enriquecimento até o follow-up pós-evento.

Nós do grafo:
  1. enrich_lead      → Enriquece perfil com dados públicos
  2. score_and_route  → Qualifica e decide próxima ação
  3. send_pre_event   → Envia convite/follow-up pré-evento
  4. process_response → Processa resposta do lead
  5. send_post_event  → Follow-up pós-evento
  6. end              → Terminal (lead convertido ou descartado)

Transições:
  capture → enrich_lead → score_and_route
  score_and_route → send_pre_event (ICP ok) | end (ICP baixo)
  send_pre_event → process_response → send_pre_event (follow-up)
                                    → end (confirmado/recusado)
  [event day] → send_post_event → end
"""

import logging
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

import google.generativeai as genai
from langgraph.graph import END, START, StateGraph

from app.agents.prompts import (
    ENRICHMENT_PROMPT,
    POST_EVENT_ATTENDED_PROMPT,
    POST_EVENT_NO_SHOW_PROMPT,
    PRE_EVENT_FOLLOWUP_PROMPT,
    PRE_EVENT_INITIAL_PROMPT,
    PRE_EVENT_RESPONSE_PROMPT,
    SYSTEM_BASE,
    format_enrichment_context,
    format_lead_context,
)
from app.core.config import settings
from app.services.enrichment import enrich_lead_profile
from app.services.notification import (
    NotificationChannel,
    notify_lead,
)

logger = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """Estado compartilhado entre todos os nós do grafo."""
    # Lead data
    lead_id: int
    lead_email: str
    lead_name: str
    lead_phone: str | None
    lead_role: str | None
    lead_company: str | None
    lead_company_size: str | None
    lead_sector: str | None
    lead_linkedin: str | None

    # Enrichment
    enrichment_data: dict[str, Any] | None
    qualification_score: float | None
    fits_icp: bool

    # Funnel state
    current_phase: str  # capture | enrichment | pre_event | post_event | closed
    current_status: str  # new | enriched | contacted | confirmed | attended | no_show | ...
    contact_attempts: int
    communication_log: list[dict]

    # Inbound response (when processing lead reply)
    inbound_message: str | None

    # Post-event
    attended: bool | None
    event_notes: str | None

    # Agent output
    last_action: str
    error: str | None


# ── Gemini Client ─────────────────────────────────────────────────────────────

def _configure_gemini() -> None:
    genai.configure(api_key=settings._gemini_key)


async def _get_phase_system_prompt(phase: str, fallback: str) -> str:
    """
    Busca o system prompt para uma fase do funil no banco de dados.

    O admin pode editar o 'body' do template no painel administrativo
    para customizar o comportamento da IA sem tocar no código.

    Se não houver template ativo para a fase informada, usa o prompt
    hardcoded de prompts.py como fallback seguro.

    Args:
        phase: Valor do ENUM TemplatePhase (ex: 'confirmation', 'post_event_attended')
        fallback: Prompt padrão de prompts.py a usar se o banco não tiver registro

    Returns:
        String do system prompt a usar como instrução para o Gemini
    """
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.message_template import MessageTemplate
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MessageTemplate).where(
                    MessageTemplate.phase == phase,
                    MessageTemplate.is_active == True,
                ).order_by(MessageTemplate.sequence_order).limit(1)
            )
            tpl = result.scalar_one_or_none()
            if tpl and tpl.body and len(tpl.body.strip()) > 20:
                logger.info(f"[Gemini] Usando system prompt do banco para phase='{phase}' (id={tpl.id})")
                return tpl.body.strip()
    except Exception as e:
        logger.warning(f"[Gemini] Não foi possível buscar template do banco para phase='{phase}': {e}")

    logger.debug(f"[Gemini] Usando prompt hardcoded para phase='{phase}'")
    return fallback


async def _call_gemini(system: str, user_message: str) -> str:
    """Wrapper para chamada assíncrona ao Gemini 2.5 Flash."""
    _configure_gemini()
    model = genai.GenerativeModel(
        model_name="gemini-3.5-flash",
        system_instruction=f"{SYSTEM_BASE}\n\n{system}",
    )
    try:
        response = await model.generate_content_async(user_message)
        return response.text
    except Exception as e:
        logger.error(f"[Gemini] Erro na chamada: {e}")
        raise


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def node_enrich_lead(state: AgentState) -> AgentState:
    """
    Nó 1: Enriquece o perfil do lead com dados públicos.
    Chama o enrichment service e atualiza o estado com os dados enriquecidos.
    """
    logger.info(f"[Agent] Enriquecendo lead_id={state['lead_id']} ({state['lead_email']})")

    try:
        enrichment = await enrich_lead_profile(
            email=state["lead_email"],
            name=state["lead_name"],
            company=state["lead_company"],
            role=state["lead_role"],
            company_size=state["lead_company_size"],
            sector=state["lead_sector"],
            linkedin_url=state["lead_linkedin"],
        )

        score = enrichment["qualification"]["score"]
        fits_icp = enrichment["qualification"]["fits_icp"]

        logger.info(
            f"[Agent] Enriquecimento concluído: score={score:.2f}, fits_icp={fits_icp}"
        )

        return {
            **state,
            "enrichment_data": enrichment,
            "qualification_score": score,
            "fits_icp": fits_icp,
            "current_phase": "enrichment",
            "current_status": "enriched",
            "last_action": f"Enriquecimento concluído. Score: {score:.2f}",
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent] Erro no enriquecimento: {e}")
        return {
            **state,
            "error": str(e),
            "last_action": "Erro no enriquecimento",
        }


async def node_score_and_route(state: AgentState) -> AgentState:
    """
    Nó 2: Avalia o score e decide o próximo passo.
    Leads fora do ICP (score < 0.60) são arquivados.
    """
    score = state.get("qualification_score", 0.0)
    fits_icp = state.get("fits_icp", False)

    logger.info(
        f"[Agent] Roteando lead_id={state['lead_id']}: "
        f"score={score:.2f}, fits_icp={fits_icp}"
    )

    if fits_icp:
        return {
            **state,
            "current_phase": "pre_event",
            "last_action": f"Lead qualificado (score={score:.2f}). Avançando para contato.",
            "error": None,
        }
    else:
        return {
            **state,
            "current_phase": "closed",
            "current_status": "out_of_icp",
            "last_action": f"Lead fora do ICP (score={score:.2f}). Arquivado.",
            "error": None,
        }


async def node_send_pre_event(state: AgentState) -> AgentState:
    """
    Nó 3: Envia mensagem de engajamento pré-evento.
    Lógica: convite inicial → follow-up 1 → follow-up 2 → encerrar
    """
    attempts = state.get("contact_attempts", 0)
    lead_id = state["lead_id"]

    if attempts >= 3:
        logger.info(f"[Agent] Máximo de tentativas atingido para lead_id={lead_id}")
        return {
            **state,
            "current_status": "no_response",
            "current_phase": "closed",
            "last_action": "Máximo de 3 tentativas de contato atingido.",
        }

    # Formatar contexto para o prompt
    lead_ctx = format_lead_context({
        "name": state["lead_name"],
        "email": state["lead_email"],
        "phone": state["lead_phone"],
        "role": state["lead_role"],
        "company": state["lead_company"],
        "company_size": state["lead_company_size"],
        "sector": state["lead_sector"],
        "linkedin_url": state["lead_linkedin"],
        "status": state["current_status"],
        "funnel_phase": state["current_phase"],
        "qualification_score": state["qualification_score"],
    })

    enrichment_ctx = format_enrichment_context(state.get("enrichment_data") or {})
    hooks = (state.get("enrichment_data") or {}).get("personalization_hooks", {})

    # Determinar canal preferencial
    preferred_channel = "whatsapp" if state["lead_phone"] else "email"

    if attempts == 0:
        # Convite inicial: Claude gera mensagem personalizada
        prompt = PRE_EVENT_INITIAL_PROMPT.format(
            lead_context=lead_ctx,
            enrichment_context=enrichment_ctx,
            sector=state["lead_sector"] or "tecnologia",
            preferred_channel=preferred_channel,
        )
        template_name = "initial_invite"
    else:
        # Follow-up: usa template renderizado
        contact_history = "\n".join(
            f"- {log.get('sent_at', '')[:10]}: {log.get('message_preview', '')}"
            for log in state.get("communication_log", [])
        )
        prompt = PRE_EVENT_FOLLOWUP_PROMPT.format(
            lead_context=lead_ctx,
            days_since_contact=7 * attempts,
            contact_history=contact_history or "Nenhuma resposta anterior.",
            attempt_number=attempts + 1,
        )
        template_name = f"follow_up_{attempts}"

    try:
        # Gera mensagem personalizada com Gemini
        generated_message = await _call_gemini(system=prompt, user_message="Gere a mensagem agora.")

        # Envia pelo canal preferencial
        if preferred_channel == "whatsapp" and state["lead_phone"]:
            notification_result = await notify_lead(
                lead_id=lead_id,
                channel=NotificationChannel.WHATSAPP,
                message=generated_message,
                phone=state["lead_phone"],
                template_name=template_name,
            )
        else:
            notification_result = await notify_lead(
                lead_id=lead_id,
                channel=NotificationChannel.EMAIL,
                message=generated_message,
                subject="Vigil Summit — Sua presença faz a diferença",
                email=state["lead_email"],
                template_name=template_name,
            )

        # Atualiza log de comunicação
        comm_log = list(state.get("communication_log", []))
        comm_log.append(notification_result)

        return {
            **state,
            "contact_attempts": attempts + 1,
            "current_status": "contacted",
            "communication_log": comm_log,
            "last_action": f"Mensagem enviada via {preferred_channel} (tentativa {attempts + 1})",
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent] Erro no envio pré-evento: {e}")
        return {**state, "error": str(e), "last_action": "Erro no envio de mensagem"}


async def node_process_response(state: AgentState) -> AgentState:
    """
    Nó 4: Processa resposta inbound do lead.
    Usa Claude para interpretar a intenção e atualizar o status.
    """
    inbound = state.get("inbound_message", "")
    lead_id = state["lead_id"]

    if not inbound:
        return {**state, "last_action": "Nenhuma mensagem inbound para processar"}

    logger.info(f"[Agent] Processando resposta do lead_id={lead_id}: {inbound[:50]}...")

    lead_ctx = format_lead_context({
        "name": state["lead_name"],
        "email": state["lead_email"],
        "role": state["lead_role"],
        "company": state["lead_company"],
        "sector": state["lead_sector"],
        "status": state["current_status"],
        "funnel_phase": state["current_phase"],
        "qualification_score": state["qualification_score"],
    })

    prompt_base = await _get_phase_system_prompt(
        phase="reply",
        fallback=PRE_EVENT_RESPONSE_PROMPT.format(
            lead_response=inbound,
            lead_context=lead_ctx,
        ),
    )
    # Se veio do banco (sem {lead_response}), injeta a resposta no user_message
    prompt = prompt_base if "{lead_response}" not in prompt_base else PRE_EVENT_RESPONSE_PROMPT.format(
        lead_response=inbound,
        lead_context=lead_ctx,
    )

    try:
        analysis = await _call_gemini(
            system=prompt,
            user_message=f'Analise a resposta e determine a intenção: "{inbound}"',
        )

        # Interpretação heurística simples + análise do Claude
        inbound_lower = inbound.lower()
        if any(w in inbound_lower for w in ["sim", "confirmo", "vou", "quero", "ok", "aceito"]):
            new_status = "confirmed"
            new_phase = "pre_event"
            action = "Lead CONFIRMADO para o evento"
        elif any(w in inbound_lower for w in ["não", "nao", "impossível", "sem interesse", "cancelar"]):
            new_status = "declined"
            new_phase = "closed"
            action = "Lead RECUSOU o convite"
        else:
            new_status = "contacted"
            new_phase = "pre_event"
            action = "Resposta recebida — aguardando nova mensagem"

        # Gera resposta personalizada se necessário
        if new_status not in ["declined", "confirmed"]:
            response_msg = analysis
            notification_result = await notify_lead(
                lead_id=lead_id,
                channel=NotificationChannel.EMAIL,
                message=response_msg,
                subject="Re: Vigil Summit",
                email=state["lead_email"],
                template_name="response_handler",
            )
            comm_log = list(state.get("communication_log", []))
            comm_log.append(notification_result)
        else:
            comm_log = state.get("communication_log", [])

        return {
            **state,
            "current_status": new_status,
            "current_phase": new_phase,
            "communication_log": comm_log,
            "inbound_message": None,
            "last_action": action,
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent] Erro ao processar resposta: {e}")
        return {**state, "error": str(e), "last_action": "Erro ao processar resposta"}


async def node_send_post_event(state: AgentState) -> AgentState:
    """
    Nó 5: Follow-up pós-evento.
    Diferencia entre presentes e ausentes para personalizar a abordagem.
    """
    lead_id = state["lead_id"]
    attended = state.get("attended", False)
    event_notes = state.get("event_notes") or "Participação no Vigil Summit"

    logger.info(
        f"[Agent] Follow-up pós-evento para lead_id={lead_id} | attended={attended}"
    )

    lead_ctx = format_lead_context({
        "name": state["lead_name"],
        "email": state["lead_email"],
        "role": state["lead_role"],
        "company": state["lead_company"],
        "sector": state["lead_sector"],
        "status": state["current_status"],
        "funnel_phase": state["current_phase"],
        "qualification_score": state["qualification_score"],
    })

    first_name = state["lead_name"].split()[0] if state["lead_name"] else "Participante"

    if attended:
        prompt = await _get_phase_system_prompt(
            phase="post_event_attended",
            fallback=POST_EVENT_ATTENDED_PROMPT.format(
                lead_context=lead_ctx,
                event_notes=event_notes,
            ),
        )
        template_name = "post_event_attended"
        subject = f"{first_name}, foi ótimo ter você no Vigil Summit! 🤝"
    else:
        prompt = await _get_phase_system_prompt(
            phase="post_event_no_show",
            fallback=POST_EVENT_NO_SHOW_PROMPT.format(lead_context=lead_ctx),
        )
        template_name = "post_event_no_show"
        subject = f"{first_name}, trouxemos algo especial para você — Vigil Summit"

    try:
        generated_message = await _call_gemini(
            system=prompt,
            user_message="Gere a mensagem de follow-up pós-evento agora. Seja altamente personalizado, consultivo e direto ao ponto.",
        )

        notification_result = await notify_lead(
            lead_id=lead_id,
            channel=NotificationChannel.EMAIL,
            message=generated_message,
            subject=subject,
            email=state["lead_email"],
            template_name=template_name,
        )

        comm_log = list(state.get("communication_log", []))
        comm_log.append(notification_result)

        return {
            **state,
            "current_phase": "post_event",
            "current_status": "followed_up",
            "communication_log": comm_log,
            "last_action": f"Follow-up pós-evento enviado (attended={attended})",
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent] Erro no follow-up pós-evento: {e}")
        return {**state, "error": str(e), "last_action": "Erro no follow-up pós-evento"}


# ── Routing Functions ─────────────────────────────────────────────────────────

def route_after_scoring(state: AgentState) -> Literal["send_pre_event", "end"]:
    if state.get("fits_icp") and state.get("current_phase") != "closed":
        return "send_pre_event"
    return END


def route_after_response(state: AgentState) -> Literal["send_pre_event", "send_post_event", "end"]:
    status = state.get("current_status", "")
    phase = state.get("current_phase", "")

    if status in ["declined", "no_response"] or phase == "closed":
        return END
    if status == "confirmed":
        return END  # Aguarda evento para pós-evento
    return "send_pre_event"  # Mais follow-up


def route_after_pre_event(state: AgentState) -> Literal["process_response", "end"]:
    status = state.get("current_status", "")
    if state.get("inbound_message"):
        return "process_response"
    if status in ["no_response", "declined"] or state.get("contact_attempts", 0) >= 3:
        return END
    return END  # Aguarda resposta externa (via webhook)


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_funnel_graph() -> StateGraph:
    """
    Constrói e compila o grafo LangGraph do funil da Vigil.AI.
    """
    graph = StateGraph(AgentState)

    # Adiciona nós
    graph.add_node("enrich_lead", node_enrich_lead)
    graph.add_node("score_and_route", node_score_and_route)
    graph.add_node("send_pre_event", node_send_pre_event)
    graph.add_node("process_response", node_process_response)
    graph.add_node("send_post_event", node_send_post_event)

    # Fluxo principal
    graph.add_edge(START, "enrich_lead")
    graph.add_edge("enrich_lead", "score_and_route")

    # Roteamento condicional pós-scoring
    graph.add_conditional_edges(
        "score_and_route",
        route_after_scoring,
        {"send_pre_event": "send_pre_event", END: END},
    )

    # Pós pré-evento
    graph.add_conditional_edges(
        "send_pre_event",
        route_after_pre_event,
        {"process_response": "process_response", END: END},
    )

    # Pós processamento de resposta
    graph.add_conditional_edges(
        "process_response",
        route_after_response,
        {
            "send_pre_event": "send_pre_event",
            "send_post_event": "send_post_event",
            END: END,
        },
    )

    graph.add_edge("send_post_event", END)

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

# Instância compilada do grafo (reutilizável)
_compiled_graph = None


def get_funnel_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_funnel_graph()
    return _compiled_graph


async def run_funnel_for_lead(lead: dict) -> AgentState:
    """
    Ponto de entrada principal para processar um lead pelo funil.

    Args:
        lead: Dicionário com dados do lead (vem do modelo Lead do PostgreSQL)

    Returns:
        Estado final do agente após processamento.
    """
    graph = get_funnel_graph()

    initial_state: AgentState = {
        "lead_id": lead["id"],
        "lead_email": lead["email"],
        "lead_name": lead["name"],
        "lead_phone": lead.get("phone"),
        "lead_role": lead.get("role"),
        "lead_company": lead.get("company"),
        "lead_company_size": lead.get("company_size"),
        "lead_sector": lead.get("sector"),
        "lead_linkedin": lead.get("linkedin_url"),
        "enrichment_data": lead.get("enrichment_data"),
        "qualification_score": lead.get("qualification_score"),
        "fits_icp": False,
        "current_phase": lead.get("funnel_phase", "capture"),
        "current_status": lead.get("status", "new"),
        "contact_attempts": lead.get("contact_attempts", 0),
        "communication_log": lead.get("communication_log") or [],
        "inbound_message": lead.get("inbound_message"),
        "attended": lead.get("attended"),
        "event_notes": lead.get("event_notes"),
        "last_action": "Iniciando funil",
        "error": None,
    }

    logger.info(f"[Agent] Iniciando funil para lead_id={lead['id']} ({lead['email']})")
    final_state = await graph.ainvoke(initial_state)
    logger.info(
        f"[Agent] Funil concluído para lead_id={lead['id']}: "
        f"status={final_state.get('current_status')} | "
        f"action={final_state.get('last_action')}"
    )
    return final_state


async def run_post_event_for_lead(lead: dict, attended: bool, event_notes: str = "") -> AgentState:
    """
    Ponto de entrada para o fluxo pós-evento de um lead específico.
    """
    graph = get_funnel_graph()

    state: AgentState = {
        "lead_id": lead["id"],
        "lead_email": lead["email"],
        "lead_name": lead["name"],
        "lead_phone": lead.get("phone"),
        "lead_role": lead.get("role"),
        "lead_company": lead.get("company"),
        "lead_company_size": lead.get("company_size"),
        "lead_sector": lead.get("sector"),
        "lead_linkedin": lead.get("linkedin_url"),
        "enrichment_data": lead.get("enrichment_data"),
        "qualification_score": lead.get("qualification_score"),
        "fits_icp": True,
        "current_phase": "post_event",
        "current_status": "attended" if attended else "no_show",
        "contact_attempts": lead.get("contact_attempts", 0),
        "communication_log": lead.get("communication_log") or [],
        "inbound_message": None,
        "attended": attended,
        "event_notes": event_notes,
        "last_action": "Iniciando follow-up pós-evento",
        "error": None,
    }

    # Executa apenas o nó de pós-evento diretamente
    return await node_send_post_event(state)
