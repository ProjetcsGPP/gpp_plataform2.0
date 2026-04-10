# Estratégia de Testes

> **Última atualização:** Fase 13 — 2026-04-10
> Reflete o estado final das Fases 1–12 (Issues #14–#25).

---

## Baseline atual

| Métrica | Valor |
|---|---|
| **Testes passando** | 749+, 1 skipped, **0 falhas** |
| **Cobertura total** | ≥ 92.37% |
| **Threshold mínimo** | 80% |
| **Framework** | `pytest` + `pytest-django` |
| **Factories** | `factory_boy` (padrão oficial do projeto) |

---

## Factories com `factory_boy` (padrão oficial)

> Localização: `apps/accounts/tests/factories.py`
> Implementadas na Fase 10 (Issue #23).

| Factory | Comportamento |
|---|---|
| `UserFactory` | Cria usuário básico sem role |
| `RoleFactory` | Cria role com group associado |
| `UserRoleFactory` | Associa usuário a role e **dispara `sync_user_permissions` automaticamente** no `_after_create` |
| `UserPermissionOverrideFactory` | Cria override (`grant`/`revoke`) e **dispara `sync_user_permissions` automaticamente** no `_after_create` |
| `PermissionFactory` | Cria `auth.Permission` do Django para uso em overrides e testes |

> **Garantia**: ao sair de `UserRoleFactory.create()` ou `UserPermissionOverrideFactory.create()`,
> `auth_user_user_permissions` já está populado. **Não é necessário chamar sync manualmente no `setUp`.**

---

## Suíte de testes de permissões

### `test_permissions_suite.py` (Fase 9 — Issue #22)

Arquivo principal com 24 casos obrigatórios em 6 classes:

| Classe | Foco | Casos |
|---|---|---|
| `TestServicePermissions` | `sync_user_permissions` escreve, recalcula, remove e é idempotente | 6/6 ✅ |
| `TestOverridePermissions` | `grant`/`revoke` adicionam/removem, sem duplicidade, revertem ao deletar | 6/6 ✅ |
| `TestOverlapPermissions` | União de roles, remoção parcial e total de origens | 3/3 ✅ |
| `TestAPIPermissions` | `/me/permissions/` reflete role e override em tempo real | 5/5 ✅ |
| `TestStructuralIntegration` | Signals `m2m_changed` em `Group.permissions`, `post_save` em `Role` | 3/3 ✅ |
| `TestNegativePermissions` | Bloqueio via `can()`, Group sem role, isolamento `auth_user_groups` (ADR-PERM-01) | 3/3 ✅ |

### Demais arquivos de teste de permissões

| Arquivo | Fase | Casos |
|---|---|---|
| `test_permission_overrides.py` | Fase 4 (Issue #17) | 17 testes de override |
| `test_permission_sync_integration.py` | Fase 5 (Issue #18) | 11 testes de integração |
| `test_management_command.py` | Fase 11 (Issue #24) | Testes do `recompute_user_permissions` |
| `test_fase12_token_blacklist_cleanup.py` | Fase 12 (Issue #25) | 11 testes de limpeza de resíduos |

---

## Tipos de testes (jobs de CI)

### Auth
- Arquivo: `test_multi_cookie.py`
- Escopo: middleware e autenticação (cookie `gpp_session`)

### Policies
- Diretório: `tests/policies/`
- Escopo: regras RBAC e controle de acesso

### Full
- Executa **toda a suíte** (749+ testes)
- Único responsável por validar a cobertura global
- Threshold: **≥ 80%** (atual: **≥ 92.37%**)

> **Atenção**: testes parciais (auth/policies) **NÃO representam cobertura total**.
> A cobertura oficial é validada apenas no job **Full**.

---

## Regras de teste para o sistema de permissões

1. **Use factories, nunca crie manualmente** — `UserRoleFactory` e `UserPermissionOverrideFactory` garantem `auth_user_user_permissions` populado na criação.
2. **Não popule `auth_user_groups`** em fixtures ou `setUp` — viola ADR-PERM-01.
3. **Use `sync_user_permissions(user)` antes do assert** em testes que não usam factories, para garantir estado consistente.
4. **Testes de permissão são transacionais** — cada teste deve criar seu próprio estado; nunca depender de estado de outro teste.
5. **Mocking de sync**: ao usar `mocker.patch`, importe explicitamente de `apps.accounts.services.permission_sync` (corrige `AttributeError` documentado na Fase 6).

---

## Referências

- [`apps/accounts/tests/factories.py`](../apps/accounts/tests/factories.py) — factories oficiais
- [`apps/accounts/tests/test_permissions_suite.py`](../apps/accounts/tests/test_permissions_suite.py) — suíte principal
- [`docs/PERMISSIONS_ARCHITECTURE.md`](./PERMISSIONS_ARCHITECTURE.md) — arquitetura completa de permissões
