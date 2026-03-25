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

4. Resposta: Set-Cookie: sessionid=<valor>; HttpOnly; SameSite=Lax

5. Requisições subsequentes: cookie sessionid no header
   → AppContextMiddleware valida a sessão e injeta no request:
        request.user          → auth.User autenticado
        request.user_profile  → accounts.UserProfile
        request.user_roles    → list[UserRole] da app_context
        request.is_portal_admin → bool

6. POST /api/accounts/auth/logout/
   → Marca AccountsSession.revoked = True
   → Limpa cookie sessionid
```

> ⚠️ `app_context` no login é o `codigointerno` da `Aplicacao` (ex: `"ACOES_PNGI"`).
> O middleware usa esse valor para carregar as roles corretas do usuário na sessão.

---

## Middleware: `AppContextMiddleware`

Localizado em `apps/accounts/middleware.py` (ou `common/middleware.py` — verificar).

Responsabilidades:
- Lê o cookie `sessionid` e valida contra `AccountsSession` (não revogada, não expirada)
- Injeta `request.user`, `request.user_profile`, `request.user_roles`
- Define `request.is_portal_admin = True` se o usuário tiver role `PORTAL_ADMIN`
- Em caso de sessão inválida: `request.user = AnonymousUser`

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
| `jti` | `CharField(255)` unique indexed | JWT-like token ID |
| `created_at` | `DateTimeField` auto | |
| `expires_at` | `DateTimeField` | Obrigatório |
| `revoked` | `BooleanField` default=False indexed | |
| `revoked_at` | `DateTimeField` nullable | |
| `ip_address` | `GenericIPAddressField` nullable | |
| `user_agent` | `TextField` blank | |

Índices compostos: `(jti, revoked)` e `(user, revoked)` para busca rápida.

A sessão é **stateless no sentido de que não carrega roles/permissões** — essas são
carregadas dinamicamente pelo middleware em cada requisição.

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
> (vigiências são domínio exclusivo de `GESTOR_PNGI` e `COORDENADOR_PNGI`).

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
