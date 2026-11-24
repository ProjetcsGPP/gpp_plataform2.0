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
