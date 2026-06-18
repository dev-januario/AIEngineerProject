# Tarefa 3: Régua de Engajamento Pré-Evento via Agente LangGraph

## 1. Objetivo de Negócio
Reduzir a taxa de no-show corporativo (historicamente de 40-60%) para garantir uma taxa de comparecimento superior a 70% no Vigil Summit[cite: 1].

## 2. Regras de Negócio da Régua Pré-Evento
- **Gatilho T-7 (7 dias antes):** Enviar mensagem de confirmação de presença. Se o lead responder confirmando, perguntar se deseja incluir um acompanhante do time de engenharia/risco (Lógica de acompanhante requisitada pela Pareto)[cite: 1].
- **Gatilho T-3 (3 dias antes):** Se o lead não respondeu ao T-7, mudar a abordagem. Se o contato inicial foi por E-mail, disparar um gatilho simulando WhatsApp para aumentar a taxa de abertura[cite: 1].
- **Personalização por IA:** O prompt do Claude 3.5 Sonnet deve obrigatoriamente usar os dados enriquecidos (`role`, `company_name`) para contextualizar o evento[cite: 1].

## 3. Estrutura do Agente (LangGraph)
Em `app/agents/graph.py`, defina um grafo de estado (`StateGraph`) que gerencia a conversa:
- **Node `analyze_intent`**: Utiliza o Claude para classificar a resposta do lead em: `confirma_presenca`, `pede_acompanhante`, `recusa` ou `duvida_tecnica`.
- **Node `generate_response`**: Gera a mensagem customizada com base na intenção e no perfil de cibersegurança da Vigil.Al (mencionar relatórios ISO 27001, LGPD ou SOC 2 dependendo do cargo do lead)[cite: 1].

## 4. Exemplo de Prompt Base (Colocar em app/agents/prompts.py)
```text
Você é o Agente de Relacionamento da Vigil.Al especializado no evento Vigil Summit[cite: 1].
Seu público-alvo são executivos de alta tecnologia (CISOs, CTOs)[cite: 1]. Seja profissional, conciso e use termos técnicos de segurança cibernética apropriados.
Dados do Lead:
- Nome: {name}
- Cargo: {role}
- Empresa: {company_name}
Contexto atual da conversa: {context}
Gere uma mensagem persuasiva focando em como o Vigil Summit abordará a conformidade de segurança para o setor deles[cite: 1].