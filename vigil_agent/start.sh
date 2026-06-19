#!/bin/bash
# start.sh — Inicializa o servidor Vigil.AI de forma segura
# Garante que variáveis de ambiente do SO não sobrescrevam o .env
#
# Uso: bash start.sh [--dev | --prod]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/activate"
MODE="${1:---dev}"

echo "╔══════════════════════════════════════════╗"
echo "║        Vigil.AI — Iniciando Servidor     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Ativa o venv
if [ ! -f "$VENV" ]; then
    echo "❌ Venv não encontrado. Execute primeiro:"
    echo "   python3.11 -m venv .venv && source .venv/bin/activate && pip install -r ../requirements.txt"
    exit 1
fi

source "$VENV"

# Carrega o .env e limpa variáveis conflitantes do SO
ENV_FILE="$SCRIPT_DIR/../.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Arquivo .env não encontrado em: $ENV_FILE"
    exit 1
fi

echo "📄 Carregando configurações de: $ENV_FILE"
echo ""

# Limpa variáveis do SO que possam conflitar com o .env
# (exportadas manualmente em sessões anteriores)
unset TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_WHATSAPP_FROM
unset ANTHROPIC_API_KEY
unset SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD EMAIL_FROM EMAIL_FROM_NAME
unset DATABASE_URL
unset SECRET_KEY ADMIN_DEFAULT_PASSWORD ADMIN_DEFAULT_USER

echo "🧹 Variáveis de ambiente do SO limpas."
echo ""

# Verifica configurações críticas lendo direto do .env
TWILIO_SID=$(grep "^TWILIO_ACCOUNT_SID=" "$ENV_FILE" | cut -d= -f2 | tr -d '"' | tr -d "'")
ANTHROPIC=$(grep "^ANTHROPIC_API_KEY=" "$ENV_FILE" | cut -d= -f2 | tr -d '"' | tr -d "'")
SMTP=$(grep "^SMTP_USER=" "$ENV_FILE" | cut -d= -f2 | tr -d '"' | tr -d "'")

echo "🔑 Configurações detectadas no .env:"
echo "   Anthropic : ${ANTHROPIC:0:15}..."
echo "   Twilio SID: ${TWILIO_SID:0:10}..."
echo "   SMTP user : $SMTP"
echo ""

# Inicia o servidor
if [ "$MODE" = "--prod" ]; then
    echo "🌍 Modo: PRODUÇÃO"
    exec gunicorn app.main:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers 4 \
        --bind 0.0.0.0:8000 \
        --timeout 120 \
        --log-level info
else
    echo "🛠️  Modo: DESENVOLVIMENTO (--reload)"
    exec uvicorn app.main:app \
        --reload \
        --host 0.0.0.0 \
        --port 8000 \
        --log-level info
fi
