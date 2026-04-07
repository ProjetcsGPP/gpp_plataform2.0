# Arquitetura do Sistema de Permissões — GPP Plataform 2.0

> **Status:** Vigente a partir de 2026-04-07
> **Branch de origem:** `feat/me_permission`
> **Última atualização:** Fase 5 — integração de gatilhos

| Fase | Issue | Status |
|---|---|---|
| Fase 1 — Auditoria técnica | [#14](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/14) | ✅ Concluída |
| Fase 2 — Congelar regra de domínio | [#15](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/15) | ✅ Concluída |
| Fase 3 — Model `UserPermissionOverride` | [#16](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/16) | ✅ Concluída |
| Fase 4 — Refatorar `permission_sync.py` | [#17](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/17) | 🔄 Em andamento |
| Fase 5 — Integrar gatilhos | [#18](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/18) | 🔜 Pendente |

---

## 1. Regra oficial do domínio

O sistema de permissões da GPP Plataform segue um modelo **RBAC com overrides individuais**, cujas regras são:

1. **`Role`** é o padrão institucional — define o conjunto de permissões de um perfil de acesso.
2. **`UserRole`** ativa uma `Role` para um usuário em uma aplicação específica.
3. O sistema **calcula e materializa** as permissões efetivas diretamente em `auth_user_user_permissions` via substituição completa (`set()`) — idempotente e transacional.
4. O sistema **permite overrides individuais** positivos (`grant`) e negativos (`revoke`) via `UserPermissionOverride` (implementado na Fase 3).
5. **A tabela final consultada em runtime é `auth_user_user_permissions`.** Nenhum componente de runtime deve derivar permissões de `auth_group_permissions` diretamente.

---

## 2. Modelo de dados

```
auth.User (auth_user)
  │
  ├── auth_user_user_permissions   ← FONTE DE VERDADE em runtime
  │     Populada por: sync_user_permissions() [substitui via set()]
  │
  ├── UserPermissionOverride (accounts_userpermissionoverride)  ← overrides individuais
  │     user_id, permission_id, mode (grant | revoke)
  │     source, reason, created_by, updated_by, timestamps
  │     UniqueConstraint: (user, permission, mode)
  │
  └── UserRole (accounts_userrole)
        │  user_id, aplicacao_id, role_id
        │  UniqueConstraint: (user, aplicacao) — 1 role por app
        │
        └── Role (accounts_role)
              │  aplicacao_id, codigoperfil, nomeperfil
              │
              └── auth.Group (auth_group)  ← definição institucional das permissões
                    │
                    └── auth_group_permissions
                          (codificação das permissões do perfil)
```

### Tabelas envolvidas

| Tabela | Papel | Escrita por |
|---|---|---|
| `auth_group_permissions` | Define permissões do perfil (institucional) | Admin / migrations |
| `auth_user_user_permissions` | Permissões materializadas do usuário (runtime) | `permission_sync.sync_user_permissions()` |
| `accounts_userpermissionoverride` | Exceções individuais por usuário (`grant`/`revoke`) | `UserPermissionOverrideViewSet`, Admin |
| `accounts_userrole` | Liga usuário ↔ role ↔ aplicação | `UserRoleViewSet`, `UserCreateWithRoleSerializer` |
| `accounts_role` | Define perfis RBAC | Admin / migrations |

---

## 3. Fórmula de cálculo de permissões efetivas

```
Permissões efetivas =
    auth_group_permissions (via grupos das roles ativas do usuário)   [base herdada]
    |= user.user_permissions (auth_user_user_permissions diretas)     [fase 4: corrige D-02]
    |= UserPermissionOverride[mode='grant']                           [fase 4: corrige D-01]
    -= UserPermissionOverride[mode='revoke']                          [fase 4: revoke vence tudo]
```

> O `revoke` é aplicado por último — neutraliza qualquer fonte, incluindo `user_permissions` diretas.

---

## 4. API do orquestrador (`permission_sync.py`)

O arquivo [`apps/accounts/services/permission_sync.py`](../apps/accounts/services/permission_sync.py) é o **único ponto de escrita** em `auth_user_user_permissions`. A nova API (Fase 4) expõe:

```python
def calculate_inherited_permissions(user) -> set[Permission]:
    """
    Calcula o conjunto de permissões herdadas das roles ativas do usuário
    via auth_group_permissions. Retorna objetos Permission.
    Não grava nada no banco.
    """

def calculate_effective_permissions(user) -> set[Permission]:
    """
    Aplica overrides (UserPermissionOverride) sobre o conjunto herdado.
    Retorna o conjunto final de permissões efetivas.
    Não grava nada no banco.
    """

def sync_user_permissions(user) -> None:
    """
    Materializa calculate_effective_permissions(user) em auth_user_user_permissions
    via substituição completa (set()). Idempotente. Transacional.
    Corrige D-04: elimina phantom perms adicionadas fora do fluxo de sync.
    """

def sync_users_permissions(user_ids: list[int]) -> None:
    """
    Chama sync_user_permissions para cada user_id da lista.
    Útil para re-sync em batch (ex: quando um grupo tem permissões alteradas — D-05).
    """

def sync_all_users_permissions() -> None:
    """
    Re-sincroniza todos os usuários que possuem pelo menos uma UserRole ativa.
    Útil para management command e manutenção.
    """
```

> **Funções antigas** (`sync_user_permissions_from_group`, `revoke_user_permissions_from_group`) serão mantidas como aliases deprecados durante a transição.

---

## 5. Fluxo de materialização de permissões

### 5.1 Atribuição de role

```
POST /api/accounts/user-roles/
  └─► UserRoleViewSet.create()
        └─► sync_user_permissions(user)   [substitui via set() — idempotente]
```

### 5.2 Remoção de role

```
DELETE /api/accounts/user-roles/{id}/
  └─► UserRoleViewSet.destroy()
        └─► sync_user_permissions(user)   [recalcula sem a role removida]
```

### 5.3 Criação de usuário com role

```
POST /api/accounts/users/create-with-role/
  └─► UserCreateWithRoleSerializer.create()  [transaction.atomic]
        ├─► User.objects.create_user()
        ├─► UserProfile.objects.create()
        ├─► UserRole.objects.create()
        └─► sync_user_permissions(user)
```

### 5.4 Override individual (grant ou revoke)

```
POST/PATCH/DELETE /api/accounts/user-permission-overrides/
  └─► UserPermissionOverrideViewSet  [mutação]
        └─► sync_user_permissions(user)   [recalcula com o override aplicado]
```

### 5.5 Mudança nas permissões de um grupo (D-05)

```
[m2m_changed em auth_group_permissions]
  └─► signal: invalidate_on_group_permission_change
        ├─► Invalida cache de authz
        └─► sync_users_permissions(user_ids)  [re-sync para todos os usuários afetados]
```

### 5.6 Mudança no `group` associado a um `Role`

```
[post_save em Role]
  └─► signal: sync_on_role_group_change
        └─► sync_users_permissions(user_ids)  [re-sync para todos com essa role]
```

---

## 6. Gatilhos de sincronização (Fase 5)

Toda alteração em uma **fonte de permissão** deve disparar automaticamente um re-sync:

| Evento | Mecanismo | Função |
|---|---|---|
| Criação de `UserRole` | `UserRoleViewSet.create()` | `sync_user_permissions(user)` |
| Atualização de `UserRole` | `UserRoleViewSet.update()` | `sync_user_permissions(user)` |
| Exclusão de `UserRole` | `UserRoleViewSet.destroy()` | `sync_user_permissions(user)` |
| Criação/edição/exclusão de `UserPermissionOverride` | `UserPermissionOverrideViewSet` | `sync_user_permissions(user)` |
| Alteração de `Role.group` | Signal `post_save` em `Role` | `sync_users_permissions(user_ids)` |
| Alteração de `auth_group_permissions` | Signal `m2m_changed` (corrige D-05) | `sync_users_permissions(user_ids)` |

---

## 7. Decisão sobre `auth_user_groups`

> **ADR-PERM-01 — `auth_user_groups` não é utilizado neste sistema.**

### Contexto

O Django oferece dois caminhos para conceder permissões a usuários:
- **Path A:** `auth_user_groups` → `auth_group_permissions` (permissões herdadas via grupo)
- **Path B:** `auth_user_user_permissions` (permissões diretas no usuário)

### Decisão

Este sistema usa **exclusivamente o Path B** (`auth_user_user_permissions`) como fonte de verdade em runtime, pelo seguinte raciocínio:

1. **Rastreabilidade:** permissões em `auth_user_user_permissions` são explícitas por usuário — mais fácil de auditar, revogar e testar.
2. **Overrides individuais:** o modelo `UserPermissionOverride` (`grant`/`revoke`) é trivialmente implementado sobre `auth_user_user_permissions`.
3. **Isolamento por aplicação:** `UserRole` já garante escopo por app; adicionar `auth_user_groups` introduziria uma segunda fonte que poderia conflitar.
4. **Previsibilidade de cache:** a invalidação de cache por `authz_version:{user_id}` funciona com uma única fonte de verdade.

### Papel residual de `auth_user_groups`

`auth_user_groups` **NÃO é populado** neste sistema. Grupos (`auth.Group`) são usados **apenas** como template de permissões (via `auth_group_permissions`), e suas permissões são **copiadas** para `auth_user_user_permissions` durante o sync. Nenhum componente deve:

- Popular `auth_user_groups` diretamente.
- Consultar `user.groups` para decisões de autorização em runtime.
- Usar `user.has_perm()` ou `get_all_permissions()` com dependência implícita de `auth_user_groups`.

### Consequência para o Django Admin

O Django Admin usa `auth_user_groups` para suas próprias verificações. Se o Admin for necessário, deve ser configurado para respeitar `auth_user_user_permissions` como fonte primária, ou ser isolado em sua própria lógica de autorização.

---

## 8. Model `UserPermissionOverride` (Fase 3)

Implementado em [`apps/accounts/models.py`](../apps/accounts/models.py) — commit [`64c909c`](https://github.com/ProjetcsGPP/gpp_plataform2.0/commit/64c909c15272b15f589ff14a0cd6ba59a052914c).

```python
class UserPermissionOverride(models.Model):
    user        = models.ForeignKey(AUTH_USER_MODEL, on_delete=CASCADE, related_name="permission_overrides")
    permission  = models.ForeignKey("auth.Permission", on_delete=CASCADE, related_name="user_overrides")
    mode        = models.CharField(max_length=6, choices=[("grant", "Grant"), ("revoke", "Revoke")])
    source      = models.CharField(max_length=200, blank=True)   # origem do override (auditoria)
    reason      = models.TextField(blank=True)                   # justificativa (auditoria)
    created_by  = models.ForeignKey(AUTH_USER_MODEL, SET_NULL, null=True, related_name="overrides_criados")
    updated_by  = models.ForeignKey(AUTH_USER_MODEL, SET_NULL, null=True, related_name="overrides_editados")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userpermissionoverride"
        constraints = [
            UniqueConstraint(fields=["user", "permission", "mode"], name="unique_user_permission_mode")
        ]
        # clean()/save() impedem coexistência de grant+revoke para o mesmo (user, permission)
```

### Regras de negócio

- `grant` → adiciona permissão que o usuário não herdaria normalmente via role.
- `revoke` → retira permissão que a role concederia (e neutraliza qualquer outra fonte).
- Não é permitida duplicidade por `(user, permission, mode)` — UniqueConstraint.
- Não é permitida coexistência de `grant` e `revoke` para o mesmo `(user, permission)` — validada via `clean()` / `save()`.

---

## 9. Componentes e sua relação com permissões

| Componente | Papel | Lê de | Escreve em | Status |
|---|---|---|---|---|
| `permission_sync.sync_user_permissions()` | Materialização (novo — Fase 4) | `auth_group_permissions`, `UserPermissionOverride` | `auth_user_user_permissions` (set) | 🔄 Em implementação |
| `permission_sync.sync_user_permissions_from_group()` | Materialização (legado — deprecar) | `auth_group_permissions` | `auth_user_user_permissions` (merge) | ⚠️ Alias temporário |
| `permission_sync.revoke_user_permissions_from_group()` | Desmaterialização (legado — deprecar) | `auth_user_user_permissions`, `auth_group_permissions` | `auth_user_user_permissions` | ⚠️ Alias temporário |
| `AuthorizationService._load_permissions()` | Runtime check | `auth_group_permissions` + `user.user_permissions` + `UserPermissionOverride` | — | ✅ Corrigido (Fase 4, commit `902ad19`) |
| `MePermissionSerializer.get_granted()` | Endpoint `/me/permissions/` | `auth_user_user_permissions` | — | ✅ Corrigido (Fase 4, commit `902ad19`) |
| `UserPermissionOverrideViewSet` | CRUD de overrides | — | `accounts_userpermissionoverride` → `sync_user_permissions()` | 🔜 Fase 5 |
| `AppContextMiddleware` | Controle de acesso à sessão | `UserRole.role__codigoperfil` (aceitável) | — | ✅ Mantido |
| `signals.invalidate_on_group_permission_change` | Invalidação de cache + re-sync | — | Cache + `auth_user_user_permissions` | 🔜 Fase 5 (D-05) |

---

## 10. Contrato para novos desenvolvedores

### ✅ Faça

- Ao atribuir ou remover uma role, chame `sync_user_permissions(user)` na mesma transação atômica.
- Ao criar/editar/excluir um `UserPermissionOverride`, chame `sync_user_permissions(user)` imediatamente após.
- Para checar permissões em runtime, use `AuthorizationService.can(user, codename)` — ele lê de `auth_user_user_permissions`.
- Para expor permissões no endpoint `/me/permissions/`, use `MePermissionSerializer` — ele lê de `auth_user_user_permissions`.
- Se precisar de uma exceção individual, crie um `UserPermissionOverride` com `mode='grant'` ou `mode='revoke'`.

### ❌ Não faça

- Não popule `auth_user_groups` diretamente.
- Não consulte `user.groups` ou `group.permissions` para decisões de autorização em runtime.
- Não use `user.has_perm()` ou `get_all_permissions()` sem garantir que `auth_user_user_permissions` está populado.
- Não adicione permissões manualmente em `auth_user_user_permissions` fora do fluxo de sync — use `UserPermissionOverride`.
- Não altere `auth_group_permissions` sem verificar que o re-sync automático via signal está ativo (Fase 5).
- Não chame as funções legadas `sync_user_permissions_from_group` ou `revoke_user_permissions_from_group` em código novo — use `sync_user_permissions(user)`.

---

## 11. Divergências da auditoria (Fase 1) — status

| ID | Ponto | Status |
|---|---|---|
| D-01 | `AuthorizationService._load_permissions()` lê de `auth_group_permissions` | ✅ Corrigido (Fase 4, commit `902ad19`) |
| D-02 | `MePermissionSerializer.get_granted()` lê de `group.permissions` | ✅ Corrigido (Fase 4, commit `902ad19`) |
| D-03 | `LoginView`/`middleware`/`_is_portal_admin()` consultam `UserRole` diretamente | ✅ Aceito (controle de acesso, não de permissão granular) |
| D-04 | `revoke_user_permissions_from_group` usa lógica incremental (phantom perms) | ✅ Eliminado pela substituição completa (`set()`) em `sync_user_permissions()` |
| D-05 | `invalidate_on_group_permission_change` não re-sincroniza `auth_user_user_permissions` | 🔜 Pendente (Fase 5) |

---

## 12. Referências

- [`apps/accounts/services/permission_sync.py`](../apps/accounts/services/permission_sync.py) — orquestrador de sincronização
- [`apps/accounts/services/authorization_service.py`](../apps/accounts/services/authorization_service.py) — serviço de autorização runtime
- [`apps/accounts/models.py`](../apps/accounts/models.py) — modelos Role, UserRole, UserPermissionOverride
- [`apps/accounts/signals.py`](../apps/accounts/signals.py) — invalidação de cache e re-sync
- [`apps/accounts/views.py`](../apps/accounts/views.py) — UserRoleViewSet, UserPermissionOverrideViewSet
- [`apps/accounts/migrations/0009_add_userpermissionoverride.py`](../apps/accounts/migrations/0009_add_userpermissionoverride.py) — migration do override
- [`docs/IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md) — documentação de autenticação e sessão
