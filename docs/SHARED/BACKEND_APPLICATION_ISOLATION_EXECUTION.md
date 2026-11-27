# Execução do isolamento do backend — linha de base e próximos gates

**Revisão:** 2026-11-27. **Estado:** plano de execução iniciado; sem ativação dos
perfis separados, troca de proxy ou alteração de banco nesta etapa. Este
documento atualiza a sequência operacional do
[plano I0–I5](./BACKEND_APPLICATION_ISOLATION_PLAN.md) sem apagar seu histórico.
Os resultados dos ensaios continuam nos contratos dos pilotos de
[Carga](./BACKEND_CARGA_ISOLAMENTO_PILOTO.md) e
[Publicações](./BACKEND_PUBLICACOES_ISOLAMENTO_PILOTO.md).

## Objetivo e ordem

Cada aplicação deve poder ser reiniciada, publicada e revertida sem reiniciar
as demais. IAM/Portal autenticado continua autoridade de identidade e
autorização; a API pública de Publicações continua independente de sessão e
IAM. `common` é biblioteca compartilhada, não serviço de rede. Uma verificação
de saúde nunca substitui a decisão de autorização de uma operação protegida.

O trabalho restante será feito em entregas pequenas, na ordem abaixo. Mudanças
de banco, clone `_hml`, separação física de dados e cutover ficam **por último**.
O banco atual é compartilhado pelos perfis piloto e não há implantação
institucional separada de produção/homologação. Nenhum teste ou perfil opt-in
constitui autorização para ativação operacional.

### Fronteira de comunicação proposta para E1

O princípio proposto pelo responsável é que uma app de negócio não importe
modelos, serviços ou regras de outra app
de negócio, nem ler ou escrever suas tabelas. Ela conhece **contratos**:
decisão IAM para operação protegida, API versionada quando precisa de uma
resposta de outro domínio, ou evento assíncrono quando o fluxo tolera atraso.
O produtor e o consumidor não compartilham ORM ou transação entre domínios.

O gateway aqui é uma **interface/adaptador por capacidade**, não um serviço
central que repassa toda chamada. O transporte genérico, validação de contrato
e correlação podem residir em `common`; IAM/`accounts` continua dono da
política e dos dados de identidade. `core` retém mecanismos profundos de
composição, sem regras de Carga/Publicações/Ações. Funções puras de `common`
continuam chamadas locais: transformá-las em HTTP só aumentaria latência e
disponibilidade exigida. Também não inserir `ping` antes de cada método: a
decisão IAM da própria operação é a verificação autoritativa, com timeout e
falha fechada. A API pública de Publicações não passa pelo IAM.

Quando surgir comunicação entre domínios de negócio, escolher contrato
direto entre proprietário e consumidor, possivelmente por trás de um cliente
compartilhado, ou evento com entrega/idempotência definidos. Não fazer
`core`/`common` depender de uma app específica nem construir um gateway
universal sem caso concreto. Mais mensagens exigem orçamento de timeout,
retry, observabilidade e comportamento quando a dependência está fora; esse
custo deve ser explícito no contrato.

| Entrega | Trabalho | Evidência para fechar | Limite |
| --- | --- | --- | --- |
| E0 — linha de base | Reconciliar plano I0–I5, inventário I0, pilotos e worktree; registrar comprovado, opt-in e pendente. | Matriz abaixo revisada contra código e ensaios. | Não converter resultado sintético em aceite operacional. |
| E1 — fronteiras | Matriz de propriedade de rotas, tarefas, configurações, modelos e dados; inventariar imports e escritas entre apps; estabelecer verificação automatizada apenas após aprovar exceções. | Nenhuma regra de domínio nova em `core`/`common` ou outra app; teste de dependências permitidas e revisão das exceções. | Não mover módulos nem separar banco nesta entrega. |
| E2 — contrato operacional | Definir vivacidade, prontidão e estado de dependências por serviço, timeouts e respostas `401/403/503/502`; manter API pública sem dependência IAM. | Testes de IAM parado, serviço parado, proxy e WebSocket; não transformar `503` em logout nem repetir mutação automaticamente. | `/api/health/` permanece vivacidade até existir contrato distinto. |
| E3 — execução independente | Perfis reproduzíveis de IAM, Carga, Publicações e Ações PNGI; filas/workers próprios quando houver tarefas, Beat único, segredos/cache e scripts de start/stop/restart por serviço. | Reinício individual e inspeção de rotas, tarefas, Beat, filas e migrações; nenhuma tarefa executada no processo errado. | Criar perfil de Ações sem alterar sua regra de negócio; não trocar launcher/proxy em uso. |
| E4 — ensaio ponta a ponta | Repetir via proxy protegido HTTP, WS, CSRF/cookies próprios, `/interno/` bloqueado, indisponibilidade, revogação, concorrência, retomada e rollback de processo. | Registros antes/durante/depois para IAM, Carga, Publicações, Portal público e Ações; auditoria e mensagens em voo preservadas. | Somente processos, broker e credenciais descartáveis até autorização de janela. |
| E5 — gate pré-ativação | Suíte, OpenAPI, lint, segredo/dependências, compatibilidade A/B, métricas/alertas por serviço/fila e runbooks de supervisão e rollback. | Critérios verificáveis no CI e ensaios de alerta/disparo/recuperação; dois artefatos do piloto coexistem sem decisão permissiva. | Não chamar `v0.1.0` de versão anterior compatível com perfis que não continha. |
| E6 — dados e ativação | Por último: política de clone/neutralização, migração/rollback real, propriedade de schemas, rota e fila operacional, um escritor e um Beat. | Backup/restauração, janela aprovada e cutover reversível por app; observar demais serviços durante cada intervenção. | Sem banco ou cutover antes dos gates anteriores. |

## Linha de base em 26/11/2026

| Área | Comprovado em código/ensaio | Opt-in ou ainda pendente |
| --- | --- | --- |
| Processos e rotas | Existem perfis ASGI/URL de IAM, Carga e Publicações. Proxy TLS alternativo foi ensaiado, inclusive reinício individual. | Perfis e proxy em uso não foram trocados; IAM piloto ainda serve Ações PNGI. Falta perfil próprio e ensaio de Ações. |
| IAM e API pública | Decisão IAM v1 e consumidor remoto de Carga/Publicações foram ensaiados. `401`, `403` e `503` falham fechados; API pública de Publicações seguiu disponível com IAM parado. | Flags dos consumidores são opt-in; canal e credenciais reais, compatibilidade de binários e monitoramento operacional não estão aprovados para corte. |
| Tarefas | Filas de Carga/Publicações, Beat único e recuperação sintética com Redis descartável foram ensaiados. Revogação em tarefas de domínio tem testes. | Tarefas reais, efeitos externos, mensagens operacionais em voo e métricas/alertas de fila precisam de ensaio. Recuperação de revisão E-Docs órfã está atrás de flag desligada até atualização coordenada de workers. |
| Mutações e auditoria | Matriz dinâmica cobriu 80 rotas mutáveis com `401/403/503` antes do handler; testes representativos confirmaram ausência de gravação quando IAM caiu. | Falta verificar efeito e auditoria de cada mutação autorizada e negação, com escopo por objeto quando aplicável. |
| Migração | Ambos os perfis de domínio bloqueiam migração. Backup, restauração e reversão 0016/0015 foram ensaiados em banco descartável. | Plano operacional de migração única, compatibilidade A/B, rollback do binário e restauração da implantação real ficam para E5/E6. |
| Saúde e observabilidade | `/api/health/` é vivacidade; `/api/ready/` verifica o banco local nos perfis piloto e monólito. Prontidão individual e falha `502` foram ensaiadas no proxy TLS alternativo. ID de correlação chegou do proxy TLS ao log IAM em ensaio anterior. | Queda real do banco, prontidão na topologia operacional futura, métricas por serviço/fila, limiares e alertas de dependências ainda faltam. Ver [E2](./BACKEND_APPLICATION_ISOLATION_E2_READINESS.md). |

### Regra de paridade IAM para E3 em diante

Qualquer alteração no contrato ou na implementação **compartilhada** do IAM
deve ser revista e testada na mesma entrega para Carga, Publicações e Ações
PNGI; incluir Portal autenticado quando a alteração afetar sessão, login,
roles, permissões ou menus. Não declarar a entrega concluída com apenas um
consumidor adaptado. A matriz mínima é: cookie exato da aplicação, decisão
por permissão e escopo, credencial M2M exclusiva, revogação, CSRF, respostas
`401`/`403`/`503`, auditoria/correlação, tarefas em curso quando existirem,
rotas/proxy e testes de regressão de cada consumidor. Uma regra específica
de domínio só será compartilhada após confirmar que o contrato é realmente
comum, não por semelhança de implementação.

O incremento de E3 adicionou o **produtor IAM opt-in** de Ações PNGI em
`/interno/iam/v1/decisoes-acoes/` e o consumidor HTTP opt-in, preservando o
modo monolítico. O validador de unicidade das credenciais M2M cobre Carga,
Publicações e Ações, inclusive decisões de atividades de Carga/Publicações.
O consumidor aceita apenas `gpp_session_ACOES_PNGI`, decide cada permissão
no IAM, mantém CSRF e responde `401`/`403`/`503` sem autorizar por cache local.
O teste ponta a ponta usa o endpoint produtor e o cliente HTTP real, mas
substitui a rede por `Client`; não é ensaio de canal operacional.

Há dois novos perfis **opt-in**: `acoes_piloto` serve só as rotas de Ações,
vivacidade e prontidão; `plataforma_quatro_piloto` serve IAM/Portal sem as
rotas de Ações. O primeiro bloqueia migrações e não registra tarefas nem
Beat; o segundo mantém o Beat único. O piloto de três processos, proxy e
launcher em uso não foram alterados. A credencial M2M exclusiva de Ações
**não foi provisionada**; o produtor retorna `404` sem ela e o consumidor
falha fechado. Não subir os novos perfis simultaneamente ao perfil IAM de
três processos, que ainda oferece as rotas de Ações.

Nesta rodada, 186 testes conjuntos de IAM, Portal, Carga, Publicações e
Ações passaram em `test_gpp_plataform`; os perfis novos passaram no
`manage.py check`, seus ASGI importaram com settings corretos e os dois
schemas OpenAPI validaram. A suíte completa de Ações e o teste estático de
fronteiras passaram (195 testes). O proxy alternativo de quatro processos
(`infra/publicacoes-dev/compose-isolamento-quatro.yaml`) e um ensaio TLS
descartável foram adicionados sem alterar o proxy em uso. O ensaio usa
credenciais sintéticas e `test_gpp_plataform`; verificou encaminhamento,
cookie próprio, revogação e parada individual de Ações sem derrubar os demais
processos. Outro ensaio parou o IAM e confirmou `503` sem gravação em Ações,
mantendo a API pública de Publicações acessível. A inspeção das mutações
aninhadas de Ações identificou e corrigiu a possibilidade de criar ou mover
um filho para uma Ação diferente da URL; as três rotas agora recusam o
vínculo divergente. A suíte de Ações passou com 199 testes. Para fechar E3,
ainda faltam credencial/canal operacional do piloto, ensaio de reinício
individual com tráfego em voo, inspeção das demais mutações e efeitos de
auditoria (especialmente exclusões) e observabilidade. A
migração/ativação real permanece no gate E6. Nenhuma senha do PostgreSQL
será trocada nesta etapa.

### Pendência de inicialização sem ordem fixa (27/11/2026)

Os serviços de Carga, Publicações e Ações PNGI não devem depender de o IAM
ser o primeiro processo a subir. Se uma aplicação iniciar antes dele, deverá
permanecer operacionalmente recuperável, aguardar a disponibilidade do IAM
para operações protegidas e passar a atendê-las quando o IAM estiver pronto,
sem reinício manual. Durante a indisponibilidade, essas operações devem
continuar falhando fechadas com o contrato `503 servico_iam_indisponivel`,
sem executar mutações nem interpretar a falha como sessão revogada. A API
pública de Publicações permanece independente do IAM.

Isto é **requisito registrado, não mecanismo implementado nem validado**.
`/api/health/` comprova somente vivacidade e `/api/ready/` verifica o banco
local; nenhum deles hoje demonstra que o consumidor aguarda o IAM na subida.
Em etapa posterior, definir supervisão, tentativa limitada com retaguarda,
prontidão de dependência e ensaio de subida em todas as ordens, queda e
recuperação do IAM, sem transformar espera em autorização permissiva nem
introduzir retry automático de mutações.

Os números de testes acima são evidência **histórica** dos documentos dos
pilotos; não são resultado de uma execução feita por este plano. Antes de
usar qualquer evidência como gate, repetir a suíte relevante no checkout e
topologia da entrega correspondente.

## Primeiro incremento: E0 → E1

1. Publicar este registro e apontar o plano e o inventário antigos para a
   linha de base atual, preservando os detalhes históricos.
2. Catalogar dependências de produção e escritas por app. Distinguir
   dependência aceita de IAM/`core`/`common`, compartilhamento legado e import
   de regra de negócio entre domínios. O catálogo será a entrada para a regra
   automatizada, não uma proibição inferida de nomes de arquivo.
3. Em seguida, pactuar exceções e implementar teste estático no CI, sem
   reestruturar módulos nem alterar comportamento. Encerrar E1 apenas após
   checar os casos de Carga, Publicações, Ações PNGI e Portal público.

### Inventário inicial de imports de produção (E1 em andamento)

Leitura estática de arquivos Python das quatro apps, excluindo testes e
migrações, em 26/11. Isto **não** cobre acesso dinâmico por `apps.get_model`,
configuração Django, consultas SQL, relacionamentos de modelo nem escrita
cruzada; essas verificações são o próximo item de E1.

| Consumidor | Dependência entre apps identificada | Tratamento a avaliar |
| --- | --- | --- |
| Carga | `consumers.py` usa `core.services.autorizacao_iam_local`; `permissoes_iam.py` herda `core.permissions.CanPermission`. | Confirmar que o piloto remoto não depende da política local ao ativar; manter modo legado até corte. |
| Publicações | `permissoes_iam.py` importa `accounts.services.authorization_service` e `core.permissions`. | Substituir a dependência local de autorização pelo contrato remoto no corte, preservando o modo legado até lá. |
| Ações PNGI | `views.py` importa `core.permissions.CanPermission`. | Definir seu perfil e contrato IAM; não assumir que o guard atual já é remoto. |
| Portal autenticado | `views.py` e `serializers.py` consultam modelos de `accounts`. | É parte da fronteira IAM/Portal, não da API pública de Publicações. |
| `common` | `common/permissions.py` reexporta `core.permissions` por compatibilidade. | Inversão conhecida: não transportar o reexport para uma biblioteca independente sem contrato. |

Não foram encontrados imports Python diretos de produção entre os três
domínios Carga, Publicações e Ações PNGI nessa varredura. A constatação é
limitada a imports literais e não valida propriedade de tabelas ou efeitos.

A introspecção dos modelos carregados encontrou 25 modelos de Carga no schema
`carga_org_lot`, 27 de Publicações em `publicacoes` e 10 de Ações PNGI em
`acoes_pngi`, sem relação ORM **ativa** entre essas apps. Isso não valida o
catálogo do banco nem migrações antigas: migrações iniciais de Carga e Ações
referenciam `AUTH_USER_MODEL`, e a antiga FK de preferência E-Flow em
Publicações só foi removida pela migração 0015. Não executar migração isolada
ou clonar banco com base apenas no estado atual dos modelos.

**Gestão futura:** o Portal deverá abrigar inicialmente as páginas de
administração de usuários, perfis, capabilities e demais recursos IAM.
O gestor do Portal terá escopo global; posteriormente, gestores das
aplicações poderão usar páginas equivalentes, limitadas aos recursos da
própria aplicação. Essas páginas deverão consumir contratos do serviço IAM,
com autorização e escopo por objeto validados no backend. As APIs atuais
oferecem apenas parte dessas operações; a gestão delegada completa ainda
não está implementada.

O eventual compartilhamento de patriarcas confirmados entre Publicações e
Carga permanece aberto para discussão posterior. Não é requisito deste
incremento de isolamento; o IAM autoriza ações, mas não é proprietário do
cadastro de patriarcas.

Na retomada de 26/11, as quatro verificações de fronteira E1 passaram por
execução direta sem banco e pelo `pytest -q --no-cov --tb=line` no banco
permanente `test_gpp_plataform` (4 aprovados); `manage.py check` passou.
A primeira tentativa no executor restrito não alcançou as asserções por
falta de conexão ao PostgreSQL; a repetição com acesso resolveu a limitação.
A inspeção de rotas confirmou os perfis piloto separados, mas Ações PNGI
ainda está no perfil IAM. A próxima frente funcional é E2 (prontidão e
dependências), sem antecipar o cutover ou a discussão de patriarcas.

**Leituras e exceções atuais:** Publicações ainda importa
`AuthorizationService` de `accounts` no caminho local legado; Carga,
Publicações e Ações usam `core.permissions` no modo atual. O Portal
autenticado consulta `Aplicacao` e `UserRole` por estar composto no serviço
IAM/Portal; se virar processo próprio, precisará de DTO IAM em vez de ORM.
`common/permissions.py` reexporta `core.permissions` por compatibilidade.
Esses caminhos não são autorização para criar novos imports. Os pilotos IAM
remotos são opt-in e não eliminam imediatamente o modo monolítico.

O primeiro controle automatizado está em
`apps/core/tests/test_fronteiras_dominio.py`: proíbe imports literais entre
apps de negócio, relações ORM ativas entre elas, imports de domínios em
`core`/`common` e novos imports diretos do IAM nas apps de negócio. Duas
exceções legadas de Publicações são congeladas por caminho exato, não
aprovadas como destino. Ainda é necessário revisar acessos dinâmicos, SQL,
URLs, jobs/Beat e catálogo físico do banco antes de remover as exceções;
o modo legado precisa de alternativa pronta.

## Gates transversais e parada segura

- Qualquer mudança de contrato exige teste consumidor/provedor e da API
  pública, inclusive no caso de IAM indisponível.
- Mutações precisam provar decisão autorizada, escopo e auditoria; `401`,
  `403` e `503` não podem deixar gravação parcial.
- Mensagens em voo não podem ser perdidas nem executadas por worker de outra
  app; reiniciar um worker não pode duplicar efeitos externos já aceitos.
- Não ativar dois escritores ou dois Beats; não migrar schema pela app de
  domínio. Artefato e configuração anteriores devem permanecer recuperáveis.
- Parar antes do cutover se faltar evidência de compatibilidade, restauração,
  proteção do canal ou observabilidade, ou se houver divergência no worktree
  que não pertença à entrega.

**Relação com as fases antigas:** E0/E1 refinam I0/I3; E2 corresponde a
I2/I3; E3/E4 ensaiam I4/I5 sem ativação; E5 prepara os gates I3–I5; E6
retoma I1 e a ativação I4/I5 somente depois das demais evidências. Os gates
antigos continuam válidos; a ordem foi ajustada à decisão de deixar banco
por último.
