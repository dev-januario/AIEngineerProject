# Tarefa 4: Régua de Follow-up Comercial Pós-Evento

## 1. Objetivo de Negócio
Iniciar uma sequência de follow-up ultra-personalizada para agendar reuniões comerciais com os tomadores de decisão[cite: 1].

## 2. Regras de Negócio e Contexto do Evento
O agente precisa diferenciar os leads que compareceram (`attended`) dos que faltaram (`absent`)[cite: 1]:
- **Leads `attended`:** O agente deve recuperar o histórico do que o lead demonstrou interesse no evento (ex: Demonstração da camada de IA que prioriza riscos e antecipa ameaças da plataforma SaaS da Vigil.Al)[cite: 1]. A mensagem deve focar em agendar um report personalizado gratuito de postura de segurança da própria empresa do lead[cite: 1].
- **Leads `absent`:** Enviar uma mensagem lamentando a ausência, enviando um sumário executivo das principais palestras e oferecendo um link direto para demonstração da plataforma da Vigil.Al[cite: 1].

## 3. Critérios de Aceitação e Testes
- Implementar o endpoint `/api/v1/event/attendance-sync` que atualiza a presença dos leads.
- No arquivo `tests/test_agent_post.py`, simule o fluxo para um lead com status `attended` que participou da demo de "Antecipação de Ameaças". Garanta que a mensagem gerada pelo Claude inclua esse termo exato[cite: 1].