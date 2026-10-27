# Segredos CargaRH/PRODEST do `carga_org_lot`

**Data:** 2026-10-26

## Escopo

O `carga_org_lot` usa credencial OAuth2 `client_credentials` para integrar com
o CargaRH/PRODEST. `client_id` e `client_secret` ficam no OpenBao; endpoints,
escopos, timeouts e ambiente permanecem como configuração não secreta.

Não há fallback automático do OpenBao para `.env`. Indisponibilidade, AppRole
inválida ou segredo ausente interrompem a autenticação com mensagem redigida.

## Separação HML e PRD

`CARGARH_ENVIRONMENT` aceita apenas `HML` ou `PRD` e seleciona um perfil
completo. Cada perfil possui configuração e identidade OpenBao independentes:

| Perfil | Caminho KV v2 | AppRole DEV |
|---|---|---|
| HML | `carga-org-lot/dev/cargarh/hml` | `carga-org-lot-hml-dev` |
| PRD | `carga-org-lot/dev/cargarh/prd` | `carga-org-lot-prd-dev` |

A policy HML não lê PRD; a policy PRD não lê HML; nenhuma delas escreve. A
escrita é uma operação administrativa de provisionamento/rotação.

No ambiente local, o `SecretID` da AppRole não expira sozinho para evitar que
o desenvolvimento pare depois de 24 horas. Ele fica em arquivo com modo 0600 e
é preservado pelo bootstrap. Não existe rotação periódica em DEV; uma
substituição exige a opção explícita de recuperação documentada em
[`OPENBAO_DEV_GUIDE.md`](./OPENBAO_DEV_GUIDE.md). HML e PRD deverão definir
identidade e rotação no momento de sua implantação.

Variáveis não secretas:

```env
CARGARH_ENVIRONMENT=HML
CARGARH_CREDENTIALS_PROVIDER=openbao

CARGARH_HML_TOKEN_URL=
CARGARH_HML_API_BASE_URL=https://api.cargarh.hom.es.gov.br/
CARGARH_HML_CLIENT_SCOPE="api-cargarh-base api-cargarh-inicial"
CARGARH_HML_TARGET_ENVIRONMENT=

CARGARH_PRD_TOKEN_URL=
CARGARH_PRD_API_BASE_URL=https://api.cargarh.es.gov.br/
CARGARH_PRD_CLIENT_SCOPE="api-cargarh-base api-cargarh-inicial"
CARGARH_PRD_TARGET_ENVIRONMENT=
```

As URLs base da API não são segredos e, portanto, não são gravadas no
OpenBao. Alterações nesses endereços devem ser feitas nas variáveis do ambiente
em que o backend é executado. Reinicie os processos Django e Celery depois da
alteração para que os settings sejam recarregados.

Os nomes reconhecidos pelo backend usam o ambiente antes do atributo
(`CARGARH_HML_API_BASE_URL` e `CARGARH_PRD_API_BASE_URL`). As formas
`CARGARH_API_BASE_URL_HML` e `CARGARH_API_BASE_URL_PRD` não são lidas pelos
settings.

HML e PRD usam atualmente os mesmos escopos, mas continuam em variáveis
separadas. Essa duplicação é intencional: uma alteração futura da PRODEST em
apenas um ambiente não deve modificar o outro implicitamente.

Os caminhos dos arquivos de identidade possuem defaults seguros sob
`infra/publicacoes-dev/runtime/openbao/` e podem ser substituídos por:

- `CARGARH_HML_OPENBAO_ROLE_ID_FILE`;
- `CARGARH_HML_OPENBAO_SECRET_ID_FILE`;
- `CARGARH_HML_OPENBAO_SECRET_PATH`;
- equivalentes iniciados por `CARGARH_PRD_`.

## Situação atual de DEV

- a credencial que estava no `.env` foi migrada para o perfil PRD;
- `CARGARH_CLIENT_ID` e `CARGARH_CLIENT_SECRET` foram removidas do `.env`;
- a aplicação leu o segredo PRD pela AppRole e declarou configuração válida;
- a URL base da API HML foi configurada com o endereço confirmado;
- o perfil HML somente ficará operacional quando URL do token e credencial
  próprios forem fornecidos.

## Provisionar ou substituir explicitamente

Primeiro, garantir as AppRoles:

```bash
infra/publicacoes-dev/scripts/bootstrap-openbao.sh
```

Para entrada interativa, sem ecoar o `client_secret`:

```bash
.venv/bin/python \
  infra/publicacoes-dev/scripts/provision_cargarh_secret.py \
  --environment HML
```

Em automação, valores podem vir de arquivos temporários protegidos:

```bash
.venv/bin/python \
  infra/publicacoes-dev/scripts/provision_cargarh_secret.py \
  --environment PRD \
  --client-id-file /run/secrets/cargarh_client_id \
  --client-secret-file /run/secrets/cargarh_client_secret
```

O utilitário grava e lê de volta pela AppRole correspondente antes de declarar
sucesso. Ele não imprime os valores. A impressão digital do `client_secret`
participa somente da chave local de cache do token, portanto uma rotação força
uma nova autenticação sem inserir o segredo bruto no cache.

Rotacionar no OpenBao não substitui a rotação no provedor PRODEST. A sequência
entre emissão, ativação e revogação da credencial externa precisa seguir o
contrato confirmado com a PRODEST para evitar indisponibilidade.
