<![CDATA[<div align="center">

# 🛡️ Vigil.AI — Autonomous Funnel Agent

### Agente de IA Autônomo para Conversão de Leads Executivos

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini_3.5_Flash-Google_AI-4285F4?logo=google&logoColor=white)](https://aistudio.google.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![MySQL 8.4](https://img.shields.io/badge/MySQL-8.4-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

---

**Sistema end-to-end** que automatiza o funil completo de captação, qualificação, engajamento e follow-up de executivos (CISOs, CTOs, Diretores de TI) para o **Vigil Summit — Segurança para a Era da IA**.

[🚀 Quick Start](#-quick-start-passo-a-passo-completo) · [🏗️ Arquitetura](#%EF%B8%8F-arquitetura) · [📡 APIs e Endpoints](#-endpoints-da-api) · [🧪 Testes](#-testes) · [🖥️ Dashboard Admin](#%EF%B8%8F-painel-administrativo)

</div>

---

## 📖 Índice

- [Visão Geral do Projeto](#-visão-geral-do-projeto)
- [Arquitetura](#%EF%B8%8F-arquitetura)
- [Stack Tecnológico](#-stack-tecnológico-justificativas)
- [Quick Start (Passo a Passo Completo)](#-quick-start-passo-a-passo-completo)
  - [Pré-requisitos](#1-pré-requisitos)
  - [Clonar o Repositório](#2-clonar-o-repositório)
  - [Obter API Key do Google Gemini (GRATUITA)](#3-obter-api-key-do-google-gemini-gratuita)
  - [Configurar Gmail App Password (E-mail)](#4-configurar-gmail-app-password-para-envio-de-emails)
  - [Configurar Twilio WhatsApp Sandbox (Opcional)](#5-configurar-twilio-whatsapp-sandbox-opcional)
  - [Configurar Variáveis de Ambiente (.env)](#6-configurar-variáveis-de-ambiente-env)
  - [Subir o MySQL com Docker](#7-subir-o-mysql-com-docker)
  - [Criar Ambiente Virtual e Instalar Dependências](#8-criar-ambiente-virtual-e-instalar-dependências)
  - [Validar e Criar Tabelas no Banco](#9-validar-e-criar-tabelas-no-banco)
  - [Iniciar o Servidor](#10-iniciar-o-servidor)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Funcionalidades Completas](#-funcionalidades-completas)
  - [Landing Page (Captação)](#1-landing-page--captação-de-leads)
  - [Check-in via QR Code](#2-check-in-via-qr-code)
  - [Painel Administrativo](#%EF%B8%8F-painel-administrativo)
  - [Fases do Funil](#-fases-do-funil-ia)
- [Endpoints da API](#-endpoints-da-api)
- [Testes](#-testes)
- [Regras de Negócio](#-regras-de-negócio)
- [LGPD](#-lgpd)
- [Cenário de Escala (Bônus)](#-cenário-de-escala-bônus)

---

## 🎯 Visão Geral do Projeto

O **Vigil.AI** foi desenvolvido como resposta ao [Case de AI Engineer da Pareto](./Case%20-%20AI%20Engineer%20(2026).pdf). O desafio é construir um **agente de IA autônomo** que gerencie todo o funil de participantes de um evento corporativo exclusivo:

| Fase | O que acontece |
|---|---|
| **1. Captação** | Lead se inscreve na landing page → qualificação imediata por cargo |
| **2. Enriquecimento** | Gemini AI analisa e infere dados profissionais → Score ICP (0.0–1.0) |
| **3. Engajamento Pré-Evento** | Mensagens personalizadas via Email/WhatsApp, geradas pela IA |
| **4. Follow-up Pós-Evento** | Presentes → proposta de reunião · Ausentes → recuperação com material |

> **O diferencial**: toda mensagem é gerada pelo **Gemini 3.5 Flash** com contexto enriquecido do lead (cargo, setor, tamanho da empresa, interesses de segurança). Nenhum template é genérico — cada lead recebe comunicação única e personalizada.

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend                                │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐   │
│  │ Landing Page  │  │ Admin Dashboard│  │ Check-in (QR Code)  │   │
│  └──────┬───────┘  └───────┬────────┘  └──────────┬──────────┘   │
└─────────┼──────────────────┼──────────────────────┼──────────────┘
          │                  │                      │
─ ─ ─ ─ ─┼─ ─ ─ ─ ─ ─ ─ ─ ─┼─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ 
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI (async)                             │
│                                                                  │
│  📌 Leads (leads.py)                                             │
│  ├── POST /api/v1/leads/                    (público — registro)│
│  ├── POST /api/v1/leads/checkin             (público — QR Code) │
│  ├── GET  /api/v1/leads/spots               (público — vagas)   │
│  ├── GET  /api/v1/leads/linkedin-preview    (público — Gemini)  │
│  ├── GET  /api/v1/leads/                    (🔑 API Key)        │
│  ├── GET  /api/v1/leads/{id}                (🔑 API Key)        │
│  ├── PATCH /api/v1/leads/{id}               (🔑 API Key)        │
│  └── POST /api/v1/leads/{id}/post-event     (🔑 API Key)        │
│                                                                  │
│  🔐 Admin (admin.py)                                             │
│  ├── POST /api/v1/admin/auth/login          (público — JWT)     │
│  ├── GET  /api/v1/admin/event               (🔐 JWT)            │
│  ├── PUT  /api/v1/admin/event               (🔐 JWT)            │
│  ├── POST /api/v1/admin/event/end           (🔐 JWT)            │
│  ├── PUT  /api/v1/admin/event/schedule-end  (🔐 JWT)            │
│  ├── GET  /api/v1/admin/leads               (🔐 JWT)            │
│  ├── POST /api/v1/admin/leads/{id}/qualify  (🔐 JWT — aprovar)  │
│  ├── GET  /api/v1/admin/templates           (🔐 JWT)            │
│  ├── POST /api/v1/admin/templates           (🔐 JWT)            │
│  ├── PUT  /api/v1/admin/templates/{id}      (🔐 JWT)            │
│  ├── DELETE /api/v1/admin/templates/{id}    (🔐 JWT)            │
│  ├── GET  /api/v1/admin/scheduler/status    (🔐 JWT)            │
│  ├── POST /api/v1/admin/scheduler/trigger-test        (🔐 JWT)  │
│  └── POST /api/v1/admin/scheduler/trigger-pre-event-test (🔐)   │
│                                                                  │
│  📣 Broadcast (broadcast.py)                                     │
│  ├── POST /api/v1/admin/broadcast/pre-event/participant  (🔐)   │
│  ├── POST /api/v1/admin/broadcast/pre-event/with-companion(🔐)  │
│  ├── POST /api/v1/admin/broadcast/pre-event/companion-pending(🔐)│
│  ├── POST /api/v1/admin/broadcast/pre-event/all          (🔐)   │
│  └── GET  /api/v1/admin/broadcast/pre-event/status       (🔐)   │
│                                                                  │
│  📥 Webhooks (webhooks.py)                                       │
│  ├── POST /api/v1/webhooks/inbound          (público — genérico)│
│  ├── POST /api/v1/webhooks/twilio/whatsapp  (Twilio callback)   │
│  └── POST /api/v1/webhooks/sendgrid/inbound (SendGrid callback) │
│                                                                  │
│  🏥 Infra                                                        │
│  └── GET  /health                           (público — status)  │
│                                                                  │
└──────────┬──────────────────────────────────────────────────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
               ┌──────────────────┐ ┌─────────────────┐ ┌──────────────────┐
               │   MySQL 8.4      │ │   Gemini 3.5    │ │ Notification Svc │
               │                  │ │   Flash (IA)    │ │                  │
               │ • leads          │ │                 │ │ • Email (SMTP)   │
               │ • events         │ │ • Enriquecimento│ │ • WhatsApp       │
               │ • message_       │ │ • Qualificação  │ │   (Twilio)       │
               │   templates      │ │ • Geração de    │ │ • Modo simulado  │
               │ • admin_users    │ │   mensagens     │ │   (sem chaves)   │
               └──────────────────┘ └─────────────────┘ └──────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────────┐
                                    │    LangGraph Agent   │
                                    │                      │
                                    │  enrich_lead         │
                                    │       ▼              │
                                    │  score_and_route     │
                                    │       ▼              │
                                    │  send_pre_event      │
                                    │       ▼              │
                                    │  process_response    │
                                    │       ▼              │
                                    │  send_post_event     │
                                    └─────────────────────┘
```

### Fluxo Detalhado do Funil

```
POST /api/v1/leads/
       │
       ▼
 [FastAPI] ──► [MySQL 8.4]
       │
       ▼ (background task)
 [Gemini AI — Qualificação & Enriquecimento]
       │
       ├── classify_lead_eligibility ──► Approved / Pending Review / Not Eligible
       │
       ├── enrich_lead_profile ────────► Score ICP + Dados Inferidos
       │
       ├── _send_ai_registration_email ► Email de confirmação via Gemini AI
       │
       └── [LangGraph Agent]
              ├── node_enrich_lead
              ├── node_score_and_route
              ├── node_send_pre_event ──► [Notification Service]
              │                              ├── WhatsApp (Twilio)
              │                              └── Email (SMTP/Gmail)
              ├── node_process_response ► Inbound via webhook
              └── node_send_post_event ► Follow-up personalizado (Gemini)
```

---

## 🔧 Stack Tecnológico (Justificativas)

| Camada | Tecnologia | Justificativa |
|---|---|---|
| **API** | FastAPI (async) | Alto throughput, geração automática de docs (`/docs`), DI nativa. Ideal para I/O-bound com chamadas a LLMs. |
| **Banco de Dados** | MySQL 8.4 + SQLAlchemy Async | ACID, suporte nativo a JSON, container Docker oficial pronto para uso. |
| **Orquestração IA** | LangGraph | Grafo de estado determinístico com ramificações condicionais. Permite escalar nós de forma independente. |
| **LLM** | Gemini 3.5 Flash (Google) | Modelo gratuito (1500 req/dia), excelente reasoning e grounding. Custo zero para testes. |
| **Email** | SMTP via Gmail App Password | Envio direto sem dependência de serviço externo. Confiável e gratuito. |
| **WhatsApp** | Twilio Sandbox | API REST com sandbox gratuito para desenvolvimento. Fallback simulado. |
| **Migrações** | Alembic + `validate_db.py` | Versionamento de schema e script standalone para criação e migração. |
| **Testes** | Pytest + HTTPX + SQLite | Testes assíncronos com SQLite em memória — **sem necessidade de MySQL para rodar testes**. |

---

## 🚀 Quick Start (Passo a Passo Completo)

### 1. Pré-requisitos

Certifique-se de ter instalado:

| Ferramenta | Versão Mínima | Verificação | Instalação |
|---|---|---|---|
| **Python** | 3.11+ | `python3 --version` | [python.org/downloads](https://www.python.org/downloads/) |
| **Docker** | 20.0+ | `docker --version` | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| **Docker Compose** | v2+ | `docker compose version` | Já incluído no Docker Desktop |
| **Git** | 2.0+ | `git --version` | [git-scm.com](https://git-scm.com/) |

### 2. Clonar o Repositório

```bash
git clone https://github.com/SEU_USUARIO/AIEngineerProject.git
cd AIEngineerProject
```

### 3. Obter API Key do Google Gemini (GRATUITA)

> ⚠️ **Esta é a única chave obrigatória.** Sem ela, o enriquecimento por IA e a geração de mensagens personalizadas não funcionarão (o sistema usará um fallback determinístico).

**Passo a passo:**

1. Acesse **[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)**
2. Faça login com sua conta Google
3. Clique em **"Create API key"**
4. Selecione um projeto existente ou crie um novo
5. Copie a chave gerada (começa com `AIza...`)

<details>
<summary>📸 Onde encontrar a API key no Google AI Studio</summary>

1. Acesse https://aistudio.google.com/app/apikey  
2. A tela mostrará "API keys" com o botão **Create API key**
3. Após criar, a chave aparece na lista — clique no ícone de copiar

</details>

**Limites gratuitos do Gemini 3.5 Flash:**
- ✅ 1.500 requisições/dia
- ✅ 1.000.000 tokens/min
- ✅ Sem cobrança para desenvolvimento

### 4. Configurar Gmail App Password (para envio de emails)

> 📧 **Opcional, mas recomendado.** Sem essa configuração, os emails serão exibidos apenas nos logs do servidor (modo simulado).

**Passo a passo:**

1. Acesse **[myaccount.google.com/security](https://myaccount.google.com/security)**
2. Ative a **Verificação em duas etapas** (obrigatório)
3. Após ativar, volte à página de segurança
4. Procure por **"Senhas de app"** (ou acesse diretamente: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords))
5. Em "Selecionar app", escolha **"Outro (nome personalizado)"**
6. Digite **"Vigil Summit"** e clique em **Gerar**
7. Copie a senha de 16 caracteres gerada (formato: `xxxx xxxx xxxx xxxx`)

> **Importante:** Use esta senha no campo `SMTP_PASSWORD` do `.env`, **não** sua senha normal do Gmail.

### 5. Configurar Twilio WhatsApp Sandbox (Opcional)

> 📱 **Opcional.** Sem Twilio, as mensagens WhatsApp serão exibidas apenas nos logs (modo simulado). O sistema funciona 100% com apenas Email.

**Passo a passo:**

1. Crie uma conta gratuita em **[twilio.com](https://www.twilio.com/try-twilio)**
2. Após o login, vá em **Console** → copie:
   - **Account SID** (começa com `AC...`)
   - **Auth Token**
3. No menu lateral: **Messaging** → **Try it out** → **Send a WhatsApp message**
4. Siga as instruções para ativar o **Sandbox**:
   - Envie a mensagem `join <código>` para **+1 (415) 523-8886** via WhatsApp no seu celular
5. O número do remetente do sandbox é: `whatsapp:+14155238886`

### 6. Configurar Variáveis de Ambiente (.env)

```bash
# Na raiz do projeto (AIEngineerProject/)
cp .env.example .env
```

Abra o arquivo `.env` no seu editor e preencha:

```env
# ─── Database (MySQL) ──────────────────────────────────────────────
# ⚠️ NÃO ALTERE se for usar o Docker Compose padrão
DATABASE_URL=mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb

# ─── Gemini (Google AI) ── ✅ OBRIGATÓRIO ──────────────────────────
# Cole a chave obtida em aistudio.google.com/app/apikey
API_KEY_AI=AIzaSy...sua-chave-aqui

# ─── Security ──────────────────────────────────────────────────────
SECRET_KEY=your-super-secret-key-change-in-production
VIGIL_API_KEY=vigil-internal-api-key-2026

# ─── SMTP Email (Gmail) ── 📧 Recomendado ─────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu_email@gmail.com             # ← Seu Gmail real
SMTP_PASSWORD=xxxx xxxx xxxx xxxx         # ← App Password gerada (passo 4)
EMAIL_FROM=seu_email@gmail.com
EMAIL_FROM_NAME=Vigil Summit

# ─── Twilio WhatsApp ── 📱 Opcional ───────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# ─── Admin Panel ── 🔐 Login do Dashboard ─────────────────────────
ADMIN_JWT_SECRET=vigil-admin-secret-change-in-production
ADMIN_DEFAULT_USER=admin
ADMIN_DEFAULT_PASSWORD=vigil2026

# ─── App ───────────────────────────────────────────────────────────
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
```

### 7. Subir o MySQL com Docker

```bash
docker compose up -d
```

Verifique se o container está rodando:

```bash
docker ps
# Deve mostrar: vigildb (mysql:8.4) em STATUS "Up ... (healthy)"
```

<details>
<summary>🔍 Verificar se o MySQL está pronto</summary>

```bash
# Aguarde o health check (pode levar ~30 segundos na primeira vez)
docker compose logs -f db

# Quando aparecer "mysqld: ready for connections" está pronto
# Pressione Ctrl+C para sair dos logs
```

</details>

### 8. Criar Ambiente Virtual e Instalar Dependências

```bash
cd vigil_agent
python3 -m venv .venv
source .venv/bin/activate        # No Windows: .venv\Scripts\activate
pip install -r ../requirements.txt
```

### 9. Validar e Criar Tabelas no Banco

```bash
# Ainda dentro de vigil_agent/
python ../scripts/validate_db.py
```

**Saída esperada:**

```
============================================================
   Vigil.AI — Validacao do Banco de Dados MySQL
============================================================

============================================================
  VERIFICACAO 1 — Conexao com o MySQL
============================================================
  Host     : localhost:3306
  Database : vigildb
  Usuario  : vigil
------------------------------------------------------------
  OK  Conexao estabelecida com sucesso!
  MySQL: 8.4.x

============================================================
  VERIFICACAO 2 — Estrutura das Tabelas
============================================================
  Tabela `leads`:         OK — Existe com 0 registro(s)
  Tabela `events`:        OK — Existe com 0 registro(s)
  Tabela `message_templates`: OK — Existe com 0 registro(s)
  Tabela `admin_users`:   OK — Existe com 0 registro(s)

============================================================
  VERIFICACAO 3 — Migracao de Colunas Novas
============================================================
  OK  (todas as colunas já existem)

============================================================
  VERIFICACAO 4 — Migracao de ENUMs
============================================================
  OK  (todos os ENUMs estão atualizados)

============================================================
  OK: Todas as verificacoes passaram! Sistema pronto.
============================================================
```

> **Dica:** Se aparecer `ERRO Falha na conexao! [2003]`, o MySQL ainda não subiu. Aguarde uns 30s e tente novamente.

### 10. Iniciar o Servidor

**Opção A — Via script (recomendado):**

```bash
# Dentro de vigil_agent/
bash start.sh
```

**Opção B — Diretamente com uvicorn:**

```bash
# Dentro de vigil_agent/
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Saída esperada no terminal:**

```
╔══════════════════════════════════════════╗
║        Vigil.AI — Iniciando Servidor     ║
╚══════════════════════════════════════════╝

🚀 Vigil.AI Funnel Agent iniciando...
✅ Tabelas verificadas/criadas (modo desenvolvimento)
✅ Admin padrão criado: admin
✅ Evento padrão criado
✅ 6 prompts de instrução criados no banco (editáveis pelo admin)
🌍 Ambiente: development
🔑 Gemini configurado: Sim
📧 SMTP configurado: Sim
📱 Twilio configurado: Não (modo simulado)
```

### ✅ Tudo Pronto! Acesse:

| Recurso | URL | Descrição |
|---|---|---|
| 🏠 **Landing Page** | [http://localhost:8000/](http://localhost:8000/) | Formulário de inscrição para leads |
| 🔐 **Dashboard Admin** | [http://localhost:8000/admin/login.html](http://localhost:8000/admin/login.html) | Painel de gestão do evento |
| 📋 **API Docs (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) | Documentação interativa da API |
| 📋 **API Docs (ReDoc)** | [http://localhost:8000/redoc](http://localhost:8000/redoc) | Documentação alternativa |
| 🎫 **Check-in QR Code** | [http://localhost:8000/checkin.html](http://localhost:8000/checkin.html) | Tela para exibir no evento |
| ❤️ **Health Check** | [http://localhost:8000/health](http://localhost:8000/health) | Verificar saúde do sistema |

---

## 📁 Estrutura do Projeto

```
AIEngineerProject/
├── 📄 .env.example                    # Template de variáveis de ambiente
├── 📄 .env                            # ⚠️ Suas chaves reais (NÃO versione!)
├── 📄 .gitignore                      # Ignora .env, __pycache__, .venv, etc.
├── 📄 docker-compose.yml              # MySQL 8.4 containerizado
├── 📄 requirements.txt                # Dependências Python do projeto
├── 📄 README.md                       # Este arquivo
├── 📄 Case - AI Engineer (2026).pdf   # Enunciado original do case
│
├── 📁 scripts/
│   └── 📄 validate_db.py             # Cria/valida tabelas MySQL (DDL completo)
│
└── 📁 vigil_agent/                    # Aplicação principal
    ├── 📄 start.sh                    # Script de inicialização segura
    ├── 📄 alembic.ini                 # Configuração do Alembic (migrações)
    ├── 📄 pytest.ini                  # Configuração de testes
    │
    ├── 📁 alembic/                    # Diretório de migrações SQL
    │
    ├── 📁 app/                        # Código da aplicação
    │   ├── 📄 main.py                 # Entry point — FastAPI app + seed de dados iniciais
    │   │
    │   ├── 📁 api/routes/             # Endpoints HTTP
    │   │   ├── 📄 leads.py            # CRUD de leads + registro + check-in + pós-evento
    │   │   ├── 📄 admin.py            # Login JWT + CRUD evento/templates + qualificação manual
    │   │   ├── 📄 broadcast.py        # Envio massivo pré-evento (por persona)
    │   │   └── 📄 webhooks.py         # Inbound: Twilio WhatsApp + SendGrid Email
    │   │
    │   ├── 📁 agents/                 # Agente de IA (LangGraph)
    │   │   ├── 📄 graph.py            # Grafo de estados: 5 nós + routing condicional
    │   │   └── 📄 prompts.py          # System prompts para cada fase do funil
    │   │
    │   ├── 📁 core/                   # Configuração global
    │   │   ├── 📄 config.py           # Pydantic Settings (lê .env)
    │   │   └── 📄 security.py         # Middleware de API Key
    │   │
    │   ├── 📁 db/                     # Camada de banco de dados
    │   │   ├── 📄 base.py             # Base declarativa SQLAlchemy
    │   │   └── 📄 session.py          # Engine async + session factory
    │   │
    │   ├── 📁 models/                 # Modelos SQLAlchemy (ORM)
    │   │   ├── 📄 lead.py             # Lead + LeadStatus + FunnelPhase (enums)
    │   │   ├── 📄 event.py            # Event + EventStatus
    │   │   ├── 📄 message_template.py # MessageTemplate + TemplatePhase + TemplateChannel
    │   │   └── 📄 admin_user.py       # AdminUser (login do dashboard)
    │   │
    │   ├── 📁 schemas/                # Schemas Pydantic (entrada/saída da API)
    │   │   └── 📄 lead.py             # LeadCreate, LeadRead, LeadUpdate, LeadWebhookEvent
    │   │
    │   ├── 📁 services/               # Lógica de negócio
    │   │   ├── 📄 enrichment.py       # Classificação + Enriquecimento via Gemini + fallback
    │   │   ├── 📄 notification.py     # Envio Email (SMTP) + WhatsApp (Twilio) + modo simulado
    │   │   ├── 📄 scheduler.py        # APScheduler (jobs agendados: pós-evento)
    │   │   ├── 📄 pre_event_scheduler.py # Régua pré-evento por persona (A/B/C)
    │   │   └── 📄 imap_poller.py      # Polling de respostas via IMAP (Gmail)
    │   │
    │   └── 📁 static/                 # Frontend (HTML/CSS/JS)
    │       ├── 📄 index.html          # Landing page (formulário de inscrição)
    │       ├── 📄 style.css           # Estilos da landing page
    │       ├── 📄 app.js              # JavaScript da landing page
    │       ├── 📄 checkin.html        # Página de check-in via QR Code
    │       └── 📁 admin/              # Painel administrativo
    │           ├── 📄 login.html      # Tela de login (JWT)
    │           ├── 📄 dashboard.html  # Dashboard completo
    │           ├── 📄 admin.css       # Estilos do admin
    │           └── 📄 admin.js        # JavaScript do admin
    │
    └── 📁 tests/                      # Suite de testes
        ├── 📄 conftest.py             # Fixtures: app de teste, banco SQLite, client
        ├── 📄 test_api.py             # Testes da API de leads
        ├── 📄 test_agent.py           # Testes do agente LangGraph
        ├── 📄 test_services.py        # Testes de notification + enrichment
        └── 📄 test_admin.py           # Testes do painel administrativo
```

---

## 🎯 Funcionalidades Completas

### 1. Landing Page — Captação de Leads

**URL:** [http://localhost:8000/](http://localhost:8000/)

A landing page temática do Vigil Summit contém:

- 🎨 Design dark mode com tema espacial e animações
- 📝 Formulário de inscrição com os campos:
  - Nome completo, Email, Telefone (com `+55`)
  - Empresa, Cargo, Tamanho da empresa, Setor
  - URL do LinkedIn (para enriquecimento automático pelo Gemini)
  - Checkbox de acompanhante (email + vínculo profissional)
  - Checkbox de consentimento LGPD (obrigatório)
- 🔍 **Preview do LinkedIn via Gemini**: ao preencher o campo LinkedIn, o Gemini tenta identificar a pessoa e pré-preenche cargo, empresa e setor
- 📊 Contador de vagas restantes em tempo real
- ✅ Validações de email duplicado e capacidade máxima (120 vagas)

**O que acontece ao se inscrever:**

1. O cargo é analisado por um **classificador determinístico** (`classify_lead_eligibility`)
2. Com base na classificação:
   - **Approved** (CISO, CTO, VP, Diretor, Head, Fundador): inscrição confirmada imediatamente → funil IA disparado → email de confirmação gerado pelo Gemini
   - **Pending Review** (Gerente, Coordenador, Especialista de área técnica): email informando análise → aguarda aprovação do admin
   - **Not Eligible** (cargos fora do ICP): email de cortesia gerado pelo Gemini → lead arquivado
3. Se informou acompanhante: convite enviado para o email do acompanhante

---

### 2. Check-in via QR Code

**URL (Tela para exibir):** [http://localhost:8000/checkin.html](http://localhost:8000/checkin.html)

Funcionalidade dupla:

| Modo | URL | Quem usa |
|---|---|---|
| **Display** (QR Code) | `/checkin.html` | Organizador exibe no evento (impressa ou tela) |
| **Scan** (Formulário) | `/checkin.html?mode=scan` | Participante escaneia e digita seu email |

**Como funciona:**
1. O organizador acessa `/checkin.html` em uma tela ou imprime a página
2. A página gera automaticamente um **QR Code** apontando para `/checkin.html?mode=scan`
3. O participante escaneia o QR Code com a câmera do celular
4. Digita o email de inscrição e confirma presença
5. O sistema marca `attended=True` e atualiza o status para `ATTENDED`
6. Se já fez check-in, exibe mensagem informativa

---

### 🖥️ Painel Administrativo

**URL:** [http://localhost:8000/admin/login.html](http://localhost:8000/admin/login.html)

#### 🔐 Credenciais de Acesso

| Campo | Valor |
|---|---|
| **Usuário** | `admin` |
| **Senha** | `vigil2026` |

> Essas credenciais são criadas automaticamente pelo seed na primeira execução. Podem ser alteradas nas variáveis `ADMIN_DEFAULT_USER` e `ADMIN_DEFAULT_PASSWORD` do `.env` (alteração deve ser feita **antes** do primeiro `bash start.sh`).

#### Funcionalidades do Dashboard

O painel administrativo (após login com JWT) oferece:

| Funcionalidade | Descrição |
|---|---|
| 📊 **Métricas do Funil** | Cards com totais: Inscritos, Confirmados, Presentes, No-shows, Pendentes |
| 👥 **Lista de Participantes** | Tabela com nome, email, empresa, cargo, status, score ICP |
| ✅ **Aprovação Manual** | Botões para aprovar/rejeitar leads em `Pending Review` |
| 📅 **Gestão do Evento** | Editar nome, data, hora, local, palestrantes, delay pós-evento |
| 📝 **Editor de Prompts** | Editar os system prompts que o Gemini usa para gerar mensagens (por fase do funil) |
| 📣 **Broadcast Pré-Evento** | Disparar manualmente régua de engajamento por persona (A/B/C) |
| 🔔 **Trigger Pós-Evento** | Encerrar evento e agendar follow-up automático |
| ⏰ **Status do Scheduler** | Ver próximo disparo agendado e configuração de lembretes |

#### Ações do Admin sobre Leads

```
Lead em "Pending Review"
        │
        ├── [Aprovar] → Status: NEW → Funil IA disparado → Email de confirmação Gemini
        │
        └── [Rejeitar] → Status: OUT_OF_ICP → Email de cortesia → Ciclo fechado
```

---

### 🤖 Fases do Funil (IA)

#### Fase 1 — Captura & Qualificação Imediata

- Lead registrado via `POST /api/v1/leads/`
- Validação de dados e consentimento LGPD
- **Qualificação determinística** por cargo:

| Classificação | Cargos | Ação |
|---|---|---|
| ✅ `approved` | CISOs, CTOs, Diretores, VPs, Fundadores, Heads, COOs | Confirmação imediata + funil IA |
| ⏳ `pending_review` | Gerentes, Coordenadores, Especialistas, Consultores de TI/Segurança | Aguarda aprovação do admin |
| ❌ `not_eligible` | Cargos fora de TI/Segurança/Risco | Email de cortesia + arquivado |

#### Fase 2 — Enriquecimento (IA Gemini)

- Gemini 3.5 Flash analisa os dados do lead e retorna:
  - **Empresa**: nome real, domínio, tamanho estimado, setor, receita
  - **Profissional**: cargo real, nível de senioridade, decision maker (sim/não)
  - **Interesses de segurança**: tópicos relevantes para o setor (ex: LGPD, Zero Trust)
  - **Score ICP** (0.0 – 1.0) com tier (A/B/C/D) e justificativa
  - **Hooks de personalização**: contexto de cargo, "dor" principal do setor, proposta de valor do evento
- Em caso de falha da IA, o sistema usa um **fallback determinístico** baseado nos dados disponíveis
- Leads com score < 0.60 são arquivados automaticamente

#### Fase 3 — Engajamento Pré-Evento

- **Gemini gera mensagens personalizadas** usando os hooks de personalização do enriquecimento
- 3 personas com réguas distintas:

| Persona | Critério | Mensagem |
|---|---|---|
| A — Participante simples | `with_companion=False` | Convite + CTA de confirmação |
| B — Com acompanhante | `with_companion=True` | Convite + lembrete sobre o acompanhante |
| C — Acompanhante pendente | `is_companion=True` | Lembrete para completar inscrição |

- Disparo multicanal: Email (SMTP) + WhatsApp (Twilio)
- Até 3 tentativas com intervalo de 7 dias

#### Fase 4 — Follow-up Pós-Evento

| Situação | Ação da IA |
|---|---|
| **Presentes** (`attended=True`) | Referencia algo do evento + proposta de reunião de 20–30min |
| **Ausentes** (`attended=False`) | Oferece material exclusivo + convite para call, sem expor o no-show |

- O admin encerra o evento pelo dashboard → pós-evento é agendado com delay configurável
- Mensagens geradas individualmente pelo Gemini com base no perfil enriquecido de cada lead

---

## 📡 Endpoints da API (Referência Completa)

> 📊 **Total: 31 endpoints** · Documentação interativa completa em [http://localhost:8000/docs](http://localhost:8000/docs)

### 🔓 Públicos (sem autenticação)

#### `POST /api/v1/leads/` — Registrar Lead

```bash
curl -X POST http://localhost:8000/api/v1/leads/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Carlos Mendes",
    "email": "carlos@techcorp.com.br",
    "phone": "+5511991234567",
    "company": "TechCorp Brasil",
    "role": "CISO",
    "company_size": "500-1000",
    "sector": "Financeiro",
    "linkedin_url": "https://linkedin.com/in/carlos-mendes",
    "lgpd_consent": true
  }'
```

#### `POST /api/v1/leads/` — Registrar Lead com Acompanhante

```bash
curl -X POST http://localhost:8000/api/v1/leads/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ana Ferreira",
    "email": "ana@empresa.com.br",
    "phone": "+5511999887766",
    "company": "CyberSec Brasil",
    "role": "Diretora de TI",
    "sector": "Tecnologia",
    "with_companion": true,
    "companion_email": "joao@cybersec.com.br",
    "companion_relationship": "director",
    "lgpd_consent": true
  }'
```

> **Vínculos profissionais aceitos:** `partner`, `director`, `manager`, `coordinator`, `team_member`, `colleague`, `business_partner`, `guest_executive`

#### `GET /api/v1/leads/spots` — Verificar Vagas Disponíveis

```bash
curl http://localhost:8000/api/v1/leads/spots
# Retorna: { "capacity": 120, "registered": 3, "remaining": 117, "is_full": false }
```

#### `POST /api/v1/leads/checkin` — Check-in via QR Code

```bash
curl -X POST http://localhost:8000/api/v1/leads/checkin \
  -H "Content-Type: application/json" \
  -d '{"email": "carlos@techcorp.com.br"}'
```

#### `GET /api/v1/leads/linkedin-preview` — Enriquecer Perfil via LinkedIn (Gemini)

```bash
curl "http://localhost:8000/api/v1/leads/linkedin-preview?username=carlos-mendes"
# Gemini usa seu conhecimento de treinamento para identificar a pessoa
```

#### `GET /health` — Health Check

```bash
curl http://localhost:8000/health
# Retorna: { "status": "healthy", "environment": "development",
#            "gemini_configured": true, "smtp_configured": true, "twilio_configured": false }
```

---

### 🔑 Protegidos por API Key

**Header necessário:** `X-API-Key: vigil-internal-api-key-2026`

#### `GET /api/v1/leads/` — Listar Leads (com filtros)

```bash
# Listar todos
curl http://localhost:8000/api/v1/leads/ \
  -H "X-API-Key: vigil-internal-api-key-2026"

# Filtrar por fase do funil
curl "http://localhost:8000/api/v1/leads/?phase=pre_event" \
  -H "X-API-Key: vigil-internal-api-key-2026"

# Filtrar por status
curl "http://localhost:8000/api/v1/leads/?status=confirmed&limit=10" \
  -H "X-API-Key: vigil-internal-api-key-2026"
```

> **Filtros disponíveis:** `phase` (capture, enrichment, pre_event, companion_pending, post_event, closed), `status` (new, enriched, contacted, confirmed, declined, no_response, attended, no_show, followed_up, meeting_booked, out_of_icp, pending_review), `limit` (1-200), `offset`

#### `GET /api/v1/leads/{id}` — Buscar Lead por ID

```bash
curl http://localhost:8000/api/v1/leads/1 \
  -H "X-API-Key: vigil-internal-api-key-2026"
```

#### `PATCH /api/v1/leads/{id}` — Atualizar Lead

```bash
curl -X PATCH http://localhost:8000/api/v1/leads/1 \
  -H "X-API-Key: vigil-internal-api-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"event_notes": "Interessado em painel sobre Zero Trust", "attended": true}'
```

#### `POST /api/v1/leads/{id}/post-event` — Disparar Follow-up Pós-Evento

```bash
curl -X POST "http://localhost:8000/api/v1/leads/1/post-event?attended=true&event_notes=Participou+do+painel+de+IA" \
  -H "X-API-Key: vigil-internal-api-key-2026"
```

---

### 🔐 Admin (JWT Bearer Token)

> **Passo 1:** Faça login para obter o token. **Passo 2:** Use o token em todas as chamadas abaixo.

#### `POST /api/v1/admin/auth/login` — Login → Token JWT

```bash
curl -X POST http://localhost:8000/api/v1/admin/auth/login \
  -d "username=admin&password=vigil2026"
# Retorna: { "access_token": "eyJhbG...", "token_type": "bearer", "username": "admin" }
```

> ⚠️ **O token expira em 5 minutos.** Faça login novamente quando expirar.

---

#### 👥 Leads (Admin)

#### `GET /api/v1/admin/leads` — Listar Todos os Participantes

```bash
curl http://localhost:8000/api/v1/admin/leads \
  -H "Authorization: Bearer <token>"
```

#### `GET /api/v1/admin/leads?pending_only=true` — Listar Pendentes de Aprovação

```bash
curl "http://localhost:8000/api/v1/admin/leads?pending_only=true" \
  -H "Authorization: Bearer <token>"
```

#### `POST /api/v1/admin/leads/{id}/qualify` — Aprovar Lead

```bash
curl -X POST http://localhost:8000/api/v1/admin/leads/1/qualify \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve", "notes": "Perfil validado pelo admin"}'
```

#### `POST /api/v1/admin/leads/{id}/qualify` — Rejeitar Lead

```bash
curl -X POST http://localhost:8000/api/v1/admin/leads/1/qualify \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "reject", "notes": "Não atende ao perfil do evento"}'
```

---

#### 📅 Evento (Admin)

#### `GET /api/v1/admin/event` — Dados do Evento

```bash
curl http://localhost:8000/api/v1/admin/event \
  -H "Authorization: Bearer <token>"
```

#### `PUT /api/v1/admin/event` — Atualizar Evento

```bash
curl -X PUT http://localhost:8000/api/v1/admin/event \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2026-07-15",
    "event_time": "09:00",
    "location": "WTC Events Center, São Paulo",
    "speakers": ["Dr. João Silva — CISO, Banco Itaú", "Maria Santos — VP Security, Nubank"],
    "post_event_delay_minutes": 5,
    "pre_event_reminder_days": [30, 15, 7, 3, 1],
    "pre_event_send_time": "09:00"
  }'
```

#### `POST /api/v1/admin/event/end` — Encerrar Evento (dispara régua pós-evento)

```bash
curl -X POST http://localhost:8000/api/v1/admin/event/end \
  -H "Authorization: Bearer <token>"
# Retorna: { "message": "Evento encerrado com sucesso",
#            "post_event_scheduled_at": "2026-07-15T18:05:00+00:00", "delay_minutes": 5 }
```

#### `PUT /api/v1/admin/event/schedule-end` — Agendar Encerramento Automático

```bash
curl -X PUT http://localhost:8000/api/v1/admin/event/schedule-end \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"scheduled_end_at": "2026-07-15T18:00:00-03:00"}'
# O evento será encerrado automaticamente no horário agendado
```

---

#### 📝 Templates / Prompts da IA (Admin)

#### `GET /api/v1/admin/templates` — Listar Templates

```bash
curl http://localhost:8000/api/v1/admin/templates \
  -H "Authorization: Bearer <token>"
```

#### `POST /api/v1/admin/templates` — Criar Novo Template

```bash
curl -X POST http://localhost:8000/api/v1/admin/templates \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "[Prompt] Meu Prompt Custom",
    "phase": "pre_event",
    "channel": "BOTH",
    "subject": "Vigil Summit — {PRIMEIRO_NOME}, não perca!",
    "body": "Seu trabalho é gerar um lembrete personalizado...",
    "sequence_order": 2,
    "is_active": true
  }'
```

> **Fases disponíveis:** `confirmation`, `pre_event`, `pre_event_participant`, `pre_event_with_companion`, `pre_event_companion_pending`, `post_event`, `post_event_attended`, `post_event_no_show`, `reply`
>
> **Canais:** `EMAIL`, `WHATSAPP`, `BOTH`

#### `PUT /api/v1/admin/templates/{id}` — Editar Template

```bash
curl -X PUT http://localhost:8000/api/v1/admin/templates/1 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "[Prompt] Confirmação — Aprovado (editado)",
    "phase": "confirmation",
    "channel": "EMAIL",
    "subject": "Vaga confirmada, {PRIMEIRO_NOME}!",
    "body": "Seu novo prompt personalizado aqui...",
    "sequence_order": 1,
    "is_active": true
  }'
```

#### `DELETE /api/v1/admin/templates/{id}` — Remover Template

```bash
curl -X DELETE http://localhost:8000/api/v1/admin/templates/3 \
  -H "Authorization: Bearer <token>"
# Retorna: { "message": "Template removido" }
```

---

#### ⏰ Scheduler (Admin)

#### `GET /api/v1/admin/scheduler/status` — Status do Scheduler

```bash
curl http://localhost:8000/api/v1/admin/scheduler/status \
  -H "Authorization: Bearer <token>"
# Retorna: { "post_event_next_run": "2026-07-15T18:05:00+00:00", "has_scheduled_job": true }
```

#### `POST /api/v1/admin/scheduler/trigger-test` — Disparar Follow-up de Teste

```bash
curl -X POST http://localhost:8000/api/v1/admin/scheduler/trigger-test \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"delay_minutes": 1}'
# Agenda disparo da régua pós-evento em 1 minuto (sem encerrar o evento)
```

#### `POST /api/v1/admin/scheduler/trigger-pre-event-test` — Disparar Régua Pré-Evento (Teste)

```bash
curl -X POST http://localhost:8000/api/v1/admin/scheduler/trigger-pre-event-test \
  -H "Authorization: Bearer <token>"
# Dispara imediatamente para todas as 3 personas, ignorando agendamento diário
# Retorna: { "total_sent": 5, "total_failed": 0, "by_persona": [...] }
```

---

#### 📣 Broadcast Pré-Evento (Admin)

#### `POST /api/v1/admin/broadcast/pre-event/all` — Broadcast Geral (3 personas)

```bash
curl -X POST http://localhost:8000/api/v1/admin/broadcast/pre-event/all \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

#### `POST /api/v1/admin/broadcast/pre-event/participant` — Persona A (Participantes)

```bash
curl -X POST http://localhost:8000/api/v1/admin/broadcast/pre-event/participant \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

#### `POST /api/v1/admin/broadcast/pre-event/with-companion` — Persona B (Com Acompanhante)

```bash
curl -X POST http://localhost:8000/api/v1/admin/broadcast/pre-event/with-companion \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

#### `POST /api/v1/admin/broadcast/pre-event/companion-pending` — Persona C (Acompanhante Pendente)

```bash
curl -X POST http://localhost:8000/api/v1/admin/broadcast/pre-event/companion-pending \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

#### `GET /api/v1/admin/broadcast/pre-event/status` — Status da Régua Pré-Evento

```bash
curl http://localhost:8000/api/v1/admin/broadcast/pre-event/status \
  -H "Authorization: Bearer <token>"
# Retorna: { "job_registered": true, "next_run": "...", "send_time": "09:00",
#            "reminder_days_configured": [30,15,7,3,1], "days_until_event": 25, "triggers_today": false }
```

---

### 📥 Webhooks (Inbound — callbacks de serviços externos)

#### `POST /api/v1/webhooks/inbound` — Resposta Genérica de Lead

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/inbound \
  -H "Content-Type: application/json" \
  -d '{
    "lead_email": "carlos@techcorp.com.br",
    "channel": "email",
    "message": "Confirmo minha participação!"
  }'
# O agente de IA processa a intenção e responde automaticamente
```

#### `POST /api/v1/webhooks/twilio/whatsapp` — Webhook Twilio WhatsApp

```
Configure no Twilio Console → Messaging → Sandbox → "When a message comes in":
URL: https://seu-dominio.com/api/v1/webhooks/twilio/whatsapp
Método: POST
```

#### `POST /api/v1/webhooks/sendgrid/inbound` — Webhook SendGrid Email

```
Configure no SendGrid → Settings → Inbound Parse:
URL: https://seu-dominio.com/api/v1/webhooks/sendgrid/inbound
```

---

## 🧪 Testes

> **Os testes usam SQLite em memória** — você **NÃO** precisa do MySQL rodando para executar os testes.

```bash
cd vigil_agent
source .venv/bin/activate

# Rodar todos os testes
pytest

# Com output detalhado
pytest -v

# Com cobertura de código
pytest --cov=app tests/

# Testes específicos por módulo:
pytest tests/test_api.py -v        # Testes da API de leads (CRUD + check-in)
pytest tests/test_agent.py -v      # Testes do agente LangGraph
pytest tests/test_services.py -v   # Testes de notification + enrichment
pytest tests/test_admin.py -v      # Testes do painel administrativo e JWT
```

### O que cada módulo de teste cobre:

| Arquivo | Cobertura |
|---|---|
| `test_api.py` | Criação de lead, validação LGPD, email duplicado, capacidade máxima, check-in, filtros |
| `test_agent.py` | Grafo LangGraph, routing condicional, classificação de elegibilidade, enriquecimento |
| `test_services.py` | Envio de email (SMTP mock), WhatsApp (Twilio mock), enrichment Gemini + fallback |
| `test_admin.py` | Login JWT, CRUD evento, CRUD templates, aprovação/rejeição de leads, autenticação |

---

## 📊 Regras de Negócio

| Regra | Valor |
|---|---|
| Score mínimo para contato | 0.60 |
| Máximo de tentativas pré-evento | 3 |
| Intervalo entre tentativas | 7 dias |
| Meta de show rate | > 70% |
| Canal padrão | WhatsApp (com fallback para Email) |
| Vagas disponíveis | 120 (exclui `out_of_icp` da contagem) |
| Acompanhantes permitidos | Apenas com vínculo profissional |
| Expiração do JWT (admin) | 5 minutos |

### Pesos da Qualificação ICP (Fallback)

| Critério | Peso |
|---|---|
| Cargo | 40% |
| Tamanho da empresa | 35% |
| Setor | 20% |
| LinkedIn ativo | 5% |

### Mapa de Status do Lead

```
new ──► enriched ──► contacted ──► confirmed ──► attended ──► followed_up ──► meeting_booked
 │           │            │             │                          │
 │           │            └── no_response ──► (closed)             │
 │           │            └── declined ──────► (closed)            │
 │           └── out_of_icp ────────────────► (closed)             │
 └── pending_review ──► [admin aprova] ──► new (re-entra no funil) │
                    └── [admin rejeita] ──► out_of_icp (closed)
```

---

## 🔒 LGPD

- ✅ Consentimento explícito obrigatório no registro (`lgpd_consent: true`)
- ✅ Data de consentimento armazenada (`consent_at`)
- ✅ Dados de enriquecimento usam apenas dados públicos + inferências por IA
- ✅ Acompanhantes limitados a vínculos profissionais (sem dados pessoais sensíveis)
- ✅ Email de consentimento enviado antes de qualquer processamento

---

## 🏗️ Cenário de Escala (Bônus)

Para escalar para **10 eventos simultâneos com 10.000 participantes**:

1. **Filas de mensageria**: substituir `BackgroundTasks` por Celery + Redis (isolamento por evento)
2. **Multi-tenancy**: adicionar campo `event_id` nas entidades
3. **Rate limiting**: por canal de notificação (WhatsApp tem limites da API Twilio)
4. **Cache de enriquecimento**: Redis com TTL de 24h para evitar re-enriquecimento
5. **Observabilidade**: Prometheus + Grafana para monitoramento de chamadas ao Gemini

O grafo LangGraph é stateless por design — escala horizontalmente sem refatoração.

---

## 🛠️ Troubleshooting

<details>
<summary><strong>❌ Erro: "Falha na conexão [2003]" ao rodar validate_db.py</strong></summary>

O MySQL ainda não subiu completamente. Execute:

```bash
docker compose up -d
# Aguarde 30 segundos
docker ps   # Verifique se o status é "healthy"
python ../scripts/validate_db.py
```

</details>

<details>
<summary><strong>❌ Erro: "Module not found" ao iniciar o servidor</strong></summary>

Certifique-se de estar no diretório correto e com o venv ativo:

```bash
cd vigil_agent
source .venv/bin/activate
pip install -r ../requirements.txt
```

</details>

<details>
<summary><strong>❌ Emails não chegam</strong></summary>

1. Verifique se `SMTP_USER` e `SMTP_PASSWORD` estão preenchidos no `.env`
2. A senha SMTP deve ser uma **App Password** do Gmail, não sua senha normal
3. Se houver erro nos logs, o sistema continua funcionando (modo simulado)
4. Verifique os logs: as mensagens aparecem como `[Email MOCK]` ou `[Email SMTP]`

</details>

<details>
<summary><strong>❌ Gemini retorna erro ou usa fallback</strong></summary>

1. Verifique se `API_KEY_AI` está preenchido no `.env`
2. Confirme que a chave é válida em [aistudio.google.com](https://aistudio.google.com)
3. O fallback determinístico é ativado automaticamente — o sistema não para
4. Verifique nos logs: `[Enrichment/Gemini] ✅` = sucesso, `→ usando fallback` = fallback ativo

</details>

<details>
<summary><strong>❌ Porta 3306 já em uso</strong></summary>

Outro serviço MySQL está usando a porta. Opções:

```bash
# Parar o MySQL local
sudo systemctl stop mysql

# OU alterar a porta no docker-compose.yml
ports:
  - "3307:3306"
# E atualizar DATABASE_URL no .env para usar a porta 3307
```

</details>

---

<div align="center">

**Desenvolvido como case técnico para AI Engineer @ Pareto**

Vigil.AI © 2026 · [Documentação da API](http://localhost:8000/docs)

</div>
]]>
