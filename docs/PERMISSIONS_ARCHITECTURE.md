# Arquitetura do Sistema de Permissões — GPP Plataform 2.0

> **Status:** Vigente a partir de 2026-04-07
> **Branch de origem:** `feat/me_permission`
> **Última atualização:** Fase 13 — atualização completa da documentação (2026-04-10)

| Fase | Issue | Entregável principal | Status |
|---|---|---|---|
| Fase 1 — Auditoria técnica | [#14](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/14) | Inventário de divergências D-01 a D-05; mapeamento completo de leituras e escritas em permissões | ✅ Concluída |
| Fase 2 — Congelar regra de domínio | [#15](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/15) | `docs/PERMISSIONS_ARCHITECTURE.md`, ADR-PERM-01, docstrings em `permission_sync.py` | ✅ Concluída |
| Fase 3 — Model `UserPermissionOverride` | [#16](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/16) | Model com `grant`/`revoke`, `UniqueConstraint`, `clean()`, migration `0009`, Admin | ✅ Concluída |
| Fase 4 — Refatorar `permission_sync.py` | [#17](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/17) | Nova API (5 funções), `AuthorizationService._load_permissions()` reescrito, 17 testes | ✅ Concluída |
| Fase 5 — Integrar gatilhos | [#18](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/18) | Signals `post_save`/`post_delete`/`m2m_changed`; `UserPermissionOverrideViewSet`; 11 testes | ✅ Concluída |
| Fase 6 — Padronizar leitura operacional | [#19](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/19) | Importação explícita em `signals.py`; correção de TC-01, TC-02, TC-03, TC-08 | ✅ Concluída |
| Fase 7 — Endpoints e contrato frontend | [#20](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/20) | `UserPermissionOverrideSerializer`; `MePermissionSerializer.get_granted()` corrigido (D-02) | ✅ Concluída |
| Fase 8 — Revisão dos testes existentes | [#21](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/21) | ~135 testes em cascata reestabilizados; suposições legadas removidas | ✅ Concluída |
| Fase 9 — Novos testes obrigatórios | [#22](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/22) | `test_permissions_suite.py` com 24 casos em 6 classes; **749 passed, 0 failed** | ✅ Concluída |
| Fase 10 — Fixtures e builders de teste | [#23](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/23) | Factories com `factory_boy`; fixtures revisadas; cobertura ≥ 92.37% | ✅ Concluída |
| Fase 11 — Management command | [#24](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/24) | `recompute_user_permissions` com 5 flags; transacional; idempotente | ✅ Concluída |
| Fase 12 — `auth_user_groups` + `token_blacklist` | [#25](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/25) | Migration `0010`; auditoria ADR-PERM-01 confirmada; re-sync executado | ✅ Concluída |
| Fase 13 — Atualizar documentação | [#26](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/26) | Revisão completa de toda documentação para refletir estado final | 🔄 Em andamento |
| Fase 14 — Políticas de domínio | [#27](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/27) | Refatorar `UserPolicy` para usar `user.has_perm()` em vez de `UserProfile.classificacao_usuario` | 🔜 Pendente |

---

## 1. Regra oficial do domínio

O sistema de permissões da GPP Plataform segue um modelo **RBAC com overrides individuais**, cujas regras são:

1. **`Role`** é o padrão institucional — define o conjunto de permissões de um perfil de acesso via `auth.Group`.
2. **`UserRole`** ativa uma `Role` para um usuário em uma aplicação específica. Um usuário pode ter no máximo **1 role por aplicação**.
3. O sistema **calcula e materializa** as permissões efetivas diretamente em `auth_user_user_permissions` via substituição completa (`set()`) — idempotente e transacional.
4. O sistema **permite overrides individuais** positivos (`grant`) e negativos (`revoke`) via `UserPermissionOverride`.
5. **A tabela final consultada em runtime é `auth_user_user_permissions`.** Nenhum componente de runtime deve derivar permissões de `auth_group_permissions` diretamente.
6. `auth_user_groups` **não é populado** neste sistema — ADR-PERM-01 (confirmado e auditado na Fase 12).

---

## 2. Modelo de dados

```
auth.User (auth_user)
  │
  ├── auth_user_user_permissions   ← FONTE DE VERDADE em runtime
  │     Populada por: sync_user_permissions() [substitui via set()]
  │     NÃO populada via auth_user_groups (ADR-PERM-01)
  │
  ├── UserPermissionOverride (accounts_userpermissionoverride)  ← overrides individuais
  │     user_id, permission_id, mode (grant | revoke)
  │     source, reason, created_by, updated_by, timestamps
  │     UniqueConstraint: (user, permission, mode)
  │     Proteção: não permite grant + revoke simultâneos para o mesmo (user, permission)
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
                          (codificação das permissões do perfil — fonte de composição, não de runtime)
```

### Tabelas envolvidas

| Tabela | Papel | Escrita por |
|---|---|---|
| `auth_group_permissions` | Define permissões do perfil (institucional — fonte de composição) | Admin / migrations |
| `auth_user_user_permissions` | Permissões materializadas do usuário (runtime — fonte de verdade) | `permission_sync.sync_user_permissions()` exclusivamente |
| `accounts_userpermissionoverride` | Exceções individuais por usuário (`grant`/`revoke`) | `UserPermissionOverrideViewSet`, Admin |
| `accounts_userrole` | Liga usuário ↔ role ↔ aplicação (1 por app) | `UserRoleViewSet`, `UserCreateWithRoleSerializer` |
| `accounts_role` | Define perfis RBAC | Admin / migrations |
| `auth_user_groups` | **Não utilizado** neste sistema (legado passivo — ADR-PERM-01) | Nunca populado |

---

## 3. Fórmula de cálculo de permissões efetivas

```
Permissões efetivas =
    auth_group_permissions (via grupos das roles ativas do usuário)   [base herdada]
    |= user.user_permissions (auth_user_user_permissions diretas)     [corrige D-02]
    |= UserPermissionOverride[mode='grant']                           [corrige D-01]
    -= UserPermissionOverride[mode='revoke']                          [revoke vence tudo]
```

> O `revoke` é aplicado por último — neutraliza qualquer fonte, incluindo `user_permissions` diretas e overrides `grant`.

**Implementado em:** `calculate_effective_permissions(user)` → `sync_user_permissions(user)` em [`apps/accounts/services/permission_sync.py`](../apps/accounts/services/permission_sync.py).

---

## 4. API do orquestrador (`permission_sync.py`)

O arquivo [`apps/accounts/services/permission_sync.py`](../apps/accounts/services/permission_sync.py) é o **único ponto de escrita** em `auth_user_user_permissions`.

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

> **Funções legadas** (`sync_user_permissions_from_group`, `revoke_user_permissions_from_group`) mantidas como aliases deprecados por retro-compatibilidade. **Não use em código novo.**

---

## 5. Fluxo de materialização de permissões

### 5.1 Atribuição de role

```
POST /api/accounts/user-roles/
  └─► UserRoleViewSet.create()
        └─► sync_user_permissions(user)   [substitui via set() — idempotente]
```

### 5.2 Atualização de role

```
PATCH /api/accounts/user-roles/{id}/
  └─► UserRoleViewSet.update()
        └─► sync_user_permissions(user)   [recalcula com a role atualizada]
```

### 5.3 Remoção de role

```
DELETE /api/accounts/user-roles/{id}/
  └─► UserRoleViewSet.destroy()
        └─► sync_user_permissions(user)   [recalcula sem a role removida]
```

### 5.4 Criação de usuário com role

```
POST /api/accounts/users/create-with-role/
  └─► UserCreateWithRoleSerializer.create()  [transaction.atomic]
        ├─► User.objects.create_user()
        ├─► UserProfile.objects.create()
        ├─► UserRole.objects.create()
        └─► sync_user_permissions(user)
```

### 5.5 Override individual (grant ou revoke)

```
POST/PATCH/DELETE /api/accounts/user-permission-overrides/
  └─► UserPermissionOverrideViewSet  [mutação]
        └─► sync_user_permissions(user)   [recalcula com o override aplicado]
```

### 5.6 Mudança nas permissões de um grupo (D-05 — corrigido na Fase 5)

```
[m2m_changed em auth_group_permissions]
  └─► signal: invalidate_on_group_permission_change
        ├─► Invalida cache de authz (authz_version:{user_id})
        └─► sync_users_permissions(user_ids)  [re-sync para todos os usuários afetados]
```

### 5.7 Mudança no `group` associado a um `Role`

```
[post_save em Role]
  └─► signal: sync_on_role_group_change
        └─► sync_users_permissions(user_ids)  [re-sync para todos com essa role]
```

---

## 6. Gatilhos de sincronização

Toda alteração em uma **fonte de permissão** dispara automaticamente um re-sync:

| Evento | Mecanismo | Função |
|---|---|---|
| Criação de `UserRole` | `UserRoleViewSet.create()` | `sync_user_permissions(user)` |
| Atualização de `UserRole` | `UserRoleViewSet.update()` | `sync_user_permissions(user)` |
| Exclusão de `UserRole` | `UserRoleViewSet.destroy()` | `sync_user_permissions(user)` |
| Criação/edição/exclusão de `UserPermissionOverride` | `UserPermissionOverrideViewSet` | `sync_user_permissions(user)` |
| Alteração de `Role.group` | Signal `post_save` em `Role` | `sync_users_permissions(user_ids)` |
| Alteração de `auth_group_permissions` | Signal `m2m_changed` (corrige D-05) | `sync_users_permissions(user_ids)` |

> **Sinal de saúde:** os 6 gatilhos acima cobrem todos os caminhos de mutação. Se uma permissão foi adicionada manualmente em `auth_user_user_permissions` fora desse fluxo, ela será **eliminada** na próxima execução de `sync_user_permissions(user)` (comportamento idempotente por substituição completa).

---

## 7. Decisão sobre `auth_user_groups`

> **ADR-PERM-01 — `auth_user_groups` não é utilizado neste sistema.**
> **Auditado e confirmado na Fase 12 (Issue #25, 2026-04-10).**

### Contexto

O Django oferece dois caminhos para conceder permissões a usuários:
- **Path A:** `auth_user_groups` → `auth_group_permissions` (permissões herdadas via grupo)
- **Path B:** `auth_user_user_permissions` (permissões diretas no usuário)

### Decisão

Este sistema usa **exclusivamente o Path B** (`auth_user_user_permissions`) como fonte de verdade em runtime:

1. **Rastreabilidade:** permissões em `auth_user_user_permissions` são explícitas por usuário — mais fácil de auditar, revogar e testar.
2. **Overrides individuais:** o modelo `UserPermissionOverride` (`grant`/`revoke`) é trivialmente implementado sobre `auth_user_user_permissions`.
3. **Isolamento por aplicação:** `UserRole` já garante escopo por app; adicionar `auth_user_groups` introduziria uma segunda fonte conflitante.
4. **Previsibilidade de cache:** a invalidação de cache por `authz_version:{user_id}` funciona com uma única fonte de verdade.

### Papel residual de `auth_user_groups`

`auth_user_groups` **NÃO é populado** neste sistema. Grupos (`auth.Group`) são usados **apenas** como template de permissões (via `auth_group_permissions`), e suas permissões são **copiadas** para `auth_user_user_permissions` durante o sync. Nenhum componente deve:

- Popular `auth_user_groups` diretamente.
- Consultar `user.groups` para decisões de autorização em runtime.
- Usar `user.has_perm()` ou `get_all_permissions()` com dependência implícita de `auth_user_groups`.

### Consequência para o Django Admin

O Django Admin usa `auth_user_groups` para suas próprias verificações. Se o Admin for necessário, deve ser configurado para respeitar `auth_user_user_permissions` como fonte primária, ou ser isolado em sua própria lógica de autorização.

---

## 8. Model `UserPermissionOverride`

Implementado em [`apps/accounts/models.py`](../apps/accounts/models.py) — commit [`64c909c`](https://github.com/ProjetcsGPP/gpp_plataform2.0/commit/64c909c15272b15f589ff14a0cd6ba59a052914c) (Fase 3 — Issue #16).

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
- `revoke` → retira permissão que a role concederia (e neutraliza qualquer outra fonte, incluindo `grant`).
- Não é permitida duplicidade por `(user, permission, mode)` — UniqueConstraint.
- Não é permitida coexistência de `grant` e `revoke` para o mesmo `(user, permission)` — validada via `clean()` / `save()`.

---

## 9. Management command `recompute_user_permissions`

Implementado em `apps/accounts/management/commands/recompute_user_permissions.py` (Fase 11 — Issue #24).

### Uso

```bash
# Recomputa para um usuário específico
python manage.py recompute_user_permissions --user-id <ID>

# Recomputa para todos os usuários com pelo menos uma UserRole ativa
python manage.py recompute_user_permissions --all-users

# Mostra o que seria feito sem persistir nada
python manage.py recompute_user_permissions --all-users --dry-run

# Modo verbose: log detalhado por usuário (permissões adicionadas/removidas)
python manage.py recompute_user_permissions --all-users --verbose

# Modo strict: torna explícita a intenção de substituição completa (equivalente ao padrão)
python manage.py recompute_user_permissions --all-users --strict
```

### Regras

1. **Nunca escreve em `auth_user_groups`** — ADR-PERM-01.
2. **Usa exclusivamente `sync_user_permissions(user)`** — não chama funções legadas.
3. **`--dry-run`** usa `transaction.atomic()` com rollback explícito.
4. **Transacional por usuário** — falha em um não aborta os demais.
5. **Idempotente** — executar duas vezes produz o mesmo estado final.

### Execução de referência (2026-04-10)

```
python manage.py recompute_user_permissions --all-users --verbose
user=2 (alexandre.mohamad) | +0 adicionadas / -0 removidas
user=4 (luciano.umbelino)  | +0 adicionadas / -0 removidas
user=3 (sabrini.canhet)    | +0 adicionadas / -0 removidas
3 usuário(s) processado(s), 0 permissão(ões) adicionada(s), 0 removida(s).
```

---

## 10. Estratégia de testes

### Factories com `factory_boy` (Fase 10 — Issue #23)

Localização: `apps/accounts/tests/factories.py`

| Factory | Comportamento |
|---|---|
| `UserFactory` | Cria usuário básico sem role |
| `RoleFactory` | Cria role com group associado |
| `UserRoleFactory` | Associa usuário a role e **chama `sync_user_permissions`** no `_after_create` |
| `UserPermissionOverrideFactory` | Cria override (`grant`/`revoke`) e **chama `sync_user_permissions`** no `_after_create` |
| `PermissionFactory` | Cria `Permission` do Django para uso em overrides e testes |

> **Garantia:** ao sair de `UserRoleFactory.create()` ou `UserPermissionOverrideFactory.create()`, `auth_user_user_permissions` já está populado. Não é necessário chamar sync manualmente no `setUp` dos testes.

### Suite de testes (Fase 9 — Issue #22)

Arquivo principal: `apps/accounts/tests/test_permissions_suite.py`

| Classe | Foco | Status |
|---|---|---|
| `TestServicePermissions` | `sync_user_permissions` escreve, recalcula, remove e é idempotente | ✅ 6/6 |
| `TestOverridePermissions` | `grant`/`revoke` adicionam/removem, sem duplicidade, revertem ao deletar | ✅ 6/6 |
| `TestOverlapPermissions` | União de roles, remoção parcial e total de origens | ✅ 3/3 |
| `TestAPIPermissions` | `/me/permissions/` reflete role e override em tempo real | ✅ 5/5 |
| `TestStructuralIntegration` | Signals `m2m_changed` em `Group.permissions`, `post_save` em `Role` | ✅ 3/3 |
| `TestNegativePermissions` | Bloqueio via `can()`, Group sem role, isolamento `auth_user_groups` (ADR-PERM-01) | ✅ 3/3 |

### Baseline atual

- **749+ testes passando, 0 falhas**
- Cobertura total ≥ **92.37%** (threshold: 80%)
- Todas as factories garantem `auth_user_user_permissions` populado na criação
- Fixtures não populam `auth_user_groups` (ADR-PERM-01)

---

## 11. Decisão sobre resíduos do `token_blacklist`

> **Executado em 2026-04-10 — Fase 12 (Issue #25)**

Registros residuais do app `token_blacklist` do SimpleJWT foram removidos para evitar:
- Permissões fantasma em `auth_user_user_permissions` de usuários mais antigos
- Poluição em `django_content_type` e `auth_permission`

**Migration de limpeza:** [`apps/accounts/migrations/0010_clean_token_blacklist_residues.py`](../apps/accounts/migrations/0010_clean_token_blacklist_residues.py) — idempotente.

Após a limpeza, `recompute_user_permissions --all-users` foi executado com sucesso (0 permissões adicionadas/removidas — sistema já estava íntegro).

---

## 12. Componentes e sua relação com permissões

| Componente | Papel | Lê de | Escreve em | Status |
|---|---|---|---|---|
| `permission_sync.sync_user_permissions()` | Materialização oficial — idempotente, transacional | `auth_group_permissions`, `UserPermissionOverride` | `auth_user_user_permissions` (set) | ✅ Implementado (Fase 4) |
| `permission_sync.calculate_inherited_permissions()` | Cálculo de herança — sem gravação | `auth_group_permissions` via roles | — | ✅ Implementado (Fase 4) |
| `permission_sync.calculate_effective_permissions()` | Cálculo com overrides — sem gravação | `auth_group_permissions`, `UserPermissionOverride` | — | ✅ Implementado (Fase 4) |
| `permission_sync.sync_users_permissions()` | Re-sync em batch | — via `sync_user_permissions` | `auth_user_user_permissions` | ✅ Implementado (Fase 4) |
| `permission_sync.sync_all_users_permissions()` | Re-sync total | — via `sync_user_permissions` | `auth_user_user_permissions` | ✅ Implementado (Fase 4) |
| `permission_sync.sync_user_permissions_from_group()` | Materialização **legada** — deprecada | `auth_group_permissions` | `auth_user_user_permissions` (merge) | ⚠️ Alias temporário — não usar em código novo |
| `permission_sync.revoke_user_permissions_from_group()` | Desmaterialização **legada** — deprecada | `auth_user_user_permissions`, `auth_group_permissions` | `auth_user_user_permissions` | ⚠️ Alias temporário — não usar em código novo |
| `AuthorizationService._load_permissions()` | Runtime check | `auth_user_user_permissions` | — | ✅ Corrigido (Fase 4, commit `902ad19`) |
| `AuthorizationService.can()` | Verificação de permissão | via `_load_permissions()` | — | ✅ Correto |
| `MePermissionSerializer.get_granted()` | Endpoint `/me/permissions/` | `auth_user_user_permissions` (`user.user_permissions`) | — | ✅ Corrigido (Fase 7, commit `902ad19`) |
| `UserPermissionOverrideViewSet` | CRUD de overrides | — | `accounts_userpermissionoverride` → `sync_user_permissions()` | ✅ Implementado (Fase 5) |
| `UserPermissionOverrideSerializer` | Serialização de overrides | — | — | ✅ Criado (Fase 7) |
| `AppContextMiddleware` | Controle de acesso à sessão | `UserRole.role__codigoperfil` | — | ✅ Mantido (D-03 aceito) |
| `signal: invalidate_on_group_permission_change` | Invalidação de cache + re-sync | — | Cache + `auth_user_user_permissions` | ✅ Corrigido (Fase 5, D-05) |
| `signal: sync_on_role_group_change` | Re-sync quando `Role.group` muda | — | `auth_user_user_permissions` via batch | ✅ Implementado (Fase 5) |
| `recompute_user_permissions` (management command) | Saneamento manual em produção | — via `sync_user_permissions` | `auth_user_user_permissions` | ✅ Implementado (Fase 11) |
| `UserPolicy.can_create_user()` / `can_edit_user()` | Política de domínio | `UserProfile.classificacao_usuario` ❌ | — | ⚠️ Violação ADR-PERM-01 — pendente (Fase 14 — Issue #27) |

---

## 13. Contrato para novos desenvolvedores

### ✅ Faça

- Ao atribuir ou remover uma role, chame `sync_user_permissions(user)` na mesma transação atômica.
- Ao criar/editar/excluir um `UserPermissionOverride`, chame `sync_user_permissions(user)` imediatamente após.
- Para checar permissões em runtime, use `AuthorizationService.can(user, codename)` — ele lê de `auth_user_user_permissions`.
- Para expor permissões no endpoint `/me/permissions/`, use `MePermissionSerializer` — ele lê de `auth_user_user_permissions`.
- Para uma exceção individual, crie um `UserPermissionOverride` com `mode='grant'` ou `mode='revoke'`.
- Para re-sincronizar em produção, use `python manage.py recompute_user_permissions --all-users`.
- Nos testes, use as factories (`UserRoleFactory`, `UserPermissionOverrideFactory`) — `auth_user_user_permissions` já estará populado.

### ❌ Não faça

- Não popule `auth_user_groups` diretamente.
- Não consulte `user.groups` ou `group.permissions` para decisões de autorização em runtime.
- Não use `user.has_perm()` ou `get_all_permissions()` sem garantir que `auth_user_user_permissions` está populado.
- Não adicione permissões manualmente em `auth_user_user_permissions` fora do fluxo de sync — use `UserPermissionOverride`.
- Não chame as funções legadas `sync_user_permissions_from_group` ou `revoke_user_permissions_from_group` em código novo.
- Não consulte `UserProfile.classificacao_usuario` para decisões de autorização — use `user.has_perm()` (correção pendente na Fase 14).

---

## 14. Divergências da auditoria (Fase 1) — status final

| ID | Ponto | Status |
|---|---|---|
| D-01 | `AuthorizationService._load_permissions()` lia de `auth_group_permissions` | ✅ Corrigido (Fase 4, commit `902ad19`) |
| D-02 | `MePermissionSerializer.get_granted()` lia de `group.permissions` | ✅ Corrigido (Fases 4/7, commit `902ad19`) |
| D-03 | `LoginView`/`middleware`/`_is_portal_admin()` consultam `UserRole` diretamente | ✅ Aceito (controle de acesso, não de permissão granular) |
| D-04 | `revoke_user_permissions_from_group` usava lógica incremental (phantom perms) | ✅ Eliminado pela substituição completa (`set()`) em `sync_user_permissions()` |
| D-05 | `invalidate_on_group_permission_change` não re-sincronizava `auth_user_user_permissions` | ✅ Corrigido (Fase 5) |

---

## 15. Próximo passo: Fase 14 — Políticas de domínio (Issue #27)

Apesar de todas as divergências D-01 a D-05 estarem corrigidas, foi identificado que **as políticas de domínio** (`apps/accounts/policies/`) ainda lêem autorização a partir de `UserProfile.classificacao_usuario` — violando o ADR-PERM-01.

Principais pontos pendentes:
- `UserPolicy.can_create_user()` → deve usar `user.has_perm("auth.add_user")` em vez de `classificacao.pode_criar_usuario`
- `UserPolicy.can_edit_user()` → deve usar `user.has_perm("auth.change_user")` em vez de `classificacao.pode_editar_usuario`
- `UserPolicy._get_classificacao()` → deve ser restrito a contextos de UI/serialização (nunca autorização)
- Auditoria das demais policies em `apps/accounts/policies/` para usos equivalentes

Ver [Issue #27](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/27) para detalhes completos.

---

## 16. Referências

- [`apps/accounts/services/permission_sync.py`](../apps/accounts/services/permission_sync.py) — orquestrador de sincronização (único ponto de escrita em `auth_user_user_permissions`)
- [`apps/accounts/services/authorization_service.py`](../apps/accounts/services/authorization_service.py) — serviço de autorização runtime
- [`apps/accounts/models.py`](../apps/accounts/models.py) — modelos `Role`, `UserRole`, `UserPermissionOverride`
- [`apps/accounts/signals.py`](../apps/accounts/signals.py) — gatilhos de sincronização automática
- [`apps/accounts/views.py`](../apps/accounts/views.py) — `UserRoleViewSet`, `UserPermissionOverrideViewSet`
- [`apps/accounts/serializers.py`](../apps/accounts/serializers.py) — `UserPermissionOverrideSerializer`, `MePermissionSerializer`
- [`apps/accounts/tests/factories.py`](../apps/accounts/tests/factories.py) — factories `factory_boy` para testes
- [`apps/accounts/tests/test_permissions_suite.py`](../apps/accounts/tests/test_permissions_suite.py) — suite de testes obrigatórios (24 casos)
- [`apps/accounts/management/commands/recompute_user_permissions.py`](../apps/accounts/management/commands/recompute_user_permissions.py) — management command
- [`apps/accounts/migrations/0009_add_userpermissionoverride.py`](../apps/accounts/migrations/0009_add_userpermissionoverride.py) — migration do override
- [`apps/accounts/migrations/0010_clean_token_blacklist_residues.py`](../apps/accounts/migrations/0010_clean_token_blacklist_residues.py) — limpeza de resíduos
- [`apps/accounts/policies/user_policy.py`](../apps/accounts/policies/user_policy.py) — ⚠️ pendente de refatoração (Fase 14)
- [`docs/IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md) — documentação de autenticação e sessão
