# GPP Plataform 2.0 — Snapshot de Arquitetura

**Atualizado**: 2026-03-25
**Branch**: `feature/acoes-pngi-policies`
**Suite de testes**: 346 passed, 1 skipped ✅

> **Fonte de verdade da arquitetura atual.**
> Documentação detalhada por tópico:
> - [`IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md) — Autenticação por sessão, middleware, roles RBAC, ABAC, `AccountsSession`
> - [`ACOES_PNGI.md`](./ACOES_PNGI.md) — App `acoes_pngi`: models, serializers, ViewSets, URLs, matriz de roles, testes
> - [`COMMON_INFRA.md`](./COMMON_INFRA.md) — `common/`, database router, settings, permissions, paginação

---

## Estrutura do Projeto

```
gpp_plataform2.0/
├── apps/
│   ├── accounts/          # IAM central — autenticação, usuários, roles, ABAC
│   ├── acoes_pngi/        # Domínio: Ações do Programa PNGI
│   ├── carga_org_lot/     # Domínio: Carga de organogramas e lotações
│   ├── core/              # Utilitários internos e permissões base
│   └── portal/            # Portal institucional
├── common/                # Infraestrutura compartilhada (mixins, models base, permissions)
├── config/
│   ├── settings/
│   │   ├── base.py        # Settings compartilhados
│   │   ├── development.py # Overrides de desenvolvimento
│   │   ├── production.py  # Overrides de produção
│   │   └── test.py        # Overrides para pytest
│   ├── routers.py         # Database router (SchemaRouter)
│   ├── urls.py            # URL router principal
│   ├── wsgi.py
│   └── asgi.py
├── docs/                  # Documentação de arquitetura (este diretório)
├── scripts/               # Scripts utilitários
├── conftest.py            # Fixtures globais do pytest
├── pytest.ini             # Configuração do pytest
├── setup.cfg              # Configuração de ferramentas (flake8, isort, etc.)
├── requirements.txt
└── requirements-dev.txt
```

---

## Tecnologias e Dependências

| Componente | Tecnologia |
|---|---|
| Framework Web | Django 4.x + Django REST Framework |
| Banco de Dados | PostgreSQL (schemas qualificados via `db_table`) |
| Autenticação | Django Session (cookie `sessionid` httpOnly) |
| Autorização | RBAC via `Role`/`UserRole` + ABAC via `Attribute` |
| Testes | `pytest-django` + `APIClient` DRF |
| URLs nested | `rest_framework_nested` |
| Dev tools | `django-debug-toolbar`, `pytest-cov` |

---

## Apps e Responsabilidades

| App | `app_label` | Responsabilidade | Schema PostgreSQL |
|---|---|---|---|
| `accounts` | `accounts` | IAM: autenticação, users, roles, sessões, ABAC | `public` |
| `acoes_pngi` | `acoes_pngi` | Ações do programa PNGI | `acoes_pngi` |
| `carga_org_lot` | `carga_org_lot` | Carga de organogramas e lotações | `carga_org_lot` |
| `portal` | `portal` | Portal institucional | `public` |
| `core` | `core` | Permissões base (`CanCreateUser`, `CanEditUser`), utilitários | `public` |
| `common` | `common` | Infra compartilhada — sem models de negócio | — |

> **Nota sobre schemas PostgreSQL**: cada app define `db_table` com schema qualificado
> (ex: `'"acoes_pngi"."tblacoes"'`). Todas as apps usam o banco `default` via `SchemaRouter`.
> A separação por schema prepara para eventual separação de bancos sem alterar models.

---

## Rotas Globais (`config/urls.py`)

```
GET/POST  /admin/                         → Django Admin
          /api/accounts/                  → Users, Roles, Aplicações, Auth
POST      /api/accounts/auth/login/       → Login por sessão (cookie sessionid)
POST      /api/accounts/auth/logout/      → Logout + revogação de sessão
          /api/portal/                    → Portal institucional
          /api/acoes-pngi/                → Ações PNGI
          /api/carga-org-lot/             → Carga org/lot
GET       /api/health/                    → Health check
GET       /__debug__/                     → Debug Toolbar (apenas DEBUG=True)
```

> ⚠️ Paths JWT (`api/auth/token/`, `token/refresh/`, `token/revoke/`) foram **removidos** na FASE-0.
> Autenticação é **exclusivamente via sessão Django**. Não há Bearer token.

---

## Modelo de Controle de Acesso

Dois mecanismos coexistem, aplicados conforme o recurso:

### RBAC — Role-Based Access Control

Usado em `acoes_pngi` e `accounts`. Roles são registradas no banco (`Role`, `UserRole`) e
carregadas com `lru_cache`. A permissão `HasRolePermission` (em `common/permissions.py`)
valida se o usuário tem ao menos uma role ativa para a aplicação da requisição.
Cada ViewSet implementa sua própria matriz de roles via `_load_role_matrix()` + `_check_roles()`.

### Escopo de Tenant (`SecureQuerysetMixin`)

Usado em `carga_org_lot`. Filtra registros pelo campo `orgao` do `UserProfile` autenticado.
**Não aplicado** em `acoes_pngi` — ações PNGI são independentes de órgão (iniciativas do programa).

### Portal Admin bypass

Usuários com `codigoperfil="PORTAL_ADMIN"` têm `request.is_portal_admin = True` injetado
pelo `AppContextMiddleware`, que bypassa todas as verificações de role específicas de app.

Detalhes completos em [`IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md).

---

## Padrão de Auditoria (`AuditableModel`)

Todos os models de negócio herdam `AuditableModel` de `common/models.py`.
O padrão usa `IntegerField` snapshot (sem `ForeignKey` para `auth_user`), o que:

- Elimina dependências cross-schema entre apps de negócio e `auth`
- Garante histórico imutável mesmo após deleção do usuário
- Permite `TRUNCATE auth_user` no teardown do pytest sem violação de constraints

Campos: `created_by_id`, `created_by_name`, `updated_by_id`, `updated_by_name`, `created_at`, `updated_at`.
Preenchimento automático via `AuditableMixin` em `perform_create`/`perform_update`.

Detalhes em [`COMMON_INFRA.md`](./COMMON_INFRA.md).

---

## Padrão de Testes

- `pytest-django` com `@pytest.mark.django_db(transaction=True)` — **sempre** `transaction=True`
- `APIClient` do DRF — **nunca** `force_authenticate` nem `force_login`
- Autenticação sempre pelo fluxo real: `POST /api/accounts/auth/login/` → cookie `sessionid`
- Fixtures em `conftest.py` local de cada app + `conftest.py` raiz para fixtures globais
- Testes de policy separados em `tests/policies/` por role
- Referência de qualidade: `apps/accounts/tests/` — suite mais completa do projeto

---

## Backlog Priorizado

| # | Escopo | Arquivo(s) | Status |
|---|--------|-----------|--------|
| 1 | Campo `orgao` em `carga_org_lot.TokenEnvioCarga` | `models.py` + migrations | 🟡 identificado |
| 2 | Campo `telefone` em `accounts.UserProfile` | `accounts/models.py` | 🟡 identificado |
| 3 | Testes nested resources `acoes_pngi` (prazos, destaques, anotações) | `tests/` | 🟡 identificado |
| 4 | Testes de policy para `carga_org_lot` | `tests/policies/` | 🔴 pendente |
| 5 | Implementação completa de `portal` | `apps/portal/` | 🔴 pendente |
| 6 | Relacionamento `Acoes` ↔ `UsuarioResponsavel` nos testes | `tests/` | 🟡 identificado |
