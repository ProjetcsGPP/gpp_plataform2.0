# Prontidão da Fase 0

**Atualização:** 2026-10-26  
**Regra:** a Fase 1 começa quando todos os gates obrigatórios da Fase 0 tiverem
decisão, responsável e evidência compatível com o risco.

| Gate | Situação | Evidência | Próxima ação |
|---|---|---|---|
| Autenticação, CSRF e sessão | Concluído | `PUB-008`; 1.138 testes backend, 1 ignorado, cobertura 87,55%; frontend e 13 E2E | Manter regressão no CI. |
| Preparador/publicador | Decidido | `PUB-009`; ADR-0001 | Implementar e testar na Fase 2. |
| `PORTAL_ADMIN` | Decidido | `PUB-010`; ADR-0002 | Aplicar IAM compartilhado e testar invariantes. |
| Rotas e redirect | Decidido | `PUB-012`; ADR-0003 | Implementar e testar na Fase 3. |
| SSR/CSR | Decidido | `PUB-013`; ADR-0004 | Implementar isolamento server/client na Fase 3. |
| Cache público/autenticado | Decidido | `PUB-014`; ADR-0005 | Implementar e testar headers, providers e purge. |
| Threat model | Documentado | `THREAT_MODEL.md` | Revisar quando piloto e infraestrutura forem definidos. |
| Inventário técnico | DEV provisionado com lacunas | `INFRASTRUCTURE_INVENTORY.md`; `infra/publicacoes-dev` | Atribuir responsáveis e fechar egress/observabilidade. |
| Plano de rollback | Processo documentado | `ROLLBACK_PLAN.md` | Aprovar flags, responsáveis e executar exercícios. |
| Pré-implementação | Pendente | `PRE_IMPLEMENTATION_CHECKLIST.md` | Decidir, provisionar e comprovar todos os itens PRE-001 a PRE-016. |
| Piloto e classificação dos dados | Pendente | `PUB-011` | Escolher origem/conjunto e preencher contrato de fonte. |
| Schema público inicial | Pendente | `PUB-017` | Definir após o piloto e antes de gráficos/layout. |
| Object storage, AV, gateway, secrets e egress | Bloqueado por achados | `PUB-020`; `SECURITY_EVIDENCE_2026-10-26.md` | Corrigir/decidir vulnerabilidades, validar o PostgreSQL real e provar egress de rede. |
| Contrato operacional de DEV | Parcialmente comprovado | `PUB-022`; restore e redação passaram | Nomear responsáveis e completar métricas, traces, alerta e categorias operacionais. |

## Bloqueios atuais para iniciar a Fase 1

1. `PUB-011`: não há piloto aprovado nem classificação campo a campo.
2. `PUB-020`: há achados altos/críticos não suprimidos, o PostgreSQL
   on-premises real ainda não foi validado e o egress de rede não foi comprovado.
3. `PUB-022`: restore e redação foram comprovados, mas faltam responsáveis,
   categorias operacionais, métricas, traces e alerta local.
4. `PRE-001` a `PRE-003`: responsáveis, piloto e classificação campo a campo
   ainda não foram aprovados.
5. O rollback exercitado vale somente para a sandbox PostgreSQL em Docker e não
   comprova recuperação da instância on-premises.

Enquanto esses itens estiverem abertos, não será criado app, model, migration,
endpoint, fixture ou teste sintético de `PUBLICACOES`. Dados sintéticos reduzem
o risco do conteúdo, mas não substituem decisões nem provas de arquitetura,
infraestrutura, segurança, operação e recuperação.
