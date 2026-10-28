# Plano de correção da fase e dos logs de autenticação CargaRH

**Preparado em:** 2026-10-27  
**Atualizado em:** 2026-10-28  
**Estado:** implementado e validado em testes; aguarda novo envio autorizado

## 1. Evidência que motivou a correção

Os envios de organograma `2` (simulação) e `3` (definitivo), ambos em HML,
foram interrompidos antes de chamar a API CargaRH. O endpoint de token do
Acesso Cidadão respondeu HTTP 400 com o código seguro `invalid_scope`.

O evento técnico registrou corretamente a operação `OBTER_TOKEN`, mas o evento
operacional foi classificado como fase `ENVIO`. A causa é a inferência atual de
fase pelo HTTP status: somente 401 e 403 são tratados como autenticação.

Após a correção do escopo, o envio `5` comprovou uma segunda situação: o token
foi obtido com HTTP 200 e o POST do organograma recebeu HTTP 403, com o título
`Client sem permissão nesse contexto de carga` e `traceId` fornecido pela
PRODEST. Essa recusa pertence à fase `ENVIO`, não à autenticação. O evento foi
preservado como evidência histórica e não foi reclassificado no banco.

## 2. Decisão de implementação

A fase será determinada pela origem da exceção, nunca apenas pelo HTTP status.

- falhas ao obter ou validar o token: `AUTENTICACAO`;
- falhas depois de obter o token, ao chamar o endpoint do organograma: `ENVIO`;
- `400 invalid_scope`, timeout do token, resposta inválida do token e token
  ausente pertencem à fase `AUTENTICACAO`;
- um eventual 401 ou 403 devolvido pelo endpoint de organograma, depois da
  tentativa controlada de renovar o token, pertence à fase `ENVIO`.

A implementação adotada mantém `CargaRHRequestError` e acrescenta metadados
explícitos de `operation`, `method` e `endpoint`. Isso preserva um único contrato
de erro seguro e permite classificar a fase pela operação que efetivamente
falhou. `CargaRHConfigurationError` permanece pertencendo à autenticação.

## 3. Contrato seguro de diagnóstico operacional

O evento operacional disponibilizado ao frontend poderá conter somente:

| Campo | Finalidade |
|---|---|
| `ambiente` | HML ou PRD selecionado pelo backend |
| `etapa` | `AUTENTICACAO` ou `ENVIO` |
| `servico` | `Acesso Cidadão` ou `API CargaRH` |
| `modo` | `SIMULACAO` ou `DEFINITIVO` |
| `operacao` | operação de integração que falhou |
| `metodo` | método HTTP seguro |
| `endpoint` | endpoint chamado, sem credenciais |
| `http_status` | status HTTP, quando houver resposta |
| `codigo_erro` | código permitido, como `invalid_scope` |
| `titulo_provedor` | título seguro devolvido pelo provedor |
| `detalhe_provedor` | detalhe seguro devolvido pelo provedor |
| `status_provedor` | status informado no corpo da resposta |
| `erros_provedor` | estrutura de erros permitida pelo contrato |
| `trace_id` | identificador de rastreamento do provedor |
| `escopos_solicitados` | nomes dos escopos, somente na autenticação |

Nunca serão persistidos ou enviados ao frontend:

- `client_id` ou `client_secret`;
- RoleID ou SecretID;
- access token ou refresh token;
- header `Authorization`;
- corpo bruto não filtrado;
- stack trace, detalhes de transporte ou arquivos de identidade.

O mesmo objeto seguro de detalhes deverá integrar a notificação em tempo real.
O frontend continuará tratando o evento persistido como fonte canônica.

## 4. Arquivos alterados

| Arquivo | Alteração |
|---|---|
| `apps/carga_org_lot/services/cargarh.py` | preservar operação, método e endpoint da falha e normalizar a composição da URL |
| `apps/carga_org_lot/services/organogram_submission.py` | classificar a fase pela origem e normalizar detalhes operacionais |
| `apps/carga_org_lot/services/integration_events.py` | incluir os detalhes seguros na notificação em tempo real |
| `apps/carga_org_lot/tests/test_cargarh.py` | cobrir `400 invalid_scope`, timeout e resposta inválida do token |
| `apps/carga_org_lot/tests/test_views_prodest.py` | cobrir timeline, fase, código, título e ausência de segredos |

Não há alteração de modelo nem migration prevista.

## 5. Testes obrigatórios

1. `400 invalid_scope` no token gera `AUTENTICACAO_REJEITADA` e fase
   `AUTENTICACAO`.
2. Timeout ao obter token permanece em `AUTENTICACAO`.
3. Token HTTP 200 com JSON inválido permanece em `AUTENTICACAO`.
4. Token HTTP 200 sem `access_token` permanece em `AUTENTICACAO`.
5. Erro HTTP no POST do organograma permanece em `ENVIO`.
6. 401 no POST do organograma renova o token uma vez; persistindo a recusa, a
   falha final permanece em `ENVIO`.
7. Evento técnico e operacional não contêm credenciais nem tokens.
8. Serializer e endpoint de eventos entregam os detalhes seguros ao frontend.
9. Notificação em tempo real contém o mesmo objeto seguro.
10. Regressão completa do fluxo de simulação, definitivo, status e relatório.

## 6. Critérios de aceite

- a timeline mostra `Autenticação` para o cenário observado de
  `400 invalid_scope`;
- o título informa que não foi possível autenticar;
- `Mais informações` apresenta ambiente, serviço, HTTP status, código do erro
  e escopos solicitados;
- nenhuma carga remota é indicada quando o token não foi obtido;
- erros reais do endpoint do organograma continuam na fase `Envio`;
- nenhum segredo aparece na API, WebSocket, banco operacional ou logs;
- testes focados e regressão aplicável passam antes do commit.

## 7. Tratamento do histórico

Os eventos `2` e `3` permanecem como evidência original e não serão alterados
automaticamente. A correção valerá para novos eventos. Qualquer retificação de
histórico exigirá decisão explícita, preservando o registro original.

## 8. Evidência de implementação

Em 2026-10-28:

- 8 testes críticos passaram para `invalid_scope`, timeout, token inválido,
  token ausente, 403 no envio, fase operacional e payload em tempo real;
- a regressão completa de `test_cargarh.py` e `test_views_prodest.py` passou com
  27 testes;
- `manage.py check`, Pylint em modo de erros e `git diff --check` passaram.

O próximo envio autorizado deverá comprovar a apresentação no frontend. Para o
403 atual, a timeline deve exibir fase `ENVIO`, ambiente, modo, endpoint,
status, título, detalhe e `traceId`. O resultado será evidência para o analista
da PRODEST, não uma inferência sobre a causa da recusa.
