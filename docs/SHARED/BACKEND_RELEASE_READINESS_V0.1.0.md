# Prontidão da primeira versão estável do backend (`v0.1.0`)

Avaliação iniciada em 2026-11-18. Estado atual: **gates locais corrigidos e
aprovados; aguardando PR e verificações remotas antes do merge**. Nenhum merge,
tag ou GitHub Release foi criado nesta avaliação.

## Escopo exato do candidato

- Base local e remota `main`: `fae9d21dc659ea77fcac34d959d4e87d4670197e`.
- Branch local e remota: `feat/publicacoes-informacoes`, em
  `8d8756783bf795e0af4639f117fb4e81e09362de`.
- O intervalo candidato é `fae9d21..8d87567` (15 commits, 218 arquivos);
  `git diff --name-status fae9d21..8d87567` é a relação integral e
  reproduzível dos caminhos. Inclui `apps/pub_institucional`, mudanças em
  `accounts`, `carga_org_lot` e `core`, componentes compartilhados em `common`,
  configurações, migrações, documentação e a sandbox `infra/publicacoes-dev`.
- As três alterações locais anteriores à avaliação eram relativas à ordenação
  lógica por competência em `apps/pub_institucional/visoes.py`, seu teste e
  `docs/PUBLICACOES/EDOCS_ADMIN_API.md`; foram preservadas na validação.
- Não existe tag local ou remota `v0.1.0`, release ou PR desta branch para
  `main` no momento da consulta. As refs remotas de branch coincidiam com as
  locais. Revalidar antes de retomar.

## Bloqueios encontrados na avaliação inicial e correções locais

1. A descoberta do `pytest` foi limitada aos diretórios `apps` e `common` em
   `pytest.ini`, evitando importar `config/settings/test_publicacoes_dev.py`
   como teste e exigir `PGPASSFILE` fora da sandbox correspondente.
2. O backend PostgreSQL de teste passou a executar `TRUNCATE ... CASCADE`
   somente em bancos cujo nome começa por `test_`, cobrindo a FK entre
   `publicacoes.preferencia_exibicao_eflow` e `auth_user`. O backend de produção
   não foi alterado. O teste de permissão de CARGA_ORG_LOT foi alinhado à ação
   `encerrar_monitoramento` que já existia. A suíte completa passou com
   **1245 aprovados, 1 ignorado e 85,5% de cobertura** (gate: 80%); o novo
   teste unitário do backend de teste passou isoladamente.
3. A falha `W391` de `flake8 apps` em dois arquivos preexistentes na `main` foi
   corrigida sem mudar a lógica:
   `apps/accounts/management/commands/seed_functional_resources.py` e
   `apps/accounts/services/functional_resource_seed.py`.
4. Espaços finais de documentos e uma linha de `preflight.sh` foram corrigidos;
   `git diff --check main` agora passa para o candidato completo.
5. Os pins de runtime e desenvolvimento foram atualizados. A resolução de
   `requirements.txt` e `requirements-dev.txt` passou; `pip-audit` não encontrou
   vulnerabilidades conhecidas em 90 dependências resolvidas. A auditoria não
   substitui revisão de código nem monitoramento de novos avisos.
6. A geração OpenAPI passa com zero erros; permanecem nove avisos de nomes de
   enums. O pipeline atual não usa `--fail-on-warn`; tratar os avisos como
   melhoria posterior sem alterar discriminadores públicos nesta release.
7. A sandbox `infra/publicacoes-dev` integra o candidato como ferramenta DEV,
   não como infraestrutura institucional de HML/produção.

## Verificações aprovadas e gates remotos pendentes

- `manage.py check`: aprovado após atualização de dependências.
- `makemigrations --check --dry-run`: nenhuma mudança de modelo detectada.
- `migrate --check`: nenhuma migração pendente no banco consultado.
- `flake8 apps` e arquivos de teste afetados: aprovado.
- `pylint apps --fail-under=7.5`: aprovado após atualização de dependências.
- `scripts/check_shell.sh`: aprovado após correção de whitespace.
- `pytest` completo com cobertura: 1245 aprovados, 1 ignorado; 85,5%.
- `pip-audit` sobre a árvore resolvida: 90 dependências, zero alertas conhecidos.
- `git diff --check main`: aprovado.
- `radon cc apps -nc -s`: executado, apenas informativo.
- Nenhum `.env`, arquivo de chave privada ou banco local apareceu no conjunto
  de arquivos rastreados verificado. Isto não substitui Gitleaks/Trivy/CodeQL;
  os jobs do PR ainda não foram executados.

## Dívida arquitetural para depois da versão

- `apps/core/permissions.py`, `apps/core/middleware/websocket.py` e
  `apps/core/views.py` acessam modelos ou serviços de `accounts`. Revisar se
  interfaces profundas do sistema pertencem a `core` ou a contratos de IAM.
- `apps/pub_institucional/visoes.py` usa diretamente o serviço de autorização
  de `accounts`; `services/recursos_funcionais.py` usa seus modelos para o
  seed. Manter o contrato IAM explícito antes de qualquer separação física.
- `config/settings/base.py` contém integração E-Docs e tarefas Celery da app;
  `config/urls.py`, `config/asgi.py` e `config/routers.py` registram rotas,
  WebSocket e schema de Publicações. São pontos esperados de composição no
  monólito, mas exigirão extração de configuração na futura divisão.
- `common/services/cofre_segredos.py` e `common/services/ibge.py` são recursos
  compartilhados; preservar o contrato genérico e impedir regras editoriais
  específicas em `common`.
- Não foram encontrados imports diretos de produção de `pub_institucional`
  dentro de `acoes_pngi` ou `carga_org_lot`, nem o inverso. O acoplamento
  observado é predominantemente via IAM e configuração central.

Não refatorar esses pontos amplamente para fechar a release. Os bloqueios
locais foram sanados; executar os checks do PR antes do merge, tag e release.
