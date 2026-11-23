# I0 — Inventário e contrato proposto de comunicação entre serviços

**Estado em 2026-11-19:** inventário estático do checkout da branch
`feat/backend-isolamento-aplicacoes`. Não é comprovação de topologia operacional.
Nenhum processo operacional, banco principal ou fila foi alterado. A suíte de
integração usa o banco Django separado `test_gpp_plataform`. Uma primeira
alteração reversível concentrou a decisão de permissão
usada por HTTP e pelo WebSocket de Carga em
`apps/core/services/autorizacao_iam_local.py`, ainda delegando ao mesmo
`AuthorizationService`; isso **não** implementa autorização remota, prova de
identidade entre serviços nem resposta `503` para queda do IAM. O contrato de
regressão local está em `apps/core/test_iam_boundary.py`. O `/api/health/`
existente passou a ignorar sessão e cadastro de aplicações e a enviar
`Cache-Control: no-store`, sem mudar o corpo da resposta; continua sendo
**somente vivacidade**, não prontidão. Este documento complementa o
[plano de isolamento](./BACKEND_APPLICATION_ISOLATION_PLAN.md).

**Atualização em 2026-11-23:** a FK ativa entre
`publicacoes.preferencia_exibicao_eflow` e `public.auth_user` foi confirmada
por consulta ao catálogo do PostgreSQL. O modelo foi convertido para
`usuario_id` lógico, preservando coluna e unicidade, e a migração `0015`
remove somente a restrição física. Passou no banco de testes e foi aplicada
de forma direcionada ao `gpp_plataform`, após confirmar que era a única
migração pendente. A consulta posterior mostrou zero FKs entre schemas de
domínio e `public`, uma preferência preservada e unicidade mantida. A API
mantém `usuario_id` no DTO e a
auditoria individual continua vinculada à preferência. O piloto de revogação
de tarefas de Carga também já existe atrás de flag desligada, substituindo as
referências abaixo que o descrevem como pendente. Foram preparados perfis
locais opt-in e proxy alternativo, detalhados em
[BACKEND_CARGA_ISOLAMENTO_PILOTO.md](./BACKEND_CARGA_ISOLAMENTO_PILOTO.md),
sem alteração do launcher ou do proxy padrão.

**Topologia local confirmada em 2026-11-23:** o Nginx em execução monta o
`nginx.conf` padrão, encaminha todo `/api/` a `host.docker.internal:8000` e
`/` a `host.docker.internal:3000`, sem rota `/ws/` própria. Há backend em
`127.0.0.1:8000`, mas não em `8001`; a porta 3000 está ocupada por um
contêiner `open-webui`, não pelo frontend GPP. Há processos Celery, sem
confirmação de Beat/filas por inspeção somente de nomes. O proxy alternativo
e os perfis separados não foram ativados. Detalhes e limites constam no
[contrato do piloto](./BACKEND_CARGA_ISOLAMENTO_PILOTO.md).
Na rechecagem posterior, o backend em 8000 e os processos Celery já não
apareciam; o estado operacional pode mudar e deve ser reconfirmado antes do
cutover.

**Ensaio direto posterior:** os dois ASGI piloto responderam `200` em portas
temporárias, e a plataforma permaneceu acessível depois de parar somente
Carga. O Debug Toolbar de DEV causou inicialmente `500` na vivacidade de
Carga e foi removido desse perfil. A ausência de uma URL não pode ser
inferida de `401` anônimo, porque o middleware autentica antes do resolvedor;
os testes de exclusão usam o resolvedor. Nesse primeiro ensaio não houve
tráfego pelo proxy alternativo, teste de WebSocket ou cutover de filas.
Um ensaio WebSocket direto posterior encontrou `500` em caminhos cruzados;
um fallback limitado aos ASGI piloto passou a recusá-los sem erro interno.
Handshakes anônimos para rotas próprias e cruzadas retornaram `403` e o
processo de Publicações permaneceu acessível após parar Carga. Ainda falta
validar sessão autorizada e revogação pelo proxy.

Em 2026-11-19, após aprovação do responsável, começou a implementação do
[contrato IAM interno v1](./BACKEND_IAM_DECISION_CONTRACT_V1.md) pelo lado do
IAM. A rota está **desativada por padrão**. O cliente M2M em
`apps/carga_org_lot/services/cliente_iam.py` está conectado somente ao guard
HTTP de Carga, por flag também desligada por padrão. Os middlewares HTTP
locais de sessão/roles continuam no modo padrão. Um segundo piloto HTTP,
`GPP_CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA`, permite dispensar suas consultas
para o prefixo de Carga e criar o ator a partir da decisão IAM, mas está
desligado por padrão. A autorização por objeto não mudou; não houve
cutover de Carga. O middleware WebSocket local preserva no modo padrão a
equivalência com HTTP: cookie dedicado inválido não cai em fallback; sessão
candidata exige usuário ativo e contexto correspondente. O piloto WebSocket
separado, também desligado por padrão, consulta o IAM na conexão, antes de
cada evento e periodicamente enquanto ocioso. Nesse modo, a rota de Carga
não lê sessão/roles do banco IAM local, mas Publicações e o modo padrão de
Carga continuam usando a resolução local.

### Verificação do executor e do PostgreSQL (2026-11-19)

O executor restrito desta sessão impede a criação de sockets: um teste mínimo
com `socket.socket()` retorna `PermissionError: [Errno 1] Operation not
permitted` antes de tentar a conexão TCP. Nesse modo, `pg_isready` reporta
`no response`, o acesso a netlink falha e a chamada a `powershell.exe` falha
com `UtilBindVsockAnyPort: socket failed 1`. Esses sintomas **não** demonstram
indisponibilidade do PostgreSQL nem erro em `DB_HOST`.
O teste do piloto WebSocket com `sync_to_async` também ficou pendente nesse
modo; a mesma chamada concluiu imediatamente fora da restrição. Por isso os
testes assíncronos do piloto foram executados fora do executor restrito.

Repetidos fora da restrição do executor, o mesmo teste TCP conectou a
`172.22.176.1:5432`, `pg_isready` respondeu `accepting connections` e o
PowerShell funcionou. Uma consulta Django somente de leitura confirmou
`current_database() = gpp_plataform`, usuário `postgres` e a existência do
banco de testes `test_gpp_plataform`. `manage.py check --database default` e
`manage.py migrate --check` passaram; nenhuma migração foi aplicada no banco
principal. Após ampliar a integração HTTP, o piloto WebSocket e a proteção
contra permissão obsoleta em cache, 225 testes de IAM/autorização/permissões
passaram, incluindo 15 testes com banco, usando o banco de testes e `--no-cov`.
Uma execução isolada dos dez testes iniciais também passou, mas
retornou código de falha por causa do gate
global de cobertura de 80% aplicado a uma seleção parcial (33,48%), não por
falha funcional.

**Procedimento para novas validações:** executar comandos que necessitem de
rede ou banco fora da restrição do executor, sempre com alvo explícito;
confirmar previamente o banco de testes antes de rodar testes que escrevem.
Não alterar `DB_HOST`, firewall ou PostgreSQL com base apenas no `no response`
do executor restrito. O isolamento do executor é uma limitação da ferramenta
de execução, não um defeito a corrigir no código do projeto.

## 1. Fatos confirmados no código

| Fronteira | Implementação atual | Consequência para o piloto de Carga |
|---|---|---|
| Composição HTTP | `config/settings/base.py` registra todas as apps; `config/urls.py` monta IAM, Portal, Ações, Carga, Publicações e API pública no mesmo Django. | Reiniciar o processo HTTP reinicia todas as apps. É necessário um perfil de execução e um destino de proxy por serviço, preservando os caminhos existentes. |
| WebSocket | `config/asgi.py` monta Carga e Publicações; `apps/core/middleware/websocket.py` consulta `AccountsSession` e `UserRole` diretamente no modo padrão, mas ignora essa consulta para rotas de Carga quando o piloto IAM remoto está ligado. | A fronteira WebSocket de Carga pode usar a decisão remota sem leitura de sessão/roles locais; o modo padrão e Publicações continuam intactos. Isso não separa o processo; o HTTP tem piloto próprio. |
| Autenticação HTTP | No modo padrão, `apps/accounts/middleware.py` resolve `AccountsSession` e os middlewares de `core` consultam cadastro/roles. No piloto `GPP_CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA`, somente o prefixo de Carga ignora essas consultas e usa a decisão IAM para identidade e permissão. | A fronteira HTTP foi implementada e testada localmente, mas falta ensaio com proxy/processo próprio e domínio em banco separado. Não ativar a flag como cutover. |
| Permissões DRF e WebSocket | `apps/carga_org_lot/views/{base,dashboard}.py` usam `CanPermissionCarga`; no modo padrão delegam à decisão local. Há pilotos separados para guard HTTP com identidade local, HTTP com identidade remota e WebSocket remoto com revalidação. | O modo HTTP integral exige nome auditável e CSRF, bloqueia view sem guard e falha fechado. WebSocket e HTTP têm flags próprias; tarefas e autorização por objeto ainda requerem validação operacional. Flags desligadas não alteram comportamento. |
| Dados | `config/settings/base.py` define um `DATABASES['default']`; `config/routers.py` envia todas as apps ao mesmo banco. Modelos de Carga usam schema próprio e auditoria com IDs lógicos de usuário (`common/models.py`). | A única FK ativa entre schemas de domínio e `public` foi removida pela migração `0015`, já aplicada ao banco principal. O perfil piloto de Carga bloqueia `migrate` antes de executá-lo; no ensaio, o perfil de plataforma é o migrador designado em janela controlada. O perfil padrão mantém seu comportamento anterior. Migrações históricas ainda criam relações intermediárias, posteriormente removidas; isso precisa ser tratado antes de migrar cada domínio isoladamente. |
| Tarefas | `config/celery.py` autodetecta tarefas; `CELERY_BEAT_SCHEDULE` agenda Carga e E-Docs no mesmo Beat; `apps/carga_org_lot/tasks.py` e `apps/pub_institucional/tasks.py` registram tarefas distintas. O piloto de revogação de Carga existe sob `GPP_CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS`, desligada por padrão. | Os perfis locais opt-in roteiam Carga para fila exclusiva, registram somente as tarefas da respectiva app e mantêm um único Beat. A revalidação/cancelamento local auditável já foi implementada; faltam ensaio operacional, autorização por objeto, decisão sobre revogação de sessão e política para mensagens pendentes no deploy. |
| Cache/canais | `config/settings/base.py` usa Memcached e Channels/Redis compartilhados por configuração. | Compartilhar servidor é possível; namespaces, credenciais, limites e canais devem impedir consumo ou invalidação cruzada. |
| Saúde | `common/urls.py` expõe `/api/health/` com `ok` fixo, agora sem consulta ao cadastro de aplicações ou à sessão. | O retorno é apenas vivacidade do processo; não comprova banco, broker, IAM, cofre nem prontidão para executar operações. O endpoint de prontidão segue pendente. |
| Inicialização local | `scripts/localhost_dev.sh` inicia um worker, um Beat e o Django e encerra os três quando um termina. O Nginx local em execução usa a configuração padrão; não há listener em 8001. | O script de desenvolvimento não atende o ensaio de parar somente Carga. A topologia da sandbox foi inspecionada; a institucional continua desconhecida. |

Não foram encontrados imports de produção diretos entre os domínios Carga,
Publicações e Ações PNGI. O acoplamento principal passa por IAM/`core`,
configuração e infraestrutura. Há também uma inversão a revisar:
`common/permissions.py` reexporta `apps/core/permissions.py`, enquanto partes
de `core` importam `accounts`. Essa cadeia não deve ser transportada
automaticamente para um pacote compartilhado de serviços independentes.

## 2. Desenho proposto de saúde e autorização

**Saúde não é autorização.** Um `ping` bem-sucedido mostra apenas que o
destino respondeu naquele instante. Não prova sessão ativa, permissão,
contexto da aplicação nem disponibilidade no instante seguinte. A proteção
deve ser aplicada uma vez na **entrada de cada operação protegida**, de modo
centralizado em adaptador/middleware, e não como chamada repetida dentro de
cada método de domínio.

| Contrato/estado | Consumidor | Semântica |
|---|---|---|
| `GET /interno/saude/v1/vivo` | supervisor local | Processo responde; sem chamada a IAM, banco ou serviços externos. Falha indica processo travado, não uma dependência indisponível. |
| `GET /interno/saude/v1/pronto` | proxy/orquestrador | Serviço consegue atender sua rota essencial; verifica dependências locais críticas com timeout curto. Não reiniciar o processo por falha temporária do IAM. |
| `GET /interno/saude/v1/dependencias` | observabilidade interna autenticada | Estado resumido de IAM, banco, broker e integração necessária. Nunca expõe URL interna sensível, credenciais, IDs de sessão ou resposta bruta de terceiros. |
| `POST /interno/iam/v1/decisoes/`, piloto v1 desativado | futuro cliente HTTP de Carga | Valida sessão e permissão por ação, com identidade de serviço própria; não decide objeto, ABAC, WebSocket prolongado ou Celery. `ping` não substitui esta operação. |

A consulta interna ao IAM foi escolhida para o piloto de Carga; uma asserção
assinada fica como alternativa futura se houver necessidade medida. O endpoint
v1 já exige credencial M2M, mas está desativado. Não reutilizar cookies entre
processos por simples cópia de banco, não confiar em headers de identidade
aceitos diretamente da internet nem ativar a rota sem canal/proxy protegidos.
Regras de revogação, expiração, cache e falha precisam dos ensaios do contrato
antes do cutover.

### Pontos de aplicação

1. **HTTP protegido:** guard único antes da view, seguido da autorização
   específica da ação/objeto. Uma decisão explícita negativa gera negação;
   timeout/erro de IAM gera indisponibilidade controlada, nunca permissão.
2. **WebSocket:** validar na conexão e definir revalidação/encerramento após
   expiração ou revogação; uma autorização única no `connect` não basta para
   conexões longas sem política de validade.
3. **Celery:** o piloto de Carga já registra o ator e eventos do envio,
   revalida a atividade antes de novas operações externas e encerra localmente
   após revogação, preservando a resposta da PRODEST mesmo se chegar durante
   a revogação. Não afirma cancelamento remoto nem retoma o acompanhamento
   depois do encerramento. A flag permanece desligada; autorização por objeto,
   revogação de sessão, correlação ponta a ponta e ensaio entre processos
   seguem pendentes. Falha de IAM não é tratada como revogação ou permissão.
4. **Comandos administrativos:** identidade de serviço/operador e escopo
   explícitos; não usar a ausência de request HTTP como dispensa de auditoria.
5. **`common` e `core`:** funções locais compartilhadas não exigem rede nem
   `ping`. Somente uma capacidade realmente remota usa cliente com timeout,
   autenticação e tratamento de falha próprios. A implementação interna do
   IAM/Portal não deve virar dependência importada por todos os serviços.
6. **Portal público e API pública de Publicações:** a página frontend `/portal`
   consome `/api/public/v1/publicacoes-institucionais/`, que hoje usa
   `authentication_classes=[]` e `AllowAny`. A resposta pública não depende
   de cookie nem de decisão IAM e não varia por cookie. Queda do IAM não deve
   transformá-la em endpoint autenticado, bloquear essa leitura por si só ou
   liberar a API administrativa. Em contraste, `/api/portal/` e o acesso às
   aplicações exigem sessão autenticada.

### Estados e testes mínimos propostos

| Situação | Comportamento esperado |
|---|---|
| IAM saudável, autorização positiva | Ação prossegue com escopo confirmado e auditoria de correlação. |
| IAM saudável, sessão revogada ou permissão negada | Ação não executa; retorno de autenticação/autorização conforme contrato. |
| IAM indisponível/timeout | Ação protegida não executa; indisponibilidade explícita e auditada, com retry apenas onde a operação é segura/idempotente. |
| Carga indisponível ou em atualização | Somente rotas e worker de Carga são afetados; IAM, Portal, Ações e Publicações continuam operacionais. |
| `common` local disponível, IAM indisponível | Função local continua utilizável; não há chamada de saúde artificial. |
| Processo vivo, dependência crítica indisponível | Vivacidade permanece distinta de prontidão/degradação; não criar ciclo de reinícios por falha externa. |

## 3. Contrato de erro para o frontend (proposto)

O guard de cada serviço deve converter falha de comunicação com IAM em uma
resposta estável, **antes** de chamar a regra de negócio ou enfileirar uma
tarefa. Não devolver `401` ou `403` quando não foi possível obter decisão:
esses códigos ficam reservados, respectivamente, a identidade inválida/ausente
e a autorização efetivamente negada. Não apagar cookie nem solicitar novo
login por um timeout do IAM.

| Caso | HTTP proposto | Efeito esperado no frontend |
|---|---|---|
| Sessão ausente, expirada ou revogada, confirmada pelo IAM | `401`, código estável de sessão | Solicitar autenticação conforme o fluxo existente. |
| Identidade válida, permissão negada pelo IAM | `403`, código estável de permissão | Exibir acesso negado sem tentar repetir automaticamente. |
| IAM indisponível, timeout ou resposta inválida | `503`, `servico_iam_indisponivel` | Manter a tela e o estado local, informar indisponibilidade temporária e oferecer nova tentativa; não presumir logout nem permissão. |
| Serviço de domínio em manutenção/indisponível | `503`, código distinto `servico_aplicacao_indisponivel` | Mostrar indisponibilidade apenas da app afetada. |
| Erro da fonte externa após autorização válida | Código próprio da integração | Não rotular como falha IAM; registrar e expor estado da operação conforme contrato da app. |

Para APIs administrativas que já usam o envelope de
`common.exceptions.gpp_exception_handler`, a forma candidata é:

```json
{
  "success": false,
  "status_code": 503,
  "errors": {
    "code": "servico_iam_indisponivel",
    "detail": "Não foi possível validar o acesso agora. Tente novamente mais tarde.",
    "correlation_id": "identificador-opaco"
  }
}
```

`correlation_id` identifica o incidente sem revelar sessão, token, usuário ou
endereço interno. Respostas desse tipo usam `Cache-Control: no-store` e, se
houver uma estimativa defensável, `Retry-After`; não inventar prazo. A API
pública de Publicações conserva **seu próprio contrato versionado de erro**,
sem transportar automaticamente o envelope administrativo para o Portal.
Também é necessário tratar indisponibilidade no proxy, que pode responder
antes de a requisição chegar à app; normalizar o erro na borda ou fazer o
frontend reconhecer ambos os formatos sem perder o código HTTP.

Para WebSocket, distinguir negação de acesso de falha temporária. O código
de fechamento `1013` é candidato para "tente novamente mais tarde"; a
interface não deve depender somente dele, pois uma falha de handshake pode
ser apresentada pelo navegador sem motivo detalhado. O estado canônico da
operação continua vindo da API HTTP, e a reconexão usa espera progressiva e
limite. Para tarefas já aceitas, o recurso HTTP mantém situação auditável de
espera/erro/retomada; a falha IAM não pode transformar uma solicitação em
sucesso silencioso. Não repetir automaticamente uma mutação `POST` se sua
idempotência não estiver garantida.

**Aceite do contrato frontend/backend:** testar `401`, `403`, `503` IAM,
`503` da app, timeout do proxy, reconexão WebSocket e tarefa pendente. O
frontend não redireciona ao login para `503`, não perde formulário em edição
e não mostra sucesso para operação não executada. O backend registra o
incidente com correlação, sem credenciais nos logs.

Os novos contratos de saúde e as respostas `503` para o frontend ainda são
**propostas**, não endpoints implementados. A rota interna de decisão IAM v1
existe, mas está desativada por padrão e não é de consumo do frontend. O
`/api/health/` preexistente é a única rota de saúde implementada; pode ser
usada como vivacidade na execução monolítica, não como prova de que outro
serviço ou uma ação protegida estão disponíveis.

## 4. Pendências para concluir o gate I0

- Confirmar a topologia institucional do processo/proxy, portas,
  certificados, origem dos cookies, CSRF e roteamento WebSocket. A sandbox
  local já foi inspecionada e não está pronta para ativar o proxy alternativo.
- Construir matriz de propriedade por schema/tabela: leitor, escritor,
  responsável por migração e backup; verificar consultas, transações e
  migrações históricas que atravessam `accounts`/`auth`. Planejar único escritor
  na coexistência da Carga antiga e extraída.
- Identificar artefatos de deploy, supervisor, pipeline, versões, limites de
  conexão/CPU/filas e rollback reais. A sandbox local não prova que isso já
  exista na operação institucional.
- Escolher o mecanismo de prova de identidade entre IAM e apps; definir
  versão do contrato, autorização por objeto, revogação, auditoria e política
  de cache. A decisão precisa cobrir `PORTAL_ADMIN` e contexto multi-cookie.
- Definir matriz de compatibilidade entre IAM, apps, frontend e migrações;
  prever testes de contrato consumidor/provedor e execução simultânea das
  versões antiga/nova durante a troca de rota.
- Classificar dependências críticas por serviço e operação. Não atrelar a
  vivacidade de Carga à saúde global do IAM ou de uma fonte externa.
- Definir sinais mínimos de observabilidade (correlação de proxy a Celery,
  métricas, alertas, retenção e expurgo seguro) e ensaios de falha/recuperação
  de IAM, broker, banco, proxy e fonte externa.
- Definir responsável por filas, Beat, tarefas em andamento e rollback; testar
  não consumo cruzado com Publicações. Verificar idempotência e duplicação das
  tarefas críticas antes de troca de worker.
- Auditar migrações históricas de Carga e os objetos de banco que dependem de
  `accounts` antes de propor banco por serviço.
- Finalizar a política de cópia e neutralização do banco `_hml` em trilha
  separada; não restaurar o dump nem executar `migrate` enquanto o gate da
  cópia não estiver fechado.

**Parecer I0:** inventário estático iniciado; contrato IAM, topologia
operacional e política do clone seguem abertos. Não iniciar o piloto de
extração de Carga ainda.
