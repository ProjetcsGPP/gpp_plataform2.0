# Prontidão da Fase 0

**Atualização:** 2026-11-03
**Regra:** a Fase 1 começa quando todos os gates obrigatórios da Fase 0 e do
marco contratual F0.5 tiverem decisão, responsável e evidência compatível com o
risco.

Este documento é o painel de prontidão. A matriz compartilhada mantém o estado
de coordenação; os documentos especializados contêm o detalhe e a evidência.
`DECIDIDO` ou `DOCUMENTADO` não significa `IMPLEMENTADO`.

## 1. Gates consolidados

| Gate | Situação | Evidência atual | Próxima ação |
|---|---|---|---|
| Autenticação, CSRF e sessão | Concluído | `PUB-008`; regressões backend/frontend e 13 E2E registradas | Manter regressão proporcional no CI. |
| Preparador/publicador | Decidido | `PUB-009`; ADR-0001 | Implementar e testar somente na F2. |
| `PORTAL_ADMIN` | Decidido | `PUB-010`; ADR-0002 | Aplicar IAM compartilhado e testar invariantes. |
| Rotas e redirect | Decidido | `PUB-012`; ADR-0003 | Implementar e testar somente na F3. |
| SSR/CSR | Decidido | `PUB-013`; ADR-0004 | Implementar isolamento server/client na F3. |
| Cache público/autenticado | Decidido | `PUB-014`; ADR-0005 | Implementar headers, providers e purge na F3. |
| Threat model | Documentado, requer revisão | `THREAT_MODEL.md` | Revisar após piloto, classificação e topologia aprovados. |
| Inventário técnico | Sandbox comprovada com lacunas | `INFRASTRUCTURE_INVENTORY.md`; `infra/publicacoes-dev` | Validar banco real, egress de rede e observabilidade. |
| Plano de rollback | Processo documentado, não exercitado no alvo | `ROLLBACK_PLAN.md` | Aprovar flags, responsáveis e exercícios por ambiente. |
| Piloto e classificação | Pendente | `PUB-011`; PRE-001 a PRE-003 | Nomear responsáveis, escolher piloto e classificar campos. |
| Contratos executáveis | Pendente, marco F0.5 | `PUB-017` a `PUB-019` | Aprovar DTO público, OpenAPI administrativo e catálogo IAM. |
| Cadeia de fornecimento | Evidência histórica bloqueada | `SECURITY_EVIDENCE_2026-10-26.md` | Corrigir/justificar achados e gerar evidência datada atual. |
| PostgreSQL on-premises | Bloqueado | `PUB-020`; restore comprovado apenas na sandbox | Validar privilégios, migrations, backup e restore na instância real. |
| Egress de rede | Bloqueado | Contrato aplicativo SSRF comprovado; restrição de rede não comprovada | Demonstrar allowlist e bloqueios no nível de rede. |
| Observabilidade de DEV | Parcial | Redação e logs locais comprovados | Nomear responsáveis e comprovar métricas, traces, correlação e alerta. |

## 2. Situação por item de pré-implementação

| ID | Estado em 2026-11-03 | Falta para aceite |
|---|---|---|
| PRE-001 | Parcial — definição registrada | Código `PUB_INSTITUCIONAL`, nome `PUBLICAÇÕES`, responsável único, ausência de substituto e perfis Zimbra `HML`/`PRD` inicialmente idênticos registrados; a manutenção temporária da credencial exposta foi aceita pelo responsável, e faltam cadastro controlado, provisionamento oculto nos dois caminhos e ativação segura/testada dos perfis. |
| PRE-002 | Pendente | Caso piloto, dono da informação e contrato de fonte aprovado. |
| PRE-003 | Pendente | Classificação campo a campo, finalidade, retenção e proibições. |
| PRE-004 | Parcial | Topologia de DEV aprovada e diagrama browser/SSR/worker. |
| PRE-005 | Bloqueado | Validar schema, privilégios, backup e restore no PostgreSQL on-premises real. |
| PRE-006 | Parcial | Sandbox S3 e negações foram exercitadas; falta decisão formal do serviço de DEV e política. |
| PRE-007 | Parcial | ClamAV/EICAR e falha fechada passaram na sandbox; falta aprovação formal do serviço e workflow. |
| PRE-008 | Parcial | OpenBao e AppRoles foram comprovados em DEV; faltam cobertura dos demais segredos e aprovação operacional. |
| PRE-009 | Parcial | Nginx/TLS/limites locais existem; faltam contrato de purge e aprovação do proxy de DEV. |
| PRE-010 | Bloqueado | Validação SSRF aplicativo existe; egress no nível de rede não foi comprovado. |
| PRE-011 | Parcial | Logs redigidos existem; faltam métricas, traces, correlação ponta a ponta e alerta recebido. |
| PRE-012 | Pendente | Categorias e responsáveis de continuidade; valores ficam para cada ambiente alvo. |
| PRE-013 | Parcial | IAM humano decidido; falta registrar responsável, fronteira e gate de F6 para M2M. O provedor final não bloqueia F1. |
| PRE-014 | Pendente, F0.5 | Schemas público, administrativo e IAM; estados, erros e concorrência. |
| PRE-015 | Bloqueado | Repetir SBOM/scans; corrigir ou justificar achados e comprovar rollback local. |
| PRE-016 | Decidido no contrato | ADR-0006 e contrato existem; adapters deverão passar pela suíte comum quando implementados. |

Estados `Parcial` e `Decidido no contrato` continuam abertos até existir a
evidência de aceite indicada. A sandbox não comprova serviço institucional nem
o PostgreSQL on-premises.

## 3. Marco F0.5 — contratos executáveis

F0.5 permite produzir somente documentação e fixtures contratuais não
executáveis. Antes de F1 devem estar aprovados:

1. DTO público v1 e estados sem publicação, revogação, `429` e `5xx`;
2. OpenAPI administrativo com recursos, UUIDs, paginação, filtros, ações,
   transições, preview, erros e concorrência;
3. catálogo IAM com aplicação, role, permissões, capabilities e menus;
4. decisões de idempotência, versionamento e compatibilidade;
5. matriz de campos permitidos por representação.

F0.5 não autoriza app, model, migration, endpoint, seed, fixture executável,
tela ou teste sintético de `PUBLICACOES`.

## 4. Bloqueios para iniciar a Fase 1

1. `PRE-001` com aceite operacional parcial; `PRE-002`, `PRE-003` e `PUB-011`
   sem aprovação.
2. `PUB-017` a `PUB-019` sem contratos executáveis aprovados em F0.5.
3. `PUB-020` bloqueado por PostgreSQL real, cadeia de fornecimento, egress de
   rede e observabilidade.
4. `PUB-022` sem responsáveis, categorias operacionais, métricas, traces,
   correlação e alerta local.
5. Rollback e restore comprovados apenas na sandbox, não na instância alvo.

Enquanto qualquer item obrigatório permanecer aberto, não será criado app,
model, migration, endpoint, seed, fixture executável ou teste sintético de
`PUBLICACOES`.
