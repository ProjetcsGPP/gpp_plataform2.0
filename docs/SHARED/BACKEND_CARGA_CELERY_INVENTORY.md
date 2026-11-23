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
- Após uma decisão IAM positiva, o worker relê o envio antes da operação externa. Se outra execução mudou o estado enquanto a decisão estava em voo (por exemplo, encerramento por revogação), ele não usa o snapshot antigo para enviar ou consultar. Isso reduz uma janela de corrida; não torna atômicas a decisão IAM e a chamada à PRODEST nem interrompe uma chamada já iniciada.
- `EnvioOrganogramaProdest` já guarda solicitante, início, estado e finalização; `EventoIntegracaoProdest` e histórico do processo guardam a causa, momento, resultado remoto conhecido e ator de sistema. Não foi criada uma tabela genérica duplicada para a tarefa Celery. A fila contém apenas `envio_id`.
- O monitor periódico não deve receber cookie nem identidade de usuário. Sua autorização é a identidade M2M do próprio serviço; apenas tarefas agendadas por ele podem fazer consultas de acompanhamento. Impedir que uma mensagem forjada use o mesmo `envio_id` para iniciar um envio sem a decisão IAM correspondente.

O piloto usa `POST /interno/iam/v1/decisoes-atividade/` com credencial M2M exclusiva de Carga, `usuario_id` obtido do envio persistido e a permissão `change_importacaoplanilha`. O IAM consulta o usuário ativo e a autorização atual sem cache. O worker revalida antes e depois de cada operação externa. O registro canônico e o evento `ATIVIDADE_ENCERRADA_REVOGACAO` são consultáveis pela API de envios/eventos existente; o WebSocket apenas notifica. O envio remoto e a interrupção local são fatos distintos.

O mesmo padrão deve ser aplicado futuramente às tarefas de **envio e acompanhamento de lotações**, quando forem criadas; elas ainda não existem no Celery.

## Lacunas para implementação

1. O contrato M2M por usuário e ação foi criado para o piloto; falta autorização por objeto (patriarca, importação e processo) no IAM ou contrato de escopo equivalente. Decidir se revogação de **sessão** também encerra trabalhos aceitos; a implementação atual cobre desativação do usuário e perda da permissão técnica.
2. A revalidação antes/depois da chamada não interrompe uma requisição HTTP já em voo nem é instantânea entre checkpoints. Para cancelamento com latência menor que o intervalo do monitor, definir notificação durável IAM→app ou varredura mais frequente. Não prometer cancelamento remoto.
3. O marco local de início da tentativa evita afirmar “não enviado” em timeout ou queda entre a resposta e sua persistência, mas não prova aceite remoto. A reserva transacional durável agora bloqueia reenvio automático da mesma tentativa mesmo após vencerem os cinco minutos da reserva de agendamento, em retry ou worker concorrente. Quando o primeiro worker cai sem resposta local, o envio permanece `SOLICITANDO` com evento `REENVIO_AUTOMATICO_BLOQUEADO` para conferência operacional; não se presume aceite, falha ou cancelamento remoto. Ainda falta definir a reconciliação manual/externa e, se disponível, uma chave de idempotência aceita pela PRODEST.
4. O código de evento diferencia revogação de falha da PRODEST e indisponibilidade do IAM. Confirmar o texto/UX no frontend. O registro canônico é o envio e seus eventos, não o resultado Celery (`CELERY_TASK_IGNORE_RESULT=True`).
5. Separar filas, worker e agendamento de Carga dos de Publicações na implantação independente. Hoje `CELERY_BEAT_SCHEDULE` contém tarefas das duas apps; não deve haver dois Beats agendando o mesmo monitor.
6. Ampliar testes com workers Celery e broker efetivos, timeout indeterminado, visibilidade no frontend e reversão das flags. A revogação simulada durante uma consulta de status já possui teste de regressão. Os testes com dois processos do sistema operacional e conexões PostgreSQL independentes cobrem as corridas de estado, mas não executam a infraestrutura Celery da topologia final.

Um teste adicional simula o encerramento local enquanto o IAM responde com
autorização positiva: o worker observa o novo estado e não chama a PRODEST.
Ele não substitui o ensaio com workers Celery reais nem prova ausência
de corrida entre a releitura e o início da chamada externa.

Cinco ensaios adicionais executam a tarefa em um processo separado com
conexão própria ao PostgreSQL de testes e bloqueiam a PRODEST ou o IAM
simulados em pontos controlados: segunda execução da mesma tentativa durante
o envio, segunda execução após o vencimento da reserva de cinco minutos,
revogação seguida de aceite remoto, revogação seguida de erro remoto
e encerramento enquanto a decisão IAM ainda está em voo. Eles confirmam
persistência do resultado remoto sem reabrir o monitoramento e ausência de
novo envio quando a mudança de estado já é observável. Não iniciam dois
workers Celery reais, não usam broker e não cobrem uma revogação ocorrida
após a releitura de estado. Um sexto ensaio simula a queda do worker após
o marco externo e antes da resposta: não há reenvio, e o bloqueio é auditado.

Até esses pontos serem resolvidos, as flags remotas de Carga continuam desligadas e este piloto não deve ser interpretado como autorização para o cutover.

Verificação local em 2026-11-23: 18 testes específicos de revogação/concorrência e 19 testes de integração PRODEST aprovados. Uma primeira execução ampla no banco permanente reutilizado apresentou falhas em cascata de preparação/limpeza de fixtures (`ProtectedError` em `StatusProgresso` e duplicidade de chaves). O primeiro teste falho, o arquivo `test_cargos.py` e a combinação de cargos com revogação passaram isoladamente; uma nova execução **serializada** de toda a suíte de Carga concluiu com **263 aprovados**. O episódio é compatível com interferência de execuções no mesmo banco reutilizado, mas a causa não foi comprovada. Como proteção, `conftest.py` passou a obter trava exclusiva no início de cada sessão PostgreSQL com `--reuse-db` e a recusar outra sessão antes da coleta; um teste automatizado e um ensaio com duas sessões confirmaram o bloqueio. Depois da proteção, a suíte de Carga mais o teste da trava concluiu com **264 aprovados**. A trava não substitui isolamento entre máquinas ou bancos diferentes. `manage.py check`, Pylint dos módulos alterados (10,00/10) e `git diff --check` aprovados neste incremento. A flag de revogação permanece desligada.
