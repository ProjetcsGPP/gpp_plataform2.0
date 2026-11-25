# Piloto local de execução separada da Carga Org/Lot

**Estado:** composição opt-in preparada; não ativada no launcher, proxy ou
banco em uso. Não representa cutover nem implantação institucional.

## Limites do piloto

- `config.settings.plataforma_piloto` mantém IAM, Portal, Ações e Publicações
  no processo principal, mas retira a rota HTTP e o WebSocket de Carga.
- `config.settings.carga_piloto` expõe somente a API, o WebSocket e a vivacidade
  de Carga. Os dois perfis ainda instalam todos os modelos Django porque o
  isolamento de banco não foi concluído. O perfil de Carga bloqueia qualquer
  `migrate` no sinal `pre_migrate` (inclusive migrações de outras apps); o
  processo de plataforma é o executor designado **no ensaio**, em janela controlada
  e após revisar plano, compatibilidade e backup. Nenhum processo deve
  executar `migrate` automaticamente na inicialização.
- Um único Beat permanece no perfil da plataforma. Ele publica a tarefa
  agendada de Carga na fila `carga_org_lot`; a coleta E-Docs continua na fila
  padrão `celery`. O worker de Carga deve consumir **somente** `carga_org_lot`,
  e o da plataforma **somente** `celery`. A descoberta Celery do piloto registra
  tarefas apenas da app correspondente em cada perfil; o perfil padrão mantém
  a descoberta completa. Não iniciar outro Beat.
- Cada ASGI piloto recusa inicializar se `DJANGO_SETTINGS_MODULE` apontar para
  outro perfil. Isso evita HTTP de um perfil junto ao WebSocket do outro.
- Uma rota WebSocket de fallback, restrita aos ASGI piloto, rejeita caminhos
  desconhecidos com código de fechamento `4404`. Sem ela, o `URLRouter`
  devolvia erro interno (`500`) ao receber uma rota da outra app.
- O perfil de Carga desliga o Debug Toolbar de DEV, pois a barra exigia a rota
  `__debug__/` e causava `500` até mesmo na vivacidade durante o ensaio direto.
- `nginx-isolamento.conf` preserva uma entrada TLS e encaminha os prefixos
  HTTP/WebSocket de Carga para a porta 8001, os demais `/api/` e WebSocket de
  Publicações para 8000, e o frontend para 3000. Proxy único **não** implica
  processo Django único. O proxy reescreve `/api/carga-org-lot/health/` para a
  vivacidade `/api/health/` de Carga, sem passar pela autorização do domínio;
  `/api/health/` identifica a plataforma. O
  arquivo alternativo não é montado por padrão.
- As flags de IAM remoto continuam desligadas por padrão. Antes de qualquer
  corte, o contrato M2M, autorização por objeto, CSRF, transporte protegido e
  comportamento de falha precisam de ensaio com processos distintos.

## Topologia local observada em 2026-11-23

O contêiner `gpp-publicacoes-dev-nginx-1` em execução monta **o arquivo
padrão** `infra/publicacoes-dev/config/nginx/nginx.conf` somente para leitura.
Ele publica TLS em `127.0.0.1:58443`, encaminha todo `/api/` para
`host.docker.internal:8000` e `/` para `host.docker.internal:3000`.
Não contém localização específica para `/ws/`; portanto o WebSocket seguiria
o destino do frontend nessa entrada. No host, foi observado somente um
backend em `127.0.0.1:8000`, nenhum listener em `8001`. A porta `3000` está
ocupada por um contêiner `open-webui`, não pelo frontend deste projeto.
Há processos Celery em execução, mas a inspeção de nome/PID não estabelece
qual deles é o Beat, quais filas consomem ou se pertencem a esta instalação.
Em nova inspeção na mesma data, o listener 8000 e os processos Celery já não
apareciam; a identificação das filas em operação continua pendente.
O proxy alternativo permanece **não ativado**. Estes achados descrevem a
sandbox local; não são a topologia institucional de HML/PRD.

Em 2026-11-24, o contêiner Nginx padrão resolveu `host.docker.internal`
para `172.17.0.1`; a consulta de vivacidade em `:8000` foi recusada enquanto
o backend escutava em `127.0.0.1:8000`. Um contêiner **efêmero** com
`network_mode: host` alcançou a mesma vivacidade por `127.0.0.1:8000`.
Isso confirma a limitação da ponte Docker nesta sandbox e a viabilidade de
loopback para um piloto Linux no mesmo host, não para hosts distintos.

Foi preparado `infra/publicacoes-dev/compose-isolamento-loopback.yaml`, projeto
Compose separado e opt-in, com
`config/nginx/nginx-isolamento-loopback.conf`. Ele escuta somente em
`127.0.0.1:58444`, preserva o proxy padrão em `58443`, roteia API e WebSocket
para os processos piloto em loopback; bloqueia `/interno/` com `404` e devolve
`503` para o frontend e demais rotas. No ensaio efêmero com certificado verificado,
`/infra/healthz` e `/api/health/` responderam `200`; o bloqueio explícito de
`/interno/` respondeu `404`. A vivacidade de Carga respondeu
`502` porque **não havia** processo
na porta `8001`. O contêiner de ensaio foi removido; o novo Compose não foi
ativado. A prova cobre apenas roteamento local da plataforma atual, não
perfis ASGI separados, login/CSRF, WebSocket ou autorização via IAM remoto.

Em seguida, o ensaio automatizado com `test_gpp_plataform` montou dois
processos WSGI temporários com os URLConfs/middlewares piloto atrás de um
Nginx efêmero derivado da nova configuração loopback. O HTTPS foi verificado
com certificado de teste; Carga autorizada retornou `200`, sem sessão `401`,
após revogação de role `403` e, com IAM parado, `503` sem `Set-Cookie`.
`/interno/` não foi encaminhado (`404`) e `/` permaneceu indisponível (`503`).
Ao parar somente o processo de Carga, sua vivacidade passou a `502`, enquanto
a API pública e a vivacidade da plataforma conservaram suas respostas. Os
quatro testes focados passaram; todos os processos e contêineres efêmeros
foram encerrados. Isso **não** demonstra boot dos perfis ASGI completos,
WebSocket autenticado, CSRF, Celery, conectividade entre hosts ou cutover.

Em 2026-11-24, outro ensaio iniciou os **dois perfis ASGI completos** em
portas temporárias, sempre direcionados ao `test_gpp_plataform` por um lançador
de teste que recusa o banco operacional. Um Nginx efêmero com TLS verificado
roteou HTTP e WebSocket. Foram confirmados: Carga `200` com sessão e `401` sem
sessão; vivacidade separada; handshake WebSocket de Carga `101` com sessão e
`403` sem sessão; emissão de cookie CSRF e recusa `403` sem o token; requisição
com token e `Referer` válido atravessando o CSRF e chegando à validação do
login; `/interno/` inacessível pelo proxy (`404`). Parar somente Carga produziu
`502` em sua vivacidade sem afetar a API pública da plataforma. Com IAM parado,
Carga respondeu `503` em recurso protegido, sem emitir `Set-Cookie`. Os dois
testes passaram e encerraram os processos/contêineres de ensaio. A sessão e a
credencial M2M eram sintéticas; não houve Celery, Beat, migração, publicação de
dados ou conexão entre hosts. TLS cobriu somente cliente→proxy; os trechos em
loopback permaneceram HTTP. O proxy operacional não foi alterado.

## Contrato de processos do ensaio (não iniciar em paralelo ao launcher atual)

| Processo | Perfil | Porta/fila | Responsabilidade |
| --- | --- | --- | --- |
| ASGI plataforma | `config.settings.plataforma_piloto` | `127.0.0.1:8000` | IAM, Portal, Ações, Publicações e API pública; não serve Carga. |
| ASGI Carga | `config.settings.carga_piloto` | `127.0.0.1:8001` | `/api/carga-org-lot/`, `/ws/carga-org-lot/` e `/api/health/`; não serve outras apps. |
| Worker plataforma | `config.settings.plataforma_piloto` | somente `-Q celery` | E-Docs e demais tarefas da plataforma; não consome Carga. |
| Worker Carga | `config.settings.carga_piloto` | somente `-Q carga_org_lot` | Tarefas `carga_org_lot.*`; não consome Publicações. |
| Beat único | `config.settings.plataforma_piloto` | publica nas duas filas | Agendamentos de Carga e E-Docs; nenhum Beat no perfil de Carga. |
| Migrador designado | `config.settings.plataforma_piloto` | banco `default` | Migrações de todas as apps, manualmente e em janela; Carga executa zero migrações. |

O worker piloto é isolado por **fila e registro de tarefas**. Porém,
`INSTALLED_APPS` ainda carrega os modelos e outros módulos das demais apps;
isso não equivale a um processo fisicamente independente. O parâmetro `-Q`
continua obrigatório, e o piloto não deve herdar o
worker do `scripts/localhost_dev.sh`. Um processo antigo consumindo `celery`
ou `carga_org_lot` em paralelo invalidaria o ensaio. O mesmo banco e broker
continuam compartilhados; parar Carga não garante isolamento de falhas dessas
dependências.

## Comandos previstos para o ensaio, após fechar os gates

Executar cada processo em um supervisor/terminal próprio, com ambiente e
variáveis de configuração do projeto já carregados. **Não executar estes
comandos enquanto o launcher monolítico ou outro Beat/worker estiver ativo.**

```bash
DJANGO_SETTINGS_MODULE=config.settings.plataforma_piloto \
  .venv/bin/daphne -b 127.0.0.1 -p 8000 config.asgi_plataforma_piloto:application
DJANGO_SETTINGS_MODULE=config.settings.carga_piloto \
  .venv/bin/daphne -b 127.0.0.1 -p 8001 config.asgi_carga_piloto:application
DJANGO_SETTINGS_MODULE=config.settings.plataforma_piloto \
  .venv/bin/celery -A config worker -Q celery --loglevel=INFO
DJANGO_SETTINGS_MODULE=config.settings.carga_piloto \
  .venv/bin/celery -A config worker -Q carga_org_lot --loglevel=INFO
DJANGO_SETTINGS_MODULE=config.settings.plataforma_piloto \
  .venv/bin/celery -A config beat --loglevel=INFO
```

Antes de trocar o proxy, verificar diretamente `GET /api/health/` em 8000 e
8001 (identidades `plataforma` e `carga_org_lot`). Confirmar a exclusão de
rotas pelo resolvedor de URL de cada perfil e, em HTTP, também com sessão
autorizada em ensaio posterior. Requisições **anônimas** a rotas desconhecidas
podem retornar `401` no middleware antes da resolução; esse `401` não prova
que a rota inexiste. Depois, testar
WebSockets, autenticação, fila, autorização, falha do IAM e desligamento
isolado. Em caso de falha, parar os processos piloto e restaurar o arquivo de
proxy padrão; **não** reativar o worker antigo sem verificar mensagens em
trânsito e possíveis duplicações. Não há troca automática de banco ou fila.

## Condições antes de ativar

1. Confirmar que o Nginx em contêiner alcança os dois processos no host sem
   expor as portas à rede externa. O uso de `host.docker.internal` nesta
   sandbox não comprova conectividade nem segurança do futuro proxy.
2. Confirmar no banco escolhido que `pub_institucional.0015` está aplicada e
   que nenhuma FK entre schemas permanece. Ela já foi aplicada ao
   `gpp_plataform` em 2026-11-23, preservando a preferência existente. Não
   aplicar migrações automaticamente ao iniciar os processos do piloto.
3. Confirmar que não existe Beat ou worker antigo consumindo simultaneamente
   a mesma fila. Verificar mensagens pendentes antes e depois da troca.
   Liberar a porta 3000 para o frontend correto e comprovar o encaminhamento
   HTTP/WebSocket e a conectividade host-contêiner antes de trocar o Nginx.
4. Validar API e WebSocket de cada app, sessão e CSRF, `401`/`403`/`503` IAM,
   queda/reinício somente de Carga, continuidade de Publicações e Portal,
   logs de correlação e rollback de rota. A vivacidade `/api/health/` não é
   prova de autorização ou prontidão.

O `scripts/localhost_dev.sh` e `nginx.conf` existentes continuam como padrão.
O arquivo alternativo pode ser selecionado no Compose por
`GPP_NGINX_CONFIG_FILE=./config/nginx/nginx-isolamento.conf` apenas após o
ensaio dos requisitos acima. Não editar `runtime/.env` nem ligar o perfil
em uma instalação em uso apenas por existir esta configuração.

## Validação estática em 2026-11-23

- A migração `0015` foi aplicada em `gpp_plataform` após plano com somente
  essa operação pendente. A consulta posterior confirmou zero FKs entre os
  schemas `public`, `acoes_pngi`, `carga_org_lot` e `publicacoes`, uma
  preferência preservada e sua restrição de unicidade.
- Suíte completa após o fechamento dos perfis: 1427 testes aprovados, um
  ignorado. Nove testes focados de composição também passaram.
- `manage.py check` dos dois perfis e boot ASGI de ambos passaram.
- O roteador Celery enviou tarefas de Carga à fila `carga_org_lot` e E-Docs à
  fila `celery` nos dois perfis.
- A descoberta Celery foi verificada em subprocessos: Carga registra somente
  tarefas `carga_org_lot.*`, plataforma somente `pub_institucional.*`.
- Testes de subprocesso confirmaram que cada ASGI piloto rejeita o perfil
  incompatível antes de inicializar.
- Ensaio HTTP local em portas temporárias `127.0.0.1:18000` (plataforma) e
  `127.0.0.1:18001` (Carga): ambas as vivacidades responderam `200`; após
  encerrar somente Carga, a plataforma continuou em `200` e 18001 recusou
  conexão. Ambos os processos temporários foram encerrados. O primeiro ensaio
  revelou `500` de `debug_toolbar` em Carga; após removê-lo do perfil, a
  vivacidade respondeu `200`. Requisições anônimas a rotas excluídas deram
  `401` nos middlewares, portanto a exclusão de URL foi validada pelo
  resolvedor, não por esses códigos HTTP. Não houve teste via Nginx ou
  WebSocket neste primeiro ensaio.
- Ensaio WebSocket direto posterior nas mesmas portas temporárias: handshakes
  sem cookie para a rota própria de cada perfil foram negados com HTTP `403`,
  como esperado; caminhos da outra app inicialmente causaram HTTP `500`.
  Depois da rota de fallback, todos os quatro handshakes foram negados com
  HTTP `403`, sem erro interno. Após parar somente Carga, o handshake de
  Publicações ainda respondeu `403`. Ambos os processos foram encerrados.
  Isto comprova rejeição e independência de processo para cliente anônimo,
  **não** autenticação positiva, entrega de eventos, revogação, canal via
  Nginx ou autorização com sessão real.
- Ensaio HTTP automatizado adicional no `test_gpp_plataform`: dois processos
  WSGI temporários em portas de loopback efêmeras montaram os URLConfs piloto
  de plataforma e Carga, com identidade HTTP remota ligada somente no processo
  de teste. Uma sessão sintética autorizada obteve `200` em Carga; ausência
  de sessão deu `401`; retirada confirmada da role passou a dar `403` pela
  decisão IAM nova. Após encerrar apenas Carga, a API pública e a vivacidade
  da plataforma mantiveram a resposta. Com a plataforma/IAM encerrada, Carga
  continuou viva, mas a operação protegida respondeu `503` sem fallback.
  O teste encerrou ambos os processos e não modificou proxy, launcher ou
  flags operacionais. A regressão IAM adjacente somou 40 testes aprovados.
  Esse ensaio usa o **settings de teste** com URLConfs/middleware piloto:
  não comprova boot/deploy dos dois perfis completos, WebSocket autenticado,
  Nginx, TLS, worker/broker, CSRF através do proxy ou o banco `_hml`.
- O bloqueio de migração do perfil de Carga foi exercitado por teste do sinal
  `pre_migrate`; não foi executado `migrate` nesse perfil contra banco real.
- `docker compose config --quiet` e `nginx -t` com imagem local, contêiner
  efêmero sem rede e host fictício passaram. Isso valida sintaxe, **não**
  conectividade real, autorização, segurança de rede ou independência sob
  reinício.
- Ensaio automatizado adicional em `test_gpp_plataform`: Nginx temporário em
  porta efêmera, com certificado de teste e configuração derivada de
  `nginx-isolamento.conf`, encaminhou HTTPS verificado para processos HTTP
  separados de plataforma e Carga. Pela entrada TLS, foram verificados `200`
  autorizado, `401` anônimo, `403` após revogação de role, API pública da
  plataforma, vivacidades roteadas e `503` sem `Set-Cookie` quando IAM cai.
  O teste passou e removeu o contêiner efêmero. **O TLS testado protege
  cliente→proxy somente**: proxy→backends e Carga→IAM ainda usaram HTTP em
  loopback. Isso não comprova canal interno cifrado/autenticado para hosts
  distintos, WebSocket, CSRF, fila/worker ou cutover. O proxy em uso e as flags
  operacionais permaneceram inalterados.

## Pendência registrada — proteção dos canais internos

**Decisão de escopo em 2026-11-24:** não há previsão de colocar os serviços em
hosts diferentes. O ensaio atual permanece restrito a processos no mesmo host
e a endereços de loopback. A exigência de TLS interno entre hosts fica
registrada para uma eventual mudança de topologia, não como implementação
imediata. Isso não dispensa verificar o vínculo a loopback, a exposição de
portas e a rede efetivamente usada pelo proxy antes de ativar o piloto.

O HTTPS do cliente termina no Nginx. `X-Forwarded-Proto: https` comunica ao
backend o protocolo de entrada, mas **não** cifra o tráfego seguinte. O
`nginx-isolamento.conf` ainda usa `proxy_pass http://host.docker.internal` para
os backends. No teste efêmero, o Nginx usou rede do host e destinos HTTP em
`127.0.0.1`; na topologia prevista para o contêiner, `host.docker.internal`
é uma rota contêiner→host, **não** loopback dentro do contêiner. O teste não
comprova a conectividade nem a confidencialidade dessa rota real. A chamada
Carga→IAM do ensaio também foi HTTP em loopback com credencial M2M; autenticar
o serviço não equivale a cifrar o canal.

Antes de ativar o isolamento, resolver e ensaiar separadamente:

1. A topologia de rede efetiva entre proxy e cada backend, inclusive alcance
   de processos ligados apenas a `127.0.0.1`, exposição de portas e isolamento
   de outros contêineres/processos.
2. A restrição a loopback para proxy→backends e Carga→IAM na topologia local.
   Se os serviços ficarem em hosts distintos, exigir HTTPS com certificado
   verificado e autenticação de serviço no IAM (preferencialmente mTLS); manter
   `/interno/` fora do proxy público. A credencial M2M não substitui TLS.
3. Testes de destino indisponível, `401`/`403`/`503` e ausência de vazamento de
   cookie/token em respostas ou logs. Confirmar também HTTP, WebSocket, CSRF
   e rollback. Testes de certificado válido, não confiável e expirado tornam-se
   obrigatórios se a topologia passar a usar TLS interno.

**Critério de fechamento:** demonstrar por teste na topologia efetiva quais
trechos são cifrados/autenticados, quais são restritos a loopback e que o
proxy não expõe o IAM interno. O ensaio HTTPS atual fecha apenas
cliente→proxy. O novo ensaio confirma loopback somente na máquina local; não
autoriza cutover nem resolve TLS/autenticação entre hosts distintos.

## Dívida antes do isolamento final

No piloto IAM remoto, o HTTP e o WebSocket de Carga agora encaminham somente
`gpp_session_CARGA_ORG_LOT`. A decisão produtora do IAM exige esse nome exato:
um cookie `gpp_session_PORTAL` ou de outra app não substitui a sessão dedicada,
mesmo para `PORTAL_ADMIN`. O modo monolítico padrão conserva o middleware
local de sessão e sua política anterior; esta alteração não ativou o piloto.

O repositório e o registro `INSTALLED_APPS` continuam compartilhados. O
`SchemaRouter` aponta todos os modelos para `default`; o serviço de Carga
ainda pode consultar IAM localmente quando as flags remotas estão desligadas.
O piloto separa rotas e consumo de tarefas, **não** propriedade física dos
dados nem os demais serviços. A execução independente exige ainda contratos
de IAM, topologia operacional final, divisão física de banco, prontidão e
observabilidade. A política **atual** de migração é um único migrador da
plataforma no ensaio; o perfil padrão conserva o comportamento preexistente.
Migrações por domínio exigiriam novo desenho e ensaios históricos.
