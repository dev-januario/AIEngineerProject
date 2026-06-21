# Vigil.AI — Autonomous Funnel Agent

> **Agente de IA autônomo** para automatizar o funil completo do **Vigil Summit — Segurança para a Era da IA**, evento exclusivo para executivos de cibersegurança (CISOs, CTOs, Diretores de TI).

---

## 🏗️ Arquitetura

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

### Stack Tecnológico

| Camada | Tecnologia | Justificativa |
|---|---|---|
| **API** | FastAPI (async) | Alto throughput, geração automática de docs, DI nativa |
| **Banco** | MySQL 8.4 + SQLAlchemy Async | ACID, suporte a JSON, contêiner Docker pronto |
| **Orquestração IA** | LangGraph | Grafo de estado determinístico com ramificações condicionais |
| **LLM** | Gemini 3.5 Flash (Google) | Modelo gratuito com bom reasoning e grounding |
| **Email** | SMTP via Gmail App Password | Envio direto sem dependência de serviço externo |
| **WhatsApp** | Twilio Sandbox | Envio via API REST com fallback simulado |
| **Migrações** | Alembic | Versionamento de schema, rollback seguro |
| **Testes** | Pytest + HTTPX | Testes assíncronos com SQLite em memória |

---

## 🚀 Quick Start

### 1. Clonar e configurar ambiente

```bash
cd vigil_agent
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp ../.env.example ../.env
# Edite o .env e adicione suas chaves:
# - API_KEY_AI (Google Gemini)
# - SMTP_USER / SMTP_PASSWORD (Gmail App Password)
# - TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN (opcional, para WhatsApp)
```

### 3. Subir MySQL com Docker

```bash
docker compose -f ../docker-compose.yml up -d
```

### 4. Validar banco de dados

```bash
python ../scripts/validate_db.py
```

### 5. Iniciar o servidor

```bash
bash start.sh
# Ou diretamente:
# uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Acesse:
- **Landing Page:** http://localhost:8000/
- **Dashboard Admin:** http://localhost:8000/admin/login.html
- **API Docs:** http://localhost:8000/docs

---

## 📡 Endpoints Principais

### Registrar Lead (público — formulário da landing page)
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

### Listar leads (requer API Key)
```bash
curl http://localhost:8000/api/v1/leads/ \
  -H "X-API-Key: vigil-internal-api-key-2026"
```

### Painel Administrativo (JWT)
```bash
# Login → retorna JWT
curl -X POST http://localhost:8000/api/v1/admin/auth/login \
  -d "username=admin&password=vigil2026"

# Listar leads pendentes
curl http://localhost:8000/api/v1/admin/leads?pending_only=true \
  -H "Authorization: Bearer <token>"

# Aprovar lead manualmente
curl -X POST http://localhost:8000/api/v1/admin/leads/1/qualify \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve", "notes": "Perfil validado"}'
```

---

## 🤖 Fases do Funil

### Fase 1 — Captura & Qualificação Imediata
- Lead registrado via `POST /api/v1/leads/`
- Validação de dados e consentimento LGPD
- **Qualificação determinística** por cargo →
  - `approved`: CISOs, CTOs, Diretores, VPs, Fundadores → confirmação imediata
  - `pending_review`: Gerentes, Coordenadores, Especialistas → aguarda aprovação do admin
  - `not_eligible`: Cargos fora do ICP → email de cortesia

### Fase 2 — Enriquecimento (IA)
- Gemini analisa os dados disponíveis e retorna perfil enriquecido
- Calcula **score ICP** (0.0 – 1.0)
- Leads com score < 0.60 são arquivados automaticamente

### Fase 3 — Engajamento Pré-Evento
- **Gemini gera mensagens personalizadas** com base no perfil enriquecido
- Disparo multicanal: Email (SMTP) + WhatsApp (Twilio)
- Régua de 3 personas: Participante solo / c/ acompanhante / acompanhante pendente

### Fase 4 — Follow-up Pós-Evento
- **Presentes**: mensagem referenciando algo do evento + proposta de reunião
- **Ausentes**: recuperação com material exclusivo + convite para call

---

## 🧪 Executar Testes

```bash
cd vigil_agent

# Todos os testes (usando SQLite em memória — sem MySQL necessário)
pytest

# Com cobertura
pytest --cov=app tests/

# Apenas testes de API
pytest tests/test_api.py -v

# Apenas testes do agente
pytest tests/test_agent.py -v

# Testes de serviços (notification, enrichment)
pytest tests/test_services.py -v

# Testes do admin
pytest tests/test_admin.py -v
```

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

---

## 🔒 LGPD

- Consentimento explícito obrigatório no registro (`lgpd_consent: true`)
- Data de consentimento armazenada (`consent_at`)
- Dados de enriquecimento usam apenas fontes públicas e IA generativa
- Acompanhantes limitados a vínculos profissionais

---

## 🏗️ Escala (Bônus)

Para escalar para **10 eventos simultâneos com 10.000 participantes**:

1. **Filas de mensageria**: substituir `BackgroundTasks` por Celery + Redis (isolamento por evento)
2. **Multi-tenancy**: adicionar campo `event_id` nas entidades
3. **Rate limiting**: por canal de notificação (WhatsApp tem limites da API Twilio)
4. **Cache de enriquecimento**: Redis com TTL de 24h para evitar re-enriquecimento
5. **Observabilidade**: Prometheus + Grafana para monitoramento de chamadas ao Gemini

O grafo LangGraph é stateless por design — escala horizontalmente sem refatoração.
