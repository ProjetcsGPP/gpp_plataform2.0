# Contrato IAM interno v1 — piloto de Carga Org/Lot

**Decisão funcional:** o responsável aprovou em 2026-11-19 iniciar pela
consulta remota ao IAM, mantendo a sessão atual e uma autoridade única de
identidade e permissões. O contrato é inspirado na introspecção, **não** é
implementação da RFC 7662: `AccountsSession` não é token OAuth.

**Estado técnico:** o lado IAM da decisão por ação e o cliente M2M foram
implementados. O guard HTTP de Carga possui um piloto remoto reversível, mas
`GPP_CARGA_IAM_DECISAO_REMOTA_ATIVA` e o endpoint IAM estão **desligados por
padrão**. O WebSocket possui um piloto remoto próprio, também desligado por
padrão, que revalida antes de enviar cada evento e enquanto ocioso. A
implantação separada de Carga **não** está implementada. Um terceiro piloto,
`GPP_CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA`, também desligado por padrão,
dispensa as consultas locais de sessão, aplicação e roles apenas nas rotas
HTTP de Carga e cria o ator auditável após a decisão IAM. No piloto WebSocket remoto, o
middleware não lê sessão/roles locais de Carga: o IAM valida a sessão e fornece
a identidade. Isso ainda não comprova isolamento do processo da aplicação.
O contrato só pode ser
ativado depois dos gates operacionais abaixo. A rota interna não substitui a
API de login, a autorização por objeto nem `/api/health/`.

## Chamada entre serviços

`POST /interno/iam/v1/decisoes/`, `Content-Type: application/json`.
O serviço chamador usa `Authorization: Bearer <credencial-M2M-exclusiva>` e
opcionalmente `X-Correlation-ID`. A credencial **nunca** pertence ao navegador
e identifica somente `CARGA_ORG_LOT`; o chamador não escolhe outra aplicação.
O corpo máximo é 4 KiB. A chave da sessão deve ser transmitida apenas no
corpo de um canal protegido, nunca em URL, log, fila ou resposta.

```json
{
  "acao": "view_importacaoplanilha",
  "credenciais_usuario": [
    {"nome_cookie": "gpp_session_CARGA_ORG_LOT", "valor": "<chave-opaca-da-sessao>"}
  ]
}
```

O IAM aceita de 1 a 8 cookies GPP sem nomes duplicados. Confirma
`AccountsSession` ativa, não revogada, não expirada, com usuário ativo e
nome/contexto do cookie correspondentes. O cookie dedicado de Carga, quando
presente, tem prioridade absoluta: se inválido, não há fallback. Sem ele, o
IAM seleciona a sessão válida **mais recente** entre os cookies enviados,
conforme o middleware atual; somente `PORTAL_ADMIN`/superusuário pode usá-la
como fallback. Mesmo assim,
a decisão final passa por `AuthorizationService` para Carga. `acao` é a
permissão técnica declarada pelo ponto de entrada. Esta versão não transporta
atributos ABAC nem decide propriedade de registros: a aplicação continua
responsável pelas restrições de objeto e de negócio.

Todos os resultados de sessão/permissão válidos usam HTTP `200`, por exemplo:

```json
{
  "versao": 1,
  "decisao_id": "<id-opaco>",
  "resultado": "AUTORIZADO",
  "usuario_id": 7,
  "usuario_nome": "Nome de Teste",
  "versao_autorizacao": 4,
  "expira_em": "2026-11-19T18:00:00-03:00"
}
```

`resultado` pode ser `AUTORIZADO`, `NEGADO` ou `SESSAO_INVALIDA`. Para
`NEGADO`, `usuario_id` identifica o ator conhecido; para `SESSAO_INVALIDA`,
não se devolvem dados do usuário. `versao_autorizacao` e `expira_em` aparecem
somente em `AUTORIZADO`. A resposta usa `Cache-Control: no-store`; o cliente
não deve adicionar cache de decisão no piloto. A decisão interna consulta as
permissões atuais no banco, sem usar o cache de permissões do
`AuthorizationService`; os fluxos locais existentes continuam com cache.
Após a alteração estar confirmada no banco, uma **nova** decisão não depende
do TTL de 300 segundos. A versão é informativa para correlação, não uma
autorização independente nem promessa de interromper uma requisição já
autorizada ou um WebSocket aberto.

`usuario_nome` é um acréscimo compatível do produtor v1, presente apenas em
`AUTORIZADO`: usa nome completo ou, se vazio, username do cadastro IAM.
Deve ser legível, sem controles e ter no máximo 200 caracteres, limite do
snapshot de auditoria de Carga. O cliente v1 aceita sua ausência para
compatibilidade com um IAM antigo durante implantação gradual, mas rejeita
um valor presente e inválido. **A ausência não autoriza o bypass da
identidade HTTP local**: o piloto de identidade HTTP remota exige esse campo
antes de criar o ator auditável. `NEGADO` e `SESSAO_INVALIDA` não expõem nome.

Erros do **canal M2M** não representam a sessão do usuário: credencial de
serviço ausente/inválida → `401`; corpo inválido → `400`/`413`/`415`; falha
interna → `503`; recurso desligado → `404`. A aplicação deve traduzir somente
`SESSAO_INVALIDA` para `401` do usuário e `NEGADO` para `403`. Timeout,
`5xx`, resposta malformada, erro M2M ou rota indisponível tornam a operação
protegida indisponível (`503 servico_iam_indisponivel`), **nunca** autorizada
e sem limpar cookie. A auditoria registra resultado, usuário quando conhecido,
`decisao_id` e correlação, sem segredo/sessão. O ID da decisão não prova acesso
por si só.

## Habilitação e limites

- `GPP_IAM_DECISOES_INTERNAS_ATIVAS` inicia em `false`. Sem essa flag ou com
  `GPP_IAM_TOKEN_SERVICO_CARGA` fora de 32–256 caracteres, a rota responde `404`.
- `GPP_CARGA_IAM_URL` configura o cliente, sem valor padrão. O cliente aceita
  apenas a rota exata `/interno/iam/v1/decisoes/` em HTTPS ou HTTP loopback,
  não segue redirects, não faz retry/cache e usa timeouts de conexão/leitura
  de 1/2 segundos. Falha de configuração ou resposta inesperada fecha acesso.
- `GPP_CARGA_IAM_DECISAO_REMOTA_ATIVA` inicia em `false`. Quando ligada, as
  views HTTP de Carga com `CanPermissionCarga` consultam o IAM após a
  autenticação local e exigem que `usuario_id` retornado coincida com o
  usuário local. Sessão inválida → `401`; permissão negada → `403`; falha de
  transporte/contrato ou identidade divergente → `503`. Contexto ABAC ainda
  não transportado bloqueia a operação no piloto, em vez de ignorar a regra.
  WebSocket e tarefas Celery não usam esta flag. O middleware WebSocket local
  já foi alinhado ao HTTP para rejeitar cookie dedicado inválido sem fallback
  e exigir usuário ativo/contexto correspondente; isto **não** é autenticação
  remota do WebSocket.
- `GPP_CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA` inicia em `false` e é
  independente das flags anteriores. Quando ligada, substitui a identidade
  HTTP local somente em `/api/carga-org-lot/`: os middlewares não consultam
  `AccountsSession`, `Aplicacao` ou `UserRole` para esse prefixo; a view deve
  declarar `CanPermissionCarga` e o IAM deve devolver `usuario_id` e
  `usuario_nome` válidos. O guard aplica CSRF em operações inseguras e só
  depois cria o principal auditável. `401` distingue sessão inválida; `403`,
  permissão negada ou CSRF; `503`, indisponibilidade/contrato insuficiente.
  Uma view nova sem guard é bloqueada antes da execução. Não cria sessão local
  nem transporta cookie de usuário para Celery. O modo padrão e todas as
  outras aplicações, inclusive a API pública sem cookie, ficam inalterados.
- `GPP_CARGA_IAM_WEBSOCKET_REMOTO_ATIVO` também inicia em `false` e é
  independente da flag HTTP. Quando ligada, o consumer de Carga consulta o
  IAM ao conectar, antes de cada evento recebido do channel layer e
  periodicamente enquanto a conexão está ociosa. O intervalo é controlado
  por `GPP_CARGA_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS`, padrão de 300 segundos,
  limitado entre 30 e 300 segundos na configuração operacional. Sessão
  inválida fecha com `4401`, permissão negada com `4403`, indisponibilidade ou
  identidade divergente com `1013`; nenhum payload é enviado nessa falha.
  O monitor é cancelado ao desconectar. Uma revogação ocorrida após a última
  decisão pode permanecer não percebida por até um intervalo, mas nenhum
  evento é entregue sem nova decisão. Para rotas de Carga, o middleware
  WebSocket deixa de consultar `AccountsSession`/roles locais quando essa flag
  está ativa, marcando o escopo como anônimo; o consumer aceita apenas a
  identidade positiva validada pelo IAM. Caso algum middleware já forneça um
  usuário autenticado, identidade divergente continua sendo falha fechada.
  Publicações e o modo padrão de Carga mantêm a resolução local. Essa mudança
  isolada não torna o processo de Carga independente do IAM local.
- `GPP_CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS` inicia em `false` e é independente
  das flags HTTP e WebSocket. Quando ligada no worker de Carga, consulta
  `POST /interno/iam/v1/decisoes-atividade/` com M2M, `usuario_id` lido do
  envio persistido e ação `change_importacaoplanilha`, sem cookie de usuário.
  O IAM verifica usuário ativo e permissão atual sem cache. A negativa encerra
  a atividade local, registra evento e interrompe novas chamadas; uma resposta
  da PRODEST que chegue durante o envio é persistida antes desse encerramento.
  Indisponibilidade do IAM não é classificada como revogação e impede iniciar
  nova chamada externa. Ver
  [inventário Celery](./BACKEND_CARGA_CELERY_INVENTORY.md).
- A credencial deve ser gerada fora do Git, entregue somente aos processos IAM
  e Carga e protegida pelo mecanismo de segredos aprovado. Não reutilizar
  `SECRET_KEY`, credenciais E-Docs ou cookies do navegador como chave M2M.
- O proxy não deve publicar `/interno/` à internet. Exigir loopback ou canal
  autenticado e cifrado (TLS com autenticação de serviço) quando houver hosts
  separados. A credencial estática é provisória para o piloto; sua rotação e
  autenticação mais forte exigem procedimento operacional.
- Não habilitar os pilotos para uso real antes de ensaiar indisponibilidade
  entre processos, proxy, canal protegido e rollback. Os guards HTTP e
  WebSocket só chamam o cliente IAM atrás de suas flags. A implementação do
  piloto HTTP integral não substitui o ensaio de implantação independente.
  Não há corte de rota nem migração de dados.
- O `POST` é exclusivo para serviços. Não entra no OpenAPI público e não deve
  ser chamado pelo frontend. Chamadas da API pública de Publicações não passam
  por este IAM.

## Evidência automatizada e limite

Em 2026-11-19, 96 testes dirigidos passaram sem rede nem banco reais. Eles
cobrem contrato consumidor–provedor com o endpoint Django, entrada M2M
inválida, limites de payload, cookies concorrentes, respostas malformadas,
timeout, `401`/`403`/`503` da view HTTP, não execução do domínio em falha,
guard em todas as views HTTP de Carga e seleção local de sessão WebSocket.
A cobertura conjunta dos cinco módulos do contrato/guards medidos foi 97%; o
cliente M2M isolado chegou a 100%. Esses números **não** substituem teste de
integração com `AccountsSession`, roles, cache, revogação e PostgreSQL reais.
As flags permanecem desligadas; não houve ensaio operacional de queda do IAM.

Foi adicionada uma suíte de 15 cenários em
`apps/accounts/tests/test_decisao_interna_banco.py`, usando somente o banco de
testes transacional do Django e fixtures sintéticas: autorização de Carga,
negação sem role, fallback administrativo, precedência do cookie dedicado,
expiração, revogação, usuário inativo, sessão mais recente e retirada de role
entre decisões. Quatro cenários adicionais exercitam guard HTTP de Carga,
cliente IAM, endpoint interno e consulta real ao banco de testes em conjunto:
autorização, retirada da role, sessão revogada e identidade divergente. O
transporte HTTP é simulado no próprio processo; isto **não** comprova rede,
proxy ou implantação separada. O cenário adicional deixa no cache uma
permissão obsoleta após alterar a relação materializada no banco sem sinal de
invalidação; a decisão interna usa o estado do banco e nega o acesso.

Em 2026-11-19, os 15 testes passaram no banco permanente
`test_gpp_plataform` com `--no-cov`. O piloto WebSocket possui agora 14
testes, incluindo rota ASGI, channel layer em memória, revogação ociosa,
falha do IAM, continuidade da conexão autorizada, cancelamento do monitor e
decisão sem usuário local. O middleware possui testes adicionais que asseguram
o isolamento da exceção a Carga e a preservação do modo padrão.
A regressão ampliada anterior de IAM, autorização, permissões, HTTP e
WebSocket somou 225 testes aprovados antes desses novos cenários. O
PostgreSQL principal
`gpp_plataform` respondeu à consulta de
leitura; uma aparente falha anterior do `pg_isready` foi causada pela
restrição de sockets do executor, não pelo banco. Uma execução parcial sem
`--no-cov` atinge o gate global de 80% e retorna falha de cobertura mesmo com
todos os testes aprovados. Nenhuma migração foi aplicada no banco principal.
Não ativar as flags com base apenas nesses testes: falta ensaio operacional
com proxy, canal protegido e serviços implantados separadamente.

Dois testes adicionais usam processos e conexões PostgreSQL distintos no
banco de testes: revogação de role e de permissão materializada. O processo
IAM continua autorizando enquanto a alteração está sem commit e nega na
primeira decisão após o commit. Isso confirma a visibilidade transacional
entre processos no ensaio local, mas não mede requisições já iniciadas nem
valida rede, proxy ou uma implantação independente.

Um ensaio HTTP adicional sobe o endpoint IAM em outro processo local, com
porta de loopback efêmera e conexão própria ao banco de testes. O guard de
Carga faz a chamada `requests` real e confirma autorização, ausência e
erro de credencial M2M, identidade divergente, sessão ausente, queda do
servidor (negação sem fallback) e reversão explícita da flag para o guard
local. O processo servidor ainda carrega o monólito Django para servir apenas
o endpoint de teste; isso comprova o transporte HTTP local e o mapeamento
de falhas, **não** a topologia final, TLS, proxy ou deploy independente.

O produtor IAM passou a incluir `usuario_nome` apenas em `AUTORIZADO`, para
preparar o snapshot de auditoria sem consultar `auth_user` no processo de
Carga. O cliente valida o campo quando presente, mas aceita sua ausência na
v1 para não interromper a implantação gradual. Em 2026-11-19, a regressão
dirigida de 118 testes de IAM, cliente, guard HTTP e WebSocket passou, assim
como `manage.py check` e Pylint dos módulos alterados (10,00/10). O bypass
HTTP local **não** foi habilitado nem implementado por essa adição.

## Próximos gates

### Fronteira HTTP implementada como piloto, não como cutover

O modo HTTP integral está atrás de uma flag nova. `config/iam_boundary.py`
restringe o bypass ao prefixo de Carga; a cadeia de middlewares deixa de
consultar os modelos IAM locais; `AuthorizationMiddleware.process_view`
recusa views sem `CanPermissionCarga`; a permissão obtém uma decisão IAM por
ação, exige `usuario_nome`, aplica CSRF e cria `IdentidadeIAM`. As views
continuam usando `request.user.pk`, `get_full_name()` e `username`; a
auditoria persiste ID/nome lógicos, sem FK ativa para `auth_user`. A
autorização por objeto continua responsabilidade da aplicação.

O ensaio no pipeline Django comprovou ausência de consultas locais de
sessão/roles/aplicação na entrada de Carga, identidade e nome auditáveis,
negação sem execução do domínio, CSRF de escrita, proteção de rota sem guard
e isolamento do prefixo. O ensaio com sessão/role reais consultou o banco
apenas no lado IAM. A API pública de Publicações continuou disponível sem
decisão IAM, mesmo com cookie de Carga presente. Esses testes **não** validam
proxy, TLS, processo/worker separado, autorização por objeto em todos os
recursos nem política de tarefas Celery. A flag permanece desligada.

Em 2026-11-19, a suíte completa do repositório passou com **1.406 testes
aprovados e 1 ignorado** (`--no-cov`). `manage.py check --database default`,
`migrate --check`, `makemigrations --check --dry-run` e Pylint dos arquivos
alterados (10,00/10) também passaram. A geração/validação OpenAPI teve zero
erros e nove avisos de nomes de enumeração. O Flake8 não estava instalado na
venv desta execução; não foi validado localmente. Nenhuma migração foi
aplicada, flag ativada ou rota cortada.

1. O ensaio local de concorrência entre processos para revogação de role e
   permissão foi executado no banco de testes. Repetir com processos IAM e
   Carga efetivamente separados antes do corte; uma decisão nova consulta o
   estado confirmado, mas não cancela ação já iniciada.
2. O ensaio HTTP local entre processos cobre reversão da flag, credenciais,
   identidade divergente e queda do IAM. Repetir sob o proxy e transporte
   protegido da topologia final antes de habilitar o piloto operacionalmente.
3. A revalidação periódica e a retirada da consulta local de sessão/roles do
   WebSocket de Carga foram implementadas atrás da flag e testadas localmente.
   O bypass HTTP coordenado também está implementado atrás de outra flag;
   falta ensaiar tempo, carga e reconexão com IAM/proxy reais.
4. O piloto de política para tarefas Celery já aceitas está implementado,
   desligado por padrão. Completar os cenários e limites do
   [inventário de Carga](./BACKEND_CARGA_CELERY_INVENTORY.md), inclusive
   concorrência, revogação durante chamada e cancelamento entre processos;
   não transportar chave de sessão na fila.
5. Validar segredo, canal, proxy, logs, observabilidade, disponibilidade,
   rollback e testes de contrato consumidor/provedor antes de qualquer cutover.
