# Infraestrutura Compartilhada (`common/` + `config/`)

**Última revisão**: 2026-03-25

> Para visão geral do projeto ver [`ARCH_SNAPSHOT.md`](./ARCH_SNAPSHOT.md).

---

## Visão Geral

A pasta `common/` contém toda a infraestrutura compartilhada entre apps:
nenhum model de negócio, apenas base classes, mixins, permissões, serializers e utilitários.
A pasta `config/` contém settings, database router e URL router global.

---

## `common/models.py` — `AuditableModel`

Base abstrata obrigatória para todos os models de negócio.

### Campos

| Campo | Tipo | Descrição |
|---|---|---|
| `created_by_id` | `IntegerField` nullable | ID lógico do criador (sem FK para `auth_user`) |
| `created_by_name` | `CharField(200)` | Snapshot do username no momento da criação |
| `updated_by_id` | `IntegerField` nullable | ID lógico do último editor |
| `updated_by_name` | `CharField(200)` | Snapshot do username na última alteração |
| `created_at` | `DateTimeField` auto_now_add | |
| `updated_at` | `DateTimeField` auto_now | |

Todos os campos são `editable=False` — preenchidos exclusivamente pelo `AuditableMixin`.

### Por que `IntegerField` em vez de `ForeignKey`?

Três razões arquiteturais:

1. **Independência cross-schema**: apps de negócio (`acoes_pngi`, `carga_org_lot`) ficam
   em schemas PostgreSQL separados. FK para `auth_user` (schema `public`) criaria
   dependência explícita entre schemas — bloqueando eventual separação de bancos.

2. **Histórico imutável**: mesmo após deleção ou renomeação do usuário, o snapshot
   `created_by_name` permanece intacto no registro.

3. **Teardown limpo no pytest**: `TRUNCATE auth_user CASCADE` no início de cada teste
   não é bloqueado por constraint de FK em nenhuma tabela de negócio.

---

## `common/mixins.py` — Mixins de ViewSet

### `AuditableMixin`

Preenche automaticamente os campos de auditoria em `perform_create` e `perform_update`.

```python
# perform_create — preenche created_by_* e updated_by_*
serializer.save(
    created_by_id=user.pk,
    created_by_name=nome_legivel,
    updated_by_id=user.pk,
    updated_by_name=nome_legivel,
)

# perform_update — atualiza apenas updated_by_*
serializer.save(
    updated_by_id=user.pk,
    updated_by_name=nome_legivel,
)
```

`_resolve_user_name(user)`: retorna `get_full_name()` com fallback para `username`.

> **Regra**: nunca sobrescrever `perform_create`/`perform_update` em ViewSets que herdam
> `AuditableMixin` sem chamar `super()`. Os campos de auditoria devem ser preenchidos
> pelo mixin, nunca pelo próprio ViewSet ou pelo serializer.

### `SecureQuerysetMixin`

Proteção contra IDOR (Insecure Direct Object Reference) via filtro por escopo.

```python
class MinhaViewSet(SecureQuerysetMixin, viewsets.ModelViewSet):
    scope_field = "orgao"    # campo no model a filtrar
    scope_source = "orgao"   # atributo em request.user.profile
```

Comportamento:
- Lê `scope_value = request.user.profile.<scope_source>`
- Filtra: `queryset.filter(orgao=scope_value)`
- Se `scope_value` for `None` (perfil sem orgão): retorna `queryset.none()` (**fail-closed**)
- Loga `IDOR_SCOPE_MISSING` no logger `gpp.security` quando scope é inválido

Usado em: `carga_org_lot`.
**Não usado** em: `acoes_pngi` (ações são independentes de órgão).

---

## `common/permissions.py` — Permissões DRF

| Classe | Descrição |
|---|---|
| `HasRolePermission` | Valida se o usuário tem ao menos 1 role ativa para a app. Usa `request.user_roles` injetado pelo middleware. |
| `IsPortalAdmin` | Acesso restrito a usuários com `request.is_portal_admin = True`. |
| `CanCreateUser` | Re-export de `apps/core/permissions.py`. Lê `classificacao_usuario.pode_criar_usuario`. |
| `CanEditUser` | Re-export de `apps/core/permissions.py`. Lê `classificacao_usuario.pode_editar_usuario`. |

> **Arquitetura de 2 camadas**: `HasRolePermission` valida a **presença** de role (gating).
> A verificação do **nível** (READ/WRITE/DELETE) é feita internamente por cada ViewSet
> via `_check_roles()` — o que permite matrizes diferentes por recurso dentro da mesma app.

---

## `common/serializers.py` — `AuditableModelSerializer`

Serializer base para models que herdam `AuditableModel`.
Declara automaticamente os campos de auditoria como `read_only`.

```python
from common.serializers import AuditableModelSerializer

class AcoesSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = Acoes
        fields = AuditableModelSerializer.Meta.fields + [
            "idacao",
            "strapelido",
            # ...
        ]
```

Campos read-only herdados: `created_by_id`, `created_by_name`, `updated_by_id`,
`updated_by_name`, `created_at`, `updated_at`.

---

## `common/pagination.py`

Classe de paginação padrão do projeto. Configurada como `DEFAULT_PAGINATION_CLASS`
nos settings. Endpoints de listagem retornam resposta paginada por padrão.

---

## `common/exceptions.py`

Handler de exceções customizado do DRF. Padroniza o formato de erros na API.

---

## `common/urls.py` — Health Check

Montado em `/api/health/`. Endpoint GET que retorna status `200 OK` para monitoramento.

---

## `config/routers.py` — `SchemaRouter`

Database router que mapeia cada `app_label` para um banco de dados.
Atualmente todas as apps usam o banco `default` (PostgreSQL único).
Os schemas PostgreSQL são controlados pelos próprios models via `db_table`.

```python
APP_DB_MAP = {
    "accounts":     "default",
    "acoes_pngi":   "default",
    "carga_org_lot": "default",
    "portal":       "default",
    "common":       "default",
}
```

Métodos:
- `db_for_read` / `db_for_write`: roteiam pelo `app_label`
- `allow_relation`: permite relações apenas entre objetos do mesmo banco
- `allow_migrate`: cada app migra apenas para seu banco correspondente

> **Preparação futura**: os comentários no router já indicam como separar
> `acoes_pngi` e `carga_org_lot` para bancos próprios sem alterar models.

---

## `config/settings/` — Settings por Ambiente

| Arquivo | Ativado por | Descrição |
|---|---|---|
| `base.py` | (base compartilhada) | INSTALLED_APPS, MIDDLEWARE, DRF, banco, logging |
| `development.py` | `DJANGO_SETTINGS_MODULE=config.settings.development` | DEBUG=True, debug_toolbar, relaxa CORS |
| `production.py` | `DJANGO_SETTINGS_MODULE=config.settings.production` | DEBUG=False, ALLOWED_HOSTS, HTTPS |
| `test.py` | `pytest.ini` (`DJANGO_SETTINGS_MODULE=config.settings.test`) | Banco de teste, PASSWORD_HASHERS rápido |

### Configurações Relevantes em `base.py`

- `INSTALLED_APPS`: inclui `apps.accounts`, `apps.acoes_pngi`, `apps.carga_org_lot`,
  `apps.portal`, `apps.core`, `common`, `rest_framework`, `rest_framework_nested`
- `MIDDLEWARE`: inclui `AppContextMiddleware` para injeção do contexto IAM
- `DATABASE_ROUTERS`: `["config.routers.SchemaRouter"]`
- `REST_FRAMEWORK`:
  - `DEFAULT_AUTHENTICATION_CLASSES`: `SessionAuthentication`
  - `DEFAULT_PERMISSION_CLASSES`: `[IsAuthenticated]`
  - `DEFAULT_PAGINATION_CLASS`: `common.pagination.<ClassePadrao>`
  - `EXCEPTION_HANDLER`: `common.exceptions.<HandlerCustomizado>`
- `SESSION_COOKIE_HTTPONLY`: `True`
- `SESSION_COOKIE_SAMESITE`: `"Lax"`

### Configurações de Teste (`test.py`)

- `PASSWORD_HASHERS`: `["django.contrib.auth.hashers.MD5PasswordHasher"]` (mais rápido)
- `DATABASES`: PostgreSQL de teste (schema separado ou SQLite em memória conforme config local)
- `DEBUG`: `False`

---

## `conftest.py` (Raiz) — Fixtures Globais

Fixtures disponíveis para toda a suite:

| Fixture | Descrição |
|---|---|
| `api_client` | `APIClient()` sem autenticação |
| `django_user_model` | Modelo de usuário do Django (padrão pytest-django) |
| Tabelas de referência | `StatusUsuario`, `TipoUsuario`, `ClassificacaoUsuario` com PKs 1 pré-criados |

> As tabelas de referência com PK=1 são necessárias porque `UserProfile` tem
> `default=1` em `status_usuario`, `tipo_usuario` e `classificacao_usuario`.
> Se não existirem no banco de teste, a criação de qualquer `UserProfile` falha.

---

## `pytest.ini` — Configuração do Pytest

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.test
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = --reuse-db -p no:warnings
```

`--reuse-db`: reutiliza o banco de teste entre execuções para economizar tempo.
Usar `--create-db` para recriar do zero (necessário após novas migrations).
