# Plano de isolamento das aplicações do backend

**Estado:** criação de um banco local `gpp_plataform_hml` e cópia de estrutura,
permissões e dados aprovadas em princípio pelo responsável em 2026-11-18.
Em 2026-11-19, o responsável definiu também a implantação independente das
aplicações como objetivo obrigatório: uma correção de Carga Org/Lot deve poder
ser publicada ou revertida sem reiniciar IAM/Portal, Publicações ou Ações PNGI.
A execução e os contratos necessários dependem dos gates abaixo. Nenhuma
separação física, cópia de banco ou alteração de runtime foi executada por
este documento.

**Base:** `main` na versão estável `v0.1.0` (`856b669`), branch de trabalho
`feat/backend-isolamento-aplicacoes`, criada em 2026-11-18. Esclarecimento de
infraestrutura recebido em 2026-11-18: há somente uma instalação PostgreSQL,
um banco do projeto, nenhuma implantação institucional separada de HML/PRD e
nenhuma previsão atual de ambientes ou usuários distintos para as apps.

## Objetivo e limites

Permitir que Carga Org/Lot continue evoluindo sem desestabilizar Publicações
Institucionais, que já atingiu maturidade funcional, preservando Portal, Ações
PNGI, IAM, APIs públicas, auditoria e integrações existentes. Hoje, “Carga em
HML” e “Publicações em PRD” descrevem **estágios de maturidade das apps e/ou
ambientes das APIs externas**, não implantações próprias do projeto. A
organização do código, o isolamento de dados e a independência de implantação
são problemas distintos. Não assumir que `common` precise virar um serviço
HTTP ou que cada app precise imediatamente de um repositório próprio.

O objetivo inclui um segundo banco na instalação existente, com estrutura,
permissões e dados copiados, **e** unidades de execução/deploy próprias para
as aplicações. O banco HML é uma trilha de ensaio e não substitui a separação
dos processos; inversamente, processos separados ainda podem compartilhar
falhas e bloqueios de um banco único. Não sobrescrever o banco atual, trocar
o mecanismo de login ou cortar rotas sem contrato e rollback. Acesso à API
externa de PRD não caracteriza o backend local como ambiente de produção. A
cópia só será executada após a definição dos dados operacionais que não podem
continuar ativos no destino e da forma segura de acesso por aplicação.

## Situação observada no código da `v0.1.0`

| Fronteira | Evidência atual | Consequência para a divisão |
|---|---|---|
| Implantação | `config/settings/base.py` registra todas as apps; `config/urls.py` registra APIs de todas elas. | Flags de visibilidade e de prontidão não equivalem a isolamento de processo, release ou migração. |
| WebSocket e saúde | `config/asgi.py` monta WebSockets de Carga e Publicações no mesmo processo; `/api/health/` é agora uma verificação de vivacidade sem sessão nem cadastro de aplicações. | A vivacidade não prova prontidão do IAM, banco, broker nem da app. O contrato de prontidão e a separação de rotas operacionais ainda faltam. |
| Dados | Segundo o responsável, existe uma instalação PostgreSQL e um banco do projeto; `DATABASES` usa `DB_NAME` (padrão `gpp_plataform`); `config/routers.py` mapeia todas as apps para `default`, apesar de schemas próprios de domínio. | Um segundo banco completo é a opção aprovada; divisão por app no mesmo processo não é equivalente. |
| Portal público | A página frontend `/portal` consome `/api/public/v1/publicacoes-institucionais/`; a view pública usa `authentication_classes=[]` e `AllowAny`, sem variar a resposta por cookie. | A leitura de publicações aprovadas não pode depender de decisão IAM, sessão ou cookie. Manter cache, rate limit e DTO público separados do administrativo. |
| IAM/Portal autenticado | `accounts` mantém login, sessões e autorização; `/api/portal/` exige usuário autenticado. `Aplicacao` guarda `base_url` e `isappproductionready`; o middleware resolve cookies por prefixo. | Destinos, sessão, permissões e proxy precisam de contrato antes de implantações independentes; falha do IAM afeta operações protegidas, não deve ser transformada em bloqueio da vitrine pública. |
| Assíncrono | `config/celery.py` descobre tarefas; `CELERY_BEAT_SCHEDULE` agenda tanto monitoramento de Carga quanto recuperação E-Docs; há um broker configurado para o processo. | Filas, workers e agendadores precisam de isolamento por app e por execução, para que reiniciar Carga não interrompa nem consuma tarefas de Publicações. |
| Integrações | E-Docs tem seleção HML/PRD por configuração; Carga e Publicações usam o cofre compartilhado em `common`. | Ambiente da API externa não equivale a ambiente de implantação; credenciais e destino precisam continuar explícitos. |
| Dependências | Apps chamam `CanPermission` em `core` e serviços/modelos em `accounts`; Publicações usa `common` para IBGE e cofre. | Formalizar contratos de IAM e utilidades compartilhadas antes de extrair processos. |

### Resultado operacional exigido

O repositório pode continuar único, mas cada serviço deve ter processo,
configuração, versão implantada, rota no proxy, verificação de saúde e rollback
próprios. Carga, Publicações e Ações PNGI devem possuir workers/filas próprios
quando executarem tarefas; cada agendamento deve ter um único responsável.
IAM/Portal é a autoridade central de identidade e autorização, não o processo
que hospeda as regras e tarefas de todas as apps. `common` é código
compartilhado por contrato/versionamento, não um serviço HTTP obrigatório para
cada função genérica.

O proxy deve preservar os caminhos públicos e administrativos existentes
enquanto encaminha cada domínio ao serviço correspondente. A aplicação deve
poder iniciar e expor seu estado local mesmo se o IAM estiver temporariamente
indisponível; operações que exigem identidade/autorização devem falhar de
forma explícita e segura, sem aprovação implícita. Distinguir vivacidade do
processo, prontidão para receber tráfego e estado das dependências. Não usar
uma chamada de saúde como prova de autorização de uma requisição.

O Portal possui duas superfícies distintas. A página pública frontend
`/portal` lê somente os contratos versionados de Publicações em
`/api/public/v1/publicacoes-institucionais/`, sem enviar ou exigir cookie; a
API pública permanece no domínio de Publicações, não no serviço IAM. Já o
dashboard autenticado do Portal, login e acesso às aplicações usam as sessões
`gpp_session_*` e a decisão de identidade/autorização do IAM. Uma queda do IAM
deve negar de forma segura novas operações protegidas, mas não deve bloquear
por si só a leitura da publicação pública vigente se frontend, API pública e
dados de Publicações estiverem disponíveis. Não expor `/api/portal/` nem a
prévia administrativa como substitutos da API pública.

O [inventário I0](./BACKEND_APPLICATION_ISOLATION_I0_INVENTORY.md) detalha
os contratos propostos de saúde e o guard de autorização para HTTP,
WebSocket, Celery e comandos. Cada **operação protegida** deve passar pelo
guard na entrada; não inserir um `ping` antes de cada método interno nem
transformar funções locais de `common` em dependências de rede.

**Cenário de aceite:** retirar Carga do encaminhamento, publicar ou reverter
somente seu processo HTTP, WebSocket e worker, e recolocá-la após validação.
Durante todo o ensaio, IAM/Portal, Ações PNGI e a API pública e administrativa
de Publicações continuam respondendo sem reinício; suas tarefas não são
consumidas por workers de Carga. O resultado deve ser comprovado por versões,
logs, requisições e filas observadas antes, durante e depois da intervenção.
Com uma única instância de Carga, apenas Carga poderá ficar indisponível na
janela; atualização sem indisponibilidade dessa própria app exige instâncias
paralelas e estratégia de troca gradual.

O registro de dívida em
[BACKEND_RELEASE_READINESS_V0.1.0.md](./BACKEND_RELEASE_READINESS_V0.1.0.md)
é a linha de base para o inventário; não é uma autorização de refatoração ampla.

## Opções viáveis para o PostgreSQL atual

| Opção | Quando usar | Ganho | Limite/custo |
|---|---|---|---|
| **Manter `gpp_plataform` e schemas atuais** | Agora, sem implantações nem usuários distintos. | Nenhuma migração; preserva dados, relações, IAM e operação existente. | Não permite testar alterações destrutivas com segurança na mesma base. |
| **Criar `gpp_plataform_hml` na mesma instalação** | Para ensaiar migrações, cargas e releases sem tocar na base atual. | Isola dados e histórico de migração por banco; aproveita a instalação existente. | Compartilha servidor, CPU, disco, administração e falhas; exige configuração, roles, backups e tratamento de dados próprios. Não é HML institucional. |
| **Nova instância PostgreSQL** | Somente se for preciso separar operação, configuração, manutenção ou capacidade; idealmente em host/VM próprio para independência real. | Maior isolamento operacional, sobretudo fora da mesma máquina. | Mais custo de implantação, observabilidade, backup, segurança e suporte; outra instância na mesma máquina ainda compartilha o host. |
| **Banco por app** | Etapa posterior, após contratos e propriedade dos dados definidos. | Independência maior de release e retenção. | Exige tratar FKs com IAM, migrações, transações e consultas; não é simples troca de `SchemaRouter`. |

**Direção aprovada:** preservar `gpp_plataform` e criar
`gpp_plataform_hml` **na instalação existente**, copiando schemas, tabelas,
histórico de migrações, dados de domínio, usuários, perfis e permissões.
Os perfis/permissões do Django são dados do banco; roles e grants do próprio
PostgreSQL são administrados no nível da instalação e exigem configuração
separada para um usuário HML sem acesso à base atual.
Os dois bancos continuarão locais; o sufixo `_hml` não representa uma HML
institucional. A cópia não deve deixar sessões autenticadas, tokens de envio
ou outras credenciais operacionais utilizáveis no destino. Decidir antes da
execução se esses registros serão removidos, revogados ou substituídos **só no
clone**, preservando o histórico/auditoria necessário. Inventariar também
arquivos binários e dados pessoais. Uma cópia integral sem esse tratamento
fica pendente de classificação e aprovação explícita.

**Verificação pontual em 2026-11-18:** o banco de origem respondia como
PostgreSQL 18.1, com cerca de 25 MB, 4 usuários, 142 linhas em
`django_session` e 324 em `AccountsSession`; `gpp_plataform_hml` não existia.
Há conexões ativas na origem. O `pg_dump` disponível neste WSL é 16.15, que
não pode exportar servidor 18. Foi confirmado também o `pg_dump.exe` 18.1
instalado no Windows, executável com autorização a partir do WSL; usar esse
cliente compatível, após ensaiar conexão, formato e restauração. Não usar
`CREATE DATABASE ... TEMPLATE
gpp_plataform` como atalho enquanto a origem tem conexões: isso falha ou
exige interrompê-las. Não desligar a aplicação para clonar.

**Seleção por aplicação:** o objetivo aprovado é poder indicar qual conjunto
de dados cada app usa e implantar suas versões independentemente. Não
implementar já um router que envie apps diferentes
para bancos diferentes no mesmo processo: `accounts` e autenticação usam
`default`, e `publicacoes.preferencia_exibicao_eflow` possui FK para
`auth_user`; o Django não suporta essa relação entre bancos. Proposta mais
segura para **ensaio transitório**: duas execuções completas do backend, cada
qual com `DB_NAME`, broker/cache, segredo, URLs e tarefas próprios. Isso
permite testar a cópia HML, mas ainda duplica IAM e não satisfaz o requisito
final de deploy por app. O desenho-alvo requer serviços próprios atrás do
proxy e contrato explícito com o IAM central, sem FKs entre bancos.

## Princípios propostos

1. **Domínio:** modelos, regras editoriais, endpoints e tarefas pertencem à app
   responsável. Não mover regras de Publicações, Carga ou Ações para `common`.
2. **Compartilhamento de código:** `common` contém abstrações genéricas
   reutilizáveis por import no mesmo processo ou, futuramente, por pacote
   versionado. Não criar uma API para uma função local apenas por ela ser comum.
3. **IAM:** `accounts` é a autoridade de identidade, sessões, menus,
   capabilities e permissões. `core` deve reter somente mecanismos profundos;
   apps não devem replicar a política de autorização. Se houver processos
   independentes, especificar uma interface segura de validação/autorização
   antes de trocar o acesso interno atual por comunicação remota.
4. **Infraestrutura reutilizável:** Celery, Redis, PostgreSQL, OpenBao,
   observabilidade e proxy podem ser tecnologias da plataforma. Se forem
   criadas implantações locais distintas, a configuração, credenciais, filas,
   agendamentos, dados e permissões de cada uma deverão ter limites explícitos.
   Compartilhar o produto Redis não significa misturar tarefas ou caches.
5. **Contratos:** APIs públicas permanecem separadas das administrativas;
   dados aprovados e congelados de Publicações não dependem de consultas ao
   estado operacional de outras apps. Frontend não implementa regras de IAM nem
   chama fontes externas em lugar do backend.
6. **Evolução incremental:** preservar o repositório e o comportamento atual
   até que cada fronteira tenha teste, migração e rollback. Separar repositórios
   só se o ganho operacional justificar manutenção, CI e versionamento extras.

## Revisão de padrões e lacunas do desenho

A direção está alinhada a serviços por **capacidade de negócio** e extração
gradual, não a uma divisão por camadas técnicas. O objetivo mensurável é
release e falha isolados, não adotar toda a infraestrutura de microsserviços.
O mesmo repositório e a mesma instalação PostgreSQL podem permanecer durante
a transição, desde que a propriedade de tabelas, processos e alterações seja
explícita. Os padrões abaixo foram avaliados contra o código atual; são
decisões de aplicação, não autorização para instalar tecnologias novas.

| Padrão/controle | Situação e lacuna concreta | Momento |
|---|---|---|
| **Contextos delimitados e propriedade de dados** | Schemas de domínio já existem, mas `accounts`/`auth` são compartilhados e não há matriz de quem pode ler, escrever e migrar cada tabela. Definir fonte autoritativa e proibir novas escritas cruzadas antes de prometer deploy autônomo. | I0: matriz de propriedade; I4/I5: isolamento progressivo de acesso. |
| **Strangler Fig + proxy** | As rotas têm prefixos estáveis, mas não há plano de coexistência com um único escritor, comparação de respostas, troca reversível de tráfego e retirada da rota antiga. Evitar escrita simultânea no legado e no serviço extraído. | I0: desenho; I4: piloto de Carga. |
| **Branch by Abstraction / adaptador de IAM** | A primeira fronteira local em `apps/core/services/autorizacao_iam_local.py` já concentra a decisão de `CanPermission` e do WebSocket de Carga, preservando o `AuthorizationService`. Ainda não é interface remota nem resolve sessão, autorização por objeto ou falha do IAM. Comparação paralela só como diagnóstico, nunca como permissão adicional. | I2: contrato remoto; I3: adaptação completa; I4: troca controlada. |
| **Bulkhead, timeout e circuit breaker** | Broker, cache, banco e execução estão compartilhados; um `ping` por método aumentaria carga e falhas em cascata. Isolar filas/workers, limites de conexão/concorrência e aplicar timeout a chamadas remotas. Circuit breaker pode limitar chamadas inúteis, mas nunca converter falha IAM em acesso permitido. | I0: orçamento de recursos/falhas; I3/I4: implementação proporcional. |
| **Compatibilidade de APIs e dados** | Há um único artefato Django e uma suíte global; versões antiga/nova de IAM, app e schema terão de coexistir durante o corte. Definir matriz de versões, testes de contrato consumidor/provedor e migrações aditivas antes de remover campos/rotas. | I2: contratos; I3: CI e migração; I4: teste de coexistência. |
| **Mensageria confiável** | Celery usa tarefas por domínio, mas ainda não há filas por serviço nem política completa de duplicação/retomada. Verificar idempotência, mensagens em voo, publicação após commit e necessidade de outbox/inbox; não implantar outbox ou saga sem fluxo entre bancos que justifique. | I0: inventário de efeitos; I3/I4: proteção dos fluxos críticos; posterior: padrões distribuídos se necessários. |
| **Observabilidade distribuída** | Há logs e auditoria de domínio, porém não foi demonstrada correlação ponta a ponta entre proxy, IAM, API, Celery e fontes externas. Definir IDs de correlação, métricas, alertas, redaction, retenção e teste de indisponibilidade. | I0: sinais mínimos; I3/I4: instrumentação e ensaio. |
| **Entrega independente** | `scripts/localhost_dev.sh` encerra todos os processos juntos; o checkout não contém pipeline de deploy por app. Definir artefato/configuração/versão por serviço, supervisor, rollback, migração executada uma vez e smoke por rota, sem exigir Kubernetes. | I0: topologia e operação; I3: automação; I4/I5: aceite por serviço. |

Referências de desenho: [análise de domínios e contextos](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis),
[Strangler Fig](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-decomposing-monoliths/strangler-fig.html),
[Branch by Abstraction](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-decomposing-monoliths/branch-by-abstraction.html),
[Bulkhead](https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead),
[dados por serviço](https://learn.microsoft.com/en-us/azure/architecture/microservices/design/data-considerations),
[comunicação e idempotência](https://learn.microsoft.com/en-us/azure/architecture/microservices/design/interservice-communication)
e [propagação de contexto de observabilidade](https://opentelemetry.io/docs/concepts/context-propagation/).

**Não necessários agora:** service mesh, Kubernetes, saga, event bus ou banco
físico por app. Só considerar cada um diante de uma necessidade medida.
`gpp_plataform_hml` é um clone por ambiente de ensaio, não o banco exclusivo
de Carga; confundir essas duas fronteiras criaria falsa independência.

## Fases e gates

### I0 — Inventário e desenho-alvo (sem runtime)

- Mapear imports entre `apps/*`, `common`, `core` e `config`; relações entre
  modelos/schemas; rotas, WebSockets, middleware, seeds, jobs, integrações,
  secrets, caches e observabilidade. Distinguir o que é genérico do que é regra
  de domínio. Identificar quem opera cada componente.
- Desenhar os fluxos **atuais**: Portal → API, app → IAM, app → Celery,
  worker → banco/cofre/fonte externa. Registrar a única implantação existente,
  sua URL, cookies, CSRF, CORS, broker e cache, e distinguir explicitamente os
  alvos externos HML/PRD; não inventar ambientes internos que não existem.
- Inventariar a saúde atual e propor contratos separados de vivacidade,
  prontidão, estado de dependências e autorização. Verificar os guardas de
  HTTP, WebSocket, tarefas e comandos, inclusive revogação e falha do IAM.
- Construir matriz de propriedade por tabela/schema e fluxo (leitura, escrita,
  migração, backup), incluindo `auth`, `accounts`, sessões e auditoria. Registrar
  transações/joins entre domínios, artefatos externos, arquivos e efeitos das
  tarefas. Definir uma única fonte autoritativa e escritor por dado durante o
  cutover. Levantar dependências operacionais, limites de recursos e metas
  mínimas de disponibilidade/recuperação por serviço.
- Inventariar o proxy, supervisor e pipeline de deploy reais, inclusive
  cabeçalhos de identidade confiáveis, TLS, portas, cookies, CSRF, WebSocket,
  versão dos artefatos, observabilidade e rollback. A sandbox `infra/publicacoes-dev`
  não é evidência de implantação institucional.
- Desenhar separadamente o ensaio de duas execuções locais e a topologia-alvo
  de serviços por app com IAM central. Não assumir que um único processo Django
  possa misturar bancos mantendo FKs e sessão; mapear a substituição dessas
  relações por contratos e identificadores estáveis quando necessária.
  Inventariar as tabelas, roles, permissões, sessões, tokens, arquivos e dados
  sensíveis a copiar ou neutralizar apenas no destino. Verificar capacidade de
  backup/restauração com cliente PostgreSQL 18 e espaço disponível.
- Definir o próximo passo justificável sem antecipar o cutover. Deploy por app
  é meta obrigatória; o protocolo de consulta/validação com IAM e a política
  de indisponibilidade ainda precisam ser aprovados antes da implementação.
- **Gate I0:** inventário da execução atual, topologia operacional e matriz
  de propriedade de dados conferidos; significado de “seleção por app”, metas
  e cenários de falha por serviço definidos. A política de cópia e
  neutralização no clone pode permanecer pendente para I1, sem impedir o
  desenho de contratos I2; nenhuma migração ou clonagem antes do gate I1.

### I1 — Banco e execução de ensaio locais

Esta trilha operacional pode avançar em paralelo ao desenho I2/I3. Seu gate
é necessário antes de um piloto I4 que use o clone, não para documentar ou
testar isoladamente o contrato IAM.

- Após I0, criar o banco de ensaio na instalação existente, com role sem
  privilégios sobre a base atual, backup/restauração verificados, cópia de
  estrutura/permissões/dados aprovada e validação do destino antes de
  `migrate` ou jobs. Neutralizar sessões e credenciais operacionais somente no
  clone, conforme política aprovada. Não tratar a base atual como PRD
  institucional.
- Documentar configurações separadas de conexão, broker, cache, storage,
  OpenBao, URLs, proxy e alvos externos para cada execução que vier a existir.
- Definir roteamento de tarefas para filas por execução e app, workers
  identificáveis e um agendador responsável por job/execução; registrar política
  para tarefas já enfileiradas durante deploy/rollback. Evitar que uma
  execução de teste consuma tarefas da execução principal. Limites de
  concorrência e falhas de Carga não devem degradar a publicação pública.
- Revisar o destino do Portal se houver mais de uma implantação:
  `Aplicacao.base_url` possui um valor único. Escolher cadastros de IAM
  separados por execução **ou** destino parametrizado; não duplicar
  identidade/capabilities sem decisão.
- **Gate I1:** testes de não cruzamento entre execuções, smoke de API/login, jobs,
  publicação pública, logs e rollback de configuração executados em ambiente
  controlado. Não equiparar `isappproductionready` à existência de PRD.

### I2 — Contratos de IAM e compartilhamento

**Avanço parcial em 2026-11-19:** a decisão de usar consulta interna ao IAM
para o piloto de Carga foi aprovada. O
[contrato v1](./BACKEND_IAM_DECISION_CONTRACT_V1.md) e seu endpoint IAM
desativado por padrão existem; testes unitários cobrem as fronteiras básicas.
O gate I2 **não** foi concluído: o cliente M2M está ligado aos guards HTTP e
WebSocket de Carga por flags distintas, desligadas por padrão; o piloto HTTP
integral já dispensa as consultas dos middlewares locais de Carga quando sua
terceira flag está ativa. Faltam ensaio na topologia final,
proteção operacional do canal e política para tarefas Celery. Concorrência
entre decisões e revogações, transporte HTTP em loopback e revalidação de
WebSocket ocioso já foram ensaiados localmente. O piloto WebSocket remoto não
consulta mais sessões/roles locais de Carga. Testes com sessões e roles reais no banco
`test_gpp_plataform` passaram, mas não comprovam isolamento de serviços.

- Documentar o contrato atual de sessão, `app_context`, autorização,
  capabilities, menus, invalidação de permissões e auditoria. Separar a
  interface consumida pelas apps da implementação interna de `accounts`.
- Aprovar como cada operação protegida obtém uma decisão IAM válida, com
  timeout e negação segura, sem fazer `ping` redundante antes da decisão.
  Definir o que acontece com WebSockets longos e tarefas já autorizadas mas
  ainda não executadas quando a sessão/permissão é revogada.
- Aprovar erros distinguíveis para `401` (sessão inválida), `403` (decisão
  negativa) e `503` (IAM ou app indisponível), correlação, `Retry-After` quando
  fundamentado e resposta própria do proxy. O frontend não deve interpretar
  indisponibilidade como logout nem repetir mutações sem idempotência.
- Para os serviços separados, decidir entre gateway com autenticação
  centralizada e contrato interno de identidade/autorização, ou tokens
  verificáveis/introspecção. Especificar revogação, expiração, propagação de
  mudanças de permissão, falhas do IAM, conta de serviço e proteção contra
  uso de credenciais HML em PRD. Não transportar cookies de sessão como
  substituto implícito de um contrato entre serviços.
- Catalogar `common`: cofre, IBGE, auditoria, serialização e utilidades de
  framework. Definir API/versão apenas para capacidades que precisem existir
  fora do processo; preferir biblioteca compartilhada para código puro.
- Versionar o contrato IAM e seus consumidores; definir matriz de
  compatibilidade entre versão central, apps e frontend, testes de contrato
  consumidor/provedor e período de coexistência. Credenciais M2M e qualquer
  cabeçalho de identidade devem ser restritos a tráfego interno confiável.
- **Gate I2:** contrato versionado, testes negativos de autorização e de
  revogação, compatibilidade de Portal e apps, auditoria e modelo de falha
  aprovados antes de substituir imports diretos.

### I3 — Modularização interna, sem extração física

- Mover gradualmente configurações de cada domínio para módulos de
  composição, mantendo `config` como ponto de montagem; definir dependências
  permitidas e verificação automática de imports. Revisar referências a
  `accounts` em `core` e nas apps, sem alterar semântica de permissões.
- Tornar rotas, tarefas e seeds explicitamente associados à app e ao ambiente
  habilitado. Proteger migrações e rotinas administrativas contra execução no
  banco ou ambiente errado. Preservar URLs e payloads existentes.
- Criar alvos de build/teste e artefatos versionados por serviço, mantendo
  suíte compartilhada; testar versões antiga/nova simultâneas e migrações
  aditivas antes de remover contratos. Definir orçamento de timeout,
  concorrência, conexão e fila para conter falha de um domínio.
- Classificar tarefas de Carga por idempotência, efeitos externos, retry,
  duplicação e estado em voo. Avaliar outbox/inbox apenas onde a gravação no
  banco e o envio de mensagem/evento formarem uma garantia necessária.
- **Gate I3:** suíte completa, migrações, OpenAPI, lint, segurança, contratos
  públicos, filas e cenários de rollback aprovados; nenhuma mudança observável
  nas apps existentes sem versão de API.

### I4 — Piloto obrigatório de implantação independente

- Só após I0–I3, usar Carga Org/Lot como piloto e construir processo/deploy próprio
  consumindo o IAM pelo contrato aprovado. Definir propriedade dos dados e
  plano de migração do schema, se necessário; não pressupor que mudar
  `SchemaRouter` sozinho separa bancos, FKs, transações ou histórico.
- Fazer deploy paralelo e cutover controlado de rotas/filas, com monitoramento,
  rollback e comparação de respostas. Preservar histórico e auditoria. Usar
  um único escritor de dados e impedir que as versões antiga e nova executem
  o mesmo agendamento; ensaiar falhas de IAM, banco, broker, proxy e fonte
  externa sem desligar as demais apps.
- **Gate I4:** atualizar e reverter Carga sem reiniciar IAM/Portal, Ações PNGI
  ou Publicações; confirmar HTTP, WebSocket e filas das demais apps antes,
  durante e depois. Testes de integração e segurança aprovados, restauração
  ensaiada e eventual janela operacional autorizada. Não chamar o banco local
  `_hml` de ambiente institucional de HML ou assumir PRD institucional.

### I5 — Extensão controlada às demais aplicações

- Após o piloto, aplicar o contrato e o processo de deploy independente a
  Publicações e Ações PNGI, sem reabrir suas regras de negócio. Preservar a
  API pública anônima, os dados congelados e os controles de publicação;
  separar workers, agendamentos e segredos por app.
- Retirar rotas/processos antigos somente após comparação, período de
  observação, rollback ensaiado e confirmação de que não há dois escritores.
  Avaliar banco próprio por serviço quando a dependência de schema/shared DB
  impedir release autônomo; não tratar a cópia HML como substituto.
- **Gate I5:** uma atualização e reversão independentes de cada app
  demonstradas sem reiniciar IAM/Portal ou as demais, com auditoria, filas,
  OpenAPI, contratos frontend e restauração verificados.

## Decisões necessárias antes da execução técnica

| Decisão | Opções a avaliar | Por que importa |
|---|---|---|
| Topologia inicial | Serviços separados por aplicação com IAM/Portal central (direção aprovada); perfis completos por banco podem ser usados como ensaio transitório, não como arquitetura final | Define contrato de IAM, proxy, deploy, tarefas e rollback independentes. |
| IAM e Portal | Único cadastro atual; futuramente, cadastro por execução ou serviço compartilhado segregado | Evita URLs, sessões e permissões cruzadas se houver duas implantações. |
| Banco | Preservar `gpp_plataform` e adicionar `gpp_plataform_hml` na mesma instalação (direção aprovada) | Evita custo de nova instância; exige cópia segura e neutralização de sessões/tokens. |
| Assíncrono | Filas por app; separar brokers/filas entre execuções quando existirem | Impede execução cruzada e contenção de recursos. |
| Fontes externas | Endereço HML ou PRD de E-Docs/PRODEST independentemente da implantação local | `GPP_EDOCS_ENVIRONMENT` não prova o ambiente do backend. |
| Serviços comuns | Biblioteca versionada, serviço de IAM, ou ambos | Evita transformar toda utilidade em API remota. |

## Validação e rollback do programa

Para cada PR, registrar comportamento anterior, contrato alterado, ambientes
atingidos, testes unitários/de integração, `manage.py check`, migrações,
OpenAPI, lint, verificação de segredos e dependências. Mudanças em IAM, cookies,
filas ou banco exigem testes de isolamento, revogação, indisponibilidade e
recuperação. Cada etapa operacional deve permitir voltar à configuração e ao
deploy anterior sem perder tarefas, publicações aprovadas ou evidência de
auditoria. Não executar migração destrutiva ou cutover sem backup/restauração
ensaiados.

## Próximo trabalho

O inventário I0 e o contrato IAM v1 já foram registrados. Existem pilotos
reversíveis de decisão remota nos guards HTTP e WebSocket de Carga, ambos
desligados por padrão; isso **não** conclui I2 nem autoriza o corte para
serviços independentes. O próximo incremento é fechar as lacunas descritas
no [contrato IAM v1](./BACKEND_IAM_DECISION_CONTRACT_V1.md): escopo de objeto,
revogação de WebSockets na topologia final, proteção das tarefas e ensaio operacional com
proxy/canal protegido. A criação de `gpp_plataform_hml` permanece
trilha operacional separada, sem restaurar o dump ou afetar o banco atual
antes do gate I1. Não ativar os pilotos nem cortar rotas enquanto os gates
de segurança, operação e rollback correspondentes estiverem abertos.

O contrato IAM v1 fornece `usuario_nome` em decisões autorizadas. O modo
HTTP integral de Carga, sob `GPP_CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA`,
dispensa as consultas locais de `AccountsSession`, `UserRole` e `Aplicacao`
somente no prefixo de Carga; foi testado no pipeline Django e permanece
desligado por padrão. O modo existente não mudou. Isso ainda não demonstra
implantação independente nem autoriza o corte de tráfego.
