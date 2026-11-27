# Piloto opt-in de três processos: IAM, Carga e Publicações

**Estado em 2026-11-25:** perfis e proxy local criados e ensaiados no
`test_gpp_plataform`, inclusive na porta alternativa fixa `58445`; credencial
local provisionada e flags habilitadas apenas nos perfis separados, mas
serviços, proxy, Celery e banco em uso não sofreram cutover.
Não representam cutover nem ambientes institucionais separados.

## Fronteiras do incremento

| Processo | Perfil | Rotas próprias | Fila/Beat |
| --- | --- | --- | --- |
| IAM/plataforma | `config.settings.plataforma_separada_piloto` | Accounts, Portal autenticado, Ações, `/interno/iam/`, `/api/health/` | Beat único; nenhum worker de domínio neste perfil. |
| Carga | `config.settings.carga_piloto` | `/api/carga-org-lot/`, `/ws/carga-org-lot/`, `/api/health/` | Worker `-Q carga_org_lot`; sem Beat. |
| Publicações | `config.settings.publicacoes_piloto` | `/api/pub-institucional/`, `/api/public/v1/publicacoes-institucionais/`, `/ws/pub-institucional/`, `/api/health/` | Worker `-Q pub_institucional`; sem Beat. |

O Beat do perfil IAM publica `carga_org_lot.*` na fila `carga_org_lot` e
`pub_institucional.*` na fila `pub_institucional`. A mudança em
`config/celery.py` impede que o perfil IAM registre todas as tarefas por
fallback quando sua lista explícita de pacotes é vazia. Não iniciar segundo
Beat; workers antigos que consomem a fila padrão devem ser inspecionados antes
de qualquer ativação. O migrador designado continua sendo a plataforma;
os perfis Carga e Publicações recusam `migrate`.

O proxy alternativo `infra/publicacoes-dev/compose-isolamento-tres.yaml` escuta
em `127.0.0.1:58445`, não altera o proxy atual, bloqueia `/interno/` e não
serve frontend. Ele requer Linux com `network_mode: host` e os três backends
ligados a loopback. A API pública segue o processo de Publicações e **não**
usa cookie, autorização IAM ou fallback administrativo, mesmo se um cliente
enviar cabeçalhos de sessão. Quando Publicações
para, a borda responde `502` para a API pública; o contrato aplicativo de
`503` só é produzido quando a requisição chega à app. O frontend deve tratar
ambos os casos sem usar uma prévia privada como substituto.

## O que o ensaio comprovou

- Contratos de rotas, WebSocket, registro de tarefas, filas e bloqueio de
  migrações passaram em oito testes focados.
- Três ASGI reais, um Nginx TLS efêmero e `test_gpp_plataform` passaram em
  teste de processo: identidades de saúde separadas; API pública em
  Publicações; API administrativa anônima recusada; WebSocket anônimo
  recusado; `/interno/` indisponível pelo proxy; ao parar Publicações, apenas
  suas rotas ficaram indisponíveis, enquanto IAM e Carga permaneceram vivos.
- O roteador Celery foi consultado diretamente: tarefa E-Docs →
  `pub_institucional`; tarefa Carga → `carga_org_lot`.
- Ensaio separado iniciou Redis descartável em loopback, um Beat com agenda
  exclusivamente sintética e um worker real do perfil Publicações. O Beat
  publicou na fila `pub_institucional`, o worker executou a tarefa de prova,
  registrou tarefas de Publicações sem registrar as de Carga e deixou uma
  mensagem de prova na fila `carga_org_lot` intocada. Processos e Redis foram
  encerrados ao fim do teste; nenhuma tarefa E-Docs ou PRODEST foi executada.
- Em 2026-11-25, um novo ensaio parou e reiniciou IAM, Publicações e Carga,
  um de cada vez, mantendo o proxy TLS efêmero ativo. A parada do IAM fez a
  API administrativa falhar fechada em `503`, sem interromper a API pública;
  a parada de Publicações devolveu `502` só em suas rotas; a parada de Carga
  devolveu `502` só em suas rotas. Cada serviço voltou a responder após seu
  reinício. Outro ensaio parou e reiniciou, sequencialmente, Beat e worker de
  Publicações usando apenas Redis descartável: a nova mensagem sintética foi
  processada e a fila de Carga permaneceu intocada. Os quatro testes focados
  de ASGI/proxy e Celery passaram; Pylint dos arquivos de ensaio: 10/10.
- O teste local **opt-in** `test_proxy_publicacoes_58445.py` iniciou a imagem
  real do Nginx alternativo na porta fixa `58445`, sem tocar no proxy `58443`.
  Os três ASGI usaram `test_gpp_plataform`, credenciais IAM sintéticas, cache
  e canais em memória. Passaram TLS, saúde dos três perfis, bloqueio de
  `/interno/`, HTTP autenticado e WebSocket de Carga e Publicações. Com IAM
  parado, as duas APIs administrativas responderam `503` com
  `servico_iam_indisponivel`, enquanto a API pública de Publicações manteve
  sua resposta. Ao fim, o container alternativo e os três ASGI foram
  encerrados; `58443` permaneceu ativo e as filas operacionais em zero.

O ensaio de filas corrigido não usa a agenda operacional nem o broker em uso. Os
testes não executaram migrações, não usaram credenciais reais e não provam
cutover operacional ou tratamento de mensagens antigas. O reinício foi
comprovado somente com processos descartáveis e configurações de ensaio,
não com o Beat/agendamentos operacionais.
O ensaio opt-in posterior cobriu a porta `58445`, mas **não** substituiu
credenciais sintéticas por autorização operacional, nem conectou canais ou
workers ao broker em uso; esses limites permanecem antes de qualquer corte.

### Inventário operacional local em 2026-11-24

Antes da parada feita pelo operador, havia um worker monolítico iniciado com
`celery -A config worker --loglevel=INFO` e um Beat monolítico iniciado com
`celery -A config beat --loglevel=INFO`. Ambos tinham cerca de sete horas de
execução. O perfil de desenvolvimento apontava o broker para o Redis local
`127.0.0.1:6379/0`; sua agenda incluía monitoramento de Carga e recuperação
de coletas E-Docs. Não iniciar o Beat do piloto enquanto o antigo estiver
ativo.

Durante a preparação do ensaio, um publicador auxiliar de teste direcionou
indevidamente cinco mensagens sintéticas `ensaio.publicacoes.ping` para esse
broker: três em `carga_org_lot` e duas em `pub_institucional`. A inspeção
somente de cabeçalhos confirmou que eram todas mensagens de teste. Após o
operador parar worker e Beat, as cinco foram removidas individualmente por
tipo e ID, sem `FLUSHDB` ou remoção de outras mensagens. A verificação final
registrou `LLEN=0` em `celery`, `carga_org_lot` e `pub_institucional`, além de
`HLEN unacked=0`, `ZCARD unacked_index=0` e nenhum processo Celery ativo.
O publicador auxiliar foi retirado do teste: a prova da fila de Carga agora
é inserida diretamente **somente** no Redis descartável do ensaio. Esse
incidente não equivale a um teste do broker operacional e deve ser considerado
na revisão antes de qualquer cutover.

Após a correção, o teste foi repetido com verificação explícita do endereço
do broker no processo worker; as filas do Redis em uso continuaram em zero.
Na verificação anterior, URL e token IAM de Publicações não estavam
configurados. Em 2026-11-24, o token local exclusivo foi provisionado no
diretório ignorado pelo Git; a URL de loopback e as flags remotas foram
configuradas **somente nos perfis separados**. O monólito continua com as
flags desligadas e sem esse token. Isso ainda **não** autoriza iniciar o perfil
separado como substituto funcional: faltam ensaio operacional e plano de
retorno.

O token local exclusivo do piloto é provisionado uma vez, sem ser exibido:

```bash
.venv/bin/python -m scripts.provisionar_token_iam_publicacoes_piloto
```

O arquivo ignorado pelo Git fica em
`infra/publicacoes-dev/runtime/secrets/iam_publicacoes_token`, com modo `0600`.
Os perfis separados IAM e Publicações leem o mesmo arquivo quando não há
token explícito no ambiente do processo; o monólito não o lê. Repetir o
comando valida o segredo existente sem rotacioná-lo. As flags
remotas são ligadas **apenas nos módulos de settings dos perfis separados**;
isso não inicia nem substitui serviços. Antes de iniciar qualquer perfil,
verificar que o monólito e seus workers não disputam rotas ou filas.
O produtor de Publicações usa a flag própria
`IAM_DECISOES_PUBLICACOES_ATIVAS`; a flag histórica de Carga
`IAM_DECISOES_INTERNAS_ATIVAS` não é ativada por consequência.

### Rechecagem operacional em 2026-11-25

Leitura do **host**, sem iniciar/parar processos nem alterar o broker:

- Não havia processo Django/Daphne/Gunicorn/Uvicorn do projeto nem Celery/Beat
  identificado; `8000`, `8001`, `8002` e `58445` não estavam em escuta.
  Trata-se de um retrato momentâneo, não de garantia para o instante do corte.
- O proxy Docker atual `gpp-publicacoes-dev-nginx-1` continuava saudável em
  `127.0.0.1:58443`; o proxy alternativo de três processos não estava ativo.
  A porta `3000` pertencia ao container `open-webui`, não ao frontend GPP.
- O broker configurado pelo perfil base era `127.0.0.1:6379/0`. Consultas
  **somente de contagem** retornaram `LLEN=0` nas filas `celery`,
  `carga_org_lot` e `pub_institucional`, `HLEN unacked=0` e
  `ZCARD unacked_index=0`. Nenhum payload foi lido ou removido.
- Os dois preflights locais de configuração, IAM e Publicações, passaram. O
  container OpenBao da sandbox aparecia `unhealthy`: a consulta de estado
  confirmou `initialized=true` e `sealed=true`. Desse modo, integrações que
  precisem buscar credenciais no cofre não estão prontas para operação; isso
  não invalida o preflight de configuração local. Os demais
  containers da sandbox necessários ao proxy/Redis/PostgreSQL apareciam
  ativos. A rechecagem não validou as integrações externas.

Na mesma data, o operador executou o bootstrap local existente **sem**
`--replace-app-identities`. O cofre foi desbloqueado com a chave local já
guardada fora do Git; nenhum segredo foi exibido e não foi solicitada rotação
de AppRoles. O healthcheck
passou a `healthy`. A leitura AppRole/KV2 das credenciais E-Docs HML e PRD
passou sem expor valores nem chamar a API externa. Em seguida, 12 testes
focados de isolamento ASGI/proxy, Celery, segredo e prontidão passaram no
`test_gpp_plataform`, com Redis descartável para o ensaio Celery. A condição
`sealed=true` acima descreve apenas o estado **antes** dessa correção. Um
reinício do container pode exigir novo desbloqueio; repetir o bootstrap sem
a opção de substituição e confirmar saúde antes de novo ensaio.

**Condição para avanço operacional:** repetir inventário imediatamente antes
do ensaio; confirmar qual processo é dono de cada porta, que somente um Beat
publicará agendamentos e que cada worker escutará exclusivamente sua fila.
Manter `58443` e a configuração monolítica disponíveis para retorno, sem
apontar tráfego real a `58445` até validar autenticação/CSRF, WebSocket,
API pública independente do IAM, indisponibilidade do IAM e recuperação dos
três processos. Interromper o ensaio se surgirem mensagens pendentes,
processos antigos concorrentes ou falha de dependência; não purgar filas nem
executar coleta E-Docs/PRODEST como prova. A janela de cutover e o plano de
retorno precisam ser confirmados antes de trocar o proxy em uso.

Conferir os dois perfis sem imprimir credencial:

```bash
DJANGO_SETTINGS_MODULE=config.settings.publicacoes_piloto \
  .venv/bin/python -m scripts.verificar_piloto_publicacoes
DJANGO_SETTINGS_MODULE=config.settings.plataforma_separada_piloto \
  .venv/bin/python -m scripts.verificar_piloto_publicacoes
```

O comando retorna código diferente de zero e descreve pendências sem imprimir
URL completa ou token. Resultado aprovado significa apenas coerência local:
o perfil de Publicações verifica o consumidor, e o perfil IAM verifica o
produtor separadamente. Ambos usam a mesma credencial local, fora do `.env`
compartilhado. A URL do IAM usa o loopback `127.0.0.1:8000` por padrão
**somente** no perfil local de Publicações, conforme a topologia do proxy de
três processos; outro destino exige configuração explícita e nova validação.
As flags permanecem desligadas no monólito.
O preflight não prova conectividade IAM, ausência de processos antigos, fila
vazia, autorização real nem aptidão para cutover. O token permanece fora do
Git; não iniciar os perfis separados antes dos ensaios e do plano de retorno.
TLS protegeu cliente→proxy; proxy→backends ficou em HTTP/loopback, conforme o
escopo de mesmo host. Não há previsão de separar hosts; se isso mudar, revisar
transporte e certificados conforme
[a pendência dos canais internos](BACKEND_CARGA_ISOLAMENTO_PILOTO.md#pendência-registrada--proteção-dos-canais-internos).

## Gates antes de ativar

1. **IAM administrativo de Publicações:** o caminho HTTP opt-in usa decisão
   remota e falha fechada `401/403/503`, com CSRF. O WebSocket possui flag
   independente para decisão remota no handshake, antes de cada evento e
   durante a ociosidade; permanece local por padrão. Tarefas e matriz de
   autorização por objeto ainda são gates antes de remover o acesso às tabelas
   IAM. Não aplicar autorização IAM à
   API pública anônima.
2. **Tarefas E-Docs:** o worker pode revalidar a autorização do solicitante
   persistido por decisão M2M exclusiva, antes da primeira chamada, de cada
   chamada seguinte e da conclusão. Resposta E-Docs já recebida é persistida
   antes da decisão seguinte. Revogação encerra a coleta em `ERRO`, com
   `AutorizacaoColetaRevogada`; indisponibilidade do IAM encerra em
   `IAMColetaIndisponivel`, sem rotular revogação. A flag fica desligada no
   monólito e ligada somente no perfil separado. O ensaio transacional entre
   processos confirmou revogação
   durante uma resposta simulada do E-Docs: a fonte já recebida ficou
   preservada e a chamada seguinte não começou. A recuperação simulada de
   solicitação antiga com permissão revogada reencaminha a mensagem, mas o
   worker a encerra antes de consultar E-Docs. Falta operação real de
   workers e broker, inclusive observar a fila durante o corte.
3. **Operação:** ensaiar Beat único, workers `-Q`, mensagens pendentes,
   reciclagem de cada processo, Redis/canais, cache, rollback, prontidão e
   falhas do IAM/proxy. Todos os perfis ainda instalam os modelos de todas
   as apps e usam `DATABASES['default']`; não há isolamento de banco.
4. **Contrato público:** preservar `ETag`, cache, `404/429/503` da app e
   tratar `502` da borda quando Publicações estiver parada. Não servir dados
   administrativos nem trocar silenciosamente a publicação vigente.

O perfil monolítico e o piloto anterior de dois processos permanecem
inalterados. Não ligar este terceiro perfil enquanto houver processo antigo
servindo as mesmas rotas ou worker antigo consumindo suas tarefas.

### Pendências após o ensaio da porta fixa

O teste de `58445` fecha a dúvida de **roteamento local** do proxy alternativo;
não fecha os gates de ativação. A próxima sequência do backend é:

1. O ensaio sintético cobre um Beat, filas exclusivas dos dois workers,
   Carga parada enquanto Publicações processa, mensagens pendentes e retomada
   de Carga. Um ensaio adicional reinicia Redis descartável com AOF e confirma
   persistência das duas filas e consumo após reconexão. Nenhum deles executa
   E-Docs/PRODEST ou usa o broker operacional. Ainda faltam concorrência,
   interrupção de tarefa em execução e roteamento de tarefas reais.
2. A varredura automatizada confirma que todas as ações administrativas HTTP
   habilitadas nos roteadores de Carga e Publicações declaram permissão
   técnica. Os ensaios TLS cobrem mutações representativas com IAM
   indisponível (`503`, nenhuma gravação), sessão ausente (`401`) e role
   revogada (`403`). A matriz dinâmica cobre agora 80 rotas mutáveis com
   `401/403/503` antes do handler. Ainda faltam efeitos e trilha de auditoria
   por mutação **autorizada** e evidência de auditoria de cada negativa.
3. Definir e testar inicialização, supervisão, versão, migração executada uma
   vez, rollback e observabilidade por serviço. Os três perfis ainda usam o
   mesmo banco e instalam modelos compartilhados; isso é isolamento de
   processos/rotas, não independência de dados ou de release.
4. Repetir inventário de processos, portas, filas e estado do OpenBao antes
   de qualquer janela de ativação. O proxy atual `58443` e o perfil monolítico
   permanecem como referência; não há autorização de cutover neste documento.

### Matriz de testes para o próximo gate

| Cenário | Evidência/critério de aceite | Estado |
| --- | --- | --- |
| Beat único e workers exclusivos | Cada fila recebe apenas sua tarefa; parar Carga preserva mensagens até o retorno, sem bloquear Publicações; nenhum worker registra tarefas da outra app. | Ensaio sintético automatizado, Redis descartável. |
| Falha e reconexão do broker | Confirmar que mensagens persistentes não se perdem, que não há consumo duplicado indevido e que tarefas idempotentes retomam após reinício. | **Parcial:** AOF descartável preservou mensagens pendentes das duas filas. Tarefa sintética com `acks_late`, interrompida por `SIGKILL`, voltou **automaticamente** após o `visibility_timeout` e concluiu no worker correto. Dois workers consumiram partes de 20 mensagens sintéticas, todas concluídas uma vez. O reinício imediato pode demorar mais que 30 s: o transporte Redis/Kombu só verifica periodicamente mensagens expiradas. Isso não prova retomada das tarefas reais nem idempotência de efeitos de negócio. |
| IAM desligado durante leitura/mutação | API administrativa responde `503` e código `servico_iam_indisponivel`, sem gravação parcial; API pública segue independente. | **Parcial:** GET/POST reais via proxy preservaram dados e API pública. Matriz dinâmica percorreu **80 rotas mutáveis distintas**, exercitando `401`, `403` e `503` (**240 combinações**) e provou que nenhum handler de domínio foi chamado. Ainda não equivale a testar efeitos e auditoria de toda mutação autorizada. |
| Sessão ausente, cookie de outra app e permissão revogada | `401` para sessão inválida, `403` para autorização negada; nenhuma decisão local substitui IAM; WebSocket fecha; ações ainda pendentes não executam. | **Parcial:** GET/POST representativos, cookie incorreto e WS cobertos; matriz de 80 rotas testa `401/403/503` antes do handler. Domínio tem testes de revogação em tarefas; falta cruzar todas as ações pendentes com a revogação. |
| Revogação durante tarefa externa | Parar antes de nova chamada externa; se resposta PRODEST já chegou, preservá-la e auditá-la; nenhuma conclusão posterior à revogação. | Testes de domínio existentes; repetir ponta a ponta por fila isolada. |
| Autorização por objeto e escopo | IDs de outra app/usuário não dão acesso nem permitem alteração; auditar tentativa negada sem vazar dados. | **Parcial:** ID inexistente dá `404` após autorização e `403` antes da busca após revogação; preferência E-Flow fica isolada por ID lógico de dois gestores. Não existe regra geral de propriedade para o acervo compartilhado do gestor; faltam escopos específicos e auditoria por endpoint. |
| Migração única e rollback | Rodar `migrate --plan`/`--check` no perfil IAM, proibir migração pelos perfis Carga/Publicações, comprovar backup e restauração antes do corte. | **Comprovado em ensaio descartável:** `migrate --check` no `test_gpp_plataform`; guardas `pre_migrate`; `pg_dump`/`pg_restore` com utilitários PostgreSQL 18, identidade do servidor conferida, migração 0016 → 0015 → 0016 e `migrate --check` no banco restaurado. O banco temporário foi removido; nenhum banco `gpp_ensaio_iso_%` permaneceu. Ainda falta procedimento operacional de backup/cutover e restauração da implantação real. |
| Versões incompatíveis durante reinício individual | API e tarefas suportam sobreposição de versões prevista; rejeição explícita de contrato incompatível; rollback recupera o serviço sem reiniciar os demais. | **Parcial:** resposta IAM versão 2 foi recusada com `503`, sem fallback; reinício individual de processos já foi ensaiado. A tag `v0.1.0` não contém os perfis separados de Carga/Publicações, portanto não serve como binário anterior comparável para este piloto. Coexistência real, versão de tarefa e rollback binário seguem pendentes. |
| Observabilidade | Correlation ID atravessa proxy, IAM e app; métricas/logs por serviço e fila permitem distinguir `401/403/503/502`, latência e falha de worker. | **Parcial:** mesmo ID foi verificado do pedido via proxy TLS até o log IAM. Faltam métricas por serviço/fila, latência, alerta e rastreio sistemático de falhas. |

O teste de filas usa `test_gpp_plataform`, Redis efêmero em loopback fora da
porta operacional padrão e tarefas sintéticas. Não substitui uma validação de
implantação nem autoriza ligar o perfil separado em operação.

**Incidente de segurança do ensaio:** um produtor Celery criado dentro do
processo pytest recebeu o broker global do Django (`127.0.0.1:6379`), apesar
de receber a URL temporária no construtor, e tentou publicar uma mensagem
**sintética** de teste. A abordagem foi removida; o produtor atual roda em
subprocesso protegido por guarda de URL/porta antes de publicar. Uma leitura
de verificação no broker operacional foi bloqueada pelo executor e não foi
contornada. Assim, não há confirmação neste ensaio de que a mensagem tenha
ficado pendente ou sido consumida; cabe inspeção operacional autorizada.

Evidências locais de 25/11/2026: suíte de regressão de isolamento, autorização,
E-Docs e revogação com **100 testes aprovados**; após os novos ensaios, suíte
direcionada dos cinco módulos modificados com **41 testes aprovados**. Os
serviços de teste usaram portas temporárias, TLS local e Redis descartável;
nenhum worker acessou o broker operacional nem executou chamadas externas.
`manage.py check`, Pylint dos módulos alterados e `git diff --check` passaram.
Os totais das duas suítes podem conter testes repetidos e não devem ser somados
como número de casos distintos.

Complemento da mesma data: a matriz dinâmica de mutações passou com **240
combinações** (`80 rotas × 3 resultados IAM`) no banco permanente de testes.
Os ensaios de restauração **automática** de tarefa sintética e de dois workers
concorrentes passaram no Redis efêmero. O ensaio opt-in de backup/restauração
passou com `GPP_PG_BIN_DIR` apontando aos utilitários PostgreSQL 18 do Windows.
O primeiro preflight falhou porque o interop WSL não encaminhava `PGPASSWORD`
ao `psql.exe`; após adicionar `PGPASSWORD/w` a `WSLENV`, a identidade do servidor
foi confirmada e o ensaio completo passou. A senha não foi posta na linha de
comando. Esses resultados não fecham auditoria por endpoint nem recuperação de
tarefas reais.

Regressão ampliada após os ajustes: **299 aprovados, 1 ignorado por opt-in e 9
avisos de `fork()` em processo multithread**. O ensaio TLS de reinício individual
falhou uma vez na inicialização do proxy descartável; passou isoladamente e na
reexecução integral. O helper agora inclui o log do contêiner quando a
inicialização falha e não substitui o erro original por falha de limpeza. O
ensaio de restauração foi executado separadamente com opt-in: **1 aprovado**;
consulta posterior confirmou **zero** bancos `gpp_ensaio_iso_%` remanescentes.

**Recuperação de Publicações, 26/11/2026:** o worker mantém bloqueio de sessão
PostgreSQL durante a coleta. A rotina periódica, com flag opt-in, só encerra
uma revisão `EXECUTANDO` antiga quando consegue obter o mesmo bloqueio; registra
`ERRO`/`ExecucaoInterrompida` com auditoria, preserva fontes e permite nova
revisão. Não repete chamadas externas. A flag
`GPP_EDOCS_ORPHAN_RECOVERY_ENABLED` fica **desligada por padrão** até todos os
workers Publicações terem sido atualizados; numa versão mista um worker antigo
não mantém o bloqueio e poderia ser classificado incorretamente como órfão.
Ensaio com morte real do processo após `EXECUCAO_INICIADA`, e com bloqueio
simultâneo por outro acesso ao banco, passou. O primeiro ensaio deixou dois
registros sintéticos no `test_gpp_plataform` devido à limitação do `flush`
entre schemas; ambos foram identificados e removidos pontualmente. Os ensaios
atuais limpam seus dados e a consulta posterior confirmou zero sobras.
Regressão ampliada após a implementação: **307 aprovados, 1 opt-in ignorado e
9 avisos de `fork()` em processo multithread**; `makemigrations --check --dry-run`
não encontrou mudança de modelo. `manage.py check`, Pylint e `git diff --check`
passaram.
Permanecem para o gate: atualização coordenada de todos os workers, habilitação
deliberada da flag, teste integrado de Beat/worker reais com falhas em cada
etapa de persistência e alerta operacional para revisões encerradas pelo
monitor. A confirmação antecipada do Celery continua; o mecanismo resolve o
estado de negócio órfão, não reentrega a mesma tarefa.

**Limite do ensaio de migração:** a reversão foi executada somente no banco
descartável restaurado. Como os três perfis compartilham o mesmo banco,
executar rollback real de schema na base em uso poderia indisponibilizar outras
apps. O teste de sobreposição de versões ainda depende de artefatos versionados
próprios; não é coberto por esse ensaio.

### Procedimentos ainda necessários para fechar o gate

1. **Mutações/auditoria:** manter a enumeração automática das rotas. Para
   cada ação com estado persistente, ensaiar sucesso, validação inválida,
   `401`, `403`, `503` e objeto fora do escopo aplicável; verificar estado
   antes/depois, evento de auditoria (ator lógico, ação, alvo e instante) e
   correlação. A matriz de `401/403/503` prova somente a barreira antes do
   handler; não substitui essa verificação de efeito e auditoria. Separar
   eventos do IAM, eventos de domínio e logs de falha quando IAM não responde.
2. **Broker:** a restauração automática foi comprovada quando o novo worker
   iniciou após o `visibility_timeout`; reinício imediato espera a cadência de
   varredura do transporte. Repetir `SIGKILL` e reinício do broker com tarefas
   reais instrumentadas e integrações externas substituídas por fakes, depois
   de definir recuperação idempotente. Comprovar que reentrega não duplica
   efeitos persistentes nem chamadas externas já aceitas.
3. **Banco:** o teste opt-in passou com os utilitários PostgreSQL 18 no Windows:
   `GPP_ENSAIO_RESTAURACAO_DESCARTAVEL=1 GPP_PG_BIN_DIR=<binarios-pg18> .venv/bin/pytest apps/core/test_isolamento_publicacoes_piloto.py::test_backup_restaura_e_reverte_migracao_em_banco_descartavel --reuse-db`
   somente com `test_gpp_plataform` como origem. O teste confere o
   identificador do servidor, cria nome aleatório, restaura, reverte 0016,
   reaplica e remove o banco criado. Se falhar após criação, confirmar a
   remoção do banco descartável; nunca apontar o ensaio para `gpp_plataform`.
4. **Versões:** criar dois artefatos *do piloto separado* a partir de commits
   conhecidos (a tag `v0.1.0` não contém os perfis). Testar IAM A/B com
   consumidores A/B no mesmo schema expandido, tarefas serializadas por ambas
   as versões e rollback do processo B para A sem reiniciar as outras apps.
   Contrato incompatível deve responder `503` e registrar decisão; não
   aceitar fallback de autorização.
5. **Observabilidade:** antes de ativação, definir coleta interna por serviço
   de contagem `401/403/503`, latência HTTP/IAM, falhas de tarefa, profundidade
   e idade da mensagem mais antiga por fila, `unacked`, heartbeat do worker e
   Beat único. Alertas precisam distinguir indisponibilidade de IAM, `502` do
   proxy para domínio parado e acúmulo de fila; testar disparo e recuperação
   com thresholds operacionais aprovados. Não expor métricas internas na API
   pública nem registrar cookies/tokens em logs.

## Inventário para o próximo gate: IAM administrativo de Publicações

O perfil de Publicações separa processos e rotas, **não** a identidade. Hoje
`AppContextMiddleware` resolve `AccountsSession` para
`/api/pub-institucional/`; os middlewares de contexto consultam aplicação e
roles; `IsAuthenticated` e `CanPermission` usam a identidade e a autorização
locais. Apenas trocar `CanPermission` por um cliente remoto não é suficiente.

| Ponto atual | Dependência a substituir antes do cutover |
| --- | --- |
| `apps/accounts/middleware.py` e `apps/core/middleware/{application_context,role_context,authorization}.py` | O bypass remoto deve valer **somente** para `/api/pub-institucional/`, com guarda obrigatório na view; `/api/public/v1/publicacoes-institucionais/` permanece anônimo e independente do IAM. |
| `apps/pub_institucional/visoes.py` (`MixinPermissaoPorAcao` e `VisaoIbgeBase`) | Cada ação administrativa precisa de decisão IAM para a permissão técnica declarada. Erros devem distinguir sessão inválida `401`, permissão negada `403` e IAM indisponível/contrato inválido `503`, sem fallback ao banco IAM local. |
| `visoes.py` (`get_serializer_context` e `_contexto_serializador`) | No piloto opt-in, os indicadores `pode_*` e `permissoes_acoes` usam decisões adicionais IAM; não há inferência por role nem fallback local. |
| `visoes.py` (atores e preferência E-Flow) | O ID e nome auditáveis devem vir da decisão IAM; a preferência persiste `usuario_id` lógico, sem FK para o schema IAM. A identidade mínima precisa oferecer `pk`, `get_full_name()` e `get_username()` ou os usos devem ser adaptados explicitamente. |
| `apps/core/middleware/websocket.py` e `apps/pub_institucional/consumidores.py` | O handshake deve consultar IAM para `visualizar_coletas_patriarcas`; conexões longas precisam revalidar a autorização e fechar após revogação, sem consultar `AccountsSession`/`has_perm` local. |
| `apps/pub_institucional/tasks.py` e serviços de coleta | Decisão M2M por solicitante persistido, antes de cada chamada externa e da conclusão; a resposta externa já concluída fica na fonte bruta. Revogação entre processos foi ensaiada; falta operação real. |

Sequência de implementação, ainda **não ativada**:

1. **Contrato produtor implementado no piloto:**
   `/interno/iam/v1/decisoes-publicacoes/` usa
   `GPP_IAM_TOKEN_SERVICO_PUBLICACOES`, recusa token ausente, inválido ou
   compartilhado com Carga e fixa `PUB_INSTITUCIONAL` no servidor. Reaproveita
   as regras de sessão/role e consulta a autorização sem cache. Permanece
   inativo sem a flag própria `IAM_DECISOES_PUBLICACOES_ATIVAS` e sem
   credencial provisionada fora do Git.
   A borda bloqueia `/interno/`; o cliente administrativo opt-in
   usa somente o endereço interno de loopback.
2. **HTTP administrativo implementado em modo opt-in:** cliente e guarda
   aceitam HTTP somente em loopback no mesmo host, com timeout curto, sem
   retry/cache de decisão e falha fechada. Exigem exatamente
   `gpp_session_PUB_INSTITUCIONAL`: cookie do Portal ou de outra aplicação
   não autoriza Publicações, mesmo para administrador. Preservam CSRF para
   mutações autenticadas por cookie e não limpam cookie em `503`.
3. **Decisões auxiliares substituídas no código:** os `pode_*` e a projeção
   de ações usam o IAM remoto quando a flag está ativa. O ensaio HTTP no proxy
   cobre leitura autorizada, revogação, CSRF, IAM indisponível e API pública;
   a matriz de mutações e autorização por objeto ainda não foi integralmente
   ensaiada.
4. O incremento WebSocket opt-in exige exclusivamente o cookie
   `gpp_session_PUB_INSTITUCIONAL`, fecha a conexão em `4401` por sessão
   inválida, `4403` por permissão negada e `1013` por indisponibilidade do
   IAM. Revalida antes de cada evento e a cada 30–300 s ocioso. A rota real
   via proxy foi ensaiada; a tarefa Celery recebeu incremento opt-in próprio.
   Revogação entre processos durante chamada em voo e fila/worker/Beat
   sintéticos foram ensaiados. Ainda falta observar broker, workers e Beat
   operacionais antes de ativar o perfil.
   O perfil padrão continua como rollback até cumprir esses gates.

**Incremento HTTP ensaiado somente em testes:** o consumidor administrativo pode ser
ativado apenas no ensaio opt-in por
`GPP_PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA`, com
`GPP_PUBLICACOES_IAM_URL` apontando ao endpoint interno em loopback e token
exclusivo configurado fora do Git. O guarda `CanPermissionPublicacoes` consulta
o IAM por ação, revalida CSRF, projeta identidade mínima e traduz negativa e
falha para `401/403/503`. As decisões `pode_*` dos serializadores também
consultam o IAM; a API pública não entra nesse fluxo. A flag permanece
desligada no monólito e ligada somente no perfil separado. O ensaio ASGI real
com Nginx TLS efêmero e
`test_gpp_plataform` verificou `200` autorizado, `401` anônimo, `403` após
revogação de role, `403` por falta de CSRF e `503` quando o IAM para, com
   `errors.code` estável; a API pública continuou respondendo sem IAM. O
WebSocket remoto foi ensaiado via proxy com handshake autorizado, recusa após
revogação e indisponibilidade do IAM; operação Celery, matriz administrativa completa e retirada do
acesso às tabelas IAM também são gates de ativação. O proxy não foi alterado
em operação.

**Flag adicional, desligada no monólito e ligada no perfil separado:**
`GPP_PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO`; intervalo opcional
`GPP_PUBLICACOES_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS` (30–300 s).
Requer URL e token IAM exclusivos de Publicações, já usados pelo HTTP.

**Tarefa mensal E-Docs, flag desligada no monólito e ligada no perfil separado:**
`GPP_PUBLICACOES_IAM_ATIVIDADES_REMOTAS_ATIVAS`. O produtor M2M é
`/interno/iam/v1/decisoes-atividade-publicacoes/`, indisponível sem token
exclusivo ou se ele coincidir com o de Carga. A identidade vem do campo
`criado_por_id` da coleta, nunca da mensagem Celery. Cada decisão autorizada
gera evento de auditoria `AUTORIZACAO_VALIDADA`, com etapa, ID de decisão e
versão, sem token ou cookie. Resposta em voo já obtida é gravada antes de
revalidar; novas chamadas param após revogação. Solicitações antigas sem
`criado_por_id` falham fechadas quando a flag estiver ligada e exigem
tratamento operacional explícito. Recuperação agendada pode reencaminhar uma
solicitação revogada, mas o worker a encerra antes de consultar E-Docs.
O `has_permission` de Carga mantém duas flags históricas: decisão remota
mantendo identidade local e identidade HTTP totalmente remota. Publicações
implementa apenas a segunda modalidade; ambos os guardas exigem o cookie
exato da própria aplicação. O produtor IAM também recusa o fallback por
cookie do Portal nos dois contratos remotos.
O transporte genérico deste incremento está em `common/services/cliente_iam.py`;
o cliente anterior de Carga permanece em sua app para não misturar uma
refatoração de contrato já ensaiado ao corte de Publicações. Consolidar os
dois clientes é dívida técnica posterior, após testes de equivalência.
