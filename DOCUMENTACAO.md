# Vigil.AI — Documentação Técnica Completa

> **Versão:** 1.0 — Junho 2026  
> **Ambiente atual:** Desenvolvimento local (localhost)

---

> [!CAUTION]
> **Este projeto atualmente funciona apenas em ambiente de desenvolvimento (localhost).**
> Para uso em produção, são necessárias adaptações descritas na seção [Deploy em Produção](#-deploy-em-produção).

---

## Índice

1. [Visão Geral](#-visão-geral)
2. [Arquitetura](#-arquitetura)
3. [Banco de Dados](#-banco-de-dados)
4. [Pré-requisitos e Configuração](#-pré-requisitos-e-configuração)
5. [Como Rodar o Projeto](#-como-rodar-o-projeto)
6. [Funcionalidades Implementadas](#-funcionalidades-implementadas)
7. [Testes Realizados](#-testes-realizados)
8. [Limitações e Próximos Passos](#-limitações-e-próximos-passos)
9. [Deploy em Produção](#-deploy-em-produção)
10. [Referência de APIs](#-referência-de-apis)

---

## Visão Geral

O **Vigil.AI** é um sistema de gerenciamento de leads com agente de IA integrado para o evento **Vigil Summit — Segurança para a Era da IA**.

O sistema automatiza o ciclo completo de vida de um participante:

```
Inscrição → Enriquecimento (IA) → Qualificação ICP → 
Convite por Email/WhatsApp → Respostas Automáticas → Pós-Evento
```

### Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI + SQLAlchemy (async) |
| Banco de Dados | MySQL 8.x via Docker |
| Agente de IA | LangGraph + Anthropic Claude 3.5 Sonnet |
| Email | SMTP Gmail (aiosmtplib) |
| WhatsApp | Twilio API |
| Scheduler | APScheduler (AsyncIOScheduler) |
| Frontend | HTML5 + Vanilla JS + CSS |

---

## Arquitetura

```
AIEngineerProject/
├── .env                          # Variáveis de ambiente (NÃO commitar)
├── .env.example                  # Template de variáveis
├── docker-compose.yml            # MySQL container
├── requirements.txt              # Dependências Python
├── DOCUMENTACAO.md               # Este arquivo
├── scripts/
│   └── validate_db.py            # Valida e cria as 4 tabelas do banco
└── vigil_agent/
    └── app/
        ├── main.py               # Entrypoint FastAPI + lifespan
        ├── core/config.py        # Settings (pydantic-settings)
        ├── db/session.py         # AsyncSession factory
        ├── models/               # Modelos ORM (SQLAlchemy)
        │   ├── lead.py
        │   ├── event.py
        │   ├── message_template.py
        │   └── admin_user.py
        ├── api/routes/
        │   ├── leads.py          # CRUD leads + registro público
        │   ├── admin.py          # Painel administrativo (JWT)
        │   └── webhooks.py       # Inbound email/WhatsApp
        ├── agents/
        │   ├── graph.py          # Grafo LangGraph do agente
        │   └── prompts.py        # Prompts do Claude
        ├── services/
        │   ├── enrichment.py     # Qualificação ICP e enriquecimento
        │   ├── notification.py   # Dispatcher de email e WhatsApp
        │   ├── scheduler.py      # APScheduler + registro polling IMAP
        │   └── imap_poller.py    # Polling de respostas de email (IMAP SSL)
        └── static/
            ├── index.html        # Landing page + formulário
            ├── app.js            # Lógica do formulário (modo LinkedIn/Manual)
            └── style.css         # Estilos (tema espacial dark mode)
```

### Fluxo do Agente

```
1. Lead se inscreve via formulário
2. node_enrich_lead: Claude analisa dados profissionais e enriquece o perfil
3. node_score_and_route: Score ICP calculado (0.0 a 1.0)
   - Score >= 0.60 → node_send_pre_event (envia convite)
   - Score < 0.60  → out_of_icp (sem contato)
4. Lead responde email
5. IMAP Poller detecta reply (a cada 60s) → POST /api/v1/webhooks/inbound
6. node_process_response: Claude interpreta intenção e responde
```

---

## Banco de Dados

O banco possui **4 tabelas**, todas com modelos SQLAlchemy e DDL no script `validate_db.py`.

### Tabelas

| Tabela | Arquivo de Modelo | Descrição |
|---|---|---|
| `leads` | `app/models/lead.py` | Participantes e ciclo de vida do funil |
| `events` | `app/models/event.py` | Dados do evento (data, local, palestrantes) |
| `message_templates` | `app/models/message_template.py` | Templates editáveis com variáveis dinâmicas |
| `admin_users` | `app/models/admin_user.py` | Usuários do painel administrativo |

> [!NOTE]
> O SQLAlchemy cria as tabelas automaticamente no startup do servidor via `Base.metadata.create_all()`.
> O script `validate_db.py` serve para validar a conexão e estrutura **antes** de subir o servidor.

### Principais Campos da Tabela `leads`

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | ENUM | `new`, `enriched`, `contacted`, `confirmed`, `declined`, `no_response`, `attended`, `no_show`, `out_of_icp` |
| `funnel_phase` | ENUM | `capture`, `enrichment`, `pre_event`, `post_event`, `closed` |
| `qualification_score` | FLOAT | Score ICP de 0.0 a 1.0 (>= 0.60 entra no funil) |
| `enrichment_data` | JSON | Dados adicionais do perfil identificados pela IA |
| `communication_log` | JSON | Histórico completo de mensagens enviadas e recebidas |

---

## Pré-requisitos e Configuração

### Dependências de Sistema

- Python 3.11+
- Docker + Docker Compose
- Git

### Variáveis de Ambiente

Copie e preencha o `.env`:

```bash
cp AIEngineerProject/.env.example AIEngineerProject/.env
```

Campos obrigatórios:

```dotenv
# Banco de Dados
DATABASE_URL=mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb

# Anthropic (Claude 3.5 Sonnet)
ANTHROPIC_API_KEY=sk-ant-...

# Email SMTP — Gmail App Password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu_email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_FROM=seu_email@gmail.com
EMAIL_FROM_NAME=Vigil Summit

# Twilio (WhatsApp) — opcional
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# IMAP (polling de respostas de email)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_POLL_INTERVAL_SECONDS=60
# Usa as mesmas credenciais SMTP_USER e SMTP_PASSWORD

# Admin
ADMIN_DEFAULT_USER=admin
ADMIN_DEFAULT_PASSWORD=vigil2026
```

> [!TIP]
> **Gmail App Password:** Em [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), crie uma senha para "Correio". Use-a em `SMTP_PASSWORD`. A senha normal do Gmail não funciona para apps.

> [!TIP]
> **Gmail IMAP:** Ative o IMAP em: Gmail → Configurações → Ver todas → Encaminhamento e POP/IMAP → **Habilitar IMAP**. Sem isso, o polling de respostas não funciona.

---

## Como Rodar o Projeto

### Passo 1 — Suba o MySQL com Docker

```bash
cd AIEngineerProject
docker compose up -d
```

Verifique se está rodando:

```bash
docker compose ps
```

### Passo 2 — Ambiente virtual Python

```bash
cd AIEngineerProject/vigil_agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
```

### Passo 3 — Valide o banco de dados

```bash
cd AIEngineerProject
source vigil_agent/.venv/bin/activate
python scripts/validate_db.py
```

Saída esperada:

```
OK — Conexao estabelecida com sucesso!
Tabela `leads`:             OK — Existe com N registro(s)
Tabela `events`:            OK — Existe com N registro(s)
Tabela `message_templates`: OK — Existe com N registro(s)
Tabela `admin_users`:       OK — Existe com N registro(s)
OK: Todas as verificacoes passaram! Sistema pronto.
```

### Passo 4 — Suba o servidor

```bash
cd AIEngineerProject/vigil_agent
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> [!NOTE]
> Se a porta 8000 já estiver em uso: `pkill -f uvicorn` e tente novamente.

### Acessos disponíveis

| URL | Descrição |
|---|---|
| http://localhost:8000 | Landing page + formulário de inscrição |
| http://localhost:8000/admin | Painel administrativo |
| http://localhost:8000/docs | Swagger UI (só em dev) |
| http://localhost:8000/redoc | ReDoc (só em dev) |
| http://localhost:8000/health | Health check |

---

## Funcionalidades Implementadas

### 1. Formulário — Modo LinkedIn / Manual

| Modo | Campos obrigatórios | O que a IA busca |
|---|---|---|
| 🔗 Tenho LinkedIn | Nome, Email, WhatsApp + Username LinkedIn | Cargo, Empresa, Tamanho, Setor |
| ✏️ Preencher manualmente | Nome, Email, WhatsApp + Cargo, Empresa, Tamanho, Setor | (Usa dados fornecidos) |

A validação é condicional: campos ocultos não são validados. O toggle é em tempo real via JS puro.

### 2. Qualificação ICP (Score ≥ 0.60 para entrar no funil)

Critérios analisados pelo Claude:
- Cargo executivo (C-level, diretor, VP, head, gerente sênior)
- Empresa com 50+ funcionários
- Setor relevante (tech, cybersec, finanças, saúde, governo)
- Localização SP preferencial

### 3. Emails com Formatação PT-BR

```
📅 Data: 15 de julho de 2026
🕘 Horário: 09h00
📍 Local: São Paulo, SP
```

Variáveis disponíveis nos templates:

| Variável | Valor de exemplo |
|---|---|
| `{{NOME}}` | Carlos Mendes |
| `{{PRIMEIRO_NOME}}` | Carlos |
| `{{CARGO}}` | CISO |
| `{{EMPRESA}}` | TechCorp Brasil |
| `{{DATA_EVENTO}}` | 15 de julho de 2026 |
| `{{HORA_EVENTO}}` | 09h00 |
| `{{LOCAL_EVENTO}}` | São Paulo, SP |
| `{{NOME_EVENTO}}` | Vigil Summit |
| `{{PALESTRANTES}}` | - João Silva\n- Maria Costa |

### 4. Polling IMAP — Respostas de Email

A cada 60 segundos, o APScheduler:
1. Conecta via IMAP SSL ao Gmail (porta 993)
2. Busca emails UNSEEN (não lidos) na INBOX
3. Extrai remetente e corpo (remove histórico citado via regex)
4. Faz HTTP POST para `/api/v1/webhooks/inbound` (dentro do uvicorn)
5. Claude interpreta a mensagem e responde por email

### 5. Webhooks de Resposta

| Endpoint | Canal | Configuração |
|---|---|---|
| `POST /api/v1/webhooks/inbound` | Genérico (testes) | Nenhuma |
| `POST /api/v1/webhooks/twilio/whatsapp` | WhatsApp | Console Twilio → When a message comes in |
| `POST /api/v1/webhooks/sendgrid/inbound` | Email (produção) | SendGrid Inbound Parse + MX |

### 6. Painel Administrativo

Login: http://localhost:8000/admin → `admin` / `vigil2026`

- Dashboard: métricas em tempo real
- Gestão de leads com filtros
- Editor de templates com preview
- Configuração do evento (data, local, palestrantes)
- Controle do scheduler (disparo pós-evento)

---

## Testes Realizados

### Teste 1 — Health Check

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Resultado esperado:
```json
{
  "status": "healthy",
  "environment": "development",
  "anthropic_configured": true,
  "smtp_configured": true,
  "twilio_configured": true
}
```

---

### Teste 2 — Validação do Banco

```bash
cd AIEngineerProject
source vigil_agent/.venv/bin/activate
python scripts/validate_db.py
```

---

### Teste 3 — Contagem de Vagas

```bash
curl -s http://localhost:8000/api/v1/leads/spots | python3 -m json.tool
```

Resultado esperado:
```json
{
  "capacity": 120,
  "registered": N,
  "remaining": 120-N,
  "is_full": false
}
```

---

### Teste 4 — Inscrição e Email de Convite

1. Acesse http://localhost:8000
2. Preencha o formulário (modo LinkedIn ou manual)
3. Clique em "Garantir Minha Vaga"
4. Verifique o banco: `curl -s http://localhost:8000/api/v1/leads/`
5. Aguarde o email de convite (se score ICP >= 0.60)

---

### Teste 5 — Webhook Inbound Manual

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/inbound \
  -H "Content-Type: application/json" \
  -d '{
    "lead_email": "email_do_lead@exemplo.com",
    "channel": "email",
    "message": "Olá, poderia levar mais um acompanhante?"
  }'
```

Resultado esperado:
```json
{
  "status": "received",
  "message": "Mensagem recebida. O agente está processando e responderá em instantes.",
  "lead_email": "email_do_lead@exemplo.com"
}
```

O lead recebe uma resposta da IA em ~30 segundos.

---

### Teste 6 — IMAP Polling Manual

```bash
cd AIEngineerProject/vigil_agent
source .venv/bin/activate
python3 -c "
import sys; sys.path.insert(0, '.')
from app.services.imap_poller import _fetch_unread_replies
replies = _fetch_unread_replies()
print(f'Emails nao lidos: {len(replies)}')
for sender, body in replies:
    print(f'De: {sender}')
    print(f'Msg: {body[:150]}')
"
```

---

### Teste 7 — Verificar Log de Comunicação de um Lead

```bash
curl -s http://localhost:8000/api/v1/leads/1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
log = d.get('communication_log', [])
print(f'Mensagens no log: {len(log)}')
for m in log:
    print(f'  [{m.get(\"channel\")}] {m.get(\"sent_at\",\"\")[:16]} | {m.get(\"message_preview\",\"\")[:80]}')
"
```

---

## Limitações e Próximos Passos

### Limitações Atuais

| Limitação | Descrição |
|---|---|
| **IMAP Polling** | Respostas de email processadas a cada 60s (não instantâneo) |
| **WhatsApp Sandbox** | Sandbox Twilio tem restrições; exige número dedicado em produção |
| **LinkedIn Mockado** | Enriquecimento usa dados fictícios; sem integração real com API LinkedIn |
| **Gmail SMTP** | Limite de 500 emails/dia; não escala para eventos grandes |
| **Sem HTTPS** | Webhooks do Twilio e SendGrid exigem HTTPS (só funciona em produção) |
| **SQLite/MySQL local** | Banco local via Docker; não recomendado para produção |

### Próximos Passos

- [ ] Integrar LinkedIn API real (ou parceiro de enriquecimento como Clearbit/Apollo)
- [ ] Migrar email para SendGrid ou Resend (sem limite diário, com Inbound Parse)
- [ ] Configurar SendGrid Inbound Parse para respostas instantâneas
- [ ] Número WhatsApp dedicado no Twilio (sair do Sandbox)
- [ ] Implementar testes automatizados (pytest + httpx)
- [ ] Dockerizar a aplicação completa
- [ ] Implementar fila de processamento (Redis/Celery) para escalar

---

## Deploy em Produção

> [!CAUTION]
> **O sistema atual só funciona em localhost.** Para produção, todas as etapas abaixo são obrigatórias.

### 1. Email — Trocar Gmail por SendGrid

```dotenv
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.xxxxxxxxxxxx
EMAIL_FROM=noreply@seudominio.com
```

Para respostas instantâneas (sem IMAP polling):
- Painel SendGrid → Settings → Inbound Parse
- URL do webhook: `https://seudominio.com/api/v1/webhooks/sendgrid/inbound`
- Configure MX do domínio para `mx.sendgrid.net`

### 2. WhatsApp — Número Dedicado Twilio

- Compre um número Twilio com WhatsApp Business API aprovado
- Configure webhook: `https://seudominio.com/api/v1/webhooks/twilio/whatsapp`
- Atualize `TWILIO_WHATSAPP_FROM` no `.env`

### 3. Variáveis de Produção

```dotenv
APP_ENV=production
DEBUG=false
SECRET_KEY=gere-chave-aleatoria-64-caracteres
ADMIN_DEFAULT_PASSWORD=senha-forte-minimo-12-chars
DATABASE_URL=mysql+aiomysql://user:senha@host-rds:3306/vigildb
```

### 4. Servidor com Gunicorn

```bash
pip install gunicorn

gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### 5. HTTPS com Nginx + Let's Encrypt

```nginx
server {
    listen 443 ssl;
    server_name seudominio.com;

    ssl_certificate /etc/letsencrypt/live/seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6. Banco de Dados Gerenciado

- AWS RDS MySQL 8.0 ou Google Cloud SQL
- Configure usuário/senha seguros
- Ative backups automáticos diários

---

## Referência de APIs

### Leads

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/api/v1/leads/register` | Registrar novo lead |
| `GET` | `/api/v1/leads/` | Listar todos os leads |
| `GET` | `/api/v1/leads/{id}` | Detalhes de um lead |
| `GET` | `/api/v1/leads/spots` | Vagas disponíveis |

### Webhooks

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/api/v1/webhooks/inbound` | Receber resposta (genérico/testes) |
| `POST` | `/api/v1/webhooks/twilio/whatsapp` | Webhook Twilio WhatsApp |
| `POST` | `/api/v1/webhooks/sendgrid/inbound` | Webhook SendGrid (produção) |

### Admin (JWT obrigatório)

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/api/v1/admin/login` | Login — retorna token JWT |
| `GET` | `/api/v1/admin/leads` | Leads com filtros avançados |
| `GET` | `/api/v1/admin/event` | Dados do evento atual |
| `PUT` | `/api/v1/admin/event` | Atualizar evento |
| `GET` | `/api/v1/admin/templates` | Listar templates |
| `PUT` | `/api/v1/admin/templates/{id}` | Editar template |
| `POST` | `/api/v1/admin/event/end` | Encerrar evento + disparar pós-evento |
| `GET` | `/api/v1/admin/scheduler/status` | Status do scheduler |

### Utilitários

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI (dev only) |
| `GET` | `/redoc` | ReDoc (dev only) |

---

*Documentação gerada em: Junho de 2026*
