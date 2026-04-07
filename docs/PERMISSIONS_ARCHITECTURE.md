# Arquitetura do Sistema de Permissões — GPP Plataform 2.0

> **Status:** Vigente a partir de 2026-04-07
> **Branch de origem:** `feat/me_permission`
> **Issue de referência:** [#15 — Fase 2: Congelar a regra de domínio de permissões](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/15)
> **Auditoria base:** [#14 — Fase 1: Auditoria técnica completa do sistema de permissões](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/14)

---

## 1. Regra oficial do domínio

O sistema de permissões da GPP Plataform segue um modelo **RBAC com overrides individuais**, cujas regras são:

1. **`Role`** é o padrão institucional — define o conjunto de permissões de um perfil de acesso.
2. **`UserRole`** ativa uma `Role` para um usuário em uma aplicação específica.
3. O sistema **calcula e materializa** as permissões herdadas das roles ativas diretamente em `auth_user_user_permissions` no momento da atribuição.
4. O sistema **permite overrides individuais** positivos (`grant`) e negativos (`revoke`) via tabela de overrides (planejada — ver Seção 5).
5. **A tabela final consultada em runtime é `auth_user_user_permissions`.** Nenhum componente de runtime deve derivar permissões de `auth_group_permissions` diretamente.

---

## 2. Modelo de dados

```
auth.User (auth_user)
  │
  ├── auth_user_user_permissions   ← FONTE DE VERDADE em runtime
  │     Populada por: sync_user_permissions_from_group()
  │     Esvaziada por: revoke_user_permissions_from_group()
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
| `auth_user_user_permissions` | Permissões materializadas do usuário (runtime) | `permission_sync.py` |
| `accounts_userrole` | Liga usuário ↔ role ↔ aplicação | `UserRoleViewSet`, `UserCreateWithRoleSerializer` |
| `accounts_role` | Define perfis RBAC | Admin / migrations |

---

## 3. Fluxo de materialização de permissões

### 3.1 Atribuição de role

```
POST /api/accounts/user-roles/
  └─► UserRoleViewSet.create()
        └─► sync_user_permissions_from_group(user, role.group)
              Operação: merge
              Efeito:   group.permissions → auth_user_user_permissions
              Regra:    nunca remove permissões existentes (R-04)
```

### 3.2 Remoção de role

```
DELETE /api/accounts/user-roles/{id}/
  └─► UserRoleViewSet.destroy()
        └─► revoke_user_permissions_from_group(user, group_removed)
              Operação: remoção seletiva
              Efeito:   remove de auth_user_user_permissions
                        apenas as perms exclusivas do grupo removido
              Regra:    não revoga perms cobertas por outros grupos ativos (R-01)
```

### 3.3 Criação de usuário com role

```
POST /api/accounts/users/create-with-role/
  └─► UserCreateWithRoleSerializer.create()  [transaction.atomic]
        ├─► User.objects.create_user()
        ├─► UserProfile.objects.create()
        ├─► UserRole.objects.create()
        └─► sync_user_permissions_from_group(user, role.group)
```

---

## 4. Decisão sobre `auth_user_groups`

> **ADR-PERM-01 — `auth_user_groups` não é utilizado neste sistema.**

### Contexto

O Django oferece dois caminhos para conceder permissões a usuários:
- **Path A:** `auth_user_groups` → `auth_group_permissions` (permissões herdadas via grupo)
- **Path B:** `auth_user_user_permissions` (permissões diretas no usuário)

### Decisão

Este sistema usa **exclusivamente o Path B** (`auth_user_user_permissions`) como fonte de verdade em runtime, pelo seguinte raciocínio:

1. **Rastreabilidade:** permissões em `auth_user_user_permissions` são explícitas por usuário — mais fácil de auditar, revogar e testar.
2. **Overrides individuais:** o modelo de overrides (`grant`/`revoke`) é trivialmente implementado sobre `auth_user_user_permissions`; seria complexo com grupos.
3. **Isolamento por aplicação:** `UserRole` já garante escopo por app; adicionar `auth_user_groups` introduziria uma segunda fonte que poderia conflitar.
4. **Previsibilidade de cache:** a invalidação de cache por `authz_version:{user_id}` funciona com uma única fonte de verdade.

### Papel residual de `auth_user_groups`

`auth_user_groups` **NÃO é populado** neste sistema. Grupos (`auth.Group`) são usados **apenas** como template de permissões (via `auth_group_permissions`), e suas permissões são **copiadas** para `auth_user_user_permissions` durante o sync. Nenhum componente deve:

- Popular `auth_user_groups` diretamente.
- Consultar `user.groups` para decisões de autorização em runtime.
- Usar `user.has_perm()` ou `get_all_permissions()` com dependência implícita de `auth_user_groups`.

### Consequência para o Django Admin

O Django Admin usa `auth_user_groups` para suas próprias verificações. Se o Admin for necessário para gerenciar usuários, ele deve ser configurado para respeitar `auth_user_user_permissions` como fonte primária, ou ser isolado em sua própria lógica de autorização.

---

## 5. Overrides individuais (planejado)

A abordagem escolhida para exceções individuais é uma **tabela única de overrides** com campo `action: grant | revoke`.

### Modelo proposto

```python
class PermissionOverride(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    action = models.CharField(choices=[("grant", "Grant"), ("revoke", "Revoke")], max_length=10)
    aplicacao = models.ForeignKey(Aplicacao, null=True, on_delete=models.CASCADE)
    reason = models.TextField(blank=True)  # auditoria
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="overrides_criados")
    created_at = models.DateTimeField(auto_now_add=True)
```

### Regra de aplicação

```
Permissões finais = (
    auth_user_user_permissions   # base: herdada das roles
    + PermissionOverride[action=grant]   # positivos individuais
    - PermissionOverride[action=revoke]  # negativos individuais
)
```

### Justificativa

Tabela única simplifica:
- Consulta: uma JOIN para obter o estado final.
- Administração: lista unificada de exceções por usuário.
- Testes: fixture única para cenários de override.

---

## 6. Componentes e sua relação com permissões

| Componente | Papel | Lê de | Escreve em |
|---|---|---|---|
| `permission_sync.sync_user_permissions_from_group` | Materialização | `auth_group_permissions` | `auth_user_user_permissions` |
| `permission_sync.revoke_user_permissions_from_group` | Desmaterialização | `auth_user_user_permissions`, `auth_group_permissions` | `auth_user_user_permissions` |
| `AuthorizationService._load_permissions()` | Runtime check | `auth_user_user_permissions` ⚠️ *atualmente lê de `auth_group_permissions`* | — |
| `MePermissionSerializer.get_granted()` | Endpoint `/me/permissions/` | `auth_user_user_permissions` ⚠️ *atualmente lê de `group.permissions`* | — |
| `AppContextMiddleware` | Controle de acesso à sessão | `UserRole.role__codigoperfil` (aceitável) | — |
| `signals.invalidate_on_group_permission_change` | Invalidação de cache | — | Cache (não re-sincroniza) ⚠️ |

> ⚠️ **Itens marcados representam divergências identificadas na Fase 1** que precisam ser corrigidas nas fases seguintes.

---

## 7. Contrato para novos desenvolvedores

### ✅ Faça

- Ao atribuir uma role a um usuário, sempre chame `sync_user_permissions_from_group(user, role.group)` na mesma transação atômica.
- Ao remover uma role, sempre chame `revoke_user_permissions_from_group(user, group_removed)` na mesma transação atômica.
- Para checar permissões em runtime, leia de `user.user_permissions` (via `AuthorizationService` — após correção D-01).
- Para expor permissões no endpoint `/me/permissions/`, leia de `user.user_permissions` (via `MePermissionSerializer` — após correção D-02).

### ❌ Não faça

- Não popule `auth_user_groups` diretamente.
- Não consulte `user.groups` ou `group.permissions` para decisões de autorização em runtime.
- Não use `user.has_perm()` ou `get_all_permissions()` sem garantir que `auth_user_user_permissions` é a fonte populada.
- Não adicione permissões manualmente em `auth_user_user_permissions` fora do fluxo de sync — use overrides (Seção 5) quando necessário.
- Não altere `auth_group_permissions` sem verificar se os usuários afetados precisam de re-sync.

---

## 8. Referências

- [`apps/accounts/services/permission_sync.py`](../apps/accounts/services/permission_sync.py) — serviço de materialização
- [`apps/accounts/services/authorization_service.py`](../apps/accounts/services/authorization_service.py) — serviço de autorização runtime
- [`apps/accounts/models.py`](../apps/accounts/models.py) — modelos Role, UserRole, Attribute
- [`apps/accounts/signals.py`](../apps/accounts/signals.py) — invalidação de cache
- [`docs/IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md) — documentação de autenticação e sessão
