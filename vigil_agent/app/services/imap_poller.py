"""
IMAP Inbox Polling Service
===========================
Verifica periodicamente a caixa de entrada do email para processar
respostas de leads (replies ao email enviado pelo sistema).

Como funciona:
  1. Conecta via IMAP SSL ao Gmail (ou qualquer servidor IMAP)
  2. Busca emails não lidos na caixa de entrada (INBOX)
  3. Para cada email, extrai o remetente (lead) e o corpo da mensagem
  4. Chama o agente de IA para processar e responder automaticamente
  5. Marca o email como lido para não processá-lo novamente

Configuração no Gmail:
  - Certifique-se de que IMAP está habilitado em:
    Gmail → Configurações → Ver todas as configurações → Encaminhamento e POP/IMAP → Habilitar IMAP
  - Use as mesmas credenciais do SMTP (App Password)
"""

import asyncio
import email
import imaplib
import logging
import quopri
import re
from email.header import decode_header
from email.policy import default as email_policy

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Helpers de decodificação ─────────────────────────────────────────────────

def _decode_header_value(raw: str | bytes | None) -> str:
    """Decodifica campos de cabeçalho MIME (Subject, From, etc.)."""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        decoded_parts = decode_header(raw.decode("utf-8", errors="replace"))
    else:
        decoded_parts = decode_header(raw)

    parts = []
    for fragment, charset in decoded_parts:
        if isinstance(fragment, bytes):
            charset = charset or "utf-8"
            parts.append(fragment.decode(charset, errors="replace"))
        else:
            parts.append(str(fragment))
    return " ".join(parts)


def _extract_email_address(from_header: str) -> str:
    """Extrai apenas o endereço de email do campo From."""
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", from_header)
    return match.group(0).lower() if match else ""


def _extract_text_body(msg: email.message.Message) -> str:
    """Extrai o corpo em texto puro de uma mensagem MIME."""
    body_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition  = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                payload  = part.get_payload(decode=True)
                charset  = part.get_content_charset() or "utf-8"
                body_parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body_parts.append(payload.decode(charset, errors="replace"))

    full_body = "\n".join(body_parts).strip()

    # Remove o histórico do email (linhas "Em ... escreveu:" e o conteúdo abaixo)
    # para processar apenas a resposta nova do lead
    cleaned = _strip_quoted_reply(full_body)
    return cleaned[:2000]  # limita para não sobrecarregar o agente


def _strip_quoted_reply(text: str) -> str:
    """
    Remove o texto citado de uma resposta de email.
    Suporta padrões Gmail/Outlook em PT-BR e EN.
    """
    patterns = [
        r"Em .+ escreveu:",          # Gmail PT-BR
        r"On .+ wrote:",             # Gmail EN
        r"De: .+",                   # Outlook PT-BR
        r"From: .+",                 # Outlook EN
        r"-{3,}.*Mensagem original", # Separador Outlook PT
        r"-{3,}.*Original [Mm]essage",
        r"_{10,}",                   # Linha de separação ______
    ]
    combined = "|".join(patterns)

    lines = text.splitlines()
    result_lines = []
    for line in lines:
        if re.search(combined, line.strip()):
            break  # para antes do histórico
        result_lines.append(line)

    cleaned = "\n".join(result_lines).strip()
    return cleaned if cleaned else text  # fallback: retorna tudo se não encontrar padrão


# ── Polling via IMAP ─────────────────────────────────────────────────────────

async def poll_inbox_for_replies() -> None:
    """
    Job agendado pelo APScheduler.
    Verifica a caixa de entrada e processa todos os emails não lidos
    que sejam respostas de leads cadastrados.
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.debug("[IMAP] Credenciais não configuradas — polling ignorado")
        return

    logger.info("[IMAP/Debug] 🔍 Verificando caixa de entrada...")
    logger.info(f"[IMAP/Debug] Conta: {settings.smtp_user} | Host: {settings.imap_host}:{settings.imap_port}")

    try:
        replies = await asyncio.to_thread(_fetch_unread_replies)
    except Exception as e:
        logger.error(f"[IMAP/Debug] ❌ Erro ao conectar ao servidor IMAP: {e}")
        return

    if not replies:
        logger.info("[IMAP/Debug] ✔️ Nenhuma resposta nova encontrada neste ciclo")
        return

    logger.info(f"[IMAP/Debug] 📨 {len(replies)} resposta(s) nova(s) encontrada(s):")
    for i, (sender, body) in enumerate(replies):
        logger.info(f"  [{i+1}] De: {sender} | Corpo: {len(body)} chars | Preview: {body[:80]!r}")

    import httpx

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
        for sender_email, message_body in replies:
            if not sender_email or not message_body:
                logger.warning(f"[IMAP/Debug] Ignorado: sender={sender_email!r} | body vazio={not message_body}")
                continue
            logger.info(f"[IMAP/Debug] ➡️ Encaminhando reply de: {sender_email}")
            try:
                resp = await client.post(
                    "/api/v1/webhooks/inbound",
                    json={
                        "lead_email": sender_email,
                        "channel": "email",
                        "message": message_body,
                    },
                )
                if resp.status_code == 200:
                    logger.info(f"[IMAP/Debug] ✅ Reply encaminhado com sucesso para {sender_email}")
                else:
                    logger.warning(f"[IMAP/Debug] ⚠️ Endpoint retornou {resp.status_code}: {resp.text[:150]}")
            except Exception as e:
                logger.error(f"[IMAP/Debug] ❌ Erro ao encaminhar reply de {sender_email}: {e}")


def _fetch_unread_replies() -> list[tuple[str, str]]:
    """
    Operação IMAP síncrona (roda em thread).
    Retorna lista de (sender_email, message_body) para emails não lidos.
    """
    replies = []

    imap = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    try:
        imap.login(settings.smtp_user, settings.smtp_password)
        imap.select("INBOX")

        # Busca emails não lidos (UNSEEN)
        _, message_ids = imap.search(None, "UNSEEN")
        if not message_ids or not message_ids[0]:
            return []

        ids = message_ids[0].split()
        logger.info(f"[IMAP] {len(ids)} email(s) não lido(s) encontrado(s)")

        for msg_id in ids[-20:]:  # processa no máximo 20 por ciclo (LIFO)
            try:
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw_email = msg_data[0][1]

                msg = email.message_from_bytes(raw_email)
                from_header = _decode_header_value(msg.get("From", ""))
                sender     = _extract_email_address(from_header)
                body       = _extract_text_body(msg)

                if sender and body:
                    replies.append((sender, body))

                # Marca como lido — independente de ser um lead ou não
                imap.store(msg_id, "+FLAGS", "\\Seen")

            except Exception as e:
                logger.warning(f"[IMAP] Erro ao processar msg_id={msg_id}: {e}")
                continue

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return replies
