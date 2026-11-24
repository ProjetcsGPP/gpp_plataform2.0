# Piloto opt-in de três processos: IAM, Carga e Publicações

**Estado em 2026-11-24:** perfis e proxy local criados e ensaiados no
`test_gpp_plataform`; não ativados nos serviços, proxy, Celery ou banco em uso.
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

Esses testes não iniciaram worker ou Beat, não executaram migrações, não
usaram credenciais reais nem verificaram publicação de mensagens no broker.
TLS protegeu cliente→proxy; proxy→backends ficou em HTTP/loopback, conforme o
escopo de mesmo host. Não há previsão de separar hosts; se isso mudar, revisar
transporte e certificados conforme
[a pendência dos canais internos](BACKEND_CARGA_ISOLAMENTO_PILOTO.md#pendência-registrada--proteção-dos-canais-internos).

## Gates antes de ativar

1. **IAM administrativo de Publicações:** `CanPermission`, middleware HTTP e
   WebSocket ainda leem `AccountsSession`, roles e permissões no banco
   compartilhado. O processo pode ser reiniciado separadamente, mas não é
   independente do IAM. Definir contrato remoto com falha fechada `401/403/503`,
   CSRF, revalidação de WebSocket e autorização por objeto antes de remover
   seu acesso às tabelas IAM. Não aplicar a autorização à API pública anônima.
2. **Tarefas E-Docs:** a coleta persiste ID/nome do solicitante, mas não
   revalida autorização antes de iniciar ou continuar chamadas externas.
   Definir semântica de revogação e recuperação, eventos de auditoria e o
   tratamento de resposta já recebida antes de copiar a política de Carga.
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
| `visoes.py` (`get_serializer_context` e `_contexto_serializador`) | Os indicadores `pode_*` e `permissoes_acoes` fazem decisões adicionais via `AuthorizationService`; devem vir de decisões IAM verificadas, nunca de inferência por role, cache desatualizado ou valor `True` padrão. |
| `visoes.py` (atores e preferência E-Flow) | O ID e nome auditáveis devem vir da decisão IAM; a preferência persiste `usuario_id` lógico, sem FK para o schema IAM. A identidade mínima precisa oferecer `pk`, `get_full_name()` e `get_username()` ou os usos devem ser adaptados explicitamente. |
| `apps/core/middleware/websocket.py` e `apps/pub_institucional/consumidores.py` | O handshake deve consultar IAM para `visualizar_coletas_patriarcas`; conexões longas precisam revalidar a autorização e fechar após revogação, sem consultar `AccountsSession`/`has_perm` local. |
| `apps/pub_institucional/tasks.py` e serviços de coleta | Atividades já aceitas precisam revalidar permissão do solicitante antes de cada etapa externa relevante. Revogação encerra novas ações; a resposta de uma chamada externa já concluída continua registrada na auditoria. |

Sequência de implementação, ainda **não ativada**:

1. **Contrato produtor implementado no piloto:**
   `/interno/iam/v1/decisoes-publicacoes/` usa
   `GPP_IAM_TOKEN_SERVICO_PUBLICACOES`, recusa token ausente, inválido ou
   compartilhado com Carga e fixa `PUB_INSTITUCIONAL` no servidor. Reaproveita
   as regras de sessão/role e consulta a autorização sem cache. Permanece
   inativo sem `GPP_IAM_DECISOES_INTERNAS_ATIVAS` e sem credencial provisionada
   fora do Git. A borda bloqueia `/interno/`; não há cliente Publicações ainda.
2. Criar cliente e guarda HTTP opt-in com canal de loopback no mesmo host,
   timeout curto, sem retry/cache de decisão e falha fechada. Preservar CSRF
   para mutações autenticadas por cookie e não limpar cookie em `503`.
3. Substituir também as decisões auxiliares e testar matriz de ações,
   identidade/auditoria, preferência, revogação, indisponibilidade e proteção
   contra rota administrativa sem guarda.
4. Tratar WebSocket e tarefa Celery em incrementos próprios. Só então ensaiar
   os três processos com IAM indisponível, revogação durante a execução e
   proxy TLS. O perfil padrão continua como rollback até cumprir os gates.
