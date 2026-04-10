# App `accounts` — Identidade, Autenticação e Permissões

> **Fase 13 — Atualização de documentação (2026-04-10)**
> Alinhado ao estado final das Fases 1–12 (Issues #14–#25).
> Referência completa: [`docs/PERMISSIONS_ARCHITECTURE.md`](../../docs/PERMISSIONS_ARCHITECTURE.md)

---

## Responsabilidade

A app `accounts` é o núcleo de **identidade, autenticação e controle de acesso** da GPP Plataform 2.0. Ela gerencia:

- Autenticação por sessão Django (cookie `gpp_session`)
- Modelo de perfil de usuário (`UserProfile`)
- Atribuição de roles por aplicação (`UserRole`)
- Templates de permissão por perfil (`Role` → `auth.Group`)
- Overrides individuais de permissão (`UserPermissionOverride`)
- Materialização de permissões em `auth_user_user_permissions` via `permission_sync`
- Sessões auditáveis com revogação explícita (`AccountsSession`)

---

## Estrutura de arquivos

```
apps/accounts/
├── admin.py                    # Admin do Django para todos os models
├── apps.py                     # Configuração da app (AccountsConfig)
├── middleware.py               # AppContextMiddleware — valida sessão e injeta app_context
├── models.py                   # Todos os models: UserProfile, Role, UserRole,
│                               #   UserPermissionOverride, AccountsSession, Attribute, ...
├── serializers.py              # Todos os serializers (inclui MePermissionSerializer,
│                               #   UserPermissionOverrideSerializer)
├── signals.py                  # Gatilhos de sincronização automática de permissões
├── urls.py                     # Roteamento de endpoints da app
├── utils.py                    # Utilitários internos
├── views.py                    # ViewSets: UserRoleViewSet, UserPermissionOverrideViewSet, ...
│
├── fixtures/                   # Fixtures de dados (não populam auth_user_groups — ADR-PERM-01)
│
├── management/
│   └── commands/
│       └── recompute_user_permissions.py  # Management command de re-sync manual
│
├── migrations/
│   ├── 0009_add_userpermissionoverride.py  # Model UserPermissionOverride (Fase 3)
│   └── 0010_clean_token_blacklist_residues.py  # Limpeza de resíduos (Fase 12)
│
├── policies/
│   └── user_policy.py          # ⚠️ PENDENTE — ainda usa classificacao_usuario (Fase 14)
│
├── services/
│   ├── permission_sync.py      # Orquestrador oficial de permissões
│   └── authorization_service.py  # AuthorizationService (runtime check)
│
└── tests/
    ├── factories.py            # Factories factory_boy (padrão de teste)
    ├── test_permissions_suite.py   # 24 casos obrigatórios (Fase 9)
    ├── test_permission_overrides.py    # 17 testes de override (Fase 4)
    ├── test_permission_sync_integration.py  # 11 testes de integração (Fase 5)
    ├── test_management_command.py      # Testes do management command (Fase 11)
    ├── test_fase12_token_blacklist_cleanup.py  # 11 testes de limpeza (Fase 12)
    └── ...                     # Demais testes da suíte
```

---

## Modelo de permissões (resumo)

> Documentação completa: [`docs/PERMISSIONS_ARCHITECTURE.md`](../../docs/PERMISSIONS_ARCHITECTURE.md)

O sistema usa **RBAC com overrides individuais**:

```
Role → auth.Group → auth_group_permissions   (template institucional)
                         │
                         ▼
              sync_user_permissions()         (materialização)
                         │
                         ▼
          auth_user_user_permissions          ← ÚNICA FONTE DE VERDADE em runtime
```

### Regras fundamentais

1. **`auth_user_user_permissions`** é a única tabela consultada em runtime (ADR-PERM-01).
2. **`auth_user_groups` NÃO é populado** — grupos são usados apenas como template.
3. Toda mutação de fonte de permissão **dispara `sync_user_permissions(user)` automaticamente**.
4. Para exceções individuais, use `UserPermissionOverride` com `mode='grant'` ou `mode='revoke'`.

---

## Orquestrador: `permission_sync.py`

Arquivo: `apps/accounts/services/permission_sync.py`

| Função | Descrição |
|---|---|
| `calculate_inherited_permissions(user)` | Permissões herdadas via roles — sem gravação |
| `calculate_effective_permissions(user)` | Herança + overrides — sem gravação |
| `sync_user_permissions(user)` | **Materializa em `auth_user_user_permissions`** (idempotente, transacional) |
| `sync_users_permissions(user_ids)` | Re-sync em batch para lista de usuários |
| `sync_all_users_permissions()` | Re-sync total para todos com `UserRole` ativa |
| `sync_user_permissions_from_group()` | ⚠️ **Deprecada** — alias temporário, não usar |
| `revoke_user_permissions_from_group()` | ⚠️ **Deprecada** — alias temporário, não usar |

---

## Factories de teste (`factory_boy`)

Arquivo: `apps/accounts/tests/factories.py`

| Factory | Comportamento |
|---|---|
| `UserFactory` | Cria usuário básico sem role |
| `RoleFactory` | Cria role com group associado |
| `UserRoleFactory` | Associa usuário a role e **dispara `sync_user_permissions`** automaticamente |
| `UserPermissionOverrideFactory` | Cria override e **dispara `sync_user_permissions`** automaticamente |
| `PermissionFactory` | Cria `auth.Permission` para overrides e testes |

> Ao sair de `UserRoleFactory.create()` ou `UserPermissionOverrideFactory.create()`, `auth_user_user_permissions` já está populado. **Não é necessário chamar sync manualmente no `setUp`.**

---

## Management command

```bash
# Usuário específico
python manage.py recompute_user_permissions --user-id <ID>

# Todos os usuários com UserRole ativa
python manage.py recompute_user_permissions --all-users

# Simulação sem persistência
python manage.py recompute_user_permissions --all-users --dry-run

# Log detalhado
python manage.py recompute_user_permissions --all-users --verbose

# Modo explícito de substituição completa (padrão)
python manage.py recompute_user_permissions --all-users --strict
```

---

## Status das Fases

| Fase | Issue | Status |
|---|---|---|
| Fases 1–12 | [#14](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/14)–[#25](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/25) | ✅ Todas concluídas |
| Fase 13 — Documentação | [#26](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/26) | 🔄 Em andamento |
| **Fase 14 — Políticas de domínio** | [#27](https://github.com/ProjetcsGPP/gpp_plataform2.0/issues/27) | 🔜 Pendente |

> ⚠️ **Fase 14 pendente:** `apps/accounts/policies/user_policy.py` ainda usa `UserProfile.classificacao_usuario` para decisões de autorização — violação de ADR-PERM-01. Deve ser refatorado para `user.has_perm()` na Fase 14.
