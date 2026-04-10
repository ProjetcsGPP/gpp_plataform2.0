"""
Testes do management command recompute_user_permissions (Fase 11).

Cada teste é completamente independente (sem dependência de ordem).
Usa as factories da Fase 10 (factories.py).

Nota sobre Role e permissões:
  Role não expõe .permissions diretamente.
  Permissões são associadas via role.group.permissions (auth_group_permissions),
  conforme documentado na docstring de make_role() em factories.py:
      role.group.permissions.add(perm)

Casos obrigatórios:
  1. test_all_users_recomputes_active_userrole_users
  2. test_user_id_recomputes_only_target_user
  3. test_dry_run_does_not_persist
  4. test_idempotency
  5. test_grant_override_reflected_after_recompute
  6. test_revoke_override_reflected_after_recompute
  7. test_user_without_role_has_empty_permissions
  8. test_single_user_failure_does_not_abort_batch

Edge-cases adicionais (Issue #24 — conclusão):
  9.  test_user_id_inexistente_levanta_command_error
  10. test_verbose_nao_altera_resultado
  11. test_strict_e_documental_nao_propaga_excecao
  12. test_dry_run_com_override_nao_persiste
  13. test_multiplas_roles_acumulam_permissoes

Garantias negativas (Issue #24 — conclusão):
  14. test_nunca_escreve_em_auth_user_groups
  15. test_nunca_chama_sync_user_permissions_from_group
  16. test_nunca_chama_revoke_user_permissions_from_group
  17. test_dry_run_nunca_escreve_em_auth_user_groups
"""

import io
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from unittest.mock import patch, MagicMock

from apps.accounts.services.permission_sync import sync_user_permissions
from apps.accounts.tests.factories import (
    PermissionFactory,
    RoleFactory,
    UserFactory,
    UserPermissionOverrideFactory,
    UserRoleFactory,
)

User = get_user_model()

# Todos os testes precisam de banco real (transações incluídas para dry-run)
pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _perm_pks(user):
    """Conjunto de PKs das permissões atuais do usuário (diretas)."""
    user.refresh_from_db()
    return set(user.user_permissions.values_list("pk", flat=True))


def _perm_codenames(user):
    """Conjunto de codenames das permissões atuais do usuário (diretas)."""
    user.refresh_from_db()
    return set(user.user_permissions.values_list("codename", flat=True))


# ---------------------------------------------------------------------------
# Teste 1 — --all-users processa todos com UserRole ativa
# ---------------------------------------------------------------------------

def test_all_users_recomputes_active_userrole_users():
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)  # Role expõe permissões via role.group

    user_a = UserFactory()
    user_b = UserFactory()
    UserRoleFactory(user=user_a, role=role)
    UserRoleFactory(user=user_b, role=role)

    # Limpa para garantir estado inicial sem o sync automático de signal
    user_a.user_permissions.clear()
    user_b.user_permissions.clear()

    call_command("recompute_user_permissions", all_users=True)

    assert perm in user_a.user_permissions.all(), (
        "user_a deveria ter a permissão da role após --all-users"
    )
    assert perm in user_b.user_permissions.all(), (
        "user_b deveria ter a permissão da role após --all-users"
    )


# ---------------------------------------------------------------------------
# Teste 2 — --user-id recomputa só o alvo, não altera outros
# ---------------------------------------------------------------------------

def test_user_id_recomputes_only_target_user():
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user_target = UserFactory()
    user_other = UserFactory()
    UserRoleFactory(user=user_target, role=role)
    # user_other não tem role

    # Garante que user_other começa sem permissões
    user_other.user_permissions.clear()
    before_other = _perm_pks(user_other)

    # Limpa target para verificar que o recompute adiciona via role
    user_target.user_permissions.clear()

    call_command("recompute_user_permissions", user_id=user_target.pk)

    after_other = _perm_pks(user_other)
    assert before_other == after_other, (
        "--user-id não deve alterar permissões de outros usuários"
    )
    assert perm in user_target.user_permissions.all(), (
        "O usuário alvo deve ter a permissão da role após recompute"
    )


# ---------------------------------------------------------------------------
# Teste 3 — --dry-run não persiste nada
# ---------------------------------------------------------------------------

def test_dry_run_does_not_persist():
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)

    # Garante que o usuário NÃO tem a permissão antes do dry-run
    user.user_permissions.clear()
    before = _perm_pks(user)
    assert perm.pk not in before, "Setup: usuário não deve ter a perm antes do dry-run"

    call_command("recompute_user_permissions", all_users=True, dry_run=True)

    after = _perm_pks(user)
    assert before == after, (
        "--dry-run não deve persistir nenhuma alteração em auth_user_user_permissions"
    )


# ---------------------------------------------------------------------------
# Teste 4 — Idempotência
# ---------------------------------------------------------------------------

def test_idempotency():
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)

    call_command("recompute_user_permissions", user_id=user.pk)
    state_1 = _perm_pks(user)

    call_command("recompute_user_permissions", user_id=user.pk)
    state_2 = _perm_pks(user)

    assert state_1 == state_2, (
        "Rodar o command duas vezes deve produzir o mesmo estado (idempotência)"
    )


# ---------------------------------------------------------------------------
# Teste 5 — override grant refletido após recompute
# ---------------------------------------------------------------------------

def test_grant_override_reflected_after_recompute():
    perm = PermissionFactory()
    user = UserFactory()
    # Sem UserRole — a permissão não viria por herança
    UserPermissionOverrideFactory(user=user, permission=perm, mode="grant")

    # Limpa para verificar que o recompute adiciona via override
    user.user_permissions.clear()

    call_command("recompute_user_permissions", user_id=user.pk)

    user.refresh_from_db()
    assert perm in user.user_permissions.all(), (
        "Override mode='grant' deve resultar na permissão em auth_user_user_permissions"
    )


# ---------------------------------------------------------------------------
# Teste 6 — override revoke refletido após recompute
# ---------------------------------------------------------------------------

def test_revoke_override_reflected_after_recompute():
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)  # permissão vem da role via group

    user = UserFactory()
    UserRoleFactory(user=user, role=role)
    UserPermissionOverrideFactory(user=user, permission=perm, mode="revoke")

    call_command("recompute_user_permissions", user_id=user.pk)

    user.refresh_from_db()
    assert perm not in user.user_permissions.all(), (
        "Override mode='revoke' deve remover a permissão mesmo que ela venha da role"
    )


# ---------------------------------------------------------------------------
# Teste 7 — usuário sem UserRole tem permissões vazias após recompute
# ---------------------------------------------------------------------------

def test_user_without_role_has_empty_permissions():
    user = UserFactory()
    # Sem UserRole e sem override

    # Força uma permissão direta espúria para verificar que o recompute limpa
    perm = PermissionFactory()
    user.user_permissions.add(perm)
    assert user.user_permissions.count() == 1, "Setup: usuário deve ter 1 perm espúria"

    call_command("recompute_user_permissions", user_id=user.pk)

    user.refresh_from_db()
    assert user.user_permissions.count() == 0, (
        "Usuário sem UserRole deve ter auth_user_user_permissions vazio após recompute"
    )


# ---------------------------------------------------------------------------
# Teste 8 — falha em um usuário não aborta o batch
# ---------------------------------------------------------------------------

def test_single_user_failure_does_not_abort_batch():
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)  # permissão via group da role

    user_ok = UserFactory()
    user_fail = UserFactory()
    UserRoleFactory(user=user_ok, role=role)
    UserRoleFactory(user=user_fail, role=role)

    user_ok.user_permissions.clear()
    user_fail.user_permissions.clear()

    original_sync = sync_user_permissions

    def patched_sync(user):
        if user.pk == user_fail.pk:
            raise RuntimeError("Erro simulado para teste de resiliência")
        return original_sync(user)

    target = (
        "apps.accounts.management.commands"
        ".recompute_user_permissions.sync_user_permissions"
    )

    with patch(target, side_effect=patched_sync):
        # Não deve lançar exceção — o command deve continuar após o erro
        call_command("recompute_user_permissions", all_users=True)

    # user_ok foi processado normalmente; deve ter a permissão da role
    user_ok.refresh_from_db()
    assert perm in user_ok.user_permissions.all(), (
        "user_ok deve ter sido processado normalmente mesmo com falha em user_fail"
    )


# ---------------------------------------------------------------------------
# Teste 9 — --user-id com PK inexistente LEVANTA CommandError (comportamento intencional)
# ---------------------------------------------------------------------------

def test_user_id_inexistente_levanta_command_error():
    """
    Passar um PK que não existe no banco deve levantar CommandError.
    Esse é o comportamento documentado em _resolve_users(): falha rápida
    e explícita quando o operador passa um ID inválido.
    """
    pk_inexistente = 999_999_999
    assert not User.objects.filter(pk=pk_inexistente).exists()

    with pytest.raises(CommandError, match=str(pk_inexistente)):
        call_command("recompute_user_permissions", user_id=pk_inexistente)


# ---------------------------------------------------------------------------
# Teste 10 — --verbose não altera o resultado final
# ---------------------------------------------------------------------------

def test_verbose_nao_altera_resultado():
    """
    --verbose apenas adiciona saída de log; o estado do banco deve ser
    idêntico ao de uma execução sem --verbose.
    """
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)
    user.user_permissions.clear()

    call_command("recompute_user_permissions", user_id=user.pk, verbose=True)

    user.refresh_from_db()
    assert perm in user.user_permissions.all(), (
        "--verbose não deve alterar o resultado do recompute"
    )


# ---------------------------------------------------------------------------
# Teste 11 — --strict é puramente documental: não propaga exceções
# ---------------------------------------------------------------------------

def test_strict_e_documental_nao_propaga_excecao():
    """
    --strict NÃO muda o comportamento de tratamento de erros no command atual.
    É uma flag documental que apenas emite um aviso no output indicando que
    a reconstrução é exata (herdadas + grants - revokes).

    Quando sync_user_permissions falha, o command:
      - loga o erro no stderr via self.stderr.write
      - NÃO propaga a exceção (o except genérico engole)
      - NÃO aborta o batch (processed=0 mas sem raise)

    Se --strict vier a mudar de comportamento, este teste deve ser atualizado
    junto com a docstring do command (contrato explícito).
    """
    user_fail = UserFactory()
    UserRoleFactory(user=user_fail, role=RoleFactory())

    target = (
        "apps.accounts.management.commands"
        ".recompute_user_permissions.sync_user_permissions"
    )

    stderr_capture = io.StringIO()

    # NÃO deve lançar — --strict é apenas documental no command atual
    with patch(target, side_effect=RuntimeError("Erro simulado --strict")):
        call_command(
            "recompute_user_permissions",
            all_users=True,
            strict=True,
            stderr=stderr_capture,
        )

    # O erro deve aparecer no stderr (self.stderr.write foi chamado)
    stderr_output = stderr_capture.getvalue()
    assert "ERRO" in stderr_output or str(user_fail.pk) in stderr_output, (
        "--strict deve logar o erro no stderr mesmo sem propagar a exceção"
    )


# ---------------------------------------------------------------------------
# Teste 12 — --dry-run com override grant não persiste
# ---------------------------------------------------------------------------

def test_dry_run_com_override_nao_persiste():
    """
    Mesmo que haja um override mode='grant', --dry-run não deve alterar
    auth_user_user_permissions.
    """
    perm = PermissionFactory()
    user = UserFactory()
    UserPermissionOverrideFactory(user=user, permission=perm, mode="grant")
    user.user_permissions.clear()

    before = _perm_pks(user)

    call_command("recompute_user_permissions", user_id=user.pk, dry_run=True)

    after = _perm_pks(user)
    assert before == after, (
        "--dry-run não deve persistir override grant em auth_user_user_permissions"
    )


# ---------------------------------------------------------------------------
# Teste 13 — múltiplas roles acumulam permissões (quando o modelo permite)
# ---------------------------------------------------------------------------

def test_multiplas_roles_acumulam_permissoes():
    """
    Se o usuário tiver UserRole em mais de uma aplicação, as permissões
    das duas roles devem estar presentes após o recompute.
    Cada role pertence a uma aplicação diferente (unicidade por app).
    """
    perm_a = PermissionFactory()
    perm_b = PermissionFactory()

    role_a = RoleFactory()  # aplicacao A
    role_b = RoleFactory()  # aplicacao B (diferente)
    role_a.group.permissions.add(perm_a)
    role_b.group.permissions.add(perm_b)

    user = UserFactory()
    # UserRoleFactory cria roles em aplicações distintas automaticamente
    UserRoleFactory(user=user, role=role_a)
    UserRoleFactory(user=user, role=role_b)

    user.user_permissions.clear()

    call_command("recompute_user_permissions", user_id=user.pk)

    user.refresh_from_db()
    assert perm_a in user.user_permissions.all(), (
        "Permissão da role_a deve estar presente após recompute com múltiplas roles"
    )
    assert perm_b in user.user_permissions.all(), (
        "Permissão da role_b deve estar presente após recompute com múltiplas roles"
    )


# ---------------------------------------------------------------------------
# Teste 14 — GARANTIA NEGATIVA: nunca escreve em auth_user_groups
# ---------------------------------------------------------------------------

def test_nunca_escreve_em_auth_user_groups():
    """
    O command NUNCA deve escrever em auth_user_groups (user.groups).
    Verifica que groups do usuário permanece vazio antes e depois,
    mesmo com role + override + dry_run=False.
    """
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)
    UserPermissionOverrideFactory(user=user, permission=perm, mode="grant")

    # Garante que o usuário não pertence a nenhum group antes
    user.groups.clear()
    assert user.groups.count() == 0, "Setup: user.groups deve estar vazio"

    call_command("recompute_user_permissions", user_id=user.pk)

    user.refresh_from_db()
    assert user.groups.count() == 0, (
        "recompute_user_permissions NUNCA deve escrever em auth_user_groups"
    )


# ---------------------------------------------------------------------------
# Teste 15 — GARANTIA NEGATIVA: nunca chama sync_user_permissions_from_group
# ---------------------------------------------------------------------------

def test_nunca_chama_sync_user_permissions_from_group():
    """
    O command não deve chamar sync_user_permissions_from_group (função legada).
    Qualquer chamada a essa função é uma regressão crítica de arquitetura.
    """
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)

    legacy_target = (
        "apps.accounts.services.permission_sync"
        ".sync_user_permissions_from_group"
    )

    mock_legacy = MagicMock()

    with patch(legacy_target, mock_legacy):
        call_command("recompute_user_permissions", user_id=user.pk)

    mock_legacy.assert_not_called(), (
        "recompute_user_permissions NUNCA deve chamar sync_user_permissions_from_group"
    )


# ---------------------------------------------------------------------------
# Teste 16 — GARANTIA NEGATIVA: nunca chama revoke_user_permissions_from_group
# ---------------------------------------------------------------------------

def test_nunca_chama_revoke_user_permissions_from_group():
    """
    O command não deve chamar revoke_user_permissions_from_group (função legada).
    Qualquer chamada a essa função é uma regressão crítica de arquitetura.
    """
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)
    UserPermissionOverrideFactory(user=user, permission=perm, mode="revoke")

    legacy_target = (
        "apps.accounts.services.permission_sync"
        ".revoke_user_permissions_from_group"
    )

    mock_legacy = MagicMock()

    with patch(legacy_target, mock_legacy):
        call_command("recompute_user_permissions", user_id=user.pk)

    mock_legacy.assert_not_called(), (
        "recompute_user_permissions NUNCA deve chamar revoke_user_permissions_from_group"
    )


# ---------------------------------------------------------------------------
# Teste 17 — GARANTIA NEGATIVA: --dry-run também nunca toca auth_user_groups
# ---------------------------------------------------------------------------

def test_dry_run_nunca_escreve_em_auth_user_groups():
    """
    Com --dry-run, auth_user_groups deve permanecer intocado.
    Garante que mesmo o caminho de rollback não escreve groups.
    """
    perm = PermissionFactory()
    role = RoleFactory()
    role.group.permissions.add(perm)

    user = UserFactory()
    UserRoleFactory(user=user, role=role)

    user.groups.clear()
    assert user.groups.count() == 0, "Setup: user.groups deve estar vazio"

    call_command("recompute_user_permissions", user_id=user.pk, dry_run=True)

    user.refresh_from_db()
    assert user.groups.count() == 0, (
        "--dry-run NUNCA deve escrever em auth_user_groups"
    )
