# GPP Plataform 2.0 — Contrato de API: Módulo Accounts

> **Branch:** `feat/me_permission`  
> **Última atualização:** 2026-04-07  
> **Referência de arquitetura:** [`docs/PERMISSIONS_ARCHITECTURE.md`](./PERMISSIONS_ARCHITECTURE.md)

Este documento descreve o contrato de requisição/resposta dos endpoints do módulo `accounts`. Cobre autenticação, perfil do usuário, roles, permissões individuais e overrides.

---

## Sumário

1. [Autenticação](#1-autenticação)
   - [POST /api/accounts/login/](#11-post-apiaccountslogin)
   - [POST /api/accounts/logout/](#12-post-apiaccountslogout)
   - [POST /api/accounts/logout/{app_slug}/](#13-post-apiaccountslogoutapp_slug)
   - [POST /api/accounts/auth/resolve-user/](#14-post-apiaccountsauthresolve-user)
2. [Aplicações](#2-aplicações)
   - [GET /api/accounts/auth/aplicacoes/](#21-get-apiaccountsauthapplicacoes)
   - [GET /api/accounts/aplicacoes/](#22-get-apiaccountsaplicacoes)
3. [Me (usuário autenticado)](#3-me-usuário-autenticado)
   - [GET /api/accounts/me/](#31-get-apiaccountsme)
   - [GET /api/accounts/me/permissions/](#32-get-apiaccountsmepermissions)
4. [Usuários e Perfis](#4-usuários-e-perfis)
   - [POST /api/accounts/users/](#41-post-apiaccountsusers)
   - [POST /api/accounts/users/create-with-role/](#42-post-apiaccountsuserscreate-with-role)
   - [GET/PATCH /api/accounts/profiles/](#43-getpatch-apiaccountsprofiles)
5. [Roles](#5-roles)
   - [GET /api/accounts/roles/](#51-get-apiaccountsroles)
6. [UserRoles](#6-userroles)
   - [GET/POST/DELETE /api/accounts/user-roles/](#61-getpostdelete-apiaccountsuser-roles)
7. [Permission Overrides](#7-permission-overrides)
   - [CRUD /api/accounts/permission-overrides/](#71-crud-apiaccountspermission-overrides)
8. [Códigos de erro globais](#8-códigos-de-erro-globais)

---

## 1. Autenticação

### 1.1 `POST /api/accounts/login/`

Realiza autenticação e cria uma sessão vinculada ao `app_context`. O cookie de sessão é específico por aplicação (`gpp_session_{APP_CONTEXT}`).

**Autenticação:** Nenhuma (AllowAny)  
**Rate limit:** Controlado globalmente via `DEFAULT_THROTTLE_CLASSES`.

#### Requisição

```json
{
  "username":    "luciano.umbelino",
  "password":    "...",
  "app_context": "PORTAL"
}
```

| Campo         | Tipo   | Obrigatório | Descrição                                              |
|---------------|--------|-------------|--------------------------------------------------------|
| `username`    | string | ✅          | Username canônico Django                               |
| `password`    | string | ✅          | Senha em texto plano (HTTPS obrigatório em produção)  |
| `app_context` | string | ✅          | Código interno da aplicação (ex: `PORTAL`, `ACOES_PNGI`) |

#### Respostas

**200 OK** — Login bem-sucedido. Cookie `gpp_session_{APP_CONTEXT}` é definido como `HttpOnly`.

```json
{ "detail": "Login realizado com sucesso" }
```

**Set-Cookie header:**
```
gpp_session_PORTAL=<session_key>; HttpOnly; SameSite=Lax; Max-Age=86400
```

**400 Bad Request** — Campos ausentes.
```json
{ "detail": "Credenciais ou app_context não informados.", "code": "invalid_request" }
```

**401 Unauthorized** — Credenciais inválidas.
```json
{ "detail": "Credenciais inválidas.", "code": "invalid_credentials" }
```

**403 Forbidden** — Aplicação bloqueada ou usuário sem acesso.
```json
{ "detail": "Aplicação inválida ou bloqueada.", "code": "invalid_app" }
{ "detail": "Usuário sem acesso ao Portal.",         "code": "no_role" }
{ "detail": "Usuário sem acesso à aplicação informada.", "code": "no_role" }
```

---

### 1.2 `POST /api/accounts/logout/`

Encerra a sessão Django e revoga todos os registros `AccountsSession` ativos do usuário.

**Autenticação:** `IsAuthenticated`

#### Resposta

**200 OK**
```json
{ "detail": "Logout realizado" }
```

---

### 1.3 `POST /api/accounts/logout/{app_slug}/`

Encerra a sessão de uma aplicação específica sem afetar outras sessões ativas do mesmo usuário.

**Autenticação:** Nenhuma (lê cookie diretamente).

| Parâmetro  | Tipo   | Descrição                           |
|------------|--------|-------------------------------------|
| `app_slug` | string | Slug da app em lowercase (ex: `portal`) |

#### Resposta

**200 OK**
```json
"Logout de PORTAL realizado com sucesso"
```
O cookie `gpp_session_{APP}` é excluído da resposta.

---

### 1.4 `POST /api/accounts/auth/resolve-user/`

Recebe um identificador (username ou email) e retorna o `username` canônico Django. Usado pelo frontend para normalizar o input antes do login.

**Autenticação:** Nenhuma (AllowAny).  
**Segurança:** Retorna 404 genérico para usuário não encontrado — não confirma existência de emails (evita user enumeration).

#### Requisição

```json
{ "identifier": "luciano.umbelino@example.com" }
```

#### Respostas

**200 OK**
```json
{ "username": "luciano.umbelino" }
```

**400 Bad Request**
```json
{ "detail": "Identificador não informado.", "code": "invalid_request" }
```

**404 Not Found**
```json
{ "detail": "Usuário não encontrado.", "code": "user_not_found" }
```

---

## 2. Aplicações

### 2.1 `GET /api/accounts/auth/aplicacoes/`

Lista aplicações ativas disponíveis para o seletor de login. **Endpoint público.**

**Autenticação:** Nenhuma (AllowAny).  
**Filtro:** `isappbloqueada=False AND isappproductionready=True`.

#### Resposta — 200 OK

```json
[
  { "codigointerno": "PORTAL",       "nomeaplicacao": "Portal GPP" },
  { "codigointerno": "ACOES_PNGI",   "nomeaplicacao": "Ações PNGI" },
  { "codigointerno": "CARGA_ORG_LOT","nomeaplicacao": "Carga Org Lot" }
]
```

> Não expõe `idaplicacao`, `base_url`, `isappbloqueada`, `isappproductionready` ou `isshowinportal`.

---

### 2.2 `GET /api/accounts/aplicacoes/`

Lista aplicações visíveis ao usuário autenticado.

**Autenticação:** `IsAuthenticated`  
**Escopo:** PORTAL_ADMIN/SuperUser vê todas; usuário comum vê apenas apps onde tem `UserRole`.

#### Resposta — 200 OK

```json
[
  {
    "idaplicacao":          1,
    "codigointerno":         "PORTAL",
    "nomeaplicacao":         "Portal GPP",
    "base_url":              "http://portal.gpp.local",
    "isshowinportal":        true,
    "isappbloqueada":        false,
    "isappproductionready":  true
  }
]
```

---

## 3. Me (usuário autenticado)

### 3.1 `GET /api/accounts/me/`

Retorna dados completos do usuário: profile + todas as roles em todas as aplicações.

**Autenticação:** `IsAuthenticated`

#### Resposta — 200 OK

```json
{
  "id":             42,
  "username":       "luciano.umbelino",
  "email":          "luciano@example.com",
  "first_name":     "Luciano",
  "last_name":      "Umbelino",
  "is_portal_admin": false,
  "name":           "Luciano Umbelino",
  "orgao":          "SESP",
  "status_usuario_id": 1,
  "roles": [
    {
      "id":               7,
      "aplicacao_codigo": "ACOES_PNGI",
      "aplicacao_nome":   "Ações PNGI",
      "role_codigo":      "GESTOR_PNGI",
      "role_nome":        "Gestor PNGI"
    }
  ]
}
```

---

### 3.2 `GET /api/accounts/me/permissions/`

> **Endpoint principal da Issue #20.**

Retorna a role do usuário na aplicação da sessão atual e as permissões efetivas concedidas por ela.

**Autenticação:** `IsAuthenticated` (lê `request.app_context` definido pelo `AppContextMiddleware`).  
**Fonte de dados:** `auth_user_user_permissions` — leitura exclusiva das permissões diretas do usuário, filtradas pelo escopo do grupo da role.

#### Fluxo de resolução

```
Request chega → AppContextMiddleware resolve cookie gpp_session_{APP}
    → grava request.app_context = "ACOES_PNGI"
    → MePermissionView lê request.app_context
    → busca Aplicacao(codigointerno=app_codigo, isappbloqueada=False)
    → busca UserRole(user, aplicacao)
    → MePermissionSerializer serializa role.codigoperfil + user_permissions filtradas pelo group
```

#### Resposta — 200 OK

```json
{
  "role":    "GESTOR_PNGI",
  "granted": [
    "add_programa",
    "change_programa",
    "view_programa"
  ]
}
```

| Campo     | Tipo            | Descrição                                                        |
|-----------|-----------------|------------------------------------------------------------------|
| `role`    | string          | `codigoperfil` da `Role` associada ao usuário nesta aplicação    |
| `granted` | array\<string\> | Codenames das permissões em `auth_user_user_permissions`, filtradas pelo `Group` da role. Ordem alfabética. |

#### Respostas de erro

**400 Bad Request** — `app_context` ausente na sessão.
```json
{ "detail": "Contexto de app não encontrado na sessão.", "code": "no_app_context" }
```

**401 Unauthorized** — Sem cookie de sessão ou cookie inválido/expirado.
```json
{ "detail": "As credenciais de autenticação não foram fornecidas." }
```

**404 Not Found** — Aplicação não encontrada/bloqueada.
```json
{ "detail": "Aplicação não encontrada ou bloqueada.", "code": "app_not_found" }
```

**404 Not Found** — Usuário sem role na aplicação.
```json
{ "detail": "Usuário sem role na aplicação informada.", "code": "no_role" }
```

#### Cenários cobertos pelos testes (`test_me_permissions.py`)

| TC    | Contexto                               | Esperado           |
|-------|----------------------------------------|--------------------|
| TC-01 | GESTOR_PNGI em ACOES_PNGI              | 200 + role + granted |
| TC-02 | COORDENADOR_PNGI em ACOES_PNGI         | 200 + role + granted |
| TC-03 | OPERADOR_ACAO em ACOES_PNGI            | 200 + role + granted |
| TC-04 | GESTOR_CARGA em CARGA_ORG_LOT          | 200 + role + granted |
| TC-05 | PORTAL_ADMIN em PORTAL                 | 200 + role + granted |
| TC-06 | SuperUser sem UserRole em PORTAL       | 404 `no_role`      |
| TC-07 | Sem autenticação                       | 401                |
| TC-08 | Cookie forjado                         | 401                |
| TC-09 | `app_context` ausente na request       | 400 `no_app_context` |
| TC-10 | `app_context` aponta para app bloqueada| 404 `app_not_found` |
| TC-11 | Usuário sem role em app válida         | 404 `no_role`      |
| TC-12 | Estrutura completa da resposta 200     | role=string, granted=list\<string\> |

---

## 4. Usuários e Perfis

### 4.1 `POST /api/accounts/users/`

Cria atomicamente `auth.User` + `UserProfile`.

**Autenticação:** `IsAuthenticated`, `CanCreateUser`

#### Requisição

```json
{
  "username":             "novo.usuario",
  "email":                "novo@example.com",
  "password":             "SenhaForte@2026",
  "first_name":           "Novo",
  "last_name":            "Usuario",
  "name":                 "Novo Usuario",
  "orgao":                "SESP",
  "status_usuario":       1,
  "tipo_usuario":         1,
  "classificacao_usuario": 1
}
```

#### Resposta — 201 Created

```json
{
  "user_id":              99,
  "username":             "novo.usuario",
  "email":                "novo@example.com",
  "name":                 "Novo Usuario",
  "orgao":                "SESP",
  "status_usuario":       1,
  "tipo_usuario":         1,
  "classificacao_usuario": 1,
  "datacriacao":          "2026-04-07T10:00:00Z"
}
```

---

### 4.2 `POST /api/accounts/users/create-with-role/`

Cria atomicamente `User` + `UserProfile` + `UserRole` + sincronização de permissões.

**Autenticação:** `IsAuthenticated`, `CanCreateUser` (restrito a PORTAL_ADMIN/SuperUser na view).

#### Requisição

```json
{
  "username":    "novo.gestor",
  "email":       "gestor@example.com",
  "password":    "SenhaForte@2026",
  "name":        "Novo Gestor",
  "orgao":       "SESP",
  "aplicacao_id": 2,
  "role_id":      2
}
```

#### Resposta — 201 Created

```json
{
  "user_id":           100,
  "username":          "novo.gestor",
  "email":             "gestor@example.com",
  "name":              "Novo Gestor",
  "orgao":             "SESP",
  "aplicacao":         "ACOES_PNGI",
  "role":              "GESTOR_PNGI",
  "datacriacao":       "2026-04-07T10:00:00Z",
  "permissions_added": 12
}
```

| Campo               | Tipo | Descrição                                        |
|---------------------|------|--------------------------------------------------|
| `permissions_added` | int  | Total de permissões materializadas para o usuário pelo sync inicial |

---

### 4.3 `GET/PATCH /api/accounts/profiles/`

Leitura e atualização parcial de `UserProfile`.

**Autenticação:** `IsAuthenticated`, `HasRolePermission`, `CanEditUser`  
**Métodos:** GET, PATCH (sem POST/PUT/DELETE).

#### GET — 200 OK (item)

```json
{
  "user_id":              42,
  "username":             "luciano.umbelino",
  "email":                "luciano@example.com",
  "name":                 "Luciano Umbelino",
  "status_usuario":       1,
  "tipo_usuario":         1,
  "classificacao_usuario": 2,
  "orgao":                "SESP",
  "datacriacao":          "2025-01-10T08:00:00Z",
  "data_alteracao":       "2026-03-15T14:30:00Z"
}
```

#### PATCH — 200 OK

Retorna a representação atualizada com os mesmos campos do GET.

**Restrições de autorização:**
- `classificacao_usuario` — apenas PORTAL_ADMIN pode alterar.
- `status_usuario` — apenas PORTAL_ADMIN pode alterar.

---

## 5. Roles

### 5.1 `GET /api/accounts/roles/`

Lista roles disponíveis. Aceita filtro por `aplicacao_id`.

**Autenticação:** `IsAuthenticated`, `IsPortalAdmin`

#### Query params

| Param          | Tipo | Descrição                         |
|----------------|------|-----------------------------------|
| `aplicacao_id` | int  | Filtra roles de uma app específica |

#### Resposta — 200 OK

```json
[
  {
    "id":               2,
    "nomeperfil":       "Gestor PNGI",
    "codigoperfil":     "GESTOR_PNGI",
    "aplicacao_id":     2,
    "aplicacao_codigo": "ACOES_PNGI",
    "aplicacao_nome":   "Ações PNGI",
    "group_id":         5,
    "group_name":       "gestor_pngi_group"
  }
]
```

---

## 6. UserRoles

### 6.1 `GET/POST/DELETE /api/accounts/user-roles/`

Gerencia atribuições de role a usuários. **Restrito a PORTAL_ADMIN.**

**Autenticação:** `IsAuthenticated`, `IsPortalAdmin`  
**Métodos permitidos:** GET, POST, DELETE.

#### POST — Requisição

```json
{
  "user":       42,
  "aplicacao":   2,
  "role":         2
}
```

#### POST — 201 Created

```json
{
  "id":               15,
  "user":              42,
  "aplicacao":          2,
  "aplicacao_codigo":  "ACOES_PNGI",
  "role":               2,
  "role_codigo":       "GESTOR_PNGI"
}
```

> Após o `create`, `sync_user_permissions(user)` é chamado atomicamente.

#### DELETE — 204 No Content

> Após o `destroy`, `sync_user_permissions(user)` é chamado para recalcular permissões com as roles remanescentes.

#### Erros de validação (400)

```json
{ "non_field_errors": ["O usuário 'x' já possui uma role na aplicação 'y'. Remova a role atual antes de atribuir uma nova."] }
{ "role": "A role selecionada não pertence à aplicação informada." }
```

---

## 7. Permission Overrides

### 7.1 `CRUD /api/accounts/permission-overrides/`

Gerencia overrides individuais de permissão (`grant` ou `revoke`) para um usuário. **Restrito a PORTAL_ADMIN.**

**Autenticação:** `IsAuthenticated`, `IsPortalAdmin`  
**Métodos:** GET, POST, PUT, PATCH, DELETE.

> Toda mutação aciona `sync_user_permissions(user)` atomicamente, garantindo que `auth_user_user_permissions` reflita o override imediatamente.

#### POST — Requisição

```json
{
  "user":       42,
  "permission":  101,
  "mode":        "grant",
  "source":      "solicitação SESP-2026-001",
  "reason":      "Acesso temporário para auditoria de programas"
}
```

| Campo        | Tipo   | Obrigatório | Valores         | Descrição                               |
|--------------|--------|-------------|-----------------|-----------------------------------------|
| `user`       | int    | ✅          | PK `auth.User`  | Usuário alvo do override                |
| `permission` | int    | ✅          | PK `auth.Permission` | Permissão a sobrescrever           |
| `mode`       | string | ✅          | `grant`/`revoke`| Tipo do override                        |
| `source`     | string | ❌          | —               | Origem (ex: número do chamado)          |
| `reason`     | string | ❌          | —               | Justificativa para trilha de auditoria  |

#### POST — 201 Created

```json
{
  "id":           7,
  "user":          42,
  "permission":    101,
  "mode":          "grant",
  "source":        "solicitação SESP-2026-001",
  "reason":        "Acesso temporário para auditoria de programas",
  "created_at":   "2026-04-07T10:00:00Z",
  "updated_at":   "2026-04-07T10:00:00Z",
  "created_by":    5,
  "updated_by":    5
}
```

#### Validação de conflito (400)

Não é permitido coexistir um override `grant` e um `revoke` para o mesmo par `(user, permission)`.

```json
{
  "mode": "Já existe um override 'revoke' para este usuário e permissão. Remova o override conflitante antes de criar um novo."
}
```

#### DELETE — 204 No Content

---

## 8. Códigos de erro globais

| Código HTTP | `code` no body         | Significado                                               |
|-------------|------------------------|-----------------------------------------------------------|
| 400         | `invalid_request`      | Campos obrigatórios ausentes ou formato inválido          |
| 400         | `no_app_context`       | `request.app_context` não resolvido pelo middleware       |
| 401         | —                      | Sessão ausente, inválida ou expirada                      |
| 403         | `invalid_app`          | Aplicação bloqueada ou inexistente no login               |
| 403         | `no_role`              | Usuário sem role na aplicação no login                    |
| 404         | `app_not_found`        | Aplicação não existe ou está bloqueada (pós-login)        |
| 404         | `no_role`              | Usuário sem `UserRole` na aplicação (pós-login)           |
| 404         | `user_not_found`       | Usuário não encontrado no resolve-user                    |

---

## Notas de implementação

### Modelo de sessão multi-app

Cada aplicação possui um cookie de sessão independente: `gpp_session_{APP_CONTEXT}`. O `AppContextMiddleware` resolve o cookie presente na request, busca o registro em `AccountsSession`, e grava `request.app_context`. A view `MePermissionView` lê **exclusivamente** `request.app_context` — nunca `request.session` — pois o middleware não usa o sistema de sessão Django padrão neste fluxo.

### Sincronização de permissões

A tabela `auth_user_user_permissions` é a fonte canônica de verdade para `AuthorizationService.can()` e `HasRolePermission`. Toda mutação em `UserRole` ou `UserPermissionOverride` aciona `sync_user_permissions(user)` dentro de uma `transaction.atomic()`, garantindo consistência imediata.

### Escopo de permissões em `/me/permissions/`

`MePermissionSerializer.get_granted()` lê de `user.user_permissions` filtrado pelos `codename` do `Group` associado à role. Isso garante que apenas as permissões do escopo da aplicação atual sejam retornadas, mesmo que o usuário tenha permissões diretas de outras roles.
