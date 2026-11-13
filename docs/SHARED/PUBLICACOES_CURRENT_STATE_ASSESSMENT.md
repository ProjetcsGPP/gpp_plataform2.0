# Avaliação arquitetural consolidada de `PUBLICACOES`

**Data da última atualização:** 2026-11-09

**Estado:** avaliação concluída; primeiro recorte E-Docs e fundação frontend
autorizados e implementados, contratos editorial e público ainda pendentes

**Backend auditado:** `feat/publicacoes-informacoes` em `005bf4c`

**Frontend auditado:** `feat/publicacoes-informacoes` em `623f58b`

**Referência de decisões:**
[`PUBLICACOES_INTEGRATION_MATRIX.md`](./PUBLICACOES_INTEGRATION_MATRIX.md)

## 1. Objetivo e limites

Este documento concluiu a verificação arquitetural conjunta e agora acompanha
a implementação incremental da aplicação `PUBLICACOES`. Ele substitui a
conclusão desatualizada de que o assessment frontend não existia.

A auditoria original foi somente de leitura. Posteriormente, o responsável
autorizou o recorte E-Docs, seu IAM, API administrativa, agregado editorial,
séries históricas e a fundação frontend. A fronteira e os endpoints do DTO
público foram implementados; sua integração no Portal ainda está pendente. Nenhuma dessas
autorizações antecipa regras de outras aplicações, conforme `PUB-003`.

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
| Backend | Fundação E-Docs anterior commitada e sincronizada; API administrativa atual ainda não commitada | `apps/pub_institucional` possui schema `publicacoes`, catálogo, reconciliação, auditoria, cliente E-Docs, IAM e API administrativa; o domínio editorial permanece parcial. |
| Frontend | Fundação implementada no worktree, ainda sem commit | `PUBLICACOES` foi adicionado ao `AppContext`; rotas `/publicacoes`, shell, login, manifesto, guards e quatro páginas neutras existem sem inventar contratos de dados. |

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
| `SOURCE_CONTRACT_TEMPLATE.md` | Contrato obrigatório de cada origem | O contrato E-Docs foi tecnicamente preenchido e a classificação campo a campo proposta; responsáveis, retenção e aprovações continuam pendentes. |
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

- `PUB-011`: piloto operacional E-Docs identificado, contrato preenchido e
  classificação proposta; responsáveis, retenção e aprovações continuam
  pendentes;
- `PUB-017`: backend implementado com projeção separada, séries, ranking e
  testes de não vazamento; integração frontend pendente;
- `PUB-018`: contrato administrativo, workflow, concorrência, preview e erros,
  obrigatório no gate contratual F0.5 antes de models e endpoints;
- `PUB-019`: identidade e catálogo IAM do recorte E-Docs implementados por seed
  idempotente; recursos editoriais futuros dependem do contrato administrativo;
- `PUB-021`: provedor e contrato M2M;
- `PUB-022`: responsáveis operacionais, métricas, traces, correlação e alerta;
- `PUB-024`: semântica e implementação backend de ausência, revogação, `429` e
  `503` concluídas; apresentação dos estados no frontend pendente;
- `PUB-025`: navegadores e meta de acessibilidade permanecem como decisão do
  frontend e não bloqueiam a geração backend das séries.

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
| `PUBLICACOES` não existe em `AppContext` | Corrigida na fundação frontend | O código usado é `PUB_INSTITUCIONAL`, com cookie, login, logout, manifesto e rotas dedicadas. |
| Portal decide cards cruzando roles e destinos hardcoded | Continua verdadeiro e conflita com `PUB-016` | Backend deve fornecer DTO autoritativo; frontend apenas apresenta e valida destino permitido. |
| Cache público/autenticado não está isolado | Continua verdadeiro | Implementar somente com o contrato público aprovado. |

### 6.1 Correções técnicas identificadas no backend atual

| Achado | Situação | Tratamento planejado |
|---|---|---|
| OpenAPI ainda exemplifica login com `username`, cita `SessionAuthentication` e resolução de usuário | Documentação do código está obsoleta em relação a `PUB-008` e `PUB-015` | Corrigir em entrega própria sem mudar o contrato já implementado de `identifier`, CSRF e cookie por aplicação. |
| Exemplos de `AplicacaoPublicaSerializer` incluem `idaplicacao`, mas o serializer público não expõe esse campo | Inconsistência documental do OpenAPI | Alinhar exemplos ao serializer mínimo e manter PKs/flags fora do contrato público de login. |
| `AplicacaoSerializer` afirma que o frontend decide visibilidade e habilitação | Conflita com a autoridade backend decidida em `PUB-016` | Corrigir a descrição e substituir o dashboard do Portal por DTO autoritativo de cards. |
| Dashboard autenticado entrega aplicações e roles em listas separadas | Mantém decisão no navegador e destinos locais | Criar contrato versionado de cards com código, destino permitido, estado e disponibilidade; autorização real continua no endpoint de destino. |
| Mapas de contexto/cookie não reconhecem `PUBLICACOES` | Corrigida no recorte E-Docs | Os middlewares reconhecem `pub-institucional` como `PUB_INSTITUCIONAL`; o cookie dedicado foi validado em teste HTTP. |

## 7. Matriz completa de arquivos impactados

Os caminhos novos são propostas de localização, não contratos de dados.

### 7.1 Backend

| Caminho | Tipo | Fase | Responsabilidade/contrato |
|---|---|---|---|
| `apps/pub_institucional/apps.py`, `__init__.py` | Criado | F1 | Registro do bounded context (`PUB-001`). |
| `apps/pub_institucional/models/`, `migrations/` | Parcial | F1–F2 | Catálogo E-Docs implementado; fonte, snapshot editorial, publicação imutável, histórico e concorrência ainda serão ampliados (`PUB-002`, `PUB-018`). |
| `apps/pub_institucional/services/` | Parcial | F1–F6 | Cliente E-Docs e reconciliação implementados; demais casos de uso, workflow e interfaces de segurança permanecem pendentes (`PUB-027`). |
| `apps/pub_institucional/selectors/` | Novo | F1–F3 | Leituras explícitas sem expor models entre domínios. |
| `apps/pub_institucional/serializadores.py`, `visoes.py`, `urls.py` | Parcial | F1–F6 | API administrativa E-Docs implementada; APIs editorial, pública e de distribuição ainda dependem de contrato. |
| `apps/pub_institucional/tasks.py` | Novo | F4–F6 | Coleta, reconciliação e processamento assíncrono idempotente. |
| `apps/pub_institucional/tests/` | Parcial | Todas | Cliente, exportação, catálogo, IAM, permissões, API, auditoria e cookie dedicado possuem cobertura; camadas futuras ainda precisarão de testes. |
| `config/settings/base.py` | Alterado | F1 | App registrada sem segredos no código. |
| `config/urls.py` | Parcial | F1/F3 | Prefixo administrativo E-Docs registrado; rotas públicas permanecem pendentes. |
| `config/routers.py` | Validar/alterar se necessário | F1 | Schema PostgreSQL e isolamento do bounded context. |
| `apps/accounts/middleware.py` | Alterado | F1 | Prefixo e cookie dedicado de `PUB_INSTITUCIONAL` reconhecidos. |
| `apps/core/middleware/application_context.py` | Alterado | F1 | Contexto resolvido pela rota sem fallback incorreto para Portal. |
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
- integração do Portal, apresentação pública e validações E2E ainda pendentes
  (`PUB-017`, `PUB-024`, `PUB-025`); projeção, allowlist e endpoints backend já
  estão implementados;
- catálogo IAM editorial futuro ainda depende do contrato administrativo
  (`PUB-018`, `PUB-019`); o catálogo E-Docs inicial já foi implementado.

F0.5 continua sendo o gate documental e contratual para a distribuição
pública. O contrato de fronteira foi aprovado, mas isso não equivale à
implementação nem ao aceite dos endpoints públicos.

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
4. aprovar o contrato E-Docs e a classificação campo a campo já propostos;
5. fechar as evidências de PostgreSQL on-premises, egress e observabilidade;
6. decidir/corrigir os achados da cadeia de desenvolvimento;
7. concluir F0.5 com schemas iniciais público, administrativo e IAM aprovados;
8. atualizar `F0_READINESS.md` e a matriz com as evidências reproduzidas;
9. concluir as pendências antes de ampliar `apps/pub_institucional` além do
   recorte E-Docs já autorizado e antes de iniciar a fundação frontend.

Até esse gate, alterações em CARGA_ORG_LOT ou outra origem continuam fora de
escopo.
