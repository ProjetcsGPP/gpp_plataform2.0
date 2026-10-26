# Matriz integrada — PUBLICACOES, Portal e aplicações relacionadas

**Status:** baseline compartilhada para planejamento e validação  
**Data de consolidação:** 2026-10-23  
**Repositório mantenedor:** backend  
**Branch de origem:** `feat/publicacoes-informacoes`

## 1. Finalidade e uso obrigatório

Esta matriz consolida as decisões e pendências transversais identificadas nos
documentos de backend e frontend. Ela deve ser lida antes de qualquer trabalho
que altere `PUBLICACOES`, Portal, autenticação, IAM, aplicações de origem,
fontes externas, planilhas ou consumidores da API de distribuição.

Ela não transforma propostas em decisões e não presume quando ou o que uma
aplicação de origem deve fornecer. Cada fonte somente adquire comportamento
normativo depois de ter contrato próprio validado por seus responsáveis.

Chats e equipes devem seguir o protocolo de
[documentos compartilhados](./README.md). Mudança material em uma linha exige
atualizar seu status e critério, os documentos especializados afetados e o
[histórico](#5-histórico-de-alterações).

## 2. Legenda

### Status

- `DECIDIDO`: orientação aprovada para a implementação inicial.
- `PENDENTE`: falta uma decisão ou validação identificada.
- `PROPOSTA`: alternativa técnica ainda não aprovada.
- `INSUMO`: informação registrada, ainda sem validação suficiente.
- `BLOQUEADO`: não pode avançar enquanto o bloqueio indicado estiver aberto.
- `SUBSTITUIDO`: preservado historicamente e ligado ao sucessor.
- `REJEITADO`: avaliado e não adotado, com justificativa preservada.

### Bloqueio de segurança

- `P0`: impede o início da implementação funcional ou a exposição correspondente.
- `P1`: impede homologação ou go-live da capacidade correspondente.
- `CONDICIONAL`: depende do threat model ou do contrato concreto.
- `NÃO`: não há bloqueio de segurança específico além da Definition of Done.

### Responsável

O campo identifica quem deve decidir ou validar, não uma pessoa já designada.
Quando houver mais de um responsável, a decisão é conjunta.

## 3. Matriz consolidada

| ID | Status | Decisão, pendência ou regra | Responsável pela decisão/validação | Contrato ou documento afetado | Fase | Bloqueio de segurança | Critério de aceite |
|---|---|---|---|---|---|---|---|
| PUB-001 | DECIDIDO | `PUBLICACOES` será bounded context próprio, inicialmente dentro do monólito Django, sem mecanismo frontend paralelo. | Arquitetura backend e frontend | Arquitetura de módulos; `AppContext`; navegação; cliente HTTP e SWR | F1 | P0: F1 aguarda os gates de F0 | Limites do módulo aprovados; app registrada; frontend usa Axios, SWR, `appContext` e navegação existentes; testes de isolamento passam. |
| PUB-002 | DECIDIDO | O conteúdo distribuído virá somente de publicação aprovada, versionada e imutável, nunca diretamente de tabelas operacionais ou preview. | Gestão de `PUBLICACOES`, backend e segurança | Workflow editorial; DTO público; API de distribuição; cache | F2–F3 | P1 | Tentativa de editar publicação vigente é rejeitada; correção gera nova versão; API e cache não expõem rascunho, preview ou revogada como vigente. |
| PUB-003 | DECIDIDO | A aplicação de origem mantém suas regras canônicas; exemplos de CARGA_ORG_LOT ou de outra aplicação não definem eventos, momentos ou dados de integração. | Responsável funcional e técnico de cada origem | Contrato de fonte; provider; eventos; snapshot | F4–F5 | CONDICIONAL | Cada integração possui contrato aprovado, schema versionado, classificação de campos e testes de contrato antes de alterar a origem. |
| PUB-004 | DECIDIDO | Integração interna seguirá, como padrão inicial, notificação transacional, obtenção de snapshot versionado e reconciliação; no mesmo backend não haverá HTTP interno nem consulta direta a models alheios. | Arquitetura backend e responsáveis das origens | Outbox; `PublicationSourceProvider`; DTO; reconciliação | F4 | P1 | Falha após commit não perde evento; replay não duplica; reconciliação recupera entrega perdida; dependências entre domínios são verificadas em teste. |
| PUB-005 | DECIDIDO | A primeira versão terá um único perfil funcional, `GESTOR_PUBLICACOES`, sustentado por permissões técnicas granulares. | Gestão funcional, IAM e segurança | Roles; permissions; capabilities; menus; matriz de autorização | F1 | P1: acesso privilegiado deve permanecer auditável | Seed idempotente criado; permissões por ação documentadas e testadas; usuário comum sem autorização recebe negação; frontend não consulta nomes de roles; `PORTAL_ADMIN` segue PUB-010. |
| PUB-006 | DECIDIDO | Capability controla disponibilidade funcional; permissão técnica autoriza ações. Componentes frontend não derivam autorização de roles. | Arquitetura frontend, backend e IAM | `/me`; permissions; menus; capabilities; guards | F1 | P1 | Testes demonstram capability com e sem permissões; ações sensíveis são negadas ao usuário comum sem permissão; o acesso administrativo global segue PUB-010 e não é reproduzido no frontend. |
| PUB-007 | DECIDIDO | Consumidores da API são identidades de máquina separadas de usuários, sessões humanas e `UserRole`. | Segurança, IAM e arquitetura backend | Autenticação M2M; credenciais; escopos; quotas | F6 | P1 | Credencial tem escopo mínimo, expiração, hash, rotação e revogação testados; não funciona como sessão humana. |
| PUB-008 | DECIDIDO | Gate F0 de autenticação concluído: CSRF efetivo, validade/revogação de sessão, usuário ativo, throttling de login e não enumeração foram implementados e validados antes da implementação funcional e da exposição pública. | Backend, segurança e frontend para testes de integração | Login por `identifier`; bootstrap CSRF; sessão; cookies; remoção de `resolve-user` | F0 | NÃO: gate concluído | Testes negativos de CSRF, sessão expirada/inativa e brute force passam; login responde genericamente e não depende de resolução enumerável; contrato de cookies está documentado. |
| PUB-009 | DECIDIDO | Não haverá segregação obrigatória entre preparação e publicação na primeira versão: a mesma pessoa poderá preparar e publicar, desde que autorizada como `GESTOR_PUBLICACOES`. | Gestão funcional e segurança | Workflow; transições; auditoria; autoria | F0–F2 | P1: ação privilegiada e erro operacional | ADR aprovado; serviços permitem o mesmo ator nas duas etapas; histórico registra preparador e publicador; testes de autorização, concorrência e auditoria passam. |
| PUB-010 | DECIDIDO | `PORTAL_ADMIN` terá em `PUBLICACOES` o mesmo tratamento vigente nas demais aplicações: acesso administrativo global concedido pelas camadas compartilhadas, sem exigir vínculo ou permissão específica da aplicação. Esse acesso não permite ignorar workflow, imutabilidade, validação, justificativa nem auditoria. | Segurança, IAM e gestão funcional | Autorização administrativa; workflow; threat model | F0–F2 | P1: conta privilegiada e trilha de auditoria | ADR e matriz de autorização aprovados; testes demonstram acesso do administrador, negação ao usuário comum sem permissão e aplicação das regras de domínio também ao administrador. |
| PUB-011 | PENDENTE | Escolher o conjunto de dados e a aplicação de origem do primeiro piloto, sem inferir seus gatilhos ou conteúdo. | Produto, gestão de `PUBLICACOES` e responsável da origem | Contrato de fonte piloto; classificação de dados; DTO | F0 e F4 | CONDICIONAL | Piloto identificado; responsáveis registrados; contrato e classificação campo a campo aprovados; dados sintéticos disponíveis para testes. |
| PUB-012 | PENDENTE | Aprovar a matriz de rotas pública e autenticada, incluindo `/portal`, `/portal/login`, `/portal/dashboard`, redirects e layouts separados. | Produto, arquitetura frontend, backend e segurança | Rotas Next; proxy; login modal; cookies; navegação | F0 e F3 | P0: open redirect e proteção de rota | ADR de rotas aprovado; allowlist de redirect definida; testes cobrem visitante, sessão válida, sessão expirada, favoritos antigos e rotas autenticadas. |
| PUB-013 | PENDENTE | Decidir CSR, SSR ou estratégia híbrida para o Portal público sem usar singleton client-side em contexto SSR. | Arquitetura frontend e infraestrutura | Renderização; cliente HTTP; cache; SEO; deploy | F0 e F3 | CONDICIONAL | ADR registra requisitos de SEO, isolamento por requisição e estratégia escolhida; build e testes comprovam ausência de vazamento entre sessões. |
| PUB-014 | PENDENTE | Definir fronteiras do cache público e autenticado em SWR e HTTP, incluindo `ETag`, `Last-Modified`, TTL, invalidação e degradação. | Backend, frontend, infraestrutura/gateway e segurança | DTO público; SWR keys; Axios público; headers e CDN/gateway | F0 e F3 | P0: mistura público/autenticado; P1: conteúdo obsoleto | Contrato de cache aprovado; chaves são namespaced; resposta pública não varia por sessão; testes cobrem `304`, troca/revogação da vigente, `stale-if-error` e ausência de contaminação. |
| PUB-015 | DECIDIDO | Login deixará de resolver usuário previamente e aceitará identificador opaco com resposta genérica; o bootstrap CSRF será definido pelo backend. | Backend e segurança; frontend valida integração | API de autenticação; formulário/modal; interceptor CSRF | F0 e F3 | P0, acompanhado por PUB-008 | Contrato implementado e documentado; endpoint enumerável descontinuado sem consumidor; cookie CSRF existe antes de mutação; mensagens não revelam cadastro. |
| PUB-016 | DECIDIDO | O backend será autoridade para aplicações disponíveis, destinos aprovados e estados; o frontend não cruzará roles nem manterá catálogo decisório duplicado. | Backend/IAM, produto e frontend | DTO do Portal; switch de aplicação; cards; destinos | F1 e F3 | P1: IDOR e URL arbitrária | DTO versionado possui código, destino permitido, estado e disponibilidade; frontend normaliza destino; testes rejeitam URL não autorizada e acesso backend sem permissão. |
| PUB-017 | PENDENTE | Aprovar schema público do dashboard antes de escolher gráficos ou layout final. | Produto, dados, gestão de `PUBLICACOES`, backend e frontend | DTO dashboard; indicadores; séries; proveniência; acessibilidade | F0 e F3 | P1: vazamento ou conteúdo ativo | Schema versionado define valores, unidades, precisão, locale, fuso, períodos e proveniência; allowlist campo a campo e testes de não vazamento passam; gráficos têm alternativa textual/tabular. |
| PUB-018 | PENDENTE | Definir contrato administrativo: recursos, IDs, paginação, filtros, `acoes_disponiveis`, transições, erros, preview e concorrência. | Gestão funcional, backend e frontend | OpenAPI administrativo; workflow; preview `no-store`; validação | F1–F2 | P1 | OpenAPI e fixtures aprovados; ações retornadas pelo backend; mutações usam precondição de concorrência; preview não é cacheado; erros são estruturados; testes cobrem UUID e conflitos. |
| PUB-019 | PENDENTE | Definir códigos finais de menus, capabilities e permissões técnicas de `PUBLICACOES`, preservando a arquitetura dinâmica atual. | Gestão funcional, IAM, backend e frontend | Seed; `/me`; permissions; menus; manifest local | F1 | P1 | Catálogo aprovado; seed idempotente; tipos frontend exaustivos; navegação e guards testados para concessão, negação e remoção de acesso. |
| PUB-020 | PENDENTE | Selecionar object storage, antivírus/sandbox, gateway, secrets manager e política de egress para APIs externas e planilhas. | Infraestrutura, segurança e backend | Upload/quarentena; conectores; armazenamento; segredos; rede | F0 e F5 | P0 antes de credencial/arquivo real; P1 para go-live | Decisões registradas em ADR; testes de SSRF, redirect, DNS, arquivo malicioso e limites passam; segredo não aparece em banco, API, logs ou eventos. |
| PUB-021 | PENDENTE | Definir provedor institucional e contrato completo de autenticação máquina-a-máquina. | IAM, segurança, infraestrutura e arquitetura backend | Emissão/validação de credencial; scopes; rotação; revogação | F0 e F6 | P1 | Provedor e fluxo aprovados; segredo exibido uma vez; somente hash/prefixo persistido; rotação sem indisponibilidade e revogação imediata demonstradas. |
| PUB-022 | PENDENTE | Definir nome funcional, retenção, SLA, RPO, RTO, responsáveis e contatos de incidente. | Produto, gestão, infraestrutura, segurança e área jurídica/LGPD quando aplicável | Operação; retenção; backup; observabilidade; resposta a incidente | F0 e F7 | P1 | Políticas aprovadas; responsáveis e contatos nomeados; restore comprova RPO/RTO; alertas e runbooks são exercitados. |
| PUB-023 | DECIDIDO | O Portal público exibirá dados já calculados pelo backend; frontend não recalculará indicadores canônicos. | Produto, dados, backend e frontend | DTO público; formatadores; componentes e gráficos | F3 | P1 | Fixtures e testes de contrato demonstram que valores chegam calculados; frontend limita-se à apresentação e formatação prevista no schema. |
| PUB-024 | PENDENTE | Definir comportamento sem publicação, após revogação, em `429`, offline e `5xx`, além da política de histórico público. | Produto, backend, frontend e infraestrutura | Semântica da API pública; estados de UI; cache e observabilidade | F3 | P1 | Matriz de estados aprovada; API usa erros estáveis; interface apresenta estado acessível e não reutiliza conteúdo revogado como vigente. |
| PUB-025 | PENDENTE | Definir navegadores suportados e meta de acessibilidade; modal, navegação, gráficos e responsividade devem ser testáveis. | Produto, frontend e qualidade | Design system; login modal; dashboard; E2E | F3 e F7 | P1 | Meta aprovada; testes cobrem teclado, foco, nomes acessíveis, contraste, zoom, redução de movimento, alternativa a gráficos e viewports suportados. |
| PUB-026 | DECIDIDO | Esta matriz é a referência de coordenação transversal e deve ser lida e atualizada pelos chats das aplicações afetadas. | Responsáveis técnicos de cada aplicação | Documentação compartilhada; ADRs; contratos; PRs | Todas | NÃO | Novos documentos e mudanças transversais citam IDs da matriz; divergências são registradas; alterações materiais atualizam a matriz e seu histórico na mesma entrega. |

## 4. Fontes consolidadas

### Backend

- [`PUBLICACOES/README.md`](../PUBLICACOES/README.md)
- [`PUBLICACOES/ARCHITECTURE.md`](../PUBLICACOES/ARCHITECTURE.md)
- [`PUBLICACOES/IMPLEMENTATION_PLAN.md`](../PUBLICACOES/IMPLEMENTATION_PLAN.md)
- [`PUBLICACOES/SECURITY_PLAN.md`](../PUBLICACOES/SECURITY_PLAN.md)
- [`PUBLICACOES/OPERATIONS_GUIDE.md`](../PUBLICACOES/OPERATIONS_GUIDE.md)
- [`PUBLICACOES/SOURCE_CONTRACT_TEMPLATE.md`](../PUBLICACOES/SOURCE_CONTRACT_TEMPLATE.md)
- [`PUBLICACOES/CONSUMER_REGISTRATION_TEMPLATE.md`](../PUBLICACOES/CONSUMER_REGISTRATION_TEMPLATE.md)

### Frontend

Os links relativos abaixo pressupõem os repositórios irmãos `backend` e
`frontend` dentro do mesmo diretório de projetos.

- [`PUBLICACOES/README.md`](../../../frontend/docs/PUBLICACOES/README.md)
- [`PUBLICACOES/FRONTEND_ASSESSMENT.md`](../../../frontend/docs/PUBLICACOES/FRONTEND_ASSESSMENT.md)
- [`PUBLICACOES/DECISIONS_AND_INPUTS.md`](../../../frontend/docs/PUBLICACOES/DECISIONS_AND_INPUTS.md)

## 5. Histórico de alterações

| Data | Alteração | Origem/validação | IDs afetados |
|---|---|---|---|
| 2026-10-23 | Criação da matriz pela consolidação dos documentos de backend e do assessment frontend. | Solicitação e concordância do responsável do projeto | PUB-001 a PUB-026 |
| 2026-10-23 | Backend de autenticação endurecido e validado; bloqueio transversal permanece até a adaptação e validação do frontend. | 25 testes específicos; suíte completa com 1.130 aprovados, 1 ignorado e cobertura de 87,46% | PUB-008 e PUB-015 |
| 2026-10-23 | Aprovadas a atuação do mesmo gestor na preparação e publicação e a manutenção do acesso administrativo global de `PORTAL_ADMIN`, sem exceção às regras das aplicações. | Decisão do responsável do projeto; ADR-0001 e ADR-0002 | PUB-005, PUB-006, PUB-009 e PUB-010 |
| 2026-10-23 | Gate F0 de autenticação concluído após adaptação e validação frontend: bootstrap/rotação CSRF, login opaco sem resolução enumerável, mensagens genéricas, sessões inválidas, logout seletivo e redirect seguro. | Backend: 25 testes focados e suíte com 1.130 aprovados; frontend: 318 testes, lint, typecheck e build Webpack aprovados; E2E indisponível no repositório frontend | PUB-008 e PUB-015 |
| 2026-10-26 | Evidência frontend do gate F0 ampliada com Playwright/Chromium, preservando dados sintéticos e a fronteira HTTP controlada. | 13 testes E2E aprovados; suíte em `frontend/e2e/auth-security.spec.ts` | PUB-008 e PUB-015 |

## 6. Modelo de atualização

Ao incluir ou alterar uma linha, registrar:

```markdown
| PUB-NNN | STATUS | Texto objetivo, sem inferência | Área responsável |
Contrato/ADR afetado | Fase | P0, P1, CONDICIONAL ou NÃO | Evidência
objetiva necessária para aceitar |
```

Na mesma mudança:

1. preservar o ID; se a orientação for substituída, marcar `SUBSTITUIDO` e
   criar ou apontar o sucessor;
2. atualizar o documento especializado ou registrar por que ele ainda não pode
   ser atualizado;
3. acrescentar uma entrada no histórico com origem e validação;
4. revisar dependências e bloqueios das demais linhas;
5. não registrar a decisão como concluída sem a evidência do critério de aceite.
