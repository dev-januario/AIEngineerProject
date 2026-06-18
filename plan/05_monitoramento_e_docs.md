# Tarefa 5: Arquitetura Multi-Tenant para Escala e Documentação Final

## 1. Cenário de Escala (Pergunta Bônus do Case)
Modifique o middleware do FastAPI e a injeção de dependência do banco de dados para suportar múltiplos eventos regionais simultâneos com perfis diferentes (Manufatura, Saúde, Financeiro, Governo) sem reescrever o agente do zero[cite: 1].
- **Solução técnica:** O sistema deve ler o `event_id` do cabeçalho da requisição ou do payload de captação[cite: 1]. O prompt do agente deve puxar dinamicamente a coluna `target_profile` da tabela `events` para adaptar o tom e os termos técnicos (ex: se o evento for de Saúde, focar em privacidade de dados médicos; se for Financeiro, focar em fraudes e conformidade bancária).

## 2. Requisitos de Documentação para a Pareto (Obrigatório)
Crie o arquivo final `DOCUMENTATION.md` contendo[cite: 1]:
- **Instruções de Acesso:** Como testar localmente usando Docker.
- **Credenciais Temporárias:** Configuração para o e-mail ramon@pareto.io realizar testes[cite: 1].
- **Conformidade LGPD:** Explicação detalhada de onde os dados ficam criptografados, a base legal usada (Consentimento e Legítimo Interesse para o pós-evento) e como o lead pode solicitar a exclusão dos dados através do chatbot[cite: 1].

## 3. Critério de Aceitação Final
- Toda a suite de testes (`pytest`) deve rodar com 100% de sucesso.
- O script deve ser capaz de exportar um log estruturado contendo 5 conversas demonstráveis completas (ponta a ponta, da captação ao agendamento) utilizando personas sintéticas para validação dos recrutadores da Pareto[cite: 1].