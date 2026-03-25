# IAM — Autenticação e Controle de Acesso

**App**: `apps/accounts`
**Schema PostgreSQL**: `public`
**Última revisão**: 2026-03-25

> Para visão geral do projeto ver [`ARCH_SNAPSHOT.md`](./ARCH_SNAPSHOT.md).

---

## Fluxo de Autenticação

A autenticação é **exclusivamente por sessão Django**. Não existe JWT, Bearer token
ou qualquer outro mecanismo. O ciclo completo:

```
1. POST /api/accounts/auth/login/
     body: { username, password, app_context }

2. Django autentica via auth.authenticate()
   → Valida credenciais contra auth_user

3. Cria AccountsSession (jti único, expires_at, ip_address, user_agent)
   → Grava sessão no banco (accounts_session)

4. Resposta: Set-Cookie: gpp_session=<valor>; HttpOnly; SameSite=Lax
   ⚠️ O nome do cookie é gpp_session (SESSION_COOKIE_NAME personalizado),
      NÃO o padrão Django sessionid. O frontend e scripts de teste
      devem usar explicitamente este nome.

5. Requisições subsequentes: cookie gpp_session no header
   → Pipeline de middlewares injeta no request (ver seção Middlewares abaixo):
        request.user             → auth.User autenticado
        request.application      → objeto Aplicacao resolvido por URL/header/domínio
        request.user_roles       → list[UserRole] para a aplicação atual
        request.is_portal_admin  → bool
        request.app_context      → codigointerno str (Fase-0, via AppContextMiddleware)

6. POST /api/accounts/auth/logout/
   → Marca AccountsSession.revoked = True
   → Limpa cookie gpp_session
```

> `app_context` no login é o `codigointerno` da `Aplicacao` (ex: `"ACOES_PNGI"`).
> O middleware usa esse valor para carregar as roles corretas do usuário na sessão.

---

## Pipeline de Middlewares (ordem de execução)

Os middlewares de autenticação e autorização executam nesta ordem em `MIDDLEWARE` de `base.py`:

```
1. SessionMiddleware            (Django) — desserializa sessão do cookie gpp_session
2. AuthenticationMiddleware     (Django) — popula request.user via sessão
3. AppContextMiddleware         (accounts) — valida AccountsSession; injeta app_context
4. ApplicationContextMiddleware (core) — resolve request.application por URL/header/domínio
5. RoleContextMiddleware        (core) — carrega request.user_roles para a app; seta is_portal_admin
6. AuthorizationMiddleware      (core) — gating final: 401/403 se não autenticado/sem role
```

### `AppContextMiddleware` (`apps/accounts/middleware.py`)

- Valida o cookie `gpp_session` contra `AccountsSession` (não revogada, não expirada)
- Injeta `request.app_context` (codigointerno string da aplicação do login)
- Em sessão inválida/revogada: `request.user` é mantido como `AnonymousUser`

### `ApplicationContextMiddleware` (`apps/core/middleware/application_context.py`)

Resolve `request.application` (objeto `Aplicacao`) em 4 etapas com prioridade decrescente:

1. Header `X-Application-Code` (maior prioridade)
2. Prefixo da URL — `/api/acoes-pngi/` → `ACOES_PNGI`
3. Domínio da request via `APPLICATION_DOMAIN_MAP` em settings
4. Fallback: `portal`

### `RoleContextMiddleware` (`apps/core/middleware/role_context.py`)

- Carrega `UserRole`s do banco para `(user, application)`, filtradas pela app atual
- Sempre inclui roles `PORTAL_ADMIN` independente da app
- Usa cache Memcached com TTL=300s e versioning para invalidação sem wildcards
- `user.is_superuser=True` → `is_portal_admin=True` sem precisar de `UserRole` no banco
- Loga `ROLE_SWITCH` quando o conjunto de roles muda entre requests

### `AuthorizationMiddleware` (`apps/core/middleware/authorization.py`)

Gating final. Lógica por ordem de prioridade:

1. Path em `AUTHORIZATION_EXEMPT_PATHS` → passa sem verificar
2. `is_portal_admin=True` → passa sem verificar
3. Usuário anônimo → `401 not_authenticated`
4. Sem role para a app atual → `403 permission_denied` + log `403_FORBIDDEN reason=no_role`
5. Path em `AUTHORIZATION_REQUIRED_ROLES` e sem a role requerida → `403` + log `403_FORBIDDEN_ROLE`

> **Implementação crítica**: `AUTHORIZATION_EXEMPT_PATHS` e `AUTHORIZATION_REQUIRED_ROLES`
> são lidos de `django.conf.settings` **a cada request** (não no `__init__` do middleware).
> Isso garante que `@override_settings` nos testes funcione sem workarounds.

---

## Dual-Session: `django_session` vs `accounts_session`

O projeto mantém **duas tabelas de sessão** com responsabilidades distintas:

| Tabela | Gerenciada por | Propósito |
|---|---|---|
| `django_session` | `SessionMiddleware` + `SESSION_ENGINE=db` | Desserializa o cookie `gpp_session` e popula `request.user` via `AuthenticationMiddleware` |
| `accounts_session` | `AppContextMiddleware` (custom) | Controle de revogação explícita por `jti`; auditoria de IP, user_agent e expiração |

**Fluxo**: `SessionMiddleware` lê `django_session` para resolver `request.user`. Em seguida,
`AppContextMiddleware` valida `accounts_session` — se a sessão estiver revogada ou expirada
no `accounts_session`, a request é tratada como anônima mesmo que `django_session` ainda
exista. Ou seja, a **fonte de verdade para revogação é `accounts_session`**.

Na prática as duas tabelas são criadas/expiradas juntas pelo fluxo de login/logout —
**não sincronize manualmente**. Utilize sempre os endpoints `/login/` e `/logout/`.

---

## Configurações de Session/Cookie (`config/settings/`)

| Setting | Valor (`base.py`) | Dev | Prod |
|---|---|---|---|
| `SESSION_ENGINE` | `django.contrib.sessions.backends.db` | — | — |
| `SESSION_COOKIE_NAME` | **`gpp_session`** | — | — |
| `SESSION_COOKIE_HTTPONLY` | `True` | — | — |
| `SESSION_COOKIE_SAMESITE` | `"Lax"` | — | — |
| `SESSION_COOKIE_AGE` | `3600` (1 hora) | — | — |
| `SESSION_SAVE_EVERY_REQUEST` | `True` | — | — |
| `SESSION_COOKIE_SECURE` | — | `False` (HTTP) | `True` (HTTPS) |
| `CSRF_COOKIE_HTTPONLY` | `False` (SPA precisa ler) | — | — |
| `CSRF_COOKIE_SAMESITE` | `"Lax"` | — | — |
| `CSRF_COOKIE_SECURE` | — | `False` | `True` |
| `CSRF_TRUSTED_ORIGINS` | default `["http://localhost:3000"]` | expandido | **obrigatório via .env** |
| `CORS_ALLOW_CREDENTIALS` | `True` | — | — |

> **`CSRF_TRUSTED_ORIGINS` em produção**: se não definido no `.env`, o servidor levanta
> `ImproperlyConfigured` na inicialização. Não existe fallback — o default de dev
> (`http://localhost:3000`) nunca vaza para produção.

---

## Models do IAM

### `Aplicacao` (tblaplicacao)

Registra cada aplicação da plataforma. É a ancora dos Roles e UserRoles.

| Campo | Tipo | Descrição |
|---|---|---|
| `idaplicacao` | `AutoField` PK | |
| `codigointerno` | `CharField(50)` unique | Identificador lógico (ex: `ACOES_PNGI`) |
| `nomeaplicacao` | `CharField(200)` | |
| `base_url` | `URLField` nullable | |
| `isshowinportal` | `BooleanField` default=True | Visibilidade no portal |

### `UserProfile` (tblusuario)

Extensão 1:1 de `auth.User`. É o perfil de negócio do usuário.

| Campo | Tipo | Descrição |
|---|---|---|
| `user` | `OneToOneField(auth.User)` PK | |
| `name` | `CharField(200)` | Nome completo |
| `orgao` | `CharField(100)` nullable | **Escopo IDOR** — usado por `SecureQuerysetMixin` |
| `status_usuario` | FK `StatusUsuario` | default=1 |
| `tipo_usuario` | FK `TipoUsuario` | default=1 |
| `classificacao_usuario` | FK `ClassificacaoUsuario` | default=1 |
| `idusuariocriacao` | FK `auth.User` nullable | Auditoria |
| `idusuarioalteracao` | FK `auth.User` nullable | Auditoria |
| `datacriacao` | `DateTimeField` auto | |
| `data_alteracao` | `DateTimeField` auto | |

> `orgao` é o campo crítico de scope para proteção IDOR em `carga_org_lot`.
> **Não usado** em `acoes_pngi` (ações são independentes de órgão).

### `Role` (accounts_role)

Define um perfil de acesso por aplicação.

| Campo | Tipo | Descrição |
|---|---|---|
| `idpk` | `AutoField` PK | |
| `aplicacao` | FK `Aplicacao` nullable | |
| `codigoperfil` | `CharField(100)` | **Identificador lógico** (ex: `GESTOR_PNGI`) |
| `nomeperfil` | `CharField(100)` | |
| `group` | FK `auth.Group` nullable | Criado automaticamente via signal |

**Constraint**: `UniqueConstraint(aplicacao, codigoperfil)`

Role especial: `codigoperfil="PORTAL_ADMIN"` — acesso root na plataforma, não restrita a uma única app.

### `UserRole` (accounts_userrole)

Atribui uma Role a um usuário em uma aplicação específica.

| Campo | Tipo | Descrição |
|---|---|---|
| `idpk` | `AutoField` PK | |
| `user` | FK `auth.User` CASCADE | |
| `aplicacao` | FK `Aplicacao` nullable CASCADE | |
| `role` | FK `Role` CASCADE | |

**Constraint**: `UniqueConstraint(user, aplicacao)` — 1 role por usuário/app.

### `AccountsSession` (accounts_session)

Registro de sessões ativas com suporte a revogação explícita.

| Campo | Tipo | Descrição |
|---|---|---|
| `idpk` | `AutoField` PK | |
| `user` | FK `auth.User` CASCADE | |
| `jti` | `CharField(255)` unique indexed | Identificador único da sessão |
| `created_at` | `DateTimeField` auto | |
| `expires_at` | `DateTimeField` | Obrigatório |
| `revoked` | `BooleanField` default=False indexed | |
| `revoked_at` | `DateTimeField` nullable | |
| `ip_address` | `GenericIPAddressField` nullable | |
| `user_agent` | `TextField` blank | |

Índices compostos: `(jti, revoked)` e `(user, revoked)` para busca rápida.
Fonte de verdade para revogação — ver seção Dual-Session acima.

### `Attribute` (accounts_attribute) — ABAC

Par chave-valor por usuário/aplicação para controle baseado em atributos.

| Campo | Tipo | Descrição |
|---|---|---|
| `idpk` | `AutoField` PK | |
| `user` | FK `auth.User` CASCADE | |
| `aplicacao` | FK `Aplicacao` SET_NULL nullable | |
| `key` | `CharField(100)` | |
| `value` | `CharField(255)` | |

**Constraint**: `UniqueConstraint(user, aplicacao, key)`

### `ClassificacaoUsuario` (tblclassificacaousuario)

Tabela de referência que define capacidades de gerenciamento de usuários.

| Campo | Tipo | Descrição |
|---|---|---|
| `idclassificacaousuario` | `SmallIntegerField` PK | |
| `strdescricao` | `CharField(100)` | |
| `pode_criar_usuario` | `BooleanField` default=False | Lido por `CanCreateUser` |
| `pode_editar_usuario` | `BooleanField` default=False | Lido por `CanEditUser` |

Esses campos são lidos diretamente pelas permissions `CanCreateUser` e `CanEditUser`
definidas em `apps/core/permissions.py` e re-exportadas por `common/permissions.py`.

### Tabelas Auxiliares

| Model | Tabela | Descrição |
|---|---|---|
| `StatusUsuario` | `tblstatususuario` | Status do usuário (ativo, inativo, etc.) |
| `TipoUsuario` | `tbltipousuario` | Tipo do usuário |

---

## Matriz de Permissões por Aplicação

### `accounts` — Gestão de Usuários

| Operação | Permissão DRF | Condição |
|---|---|---|
| Criar usuário | `CanCreateUser` | `classificacao_usuario.pode_criar_usuario = True` |
| Editar usuário | `CanEditUser` | `classificacao_usuario.pode_editar_usuario = True` |
| Listar/ver usuários | `IsAuthenticated` | Autenticado + role ativa |
| Gestão de roles | `IsPortalAdmin` | `is_portal_admin = True` |

### `acoes_pngi` — Roles e Permissões

Ver detalhes completos em [`ACOES_PNGI.md`](./ACOES_PNGI.md).

| Role (`codigoperfil`) | READ | WRITE | DELETE |
|---|---|---|---|
| `GESTOR_PNGI` | ✅ | ✅ | ✅ |
| `COORDENADOR_PNGI` | ✅ | ✅ | ❌ |
| `OPERADOR_ACAO` | ✅ | ✅ | ❌ |
| `CONSULTOR_PNGI` | ✅ | ❌ | ❌ |
| (sem role) | ❌ | ❌ | ❌ |

> `OPERADOR_ACAO` pode escrever `Acoes` mas **não pode escrever `VigenciaPNGI`**
> (vigências são domínio exclusivo de `GESTOR_PNGI` e `COORDENADOR_PNGI`).

---

## Permissões DRF Disponíveis

Definidas em `apps/core/permissions.py`, re-exportadas por `common/permissions.py`:

| Classe | Localização | Descrição |
|---|---|---|
| `HasRolePermission` | `common/permissions.py` | Valida se usuário tem ao menos 1 role ativa para a app |
| `IsPortalAdmin` | `common/permissions.py` | Acesso exclusivo a `PORTAL_ADMIN` |
| `CanCreateUser` | `apps/core/permissions.py` | `classificacao_usuario.pode_criar_usuario` |
| `CanEditUser` | `apps/core/permissions.py` | `classificacao_usuario.pode_editar_usuario` |

`HasRolePermission` só valida a **presença** de role — a verificação do **nível** (READ/WRITE/DELETE)
é responsabilidade de cada ViewSet via `_check_roles()`.

---

## Dependências de Pacotes — JWT

`djangorestframework-simplejwt` **não está** no `requirements.txt`. O pacote foi
completamente removido na FASE-0. Não reintroduzir.

A única dependência de autenticação é `djangorestframework` (SessionAuthentication
nativo). Nenhuma configuração `SIMPLE_JWT` deve existir em nenhum settings file.
