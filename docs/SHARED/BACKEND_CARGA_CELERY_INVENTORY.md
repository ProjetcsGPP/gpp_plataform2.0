# Inventário de tarefas Celery — Carga Org/Lot

Estado observado em 2026-11-19. O piloto de revogação foi implementado atrás de `GPP_CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS`, **desligada por padrão**. Não há cutover de serviço ou worker.

## Tarefas e pontos de entrada

| Tarefa | Origem | Dados na mensagem | Efeito | Autorização atual no worker |
| --- | --- | --- | --- | --- |
| `carga_org_lot.processar_envio_organograma` | `EnvioOrganogramaProdestViewSet.create`, via `transaction.on_commit`; ou monitor periódico | Somente `envio_id` | Em `SOLICITANDO`, envia o payload à PRODEST, inclusive em `dry_run`; em `PROCESSANDO`, consulta o estado remoto e atualiza banco, eventos e WebSocket | No piloto, revalida a autorização atual pelo IAM antes de agir e após registrar a resposta remota; não usa cookie na fila. No modo padrão, a flag permanece desligada. |
| `carga_org_lot.monitorar_envios_organograma` | Celery Beat, no intervalo configurado | Nenhum parâmetro | Localiza envios `SOLICITANDO` ou `PROCESSANDO` vencidos e enfileira `processar_envio_organograma` | Tarefa de sistema, sem usuário solicitante nem decisão IAM. |

O mesmo nome de tarefa mistura **início de ação externa** e **acompanhamento de ação já iniciada**. `SOLICITANDO` não prova que nada foi transmitido: é preciso preservar a proteção contra reenvio após falha entre a chamada remota e a persistência do identificador externo. `PROCESSANDO` pode representar carga já recebida pela PRODEST; interromper sua consulta por revogação de um usuário não desfaz a carga remota.

## Regra funcional confirmada

- Antes do primeiro envio externo, consultar o IAM no momento da execução. Se a autorização atual foi negada, **não chamar a PRODEST**; encerrar a tentativa local com mensagem explícita.
- Se a revogação ocorrer durante a chamada, **registrar primeiro a resposta da PRODEST** (inclusive o identificador de carga quando retornado) e somente depois encerrar localmente. Uma carga aceita pode continuar na PRODEST; o backend **não faz novas consultas** e não afirma cancelamento remoto. O estado local é `SITUACAO_REMOTA_INDETERMINADA`.
- O evento `ENVIO_EXTERNO_INICIADO` antecede a tentativa de envio. Se houver revogação sem identificador de carga após esse marco, o estado remoto permanece indeterminado: não se afirma que o envio não ocorreu. Se o aceite ou uma resposta de erro chegar depois do encerramento local, a resposta é preservada nos dados/eventos da tentativa sem reabrir o monitoramento.
- A mesma regra se aplica à consulta de status que já estava em voo: o JSON retornado ou o erro da PRODEST é registrado, enquanto o estado local encerrado e a ausência de novas consultas são mantidos.
- Se o IAM estiver indisponível, não rotular como revogação nem iniciar nova chamada externa. A tentativa aguarda outra revalidação; o evento operacional informa a indisponibilidade.
- `EnvioOrganogramaProdest` já guarda solicitante, início, estado e finalização; `EventoIntegracaoProdest` e histórico do processo guardam a causa, momento, resultado remoto conhecido e ator de sistema. Não foi criada uma tabela genérica duplicada para a tarefa Celery. A fila contém apenas `envio_id`.
- O monitor periódico não deve receber cookie nem identidade de usuário. Sua autorização é a identidade M2M do próprio serviço; apenas tarefas agendadas por ele podem fazer consultas de acompanhamento. Impedir que uma mensagem forjada use o mesmo `envio_id` para iniciar um envio sem a decisão IAM correspondente.

O piloto usa `POST /interno/iam/v1/decisoes-atividade/` com credencial M2M exclusiva de Carga, `usuario_id` obtido do envio persistido e a permissão `change_importacaoplanilha`. O IAM consulta o usuário ativo e a autorização atual sem cache. O worker revalida antes e depois de cada operação externa. O registro canônico e o evento `ATIVIDADE_ENCERRADA_REVOGACAO` são consultáveis pela API de envios/eventos existente; o WebSocket apenas notifica. O envio remoto e a interrupção local são fatos distintos.

O mesmo padrão deve ser aplicado futuramente às tarefas de **envio e acompanhamento de lotações**, quando forem criadas; elas ainda não existem no Celery.

## Lacunas para implementação

1. O contrato M2M por usuário e ação foi criado para o piloto; falta autorização por objeto (patriarca, importação e processo) no IAM ou contrato de escopo equivalente. Decidir se revogação de **sessão** também encerra trabalhos aceitos; a implementação atual cobre desativação do usuário e perda da permissão técnica.
2. A revalidação antes/depois da chamada não interrompe uma requisição HTTP já em voo nem é instantânea entre checkpoints. Para cancelamento com latência menor que o intervalo do monitor, definir notificação durável IAM→app ou varredura mais frequente. Não prometer cancelamento remoto.
3. O marco local de início da tentativa evita afirmar “não enviado” em timeout ou queda entre a resposta e sua persistência, mas não prova aceite remoto. Reforçar idempotência diante de Beat, retry e workers concorrentes; o evento de início e a ausência de UUID não autorizam novo envio automático.
4. O código de evento diferencia revogação de falha da PRODEST e indisponibilidade do IAM. Confirmar o texto/UX no frontend. O registro canônico é o envio e seus eventos, não o resultado Celery (`CELERY_TASK_IGNORE_RESULT=True`).
5. Separar filas, worker e agendamento de Carga dos de Publicações na implantação independente. Hoje `CELERY_BEAT_SCHEDULE` contém tarefas das duas apps; não deve haver dois Beats agendando o mesmo monitor.
6. Ampliar testes de concorrência real entre workers, timeout indeterminado, visibilidade no frontend, reversão das flags e processos/worker efetivamente separados. A revogação simulada durante uma consulta de status já possui teste de regressão.

Até esses pontos serem resolvidos, as flags remotas de Carga continuam desligadas e este piloto não deve ser interpretado como autorização para o cutover.

Verificação local em 2026-11-23: 11 testes específicos de revogação e 19 testes de integração PRODEST aprovados; suíte completa com 1.417 aprovados e 1 ignorado. `manage.py check`, `migrate --check`, Pylint dos módulos alterados (9,99/10) e `git diff --check` aprovados. A flag de revogação permanece desligada.
