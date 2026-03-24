# GPP Plataform 2.0 — Snapshot de Arquitetura

**Data**: 2026-03-24
**Branch**: feature/acoes-pngi-policies
**Suite**: 346 passed, 1 skipped ✅

> Este documento é a fonte de verdade da arquitetura atual.
> Documentos detalhados por tópico:
> - [`IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md) — Autenticação, sessão, roles, ABAC
> - [`ACOES_PNGI.md`](./ACOES_PNGI.md) — App acoes_pngi: models, views, serializers, URLs, testes, policies
> - [`COMMON_INFRA.md`](./COMMON_INFRA.md) — common, database router, configurações, URLs globais

---

## Estrutura do Projeto

```
gpp_plataform2.0/
├── apps/
│   ├── accounts/          # IAM central — autenticação, usuários, roles, ABAC
│   ├── acoes_pngi/        # Domínio: Ações do Programa PNGI
│   ├── carga_org_lot/     # Domínio: Carga de organogramas e lotações
│   ├── core/              # App base (utilitários internos)
│   └── portal/            # Portal institucional
├── common/                # Infraestrutura compartilhada entre apps
├── config/                # Django settings, URL router, DB router
├── docs/                  # Documentação de arquitetura (este diretório)
├── scripts/               # Scripts utilitários
├── conftest.py            # Fixtures globais do pytest
├── pytest.ini             # Configuração do pytest
├── requirements.txt
└── requirements-dev.txt
```

---

## Tecnologias e Dependências Principais

| Componente | Tecnologia |
|---|---|
| Framework Web | Django 4.x + Django REST Framework |
| Banco de Dados | PostgreSQL (schemas qualificados via `db_table`) |
| Autenticação | Django Session (cookie `sessionid` httpOnly) |
| Autorização | RBAC via `Role`/`UserRole` + ABAC via `Attribute` |
| Testes | pytest-django + APIClient DRF |
| URLs nested | `rest_framework_nested` |
| Dev tools | debug_toolbar, pytest-cov |

---

## Apps e Responsabilidades

| App | `app_label` | Responsabilidade | Schema PostgreSQL |
|---|---|---|---|
| `accounts` | `accounts` | IAM: auth, users, roles, sessões | `public` (tabelas Django padrão + tblaplicacao, etc.) |
| `acoes_pngi` | `acoes_pngi` | Ações do programa PNGI | `acoes_pngi` |
| `carga_org_lot` | `carga_org_lot` | Carga de org/lotação | `carga_org_lot` |
| `portal` | `portal` | Portal institucional | `public` |
| `core` | `core` | Utilitários base | `public` |
| `common` | `common` | Infra compartilhada (sem models de negócio) | — |

---

## Rotas Globais (`config/urls.py`)

```
GET/POST  /admin/                    → Django Admin
POST      /api/accounts/auth/login/  → Login por sessão
POST      /api/accounts/auth/logout/ → Logout + revogação de sessão
          /api/accounts/             → Users, Roles, Aplicações, etc.
          /api/portal/               → Portal
          /api/acoes-pngi/           → Ações PNGI
          /api/carga-org-lot/        → Carga org/lot
GET       /api/health/               → Health check
GET       /__debug__/                → Debug Toolbar (apenas DEBUG=True)
```

> ⚠️ Paths JWT (`api/auth/token/`, `token/refresh/`, `token/revoke/`) foram **removidos** na FASE-0.
> A autenticação é exclusivamente via sessão Django.

---

## Modelo de Controle de Acesso

Dois mecanismos coexistem, aplicados conforme o recurso:

### RBAC — Role-Based Access Control
Usado em `acoes_pngi` e `accounts`. Roles são registradas no banco (`Role`, `UserRole`) e carregadas com `lru_cache`. A permissão `HasRolePermission` valida se o usuário tem a role necessária para a operação.

### Escopo de Tenant (`SecureQuerysetMixin`)
Usado em `carga_org_lot`. Filtra registros pelo `orgao` do `UserProfile` autenticado. **Não aplicado** em `acoes_pngi` — ações PNGI são independentes de órgão.

Ver detalhes completos em [`IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md).

---

## Padrão de Auditoria (`AuditableModel`)

Todos os models de negócio herdam `AuditableModel` (de `common/models.py`). O padrão usa `IntegerField` snapshot ao invés de `ForeignKey` para `auth_user`, eliminando dependências cross-schema e facilitando o teardown do pytest.

Ver detalhes em [`COMMON_INFRA.md`](./COMMON_INFRA.md).

---

## Padrão de Testes

- `pytest-django` + `@pytest.mark.django_db(transaction=True)`
- `APIClient` do DRF — **sem** `force_authenticate`
- Sempre autentica pelo fluxo real: `POST /api/accounts/auth/login/` → cookie sessionid
- Fixtures em `conftest.py` local de cada app
- Testes de policy separados em `tests/policies/` por role

Referência de qualidade: `apps/accounts/tests/` — suite mais completa do projeto.

---

## Backlog Priorizado

| # | Escopo | Arquivo(s) | Status |
|---|--------|-----------|--------|
| 1 | Campo `orgao` em `carga_org_lot.TokenEnvioCarga` | models.py + migrations | 🟡 identificado |
| 2 | Campo `telefone` em `accounts.UserProfile` | accounts/models.py | 🟡 identificado |
| 3 | Testes nested resources `acoes_pngi` (prazos, destaques, anotações) | tests/ | 🟡 identificado |
| 4 | Testes de policy para `carga_org_lot` | tests/policies/ | 🔴 pendente |
| 5 | Implementação completa de `portal` | apps/portal/ | 🔴 pendente |
