# Tarefa 1: Configuração do Ambiente, Estrutura de Pastas e Banco de Dados

## 1. Contexto do Projeto
Você está desenvolvendo uma solução para a Vigil.Al, uma plataforma SaaS de cibersegurança. O objetivo é automatizar o funil do evento "Vigil Summit" focado em CISOs, CTOs e Diretores de TI de empresas com mais de 200 funcionários.

## 2. Stack Tecnológica Obrigatória
- **Linguagem:** Python 3.11+
- **Framework Web:** FastAPI (Assíncrono)
- **Banco de Dados:** PostgreSQL com SQLAlchemy (Async) e Alembic para migrações
- **Orquestração de IA:** LangGraph e Anthropic Python SDK (Claude 3.5 Sonnet)
- **Testes:** Pytest e HTTPX (para testes de integração assíncronos)

## 3. Estrutura de Diretórios Esperada
```text
vigil_agent/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   └── security.py
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   │   └── lead.py
│   ├── schemas/
│   │   └── lead.py
│   ├── services/
│   │   ├── enrichment.py
│   │   └── notification.py
│   └── agents/
│       ├── graph.py
│       └── prompts.py
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   └── test_agent.py
├── requirements.txt
└── README.md