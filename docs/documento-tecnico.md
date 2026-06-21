# Documento Técnico — Vigil.AI Funnel Agent

> Documento técnico completo cobrindo todos os entregáveis do Case AI Engineer (Pareto 2026). Para instruções de instalação e uso da aplicação, consulte o [README principal](../README.md).

---

## Índice

- [1. Arquitetura da Solução](#1-arquitetura-da-solução)
- [2. Stack Tecnológico Justificado](#2-stack-tecnológico-justificado)
- [3. Réguas de Comunicação](#3-réguas-de-comunicação)
- [4. Estratégia de Dados e Personalização](#4-estratégia-de-dados-e-personalização)
- [5. Decisões Estratégicas e Racional](#5-decisões-estratégicas-e-racional)
- [6. Plano de Execução — Primeiros 5 Dias](#6-plano-de-execução--primeiros-5-dias)
- [Canal de Comunicação — Justificativa](#canal-de-comunicação--justificativa)
- [Cenário de Escala (Bônus)](#cenário-de-escala-bônus)

---

## 1. Arquitetura da Solução

### 1.1 — Diagrama Geral

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
           ├──────────────────┬──────────────────┐
           ▼                  ▼                  ▼
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
                    │  (grafo de estado)   │
                    │                      │
                    │  node_enrich_lead    │
                    │       ▼              │
                    │  node_score_route    │
                    │       ▼              │
                    │  node_send_pre_event │
                    │       ▼              │
                    │  node_process_resp   │
                    │       ▼              │
                    │  node_send_post_event│
                    └─────────────────────┘
```

### 1.2 — Camadas da Aplicação

| Camada | Componentes | Responsabilidade |
|---|---|---|
| **Frontend** | `index.html`, `checkin.html`, `admin/dashboard.html` | Captação de leads, check-in via QR Code, painel de gestão |
| **API** | FastAPI — `leads.py`, `admin.py`, `broadcast.py`, `webhooks.py` | Orquestra todas as operações. Valida dados, aplica segurança (API Key / JWT), dispara background tasks |
| **Agente IA** | LangGraph — `graph.py` | Grafo de estado que gerencia o ciclo de vida do lead do enriquecimento ao follow-up |
| **Serviços** | `enrichment.py`, `notification.py`, `scheduler.py`, `pre_event_scheduler.py`, `imap_poller.py` | Lógica de negócio isolada: enriquecimento via Gemini, envio multicanal, agendamento temporal, polling de respostas |
| **Banco de Dados** | MySQL 8.4 + SQLAlchemy Async — `leads`, `events`, `message_templates`, `admin_users` | Persistência de todos os dados do funil com suporte a JSON nativo |
| **LLM** | Gemini 3.5 Flash via `google-generativeai` | Geração de mensagens personalizadas, enriquecimento de perfil, classificação de intenção em respostas |

### 1.3 — Fluxo de Dados Entre os Componentes

```
POST /api/v1/leads/
       │
       ▼
 [FastAPI] ──► [MySQL 8.4]  ← persiste o lead imediatamente
       │
       ▼ (background task — não bloqueia a resposta HTTP)
 [Gemini AI — Qualificação & Enriquecimento]
       │
       ├── classify_lead_eligibility ──► approved / pending_review / not_eligible
       │
       ├── enrich_lead_profile ────────► Score ICP (0.0–1.0) + hooks de personalização
       │
       ├── _send_ai_registration_email ► Email de confirmação gerado pelo Gemini
       │
       └── [LangGraph Agent]
              ├── node_enrich_lead      ← completa enriquecimento no estado do grafo
              ├── node_score_and_route  ← decide: continuar funil ou arquivar
              ├── node_send_pre_event   ── [Notification Service]
              │                              ├── WhatsApp (Twilio)
              │                              └── Email (SMTP/Gmail)
              ├── node_process_response ← inbound via webhook (lead responde)
              └── node_send_post_event  ← follow-up personalizado pós-evento


Webhook inbound (lead responde por email ou WhatsApp):
  Twilio → POST /webhooks/twilio/whatsapp ─┐
  Gmail IMAP polling ──────────────────────┤─► node_process_response ──► resposta automática
  SendGrid → POST /webhooks/sendgrid/inbound┘
```

### 1.4 — Onde Cada Fase do Funil se Encaixa

| Fase | Componente Principal | Gatilho |
|---|---|---|
| **Fase 1 — Captação** | `POST /api/v1/leads/` + `index.html` | Lead preenche o formulário |
| **Fase 2 — Enriquecimento** | `enrichment.py` + `node_enrich_lead` | Background task após registro |
| **Fase 3 — Engajamento Pré-Evento** | `pre_event_scheduler.py` + `node_send_pre_event` | Job APScheduler diário (dias configuráveis) |
| **Fase 4 — Follow-up Pós-Evento** | `scheduler.py` + `node_send_post_event` | Admin encerra evento → delay configurável |
| **Inbound (respostas)** | `webhooks.py` + `imap_poller.py` + `node_process_response` | Lead responde por qualquer canal |

---

## 2. Stack Tecnológico Justificado

### 2.1 — Visão Geral

| Camada | Tecnologia | Versão | Justificativa |
|---|---|---|---|
| **API** | FastAPI | 0.115 | Alto throughput com async nativo. Geração automática de docs Swagger/ReDoc. DI (Depends) simplifica injeção de sessão de banco e autenticação. Ideal para I/O-bound com chamadas a LLMs e banco. |
| **Banco de Dados** | MySQL 8.4 + SQLAlchemy Async | 8.4 / 2.0 | ACID completo, suporte nativo a coluna JSON (para `enrichment_data` e `communication_log`), container Docker oficial com health check. SQLAlchemy async evita bloqueio de event loop em endpoints de alta concorrência. |
| **Orquestração IA** | LangGraph | 0.2 | Único framework que modela o funil como grafo de estado determinístico com re-entrada. Permite que um webhook recebido dias depois seja processado exatamente no nó correto sem reconstruir contexto. Stateless por design — escala horizontal sem refatoração. |
| **LLM** | Gemini 3.5 Flash (Google AI) | API v0.8 | Gratuito com 1.500 req/dia — zero custo para desenvolvimento e demonstração. Reasoning sólido para geração de mensagens personalizadas. Ver [Seção 5.3](#53--gemini-35-flash-como-llm) para contexto completo da decisão. |
| **Email** | SMTP via `aiosmtplib` | 3.0+ | Envio async direto ao servidor SMTP sem dependência de serviço externo. Gmail App Password funciona sem aprovação de terceiros. Fallback para log simulado quando sem credenciais. |
| **WhatsApp** | Twilio Sandbox | SDK 9.0+ | API REST com sandbox gratuito para desenvolvimento sem aprovação do Meta. Fallback automático para email quando Twilio não configurado. |
| **Migrações** | Alembic + `validate_db.py` | 1.14 | Alembic para versionamento formal de schema. `validate_db.py` como script standalone que cria tabelas do zero — elimina a necessidade de rodar migrações em sequência para novos ambientes. |
| **Testes** | Pytest + HTTPX + SQLite | 8.3 / 0.28 | Testes assíncronos com banco SQLite em memória — sem dependência de MySQL. `pytest-asyncio` com `asyncio_mode=auto` simplifica fixtures. HTTPX com `ASGITransport` testa a API sem servidor HTTP real. |
| **Agendamento** | APScheduler | 3.x | Scheduler in-process, sem dependência de Redis ou fila externa. Suficiente para o volume de um evento. Para escala (ver [Cenário de Escala](#cenário-de-escala-bônus)), seria substituído por Celery + Redis. |
| **Segurança** | JWT (`python-jose`) + API Key + bcrypt | 3.3 | JWT para sessão do admin com expiração curta (5 min). API Key para endpoints internos/integração. bcrypt para senhas de admin. |
| **Deploy** | Docker Compose (MySQL) | v2 | MySQL containerizado com health check garante ambiente reproduzível. A aplicação FastAPI roda diretamente com `uvicorn` — para produção, containerizar também a app. |

### 2.2 — Decisões Não Óbvias

**Por que MySQL e não PostgreSQL?**
Postgres seria igualmente válido. MySQL foi escolhido por familiaridade e pelo container oficial `mysql:8.4` ter health check nativo para `docker compose`. A mudança seria trivial — apenas alterar o driver (`aiomysql` → `asyncpg`) e a URL de conexão.

**Por que SQLAlchemy async e não SQLModel ou Tortoise?**
SQLAlchemy 2.0 async é o padrão de facto do ecossistema FastAPI. Maior base de documentação, suporte a todos os tipos de coluna necessários (JSON, Enum, DateTime com timezone) e compatibilidade total com Alembic para migrações.

**Por que `validate_db.py` em vez de só Alembic?**
Alembic requer que as migrações sejam rodadas em ordem e que o banco exista previamente. Para onboarding de um novo avaliador, um script que cria tudo do zero em uma chamada é mais confiável do que instruções de migração que podem falhar por inconsistência de estado.

---

## 3. Réguas de Comunicação

### 3.1 — Régua Pré-Evento

A régua pré-evento funciona como uma jornada proativa entre a inscrição do lead e o dia do evento. O objetivo é duplo: confirmar presença e criar antecipação de valor — combatendo o no-show com relevância, não com spam.

#### Gatilhos e Timing

O admin configura os dias de disparo no painel (campo `pre_event_reminder_days`, padrão: `[30, 15, 7, 3, 1]`). Um job APScheduler roda diariamente no horário configurado (`pre_event_send_time`, padrão: `09:00`) e verifica quantos dias faltam para o evento. Se o número de dias corresponde a um dos gatilhos configurados, a régua é disparada para todos os leads elegíveis.

```
D-30: Boas-vindas + agenda geral + o que esperar do evento
D-15: Palestrantes confirmados + pain point do setor do lead
D-7:  Lembrete de urgência + nudge para o acompanhante (quando aplicável)
D-3:  "Quase lá" + logística prática (endereço, estacionamento, credencial)
D-1:  "Amanhã" — última confirmação + WhatsApp direto
```

**Regra de negócio — Lead não responde:** se após D-15 o lead não confirmou presença explicitamente, a mensagem de D-7 usa um tom diferente (mais direto, com CTA de "confirmar em 1 clique"). Não há rastreamento de abertura de e-mail nativo, mas o sistema infere engajamento pela ausência de resposta via webhook.

**Regra de negócio — Lead confirma:** assim que o agente processa uma resposta de confirmação (`node_process_response` detecta intenção "confirmação"), o lead muda para status `CONFIRMED` e a régua de lembrete de presença é encerrada. Apenas lembretes logísticos (D-3 e D-1) continuam.

**Regra de negócio — Lead declina:** status muda para `DECLINED`. Régua encerrada. Nenhuma comunicação adicional.

**Regra de negócio — Máximo de tentativas:** 3 tentativas por fase. Se atingido sem resposta, status muda para `NO_RESPONSE` e lead é colocado em stand-by.

#### 3 Personas Separadas

| Persona | Critério | Foco da Mensagem |
|---|---|---|
| **A — Participante** | `with_companion = False` | Convite, agenda, valor do evento para o cargo/setor |
| **B — Com Acompanhante** | `with_companion = True` | Idem + nudge para o acompanhante confirmar inscrição |
| **C — Acompanhante Pendente** | `is_companion = True` e fase `COMPANION_PENDING` | Urgência para completar inscrição antes de fechar vagas |

---

#### Exemplo de Mensagem Pré-Evento — Persona A (D-7, CISO, setor Financeiro)

> *Gerada pelo Gemini com os hooks de personalização do enriquecimento. O template base existe no banco, mas o corpo da mensagem é criado individualmente para cada lead.*

**Assunto:** [Vigil Summit] Faltam 7 dias — o que um CISO do setor financeiro não pode perder

```
Carlos,

Com 7 dias para o Vigil Summit, quero chamar sua atenção para algo que 
foi desenhado especificamente para o seu contexto.

Como CISO em uma empresa financeira, você lida diariamente com o dilema 
entre velocidade de entrega e compliance com BACEN, LGPD e PCI-DSS. 
No Vigil Summit, dedicamos 2 horas a esse tema — com cases reais de 
três instituições financeiras que reduziram o tempo de resposta a 
incidentes em 60% sem comprometer a conformidade regulatória.

━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 15 de julho de 2026 às 09h00
📍 WTC Events Center — São Paulo, SP
🎫 Sua vaga está confirmada
━━━━━━━━━━━━━━━━━━━━━━━━━━

Alguma dúvida antes do evento? Basta responder este e-mail.

Até lá,
Equipe Vigil.AI
```

---

#### Exemplo de Mensagem Pré-Evento — Persona B (D-7, Diretor de TI com acompanhante, setor Saúde)

**Assunto:** [Vigil Summit] 7 dias — você e seu acompanhante confirmaram?

```
Ana,

Faltam 7 dias para o Vigil Summit e quero garantir que tudo esteja 
certo para você e seu acompanhante.

Como Diretora de TI no setor de saúde, a LGPD de dados de pacientes 
e os requisitos da ANS são dois dos maiores vetores de risco que você 
gerencia. O painel de auditoria e conformidade automática do Vigil Summit 
vai mostrar como outras organizações de saúde estão automatizando esse 
processo — e o que isso libera na agenda da equipe.

━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 15 de julho de 2026 às 09h00
📍 WTC Events Center — São Paulo, SP
━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Lembrete: seu acompanhante (joao@empresa.com.br) ainda não finalizou 
a inscrição. As vagas estão se esgotando — peça para ele confirmar hoje 
pelo link: https://vigil.ai/inscricao

Qualquer dúvida, responda este e-mail.

Equipe Vigil.AI
```

---

#### Exemplo de Mensagem Pré-Evento — Persona C (D-7, Acompanhante Pendente)

**Assunto:** [Vigil Summit] João, sua vaga está reservada — confirme até amanhã

```
João,

Ana Ferreira (Diretora de TI da CyberSec Brasil) reservou uma vaga 
para você no Vigil Summit — Segurança para a Era da IA.

O evento acontece em 7 dias e as vagas restantes estão se esgotando 
rapidamente. Para garantir sua participação, complete o cadastro agora:

→ https://vigil.ai/inscricao

━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 15 de julho de 2026 às 09h00
📍 WTC Events Center — São Paulo, SP
━━━━━━━━━━━━━━━━━━━━━━━━━━

Se já se inscreveu e recebeu esta mensagem por engano, ignore.

Equipe Vigil.AI
```

---

### 3.2 — Régua Pós-Evento

A régua pós-evento é o coração comercial do funil. Cada mensagem é gerada individualmente pelo Gemini com o contexto enriquecido do lead e, quando disponível, notas do evento (o que o participante viu, interesse demonstrado).

#### Gatilhos e Timing

O admin encerra o evento pelo dashboard → sistema agenda o disparo pós-evento com delay configurável (`post_event_delay_minutes`, padrão: 3 min para testes, recomendado: 1440 min = 24h para produção).

```
D+1:  1ª mensagem (referência ao evento, CTA de reunião)
D+7:  2ª mensagem (follow-up com oferta de material complementar)
─ Se agendar reunião → status MEETING_BOOKED → encerra régua
─ Se declinar → status DECLINED → encerra régua
─ Se sem resposta após 2ª → status NO_RESPONSE → encerra régua
```

**Regra de negócio — Presente vs. Ausente:**
- `attended = True`: mensagem referencia algo específico do evento (palestras, demos, debates)
- `attended = False`: não expõe o no-show. Oferece material e propõe call de forma natural, como se fosse uma extensão do convite

**Regra de negócio — event_notes:** o admin pode preencher `event_notes` no PATCH do lead durante o evento ("participou do painel de Zero Trust", "perguntou sobre integração com SIEM"). Esses dados alimentam a personalização da mensagem pós-evento, tornando a abordagem ainda mais cirúrgica.

---

#### Exemplo de Mensagem Pós-Evento — Presente (CISO, setor Financeiro)

**Assunto:** [Vigil Summit] Carlos — os próximos passos sobre o que debatemos ontem

```
Carlos,

Foi ótimo ter você no Vigil Summit ontem. A discussão sobre Zero Trust 
em ambientes financeiros regulados foi, na minha opinião, o momento 
mais denso do dia — e você estava presente em cada minuto.

Com base no que apresentamos, gostaria de propor 30 minutos para 
mostrar como a plataforma Vigil.AI aplicaria esse modelo ao ambiente 
da TechCorp Brasil especificamente — com uma análise prévia da sua 
postura de segurança baseada em dados públicos.

Sem compromisso. Só uma conversa técnica entre profissionais.

→ Escolha um horário: https://calendly.com/vigil-cso/30min

Carlos Nunes
Chief Security Officer, Vigil.AI
```

---

#### Exemplo de Mensagem Pós-Evento — Ausente (Diretora de TI, setor Saúde)

**Assunto:** Material exclusivo do Vigil Summit para você, Ana

```
Ana,

Entendo que a agenda de uma Diretora de TI raramente permite pausas — 
a quantidade de prioridades simultâneas no setor de saúde é real.

Por isso, separei o que foi mais relevante do Vigil Summit para o 
seu contexto:

📊  "Conformidade ANS + LGPD em dados de pacientes: automação possível"
     (relatório com cases de 3 hospitais, 2026)

🎥  Gravação da keynote: "IA preditiva na detecção de ransomware em saúde"

📋  Checklist: Postura de segurança em 30 dias para organizações de saúde

Posso compartilhar tudo isso em uma call de 20 minutos e mostrar 
como a Vigil.AI pode acelerar esse roadmap na CyberSec Brasil.

→ Agendar 20 min: https://calendly.com/vigil-cso/20min

Carlos Nunes
Chief Security Officer, Vigil.AI
```

---

## 4. Estratégia de Dados e Personalização

### 4.1 — Coleta de Dados

Os dados são coletados em **um único ponto de entrada** controlado: o formulário da landing page. Isso garante consentimento explícito e auditável antes de qualquer processamento.

**Campos coletados no formulário:**
- Identidade: nome completo, email, telefone
- Contexto profissional: empresa, cargo, tamanho da empresa, setor de atuação
- Sinal de enriquecimento: URL do LinkedIn (voluntário)
- Acompanhante: email + vínculo profissional (quando aplicável)
- **Consentimento LGPD** (campo obrigatório — sem ele, o cadastro é rejeitado)

Nenhum dado sensível (RG, CPF, dados financeiros) é coletado ou processado.

### 4.2 — Armazenamento

| Dado | Onde | Formato |
|---|---|---|
| Dados básicos do lead | Tabela `leads` (MySQL) | Colunas tipadas |
| Dados enriquecidos | Coluna `enrichment_data` (JSON) | JSON flexível |
| Histórico de comunicações | Coluna `communication_log` (JSON) | Array de objetos |
| Consentimento | Coluna `consent_at` (DateTime) | ISO 8601 com timezone |
| Prompts da IA | Tabela `message_templates` | TEXT editável pelo admin |
| Configuração do evento | Tabela `events` | Colunas tipadas + JSON |

Todos os registros têm `created_at` e `updated_at` com timezone para auditoria.

### 4.3 — Enriquecimento em Prática

O enriquecimento ocorre automaticamente como background task após o registro do lead, antes de qualquer comunicação. O fluxo é:

```
Lead registrado
       │
       ▼
classify_lead_eligibility()    ← determinístico, sem IA (regex por cargo)
       │
       ├── not_eligible → email de cortesia → arquivado
       ├── pending_review → aguarda admin
       └── approved
              │
              ▼
       enrich_lead_profile()   ← Gemini AI
              │
              └── Retorna JSON com:
                    company.real_name        (inferido pelo domínio do email)
                    company.estimated_size   (baseado no nome/setor)
                    company.revenue_range    (inferência de mercado)
                    professional.real_role   (cargo real vs. declarado)
                    professional.seniority   (C-level / VP / Director / Manager)
                    professional.is_decision_maker (bool)
                    security_topics[]        (tópicos de segurança do setor)
                    icp_score (0.0–1.0)
                    icp_tier  (A / B / C / D)
                    personalization_hooks:
                      cargo_context          (abre mensagens com contexto do cargo)
                      pain_point             (problema principal do setor/cargo)
                      value_proposition      (o que o evento resolve para esse perfil)
                      event_relevance        (por que esse lead deve estar no evento)
```

**Fontes de enriquecimento:**
- **Gemini AI (conhecimento de treinamento):** analisa domínio do email, nome da empresa, cargo declarado e setor para inferir dados com alta precisão para empresas conhecidas. Não é dado em tempo real — é inferência a partir do conhecimento do modelo.
- **LinkedIn (limitado):** o username do LinkedIn é extraído da URL fornecida. O endpoint `/api/v1/leads/linkedin-preview` usa o Gemini para identificar o perfil pelo username — sem scraping, sem API paga. Funciona bem para executivos com perfis públicos conhecidos.

**Limitação conhecida e honesta:** sem integração com APIs de enriquecimento profissional (Apollo.io, Hunter.io, Clearbit, People Data Labs), o enriquecimento é baseado em inferência de IA, não em dados em tempo real. Para uma versão de produção com budget, a integração com Apollo seria o próximo passo natural — substituição de `enrich_lead_profile()` por uma chamada à API, com fallback para o Gemini caso o lead não seja encontrado.

**Fallback determinístico:** se o Gemini falhar (timeout, quota esgotada), o sistema calcula o score por pesos fixos:

| Critério | Peso |
|---|---|
| Cargo | 40% |
| Tamanho da empresa | 35% |
| Setor | 20% |
| LinkedIn fornecido | 5% |

### 4.4 — Como o Dado Enriquecido Alimenta as Mensagens

Cada nó do LangGraph que gera mensagens recebe o `enrichment_data` completo e usa os `personalization_hooks` para construir o prompt enviado ao Gemini:

```python
# Exemplo simplificado de como os hooks são usados no prompt
hooks = enrichment_data.get("personalization_hooks", {})
user_prompt = f"""
Gere um e-mail de follow-up pós-evento para:
- Nome: {lead.name}
- Cargo: {hooks['cargo_context']}          # "CISO responsável por conformidade BACEN"
- Problema principal: {hooks['pain_point']} # "tempo de resposta a incidentes vs. regulação"
- O que o evento resolveu: {hooks['value_proposition']} # "cases reais de Zero Trust em financeiro"
- Tom: profissional, consultivo, direto
"""
```

O resultado é uma mensagem que parece escrita por um humano que conhece o interlocutor — não um template genérico com `{{NOME}}` substituído.

### 4.5 — Conformidade com LGPD

| Princípio LGPD | Implementação |
|---|---|
| **Consentimento** | Campo obrigatório no formulário. Sem `lgpd_consent: true`, o cadastro é rejeitado com HTTP 422. |
| **Finalidade** | Dados usados exclusivamente para gestão do funil do evento. Nenhum dado é compartilhado com terceiros. |
| **Necessidade** | Apenas dados necessários para qualificação e personalização são coletados. Sem dados sensíveis. |
| **Transparência** | O lead sabe que seus dados serão usados para comunicações do evento (explicado no formulário). |
| **Segurança** | Dados em MySQL com acesso restrito. API Key e JWT para endpoints administrativos. Senhas com bcrypt. |
| **Direito ao esquecimento** | Admin pode atualizar/excluir leads via API (`PATCH` + exclusão manual). Em versão de produção, endpoint `DELETE /api/v1/leads/{id}` seria adicionado com confirmação. |
| **Acompanhantes** | Somente email + vínculo profissional. Nenhum dado adicional é solicitado ou armazenado. |
| **Data de consentimento** | Armazenada em `consent_at` com timezone para auditoria completa. |

---

## 5. Decisões Estratégicas e Racional

### 5.1 — LangGraph como Orquestrador do Agente

**A decisão:** usar LangGraph em vez de uma chain linear ou orquestrador de agentes multi-papel.

**Alternativas consideradas:**

| Alternativa | Por que descartada |
|---|---|
| **CrewAI** | Otimizado para múltiplos agentes com papéis distintos (pesquisador, escritor, revisor). Para um funil linear com bifurcações condicionais, adiciona overhead arquitetural desnecessário. |
| **LangChain LCEL** | Chains lineares sem estado persistente entre execuções. Um lead que responde um e-mail 5 dias depois do envio precisaria que o contexto fosse reconstruído do zero — sem grafo de estado, isso é frágil. |
| **SDK nativo (puro Python com async)** | Mais controle, sem abstração. Mas toda a lógica de estado, routing condicional e persistência teria que ser implementada manualmente, aumentando a superfície de bugs. |
| **Agno / AutoGen** | Frameworks menos maduros no ecossistema Python. Menos documentação, menor comunidade, maior risco de breaking changes. |

**Por que LangGraph:**
- **Grafo de estado determinístico:** cada nó conhece exatamente em que fase o lead está. O routing é explícito, auditável e testável.
- **Re-entrada natural:** quando um webhook chega (lead responde), o sistema localiza o nó correto (`node_process_response`) e processa sem reconstruir estado.
- **Stateless por design:** o estado é passado como parâmetro, não armazenado no processo. Isso permite escala horizontal sem refatoração.
- **Ramificações condicionais limpas:** `score_and_route → send_pre_event | end` é um edge condicional de uma linha no LangGraph.

**Referência de mercado:** a abordagem de state machine para jornadas de cliente é o modelo canônico usado por Salesforce Marketing Cloud (Journey Builder), Braze e Klaviyo — todos orquestram fluxos como grafos de estado, não pipelines lineares.

---

### 5.2 — Email como Canal Principal, WhatsApp como Complementar

**A decisão:** implementar email SMTP como base confiável e WhatsApp via Twilio como camada de alta conversão adicional.

**Alternativas consideradas:**

| Alternativa | Por que descartada |
|---|---|
| **Só WhatsApp** | Requer opt-in explícito do usuário (enviar mensagem para o sandbox Twilio antes de receber qualquer contato). Para leads que ainda não interagiram, a empresa precisa usar WhatsApp Business API com templates pré-aprovados pelo Meta — processo burocrático, pago e com SLA de aprovação de dias. |
| **Só Email** | Taxa de abertura média de 20–25% para B2B corporativo. Funcional, mas desperdiça o potencial de um canal com 70%+ de leitura para o mesmo público. |
| **Telegram** | Penetração corporativa muito baixa no Brasil. Executivos de segurança usam Telegram pessoalmente, mas não como canal profissional. Inadequado para o perfil do público. |
| **SMS** | Alta taxa de abertura, mas custo por mensagem mais alto que WhatsApp e percepção de canal para alertas/OTP, não para convites executivos. |

**Por que a combinação email + WhatsApp:**
- Email é o canal formal do mundo corporativo. CISOs, CTOs e Diretores recebem propostas, contratos e convites por email. É o canal de referência para comunicações B2B.
- WhatsApp é o canal de alta urgência e alta leitura. Para lembretes de D-1, D+1 pós-evento, é incomparável.
- A implementação usa fallback automático: se Twilio não está configurado, tudo funciona via email. Zero downtime por canal indisponível.
- O Twilio Sandbox (gratuito) permite desenvolvimento e testes completos sem necessidade de aprovação do Meta.

**Justificativa para o perfil específico do público:**
Executivos de segurança são, por definição, avessos a riscos e conservadores em adotar novos canais de comunicação corporativa. Email é o denominador comum universal — não requer que o lead tome nenhuma ação prévia para recebê-lo.

---

### 5.3 — Gemini 3.5 Flash como LLM

**A decisão:** usar Gemini 3.5 Flash (Google AI) em vez do Claude (Anthropic), preferência declarada no enunciado do case.

**Alternativas consideradas e por que Gemini:**

| LLM | Avaliação |
|---|---|
| **Claude Sonnet 3.5 / 3.7 (Anthropic)** | Melhor reasoning estruturado, excelente para tool use e agência. Seria a escolha ideal — o case explicita preferência por Claude especialmente "para implementações que envolvam agência, uso de ferramentas e raciocínio estruturado". |
| **GPT-4o (OpenAI)** | Excelente capacidade geral, MAS sem free tier generoso. Custo significativo para volume de testes. |
| **Gemini 2.5 Flash / 3.5 Flash** | Gratuito, boa capacidade de reasoning, 1.500 req/dia no free tier — suficiente para todo o desenvolvimento e demonstração do case. |

**A razão honesta por trás da escolha:**

A opção pelo Gemini foi uma decisão imposta por restrição financeira real, não por preferência técnica. No período de desenvolvimento deste projeto, enfrentei uma situação familiar crítica: minha sogra foi internada, precisei custear deslocamentos (Uber) para acompanhá-la, ajudar minha irmã com necessidades básicas (incluindo fraldas) e arcar com contas familiares urgentes. Isso impediu que eu pudesse manter saldo nos serviços pagos necessários.

Tentativas realizadas antes de optar pelo Gemini:
- **API Claude (Anthropic):** chave criada, código adaptado — barrado por falta de créditos
- **Apollo.io (enriquecimento real de leads):** plano gratuito tem limite de 50 exportações/mês, insuficiente; plano pago bloqueado por falta de recurso
- **NinjaPear / Hunter.io:** mesma situação — APIs com limite de uso gratuito esgotado rapidamente
- **LinkedIn scraping:** tentativa de acesso direto via HTTPX — LinkedIn retorna erro 999 (detecção de bot automático) para qualquer acesso programático sem autenticação

**Impacto arquitetural dessa limitação:**

A arquitetura foi desenhada para ser **LLM-agnóstica**. Trocar o Gemini por Claude exige alterar apenas:
1. O cliente LLM em `graph.py` (linha do `genai.GenerativeModel`)
2. O cliente em `enrichment.py` e `pre_event_scheduler.py`
3. Adicionar `anthropic` ao `requirements.txt`

Os prompts, a lógica de estado, os nós do grafo e toda a API permanecem intactos. Estima-se 2–4 horas de trabalho para a migração completa.

**Em produção real com budget disponível:** Claude Sonnet seria a escolha imediata, dado o raciocínio estruturado superior para geração de mensagens personalizadas e o ecossistema de tool use mais maduro.

---

## 6. Plano de Execução — Primeiros 5 Dias

> Assumindo início amanhã, sem configurações prévias.

### Dia 1 — Fundação (Infraestrutura + Banco)

**Objetivo:** sistema vivo, banco criado, health check verde.

```
Manhã:
  ├── Clonar repositório e configurar .env com chaves disponíveis
  ├── docker compose up -d  (MySQL 8.4)
  ├── Criar venv, instalar dependências
  └── python scripts/validate_db.py  (criar tabelas)

Tarde:
  ├── bash vigil_agent/start.sh
  ├── Validar: GET /health → { "status": "healthy" }
  ├── Configurar Gemini API Key (obrigatório)
  └── Configurar Gmail App Password para SMTP (recomendado)
```

**O que provisionar primeiro:** banco de dados e chave de LLM. Sem o banco, nenhum lead é salvo. Sem o LLM, o enriquecimento usa fallback determinístico (funciona, mas sem personalização).

---

### Dia 2 — Captação + Qualificação

**Objetivo:** primeiro lead qualificado e confirmado via IA.

```
Manhã:
  ├── Abrir http://localhost:8000/ e testar formulário
  ├── Inserir lead com cargo CISO + empresa + LinkedIn
  ├── Verificar logs: qualificação → enriquecimento → email de confirmação
  └── Verificar banco: GET /api/v1/leads/ com API Key

Tarde:
  ├── Testar lead com cargo intermediário (Gerente de TI)
  │   → deve ir para status pending_review
  ├── Aprovar pelo admin dashboard
  │   → deve disparar funil IA
  ├── Testar lead fora do ICP (cargo não relacionado)
  │   → deve ir para out_of_icp + email de cortesia
  └── Ajustar prompts de confirmação no editor do admin se necessário
```

**Fase do funil atacada:** Fase 1 (Captação) + início da Fase 2 (Enriquecimento). **Rationale:** sem leads qualificados no banco, todas as outras fases são inócuas. O caminho crítico do sistema começa pela entrada.

---

### Dia 3 — Régua Pré-Evento

**Objetivo:** régua pré-evento rodando para as 3 personas.

```
Manhã:
  ├── Acessar admin dashboard → Evento → configurar data futura
  ├── Inserir 3-5 leads com perfis distintos:
  │   ├── CISO, setor Financeiro, sem acompanhante (Persona A)
  │   ├── Diretora de TI, setor Saúde, com acompanhante (Persona B)
  │   └── Acompanhante pendente (Persona C)
  └── Verificar enriquecimento de cada um nos logs

Tarde:
  ├── Disparar régua de teste: POST /admin/scheduler/trigger-pre-event-test
  ├── Verificar mensagens geradas nos logs (ou emails reais)
  ├── Avaliar qualidade da personalização por persona
  └── Ajustar prompts no admin se necessário
```

---

### Dia 4 — Webhooks + Follow-up Pós-Evento

**Objetivo:** fluxo ponta a ponta testado com resposta do lead.

```
Manhã:
  ├── Simular resposta de lead via webhook:
  │   POST /webhooks/inbound
  │   { "lead_email": "...", "channel": "email", "message": "Confirmo minha presença!" }
  ├── Verificar: agente processa intenção → responde automaticamente
  └── Verificar: status lead mudou para CONFIRMED

Tarde:
  ├── Encerrar evento: POST /admin/event/end
  ├── Aguardar delay configurado (3 min no padrão de teste)
  ├── Verificar disparo pós-evento nos logs:
  │   ├── Lead presente → mensagem com referência ao evento
  │   └── Lead ausente → mensagem com oferta de material
  └── Verificar status: leads presentes → FOLLOWED_UP
```

---

### Dia 5 — Ajustes Finais + Documentação para Avaliação

**Objetivo:** sistema demonstrável, documentado e acessível para o avaliador.

```
Manhã:
  ├── Criar personas sintéticas completas para demo:
  │   ├── "Rodrigo Alves" — CISO, Banco Nacional, score A
  │   ├── "Mariana Costa" — CTO, Healthtech, com acompanhante, score A
  │   └── "Felipe Souza" — Gerente de TI, pending_review → aprovado pelo admin
  └── Rodar suite de testes: pytest vigil_agent/tests/ -v

Tarde:
  ├── Ajustar ADMIN_DEFAULT_PASSWORD no .env para a demo
  ├── Documentar credenciais de acesso:
  │   Admin: http://localhost:8000/admin/login.html
  │   API Key: vigil-internal-api-key-2026
  │   JWT: POST /api/v1/admin/auth/login
  └── Compartilhar acesso com o avaliador (ramon@pareto.io)
```

---

## Canal de Comunicação — Justificativa

**Escolha:** Email (SMTP) como canal primário + WhatsApp (Twilio) como canal complementar de alto engajamento.

### Por que não escolher apenas um canal

O público-alvo do Vigil Summit é composto por CISOs, CTOs, Diretores de TI e Gestores de Risco. Esse perfil tem características específicas que determinam o mix de canais ideal:

**Email — o canal formal do mundo corporativo:**
- Todos os decisores B2B têm email corporativo e o monitoram ativamente
- Convites, contratos e propostas chegam por email — é o canal de referência para comunicações executivas
- Zero burocracia: não requer opt-in, aprovação ou configuração prévia do destinatário
- Permite mensagens HTML ricas, com links rastreáveis e assinatura profissional
- Taxa de entrega: ~97% (vs. dependência de conta WhatsApp ativa do destinatário)

**WhatsApp — o canal de alta urgência:**
- Taxa de abertura: 70–90% vs. 20–25% do email B2B
- Leitura quase imediata (90% das mensagens lidas em 3 minutos)
- Ideal para: D-1 (lembrete de véspera), D+1 (follow-up pós-evento enquanto o evento ainda está fresco)
- Limitação: requer que o lead tenha WhatsApp no número fornecido e que o sandbox Twilio esteja ativo

**Combinação estratégica por fase:**

| Fase do Funil | Email | WhatsApp |
|---|---|---|
| Confirmação de inscrição | ✅ Primário | ✅ Complementar (quando disponível) |
| D-30 e D-15 | ✅ Primário | — (muito cedo para WhatsApp) |
| D-7 | ✅ Primário | ✅ Reforço |
| D-3 e D-1 | ✅ Primário | ✅ Urgência (alta prioridade) |
| D+1 pós-evento | ✅ Primário | ✅ Alto impacto |
| Follow-up de reunião | ✅ Primário | — (contexto mais formal) |

---

## Cenário de Escala (Bônus)

### O Problema

10 eventos regionais simultâneos, públicos distintos (manufatura, saúde, financeiro, governo), sem reescrever o agente.

### O que NÃO precisa mudar

A boa notícia é que o agente foi desenhado com essa possibilidade em mente:

- **O grafo LangGraph** é completamente stateless. Ele recebe um lead como input e produz ações como output. Não tem conhecimento do evento — apenas do lead e de seu estado no funil.
- **Os nós do agente** (`enrich`, `score`, `pre_event`, `post_event`) são agnósticos de evento. Funcionam para qualquer lead de qualquer contexto.
- **O sistema de templates no banco** já permite que prompts sejam customizados sem alterar código — só precisam ser filtrados por `event_id`.
- **A API FastAPI** é stateless e escala horizontalmente sem modificação.

### O que precisa ser adicionado

**1. Multi-tenancy no modelo de dados**

```sql
-- Adicionar event_id como FK em leads e message_templates
ALTER TABLE leads ADD COLUMN event_id INT REFERENCES events(id);
ALTER TABLE message_templates ADD COLUMN event_id INT REFERENCES events(id);

-- Cada evento tem seus próprios prompts e configurações de ICP
```

O modelo de dados fica:
```
events (id, name, sector_focus, icp_config, ...)
  ├── leads (id, event_id, ...)
  └── message_templates (id, event_id, phase, body, ...)
```

Cada admin de evento edita seus próprios prompts sem afetar outros eventos. O peso ICP para "manufatura" valoriza setores diferentes do "financeiro".

---

**2. Filas de mensageria isoladas (Celery + Redis)**

Hoje: FastAPI `BackgroundTasks` — executa em thread separada no mesmo processo. Não escala para múltiplos eventos simultâneos com alta volumetria.

Substituição:

```python
# Hoje
background_tasks.add_task(run_funnel_for_lead, lead_dict)

# Com Celery
from celery import Celery
app_celery = Celery(broker="redis://localhost:6379/0")

@app_celery.task(queue=f"event.{event_id}")
def process_lead_task(lead_dict):
    asyncio.run(run_funnel_for_lead(lead_dict))
```

Cada evento tem sua própria fila (`event.1`, `event.2`, ...). Workers dedicados por evento garantem que um pico de inscrições em "manufatura" não atrasa o processamento de "saúde".

```
Redis
  ├── queue: event.1.pre_event   → worker-saude (1 instância)
  ├── queue: event.2.pre_event   → worker-financeiro (2 instâncias — maior volume)
  ├── queue: event.3.pre_event   → worker-governo (1 instância)
  └── ...
```

---

**3. Rate limiting por canal**

Com 10 eventos × 120 leads = até 1.200 leads recebendo mensagens no mesmo gatilho (ex.: todos os D-7), o rate limiting se torna crítico:

- **WhatsApp (Twilio Business):** limite de 80 mensagens/segundo por número
- **SMTP (Gmail):** limite de 500 emails/dia no plano gratuito; para produção, migrar para SendGrid (100/dia grátis, escala paga)
- **Gemini API:** 1.500 req/dia no free tier — para 10 eventos × 120 leads, migrar para plano pago ou Claude (sem limite hard no plano Teams)

Solução: rate limiter por canal usando Redis como semáforo distribuído.

```python
# Exemplo conceitual com redis-py
async def send_with_rate_limit(channel: str, send_fn, *args):
    key = f"ratelimit:{channel}"
    async with redis.pipeline() as pipe:
        current = await redis.get(key) or 0
        if int(current) < CHANNEL_LIMITS[channel]:
            await redis.incr(key)
            await redis.expire(key, 1)  # janela de 1 segundo
            await send_fn(*args)
```

---

**4. Cache de enriquecimento (Redis TTL)**

Domínios corporativos se repetem: se 15 funcionários do Banco Itaú se inscrevem em eventos diferentes, a chamada ao Gemini para enriquecer "itau.com.br" não precisa ser feita 15 vezes.

```python
cache_key = f"enrichment:{email_domain}"
cached = await redis.get(cache_key)
if cached:
    return json.loads(cached)  # cache hit

result = await call_gemini_enrichment(...)
await redis.setex(cache_key, 86400, json.dumps(result))  # TTL: 24h
return result
```

Redução estimada de chamadas ao LLM: **60–70%** para eventos no mesmo ecossistema corporativo.

---

**5. Configuração de ICP por setor de evento**

Em vez de um score ICP genérico, cada evento define seus próprios pesos e setores de alta propensidade:

```json
// Evento: "Vigil Summit — Manufatura"
{
  "icp_config": {
    "high_value_sectors": ["manufatura", "automotivo", "energia", "logística"],
    "target_roles": ["CISO", "Diretor de Operações", "CTO", "Head de OT Security"],
    "security_topics_focus": ["OT/ICS security", "SCADA", "supply chain security"],
    "min_score": 0.55
  }
}
```

O agente lê essa configuração do evento no início do `node_score_and_route` e ajusta os pesos dinamicamente.

---

**6. Observabilidade**

Com 10 eventos simultâneos, logs em console são insuficientes:

| Ferramenta | Finalidade |
|---|---|
| **Prometheus** | Métricas: throughput de mensagens/hora por evento, taxa de erro do LLM, latência de enriquecimento, tamanho das filas |
| **Grafana** | Dashboard: funil de conversão por evento em tempo real, alertas de fila parada |
| **Sentry** | Rastreamento de exceções: erros no agente, falhas de envio por canal |

---

**Resumo da arquitetura escalada:**

```
[FastAPI] → [Redis Queues] → [Celery Workers por Evento]
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                    Worker-Saúde  Worker-Financ  Worker-Gov
                          │            │            │
                          └────────────┴────────────┘
                                       │
                              [LangGraph Agent]  ← stateless, compartilhado
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                      [MySQL]      [Gemini AI]   [Redis Cache]
                   (event_id FK)   (rate limited)  (enrichment TTL)
```

O grafo LangGraph permanece **exatamente o mesmo**. Apenas o contexto (event_id, configuração de ICP, prompts do banco) muda por execução. Sem reescrita. Sem refatoração estrutural.
