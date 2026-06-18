# Vigil.AI — Autonomous Funnel Agent

> **Agente de IA autônomo** para automatizar o funil completo do **Vigil Summit — Segurança para a Era da IA**, evento exclusivo para executivos de cibersegurança (CISOs, CTOs, Diretores de TI).

---

## 🏗️ Arquitetura

```
POST /api/v1/leads/
       │
       ▼
  [FastAPI] ──► [PostgreSQL]
       │
       ▼ (background task)
  [LangGraph Agent]
       │
       ├── node_enrich_lead ────► [Enrichment Service] ──► Score ICP
       │
       ├── node_score_and_route ─► Qualificado? ──┬── Sim ──► pre_event
       │                                          └── Não ──► closed
       │
       ├── node_send_pre_event ──► [Notification Service]
       │                               ├── WhatsApp (Twilio)
       │                               └── Email (SendGrid)
       │
       ├── node_process_response ─► Inbound via webhook
       │
       └── node_send_post_event ──► Follow-up personalizado (Claude)
```

### Stack Tecnológico

| Camada | Tecnologia | Justificativa |
|---|---|---|
| **API** | FastAPI (async) | Alto throughput, geração automática de docs, DI nativa |
| **Banco** | PostgreSQL + SQLAlchemy Async | ACID, JSONB para dados dinâmicos, suporte a Alembic |
| **Orquestração IA** | LangGraph | Grafo de estado determinístico com ramificações condicionais |
| **LLM** | Claude 3.5 Sonnet (Anthropic) | Superior em reasoning, seguimento de instruções e tool use |
| **Migrações** | Alembic | Versionamento de schema, rollback seguro |
| **Testes** | Pytest + HTTPX | Testes assíncronos sem necessidade de PostgreSQL real |

---

## 🚀 Quick Start

### 1. Clonar e configurar ambiente

```bash
cd vigil_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env e adicione sua ANTHROPIC_API_KEY
```

### 3. Subir PostgreSQL com Docker

```bash
docker compose up -d
```

### 4. Rodar migrações

```bash
alembic upgrade head
```

### 5. Iniciar o servidor

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Acesse a documentação interativa em: **http://localhost:8000/docs**

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
  -H "X-API-Key: vigil-internal-api-key-2024"
```

### Registrar presença e disparar follow-up pós-evento
```bash
curl -X POST "http://localhost:8000/api/v1/leads/1/post-event?attended=true&event_notes=Interesse+em+Zero+Trust" \
  -H "X-API-Key: vigil-internal-api-key-2024"
```

### Simular resposta inbound do lead (webhook)
```bash
curl -X POST http://localhost:8000/api/v1/webhooks/inbound \
  -H "Content-Type: application/json" \
  -d '{
    "lead_email": "carlos@techcorp.com.br",
    "channel": "whatsapp",
    "message": "Confirmo minha presença!"
  }'
```

---

## 🤖 Fases do Funil

### Fase 1 — Captura
- Lead registrado via `POST /api/v1/leads/`
- Validação de dados e consentimento LGPD
- Trigger automático para enriquecimento

### Fase 2 — Enriquecimento (IA)
- Busca dados públicos: cargo, porte, setor, presença LinkedIn
- Calcula **score ICP** (0.0 – 1.0):
  - Cargo: 40% (CISO/CTO = máximo)
  - Porte da empresa: 35% (200+ funcionários)
  - Setor: 20% (Financeiro, Saúde, Governo = máximo)
  - LinkedIn ativo: 5%
- Leads com score < 0.60 são arquivados automaticamente

### Fase 3 — Engajamento Pré-Evento
- **Claude gera mensagens 100% personalizadas** com base no perfil enriquecido
- Sequência de até 3 tentativas (7 dias de intervalo)
- Canal preferencial: WhatsApp (se phone disponível) → Email
- Respostas processadas via webhook → agente interpreta e responde

### Fase 4 — Follow-up Pós-Evento
- **Presentes**: mensagem referenciando algo do evento + proposta de reunião
- **Ausentes**: recuperação com material exclusivo + convite para call

---

## 🧪 Executar Testes

```bash
# Todos os testes (usando SQLite em memória — sem PostgreSQL necessário)
pytest

# Com cobertura
pytest --cov=app tests/

# Apenas testes de API
pytest tests/test_api.py -v

# Apenas testes do agente
pytest tests/test_agent.py -v
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

---

## 🔒 LGPD

- Consentimento explícito obrigatório no registro (`lgpd_consent: true`)
- Data de consentimento armazenada (`consent_at`)
- Dados de enriquecimento usam apenas fontes públicas
- Possibilidade de exclusão por email (não implementado nesta versão)

---

## 📧 Acesso de Teste

Para testes da equipe Pareto, o email `ramon@pareto.io` pode ser usado como lead de teste.

**API Key de teste**: `vigil-internal-api-key-2024`

---

## 🏗️ Escala (Bônus)

Para escalar para **10 eventos simultâneos com 10.000 participantes**:

1. **Filas de mensageria**: substituir `BackgroundTasks` por Celery + Redis (isolamento por evento)
2. **Multi-tenancy**: adicionar campo `event_id` nas entidades
3. **Rate limiting**: por canal de notificação (WhatsApp tem limites da API Twilio)
4. **Cache de enriquecimento**: Redis com TTL de 24h para evitar re-enriquecimento
5. **Observabilidade**: LangSmith para tracing de chamadas ao Claude, Prometheus + Grafana

O grafo LangGraph é stateless por design — escala horizontalmente sem refatoração.
