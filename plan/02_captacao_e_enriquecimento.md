# Tarefa 2: Módulo de Captação e Pipeline de Enriquecimento de Dados

## 1. Regras de Negócio (Baseado no Case - AI Engineer (2026).pdf)
- **Captação**: Criar um endpoint `/api/v1/leads/webhook` que recebe `name`, `email`, `linkedin_url` e `consent_lgpd`[cite: 1]. Se `consent_lgpd` for falso, rejeitar a requisição em conformidade com a lei[cite: 1].
- **Enriquecimento**: Assim que o lead for inserido com status `captured`, disparar uma tarefa assíncrona para enriquecer o perfil[cite: 1].

## 2. Implementação do Enriquecimento (Mock & Integração estruturada)
Crie um serviço `app/services/enrichment.py`. Como este é um ambiente de testes, simule uma chamada de API para ferramentas como Apollo.io/Clearbit[cite: 1].
- Se o e-mail terminar com `@empresa.com`, o mock deve retornar:
  - `role`: "CISO" ou "CTO"[cite: 1]
  - `company_size`: 250 (Garante o critério de >200 funcionários)[cite: 1]
  - `sector`: "Tecnologia / Setor Financeiro"[cite: 1]
- Atualizar o status do lead no banco para `enriched`[cite: 1].

## 3. Critérios de Aceitação e Testes
- Escrever um teste em `tests/test_enrichment.py`.
- O teste deve enviar um payload de captação válido, interceptar a tarefa de enriquecimento, e verificar se os campos `role`, `company_size` e `status` foram atualizados corretamente no banco de dados.