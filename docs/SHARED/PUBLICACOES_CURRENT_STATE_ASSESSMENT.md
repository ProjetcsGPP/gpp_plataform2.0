# Avaliação arquitetural consolidada de `PUBLICACOES`

**Data da reconfirmação:** 2026-11-03

**Estado:** avaliação concluída; implementação funcional ainda não autorizada

**Backend auditado:** `feat/publicacoes-informacoes` em `005bf4c`

**Frontend auditado:** `feat/publicacoes-informacoes` em `623f58b`

**Referência de decisões:**
[`PUBLICACOES_INTEGRATION_MATRIX.md`](./PUBLICACOES_INTEGRATION_MATRIX.md)

## 1. Objetivo e limites

Este documento conclui a verificação arquitetural conjunta de backend e
frontend antes da criação da aplicação `PUBLICACOES`. Ele substitui a conclusão
desatualizada de que o assessment frontend não existia.

A auditoria foi somente de leitura sobre o código. Não foi criado app, model,
migration, endpoint, fixture, tela ou contrato de fonte. Exemplos envolvendo
`CARGA_ORG_LOT` ou outra aplicação continuam não normativos, conforme
`PUB-003`.

## 2. Resultado da entrega anteriormente considerada incompleta

| Entrega | Situação em 2026-11-03 | Evidência |
|---|---|---|
| Documento final consolidado | Concluído com ressalvas de atualização | O frontend possui `docs/PUBLICACOES/FRONTEND_ASSESSMENT.md`; este documento faz a reconciliação transversal atual. |
| Matriz de arquivos impactados | Concluída abaixo | Seção 7, separada por repositório, fase e contrato. |
| Proposta faseada frontend/backend | Concluída | Seção 8 e `IMPLEMENTATION_PLAN.md`. |
| Conflitos, riscos e compatibilidade | Concluídos | Seções 5, 6 e 9. |
| Testes e rollout | Concluídos | Seções 10 e 11. |

O arquivo pretendido não foi criado na raiz `docs/`. O documento efetivamente
existente e adotado pelo frontend está em
`frontend/docs/PUBLICACOES/FRONTEND_ASSESSMENT.md`. Ele contém 502 linhas e as
cinco entregas acima, mas ainda registra o commit antigo `1b657cb` e mistura
achados da auditoria inicial com decisões tomadas posteriormente. Este
assessment compartilhado é a reconfirmação canônica até que o documento local
do frontend seja sincronizado.

## 3. Estado atual dos repositórios

| Repositório | Estado observado | Implementação de `PUBLICACOES` |
|---|---|---|
| Backend | Commit funcional auditado sincronizado com `origin/feat/publicacoes-informacoes`; o worktree contém somente as alterações documentais desta reconfirmação, ainda não commitadas | `apps/publicacoes` não existe. |
| Frontend | Branch limpa e sincronizada com `origin/feat/publicacoes-informacoes` | `src/app/publicacoes`, `src/features/publicacoes` e `PUBLICACOES` em `AppContext` não existem. |

O backend possui 18 documentos diretamente em `docs/PUBLICACOES`, seis ADRs e
a documentação compartilhada. Os sete documentos-base citados pela matriz
existem e são coerentes quanto à arquitetura proposta.

## 4. Reconciliação dos sete documentos-base

| Documento | Papel | Situação atual |
|---|---|---|
| `README.md` | Índice, vocabulário e regras de uso | Válido e atualizado para apontar para esta reconfirmação. |
| `ARCHITECTURE.md` | Bounded context, publicação imutável, fontes e Portal | Válido; padrões de fonte são decisões arquiteturais, mas cada fonte exige contrato próprio. |
| `IMPLEMENTATION_PLAN.md` | Fases F0 a F7 e gates | Válido; F1 continua impedida pelos gates abertos de F0. |
| `SECURITY_PLAN.md` | Ativos, fronteiras, ameaças e controles | Válido; `PUB-008` está concluído, mas não encerra os demais controles. |
| `OPERATIONS_GUIDE.md` | Operação futura por gestores e consumidores | Válido como procedimento-alvo; não prova provisionamento ou treinamento. |
| `SOURCE_CONTRACT_TEMPLATE.md` | Contrato obrigatório de cada origem | O piloto operacional E-Docs foi identificado, mas o contrato ainda não foi preenchido e aprovado. |
| `CONSUMER_REGISTRATION_TEMPLATE.md` | Cadastro e governança de consumidores | Válido para F6; não define ainda o provedor M2M. |

Documentos complementares como `PRE_IMPLEMENTATION_CHECKLIST.md`,
`F0_READINESS.md`, `THREAT_MODEL.md`, `DEVELOPMENT_ENVIRONMENT.md`, os ADRs e
os guias do OpenBao não substituem os sete documentos-base; eles registram
evidências e bloqueios específicos.

## 5. Decisões consolidadas e pendências reais

### 5.1 Decidido

- `PUBLICACOES` será bounded context próprio dentro do monólito inicialmente,
  sem cliente HTTP, autenticação ou autorização paralelos (`PUB-001`).
- somente publicação aprovada, versionada e imutável será distribuída
  (`PUB-002`).
- aplicações de origem preservam suas regras; exemplos não criam obrigações de
  evento, conteúdo ou momento (`PUB-003`).
- integração interna usará notificação transacional, snapshot versionado e
  reconciliação; no mesmo backend não haverá HTTP interno nem leitura direta de
  tabelas de outro domínio (`PUB-004`).
- haverá um perfil funcional inicial, `GESTOR_PUBLICACOES`, com permissões
  técnicas; a mesma pessoa poderá preparar e publicar (`PUB-005`, `PUB-009`).
- `PORTAL_ADMIN` acessará tudo pelas regras compartilhadas, mas continuará
  sujeito aos invariantes do domínio (`PUB-010`).
- `/portal` será público; `/portal/login` será compatível com o modal;
  `/portal/dashboard` continuará autenticado (`PUB-012`).
- Portal público será híbrido SSR/hidratação; Axios/Zustand do browser não
  serão usados no SSR (`PUB-013`).
- caches público, autenticado e preview serão separados (`PUB-014`).
- backend será autoridade para cards, destinos e disponibilidade; frontend não
  cruzará roles para decidir aplicações (`PUB-016`).
- valores canônicos chegarão calculados ao frontend (`PUB-023`).

### 5.2 Pendente antes da fundação ou em fases posteriores

- `PUB-011`: piloto operacional E-Docs identificado; responsáveis, contrato e
  classificação campo a campo continuam pendentes;
- `PUB-017`: schema público inicial e estados sem publicação, obrigatório no
  gate contratual F0.5;
- `PUB-018`: contrato administrativo, workflow, concorrência, preview e erros,
  obrigatório no gate contratual F0.5 antes de models e endpoints;
- `PUB-019`: código da aplicação decidido como `PUB_INSTITUCIONAL`; menus,
  capabilities e permissões continuam pendentes no gate F0.5 antes do seed;
- `PUB-021`: provedor e contrato M2M;
- `PUB-022`: responsáveis operacionais, métricas, traces, correlação e alerta;
- `PUB-024`: estados de ausência, revogação, `429`, offline e `5xx`;
- `PUB-025`: navegadores e meta de acessibilidade.

### 5.3 Bloqueio para iniciar F1

`PUB-020` permanece bloqueado. A documentação não contém evidência suficiente
para considerar concluídos a validação operacional do PostgreSQL on-premises,
o controle de egress e a observabilidade. Também faltam as aprovações de
`PRE-001` a `PRE-003`.

O `npm audit` executado em 2026-11-03 encontrou **zero vulnerabilidades nas
dependências de produção** (`--omit=dev`). Na árvore completa encontrou 22
achados de ferramentas de desenvolvimento: 1 alto, 19 moderados e 2 baixos.
Não houve alteração automática de dependências. O achado alto e os demais
achados precisam de correção ou ordem justificada registrada antes do aceite da
cadeia de fornecimento; não devem ser confundidos com vulnerabilidades de
runtime do Portal.

As evidências de `SECURITY_EVIDENCE_2026-10-26.md` são históricas. Elas devem
ser repetidas e registradas em novo documento datado antes de encerrar
`PUB-020`; não comprovam, sozinhas, o estado atual da cadeia de fornecimento ou
da infraestrutura.

## 6. Conflitos e correções da auditoria frontend antiga

| Afirmação antiga | Situação atual | Tratamento |
|---|---|---|
| Assessment final não foi criado | Falsa no estado atual | O arquivo existe em `frontend/docs/PUBLICACOES/FRONTEND_ASSESSMENT.md`. |
| Preparador/publicador ainda precisava ser decidido | Obsoleta | Resolvido por `PUB-009` e ADR-0001. |
| Rotas, SSR/CSR e cache ainda precisavam ser decididos | Obsoleta como decisão | Resolvidos por `PUB-012` a `PUB-014`; implementação e testes continuam pendentes. |
| Next `16.3.6` e dependências antigas bloqueavam por alerta específico | Obsoleta | Manifest atual usa Next/ESLint `16.4.3`, Vitest `4.1.12` e shadcn `4.22.1`; vale a auditoria atual da seção 5.3. |
| `sessionExpiredMessage` não era renderizada | Corrigida no código atual | Manter teste de regressão. |
| `/portal` não possui página pública | Continua verdadeiro | `src/app/portal/page.tsx` não existe e o proxy ainda protege o prefixo. |
| `PUBLICACOES` não existe em `AppContext` | Continua verdadeiro | Trabalho de F1, após os gates de F0. |
| Portal decide cards cruzando roles e destinos hardcoded | Continua verdadeiro e conflita com `PUB-016` | Backend deve fornecer DTO autoritativo; frontend apenas apresenta e valida destino permitido. |
| Cache público/autenticado não está isolado | Continua verdadeiro | Implementar somente com o contrato público aprovado. |

### 6.1 Correções técnicas identificadas no backend atual

| Achado | Situação | Tratamento planejado |
|---|---|---|
| OpenAPI ainda exemplifica login com `username`, cita `SessionAuthentication` e resolução de usuário | Documentação do código está obsoleta em relação a `PUB-008` e `PUB-015` | Corrigir em entrega própria sem mudar o contrato já implementado de `identifier`, CSRF e cookie por aplicação. |
| Exemplos de `AplicacaoPublicaSerializer` incluem `idaplicacao`, mas o serializer público não expõe esse campo | Inconsistência documental do OpenAPI | Alinhar exemplos ao serializer mínimo e manter PKs/flags fora do contrato público de login. |
| `AplicacaoSerializer` afirma que o frontend decide visibilidade e habilitação | Conflita com a autoridade backend decidida em `PUB-016` | Corrigir a descrição e substituir o dashboard do Portal por DTO autoritativo de cards. |
| Dashboard autenticado entrega aplicações e roles em listas separadas | Mantém decisão no navegador e destinos locais | Criar contrato versionado de cards com código, destino permitido, estado e disponibilidade; autorização real continua no endpoint de destino. |
| Mapas de contexto/cookie não reconhecem `PUBLICACOES` | Implementação inexistente, esperada antes de F1 | Adicionar `PUBLICACOES` aos dois middlewares, settings, router e OpenAPI somente após os gates. |

## 7. Matriz completa de arquivos impactados

Os caminhos novos são propostas de localização, não contratos de dados.

### 7.1 Backend

| Caminho | Tipo | Fase | Responsabilidade/contrato |
|---|---|---|---|
| `apps/publicacoes/apps.py`, `__init__.py` | Novo | F1 | Registro do bounded context (`PUB-001`). |
| `apps/publicacoes/models/`, `migrations/` | Novo | F1–F2 | Fonte, snapshot, publicação imutável, histórico e concorrência (`PUB-002`, `PUB-018`). |
| `apps/publicacoes/services/` | Novo | F1–F6 | Casos de uso, transações, workflow e interfaces de segurança (`PUB-027`). |
| `apps/publicacoes/selectors/` | Novo | F1–F3 | Leituras explícitas sem expor models entre domínios. |
| `apps/publicacoes/serializers/`, `views/`, `urls.py` | Novo | F1–F6 | APIs administrativas, públicas e de distribuição versionadas. |
| `apps/publicacoes/tasks.py` | Novo | F4–F6 | Coleta, reconciliação e processamento assíncrono idempotente. |
| `apps/publicacoes/tests/` | Novo | Todas | Unidade, contrato, autorização, segurança, concorrência e integração. |
| `config/settings/base.py` | Alterar | F1 | Registrar app/configuração sem segredos no código. |
| `config/urls.py` | Alterar | F1/F3 | Rotas administrativas e públicas versionadas. |
| `config/routers.py` | Validar/alterar se necessário | F1 | Schema PostgreSQL e isolamento do bounded context. |
| `apps/accounts/middleware.py` | Alterar | F1 | Reconhecer o prefixo e o cookie dedicado de `PUBLICACOES`. |
| `apps/core/middleware/application_context.py` | Alterar | F1 | Resolver o contexto pela rota sem fallback incorreto para Portal. |
| `apps/accounts/**` | Alterar de forma aditiva | F1/F3 | Aplicação, role, permissões, capabilities, menus e DTO autoritativo de cards. |
| `apps/portal/**` | Alterar | F3 | Contrato autenticado de aplicações, sem decisão por roles no browser. |
| `common/**` | Reusar; alterar apenas por contrato transversal | F1–F7 | Auditoria, autorização, paginação, erros e controles comuns. |
| `infra/publicacoes-dev/**` | Corrigir/validar | F0 | Banco real, storage, AV, secrets, proxy, egress, observabilidade e rollback. |
| `docs/PUBLICACOES/**`, `docs/SHARED/**` | Atualizar | Todas | ADRs, OpenAPI, contratos, evidências e matriz. |

### 7.2 Frontend

| Caminho | Tipo | Fase | Responsabilidade/contrato |
|---|---|---|---|
| `src/types/auth.ts`, `src/types/navigation.ts` | Alterar | F1 | Adicionar `PUBLICACOES` de forma exaustiva. |
| `src/lib/api.ts`, `src/lib/auth.ts`, `src/lib/authRedirect.ts` | Estender, sem cliente paralelo | F1/F3 | Modo público, CSRF, 401 e redirect seguro. |
| `src/proxy.ts` | Alterar | F1/F3 | `/portal` público exato e prefixos autenticados explícitos. |
| `src/hooks/useNavigation*.ts`, stores de auth/permissões/navegação | Estender | F1 | Contexto, menus, capabilities e permissões técnicas. |
| `public/nav/PUBLICACOES.json` | Novo | F1 | Fallback não decisório da navegação. |
| `src/app/publicacoes/**` | Novo | F1–F2 | Shell e administração conforme OpenAPI. |
| `src/features/publicacoes/**` | Novo | F1–F6 | Adapters, hooks e componentes do domínio de apresentação. |
| `src/app/portal/page.tsx` | Novo | F3 | Dashboard público canônico. |
| `src/app/portal/layout.tsx`, `dashboard/**`, `login/**` | Alterar | F3 | Separação público/autenticado e compatibilidade do modal. |
| `src/components/auth/LoginPage.tsx` | Refatorar | F3 | Extrair formulário reutilizável e modal acessível. |
| `src/hooks/usePortalDashboard.ts` e dashboard atual | Substituir contrato | F3 | Remover cruzamento de roles e destinos hardcoded (`PUB-016`). |
| `src/components/admin/**`, `src/lib/adminResource.ts`, hook/tipos | Reusar/estender | F1–F2 | CRUD simples; workflow não deve ser forçado em abstração inadequada. |
| `src/components/layout/**`, `globals.css` | Estender | F1/F3 | Tema, shell, responsividade e acessibilidade. |
| testes unitários, `src/__tests__/middleware.test.ts`, `e2e/**` | Alterar/novo | Todas | Matriz de rotas, contrato, segurança, acessibilidade e E2E. |
| `docs/PUBLICACOES/**` | Atualizar | Todas | Sincronizar o assessment local com este documento e a matriz. |

## 8. Proposta faseada frontend/backend

| Fase | Backend | Frontend | Gate de saída |
|---|---|---|---|
| F0 — fechar pré-condições | Responsáveis, piloto, classificação, banco real, egress, observabilidade e cadeia de fornecimento | Atualizar assessment e validar dependências | `PRE-001` a `PRE-016` com decisão/evidência aplicável; `PUB-020` desbloqueado. |
| F0.5 — contratos executáveis | Aprovar DTO público v1, OpenAPI administrativo, catálogo IAM, estados/erros, idempotência e concorrência, sem criar código funcional | Aprovar fixtures contratuais e impactos tipados, sem criar telas | `PUB-017` a `PUB-019` aprovados; contratos especializados não contradizem a matriz. |
| F1 — fundação | Criar app/schema, IAM, auditoria e modelos-base | `AppContext`, config, proxy autenticado, tema, manifest e guards | Isolamento, migrations, IAM e regressão compartilhada aprovados. |
| F2 — vertical editorial manual | Rascunho, validação, publicação imutável, substituição/revogação | Administração, preview e histórico dirigidos por ações backend | Concorrência, autorização e imutabilidade comprovadas. |
| F3 — API pública e Portal | DTO público v1, vigente, ETag/cache, rate limit; DTO autoritativo de cards | `/portal` público, SSR seguro, hidratação, modal e cards | Sem vazamento/cache cruzado; acessibilidade e estados aprovados. |
| F4 — fontes internas | Outbox, provider, snapshot e reconciliação do piloto aprovado | Acompanhamento e proveniência | Contrato produtor/consumidor e replay idempotente. |
| F5 — APIs externas e arquivos | Conectores, egress, quarentena, scan e limites | Upload/acompanhamento/relatório | SSRF, arquivos maliciosos e indisponibilidade testados. |
| F6 — consumidores | M2M, escopos, quotas, emissão única, rotação/revogação | Cadastro e operação segura | Segredo não persistido/exposto; revogação e escopos comprovados. |
| F7 — entrada em operação | Hardening, carga, restore, alertas e runbooks | E2E full-stack, acessibilidade, desempenho e rollout | Aceites funcional, técnico, segurança e operação. |

Fases posteriores podem ter seus contratos preparados antes, mas não podem
contornar o gate que protege a capacidade correspondente.

## 9. Análise final de riscos e compatibilidade

### Bloqueiam início da implementação funcional

- aceite operacional parcial de PRE-001 e validação/contrato/classificação do
  piloto E-Docs (`PRE-002`, `PRE-003` e `PUB-011`);
- `PUB-020` bloqueado por banco real, egress, observabilidade e achados ainda
  sem resolução formal;
- inexistência de schema público e contrato administrativo executáveis
  (`PUB-017`, `PUB-018`);
- catálogo IAM final ainda pendente (`PUB-019`).

F0.5 é trabalho documental e contratual. Ele pode ocorrer enquanto evidências
operacionais de F0 são fechadas, mas não autoriza app, model, migration,
endpoint, fixture executável ou teste sintético de `PUBLICACOES`.

### Bloqueiam exposição pública ou go-live, não necessariamente todo F1

- cache público/preview não implementado nem testado;
- DTO de cards ainda dependente de roles e destinos locais;
- estados de erro/revogação e acessibilidade pendentes;
- M2M, quotas, retenção e operação ainda incompletos;
- dependências de desenvolvimento com achados sem decisão registrada.

### Compatibilidade obrigatória

- preservar Axios, SWR, Zustand, `AppContext`, menus e permissões existentes;
- não verificar role em componentes;
- manter `/portal/login` e `/portal/dashboard` durante a transição;
- não encaminhar cookie/Authorization do visitante ao SSR público;
- nunca misturar cache público, autenticado e preview;
- frontend não recalcula valores canônicos;
- WebSocket/fila notifica; estado persistido permanece canônico;
- nenhuma origem é alterada antes de seu contrato ser aprovado.

## 10. Estratégia completa de testes

### F0/F1

- regressão de autenticação, cookie, CSRF, sessão, throttling e redirect;
- migrations e rollback no PostgreSQL on-premises isolado;
- seed idempotente e matriz de role/permissão/capability/menu;
- negação para usuário sem permissão, `GESTOR_PUBLICACOES` e
  `PORTAL_ADMIN` sujeito aos mesmos invariantes;
- análise de dependências de produção e desenvolvimento separadamente.

### F2

- máquina de estados, transações, auditoria e justificativa;
- concorrência otimista/pessimista conforme contrato;
- imutabilidade após publicação e nova versão para correção;
- preview `private, no-store` e não acessível publicamente;
- IDOR, paginação, filtros e erros estruturados.

### F3

- contrato por `schema_version` e allowlist campo a campo;
- `ETag`, `Last-Modified`, `304`, purge e revogação da vigente;
- ausência de `Vary: Cookie` e de conteúdo autenticado na resposta pública;
- isolamento SWR e por requisição SSR;
- visitante, login modal, favorito antigo, redirect seguro, cards e logout;
- teclado, foco, nomes acessíveis, contraste, zoom, movimento reduzido,
  alternativas tabular/textual e viewports;
- carga, `429`, offline, timeout e `5xx`.

### F4–F6

- contrato produtor/consumidor, outbox, replay, retry, dead-letter e
  reconciliação;
- SSRF, DNS rebinding, redirects, timeout, paginação e circuit breaker;
- extensão/tipo real, macro, ZIP/XML bomb, EICAR, quarentena e falha fechada;
- segredo de consumidor exibido uma vez, armazenado como hash/prefixo, escopo,
  quota, rotação e revogação imediata.

### Pipeline mínimo por entrega

- backend: checks Django, migrations, lint, OpenAPI, testes focados e regressão;
- frontend: lint, typecheck, Vitest, build Webpack e Playwright;
- integração: fixtures versionadas e E2E full-stack em ambiente isolado;
- segurança: SAST, dependências, segredos, SBOM e testes negativos do controle
  alterado.

Evidências históricas não substituem a repetição proporcional após mudanças.

## 11. Estratégia de rollout e rollback

1. manter `PUBLICACOES` e o Portal público atrás de flags independentes;
2. ativar primeiro a vertical editorial com dados sintéticos e acesso restrito;
3. publicar contrato v1 com uma publicação sintética imutável;
4. ativar `/portal` público sem retirar `/portal/login` e
   `/portal/dashboard`;
5. liberar cards autoritativos somente após testes de destino e autorização;
6. habilitar uma fonte piloto apenas após contrato e reconciliação;
7. habilitar consumidores por cadastro individual, escopo e quota;
8. observar erros, latência, cache, fila, segurança e incompatibilidade de
   schema em cada expansão;
9. rollback desativa flags/rotas e restaura artefato anterior, sem apagar
   publicação, histórico ou evidência;
10. qualquer mudança de banco segue migration reversível e restore exercitado.

## 12. Parecer e próxima sequência

A avaliação arquitetural está concluída, mas **não autoriza iniciar F1**. A
sequência correta é:

1. reconciliar `F0_READINESS.md`, o inventário e as evidências históricas com
   esta reconfirmação;
2. atualizar o assessment local do frontend com esta reconfirmação;
3. nomear responsáveis e validar o piloto E-Docs sem converter a ferramenta
   operacional em contrato de fonte por antecipação;
4. preencher e aprovar o contrato de fonte e a classificação campo a campo;
5. fechar as evidências de PostgreSQL on-premises, egress e observabilidade;
6. decidir/corrigir os achados da cadeia de desenvolvimento;
7. concluir F0.5 com schemas iniciais público, administrativo e IAM aprovados;
8. atualizar `F0_READINESS.md` e a matriz com as evidências reproduzidas;
9. somente então autorizar a criação de `apps/publicacoes` e da fundação
   frontend.

Até esse gate, alterações em CARGA_ORG_LOT ou outra origem continuam fora de
escopo.
