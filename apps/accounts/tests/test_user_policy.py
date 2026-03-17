"""
Testes unitários para UserPolicy.

Estratégia:
- Mockar APENAS dependências externas (ORM / UserRole / profile)
- NUNCA mockar métodos da própria Policy
- Cobrir todos os cenários: admin, não-admin, True/False, sem classificação,
  interseção de aplicações
"""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.accounts.policies import UserPolicy


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_user(user_id=1):
    user = MagicMock()
    user.id = user_id
    return user


def make_classificacao(pode_criar=False, pode_editar=False, pk=10, descricao="Gestor"):
    cl = MagicMock()
    cl.pode_criar_usuario = pode_criar
    cl.pode_editar_usuario = pode_editar
    cl.pk = pk
    cl.strdescricao = descricao
    return cl


# ─────────────────────────────────────────────
# can_create_user
# ─────────────────────────────────────────────

@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_user_portal_admin(MockUserRole):
    """Portal admin sempre pode criar usuário."""
    MockUserRole.objects.filter.return_value.exists.return_value = True
    user = make_user()
    policy = UserPolicy(user)
    assert policy.can_create_user() is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_user_no_classificacao(MockUserRole):
    """Sem classificação, não pode criar."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    user.profile.classificacao_usuario = None
    # força AttributeError no acesso ao profile para garantir o caminho None
    type(user).profile = PropertyMock(side_effect=AttributeError)
    policy = UserPolicy(user)
    assert policy.can_create_user() is False


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_user_classificacao_true(MockUserRole):
    """Classificação com pode_criar=True retorna True."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    user.profile.classificacao_usuario = make_classificacao(pode_criar=True)
    policy = UserPolicy(user)
    assert policy.can_create_user() is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_user_classificacao_false(MockUserRole):
    """Classificação com pode_criar=False retorna False."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    user.profile.classificacao_usuario = make_classificacao(pode_criar=False)
    policy = UserPolicy(user)
    assert policy.can_create_user() is False


# ─────────────────────────────────────────────
# can_edit_user
# ─────────────────────────────────────────────

@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_user_portal_admin(MockUserRole):
    """Portal admin sempre pode editar usuário."""
    MockUserRole.objects.filter.return_value.exists.return_value = True
    user = make_user()
    policy = UserPolicy(user)
    assert policy.can_edit_user() is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_user_no_classificacao(MockUserRole):
    """Sem classificação, não pode editar."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    type(user).profile = PropertyMock(side_effect=AttributeError)
    policy = UserPolicy(user)
    assert policy.can_edit_user() is False


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_user_classificacao_true(MockUserRole):
    """Classificação com pode_editar=True retorna True."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    user.profile.classificacao_usuario = make_classificacao(pode_editar=True)
    policy = UserPolicy(user)
    assert policy.can_edit_user() is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_user_classificacao_false(MockUserRole):
    """Classificação com pode_editar=False retorna False."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    user.profile.classificacao_usuario = make_classificacao(pode_editar=False)
    policy = UserPolicy(user)
    assert policy.can_edit_user() is False


# ─────────────────────────────────────────────
# can_create_user_in_application
# ─────────────────────────────────────────────

@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_in_app_portal_admin(MockUserRole):
    """Portal admin sempre pode criar em qualquer app."""
    MockUserRole.objects.filter.return_value.exists.return_value = True
    user = make_user()
    policy = UserPolicy(user)
    aplicacao = MagicMock(codigointerno="APP1")
    assert policy.can_create_user_in_application(aplicacao) is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_in_app_no_create_permission(MockUserRole):
    """
    Sem permissão geral de criar usuário, não pode criar na app.
    O mock precisa retornar False para _is_portal_admin E para has_role.
    """
    # Primeiro filter = _is_portal_admin (False), segundo = has_role
    user = make_user()
    type(user).profile = PropertyMock(side_effect=AttributeError)

    mock_filter = MagicMock()
    mock_filter.exists.return_value = False
    MockUserRole.objects.filter.return_value = mock_filter

    policy = UserPolicy(user)
    aplicacao = MagicMock(codigointerno="APP1")
    assert policy.can_create_user_in_application(aplicacao) is False


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_create_in_app_has_role(MockUserRole):
    """Com permissão de criar E role na app, retorna True."""
    user = make_user()
    user.profile.classificacao_usuario = make_classificacao(pode_criar=True)

    call_count = [0]

    def side_effect(**kwargs):
        call_count[0] += 1
        mock = MagicMock()
        # 1º call: _is_portal_admin → False
        # 2º call: has_role in app → True
        mock.exists.return_value = call_count[0] != 1
        return mock

    MockUserRole.objects.filter.side_effect = side_effect

    policy = UserPolicy(user)
    aplicacao = MagicMock(codigointerno="APP1")
    assert policy.can_create_user_in_application(aplicacao) is True


# ─────────────────────────────────────────────
# can_edit_target_user / can_manage_target_user
# ─────────────────────────────────────────────

@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_target_user_portal_admin(MockUserRole):
    """Portal admin pode editar qualquer usuário."""
    MockUserRole.objects.filter.return_value.exists.return_value = True
    user = make_user(1)
    target = make_user(2)
    policy = UserPolicy(user)
    assert policy.can_edit_target_user(target) is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_target_user_no_edit_permission(MockUserRole):
    """Sem permissão de editar usuário, não pode editar target."""
    user = make_user(1)
    type(user).profile = PropertyMock(side_effect=AttributeError)
    MockUserRole.objects.filter.return_value.exists.return_value = False
    target = make_user(2)
    policy = UserPolicy(user)
    assert policy.can_edit_target_user(target) is False


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_target_user_with_intersection(MockUserRole):
    """Com permissão de editar E interseção de apps, retorna True."""
    user = make_user(1)
    target = make_user(2)
    user.profile.classificacao_usuario = make_classificacao(pode_editar=True)

    call_count = [0]

    def side_effect(**kwargs):
        call_count[0] += 1
        mock = MagicMock()
        # 1º: _is_portal_admin → False
        # 2º: _get_user_applications values_list (retorna queryset iterável)
        # 3º: _has_application_intersection → True
        if call_count[0] == 1:
            mock.exists.return_value = False
        elif call_count[0] == 2:
            mock.values_list.return_value = [10, 20]
        else:
            mock.exists.return_value = True
        return mock

    MockUserRole.objects.filter.side_effect = side_effect

    policy = UserPolicy(user)
    assert policy.can_edit_target_user(target) is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_edit_target_user_no_intersection(MockUserRole):
    """Com permissão de editar MAS sem interseção de apps, retorna False."""
    user = make_user(1)
    target = make_user(2)
    user.profile.classificacao_usuario = make_classificacao(pode_editar=True)

    call_count = [0]

    def side_effect(**kwargs):
        call_count[0] += 1
        mock = MagicMock()
        if call_count[0] == 1:
            mock.exists.return_value = False
        elif call_count[0] == 2:
            mock.values_list.return_value = [10, 20]
        else:
            mock.exists.return_value = False
        return mock

    MockUserRole.objects.filter.side_effect = side_effect

    policy = UserPolicy(user)
    assert policy.can_edit_target_user(target) is False


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_manage_target_user_portal_admin(MockUserRole):
    """Portal admin pode gerenciar qualquer usuário."""
    MockUserRole.objects.filter.return_value.exists.return_value = True
    user = make_user(1)
    target = make_user(2)
    policy = UserPolicy(user)
    assert policy.can_manage_target_user(target) is True


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_manage_target_user_no_edit_permission(MockUserRole):
    """Sem permissão de editar, não pode gerenciar."""
    user = make_user(1)
    type(user).profile = PropertyMock(side_effect=AttributeError)
    MockUserRole.objects.filter.return_value.exists.return_value = False
    target = make_user(2)
    policy = UserPolicy(user)
    assert policy.can_manage_target_user(target) is False


@patch("apps.accounts.policies.user_policy.UserRole")
def test_can_manage_target_user_with_intersection(MockUserRole):
    """Com permissão de editar E interseção de apps, pode gerenciar."""
    user = make_user(1)
    target = make_user(2)
    user.profile.classificacao_usuario = make_classificacao(pode_editar=True)

    call_count = [0]

    def side_effect(**kwargs):
        call_count[0] += 1
        mock = MagicMock()
        if call_count[0] == 1:
            mock.exists.return_value = False
        elif call_count[0] == 2:
            mock.values_list.return_value = [10]
        else:
            mock.exists.return_value = True
        return mock

    MockUserRole.objects.filter.side_effect = side_effect

    policy = UserPolicy(user)
    assert policy.can_manage_target_user(target) is True


# ─────────────────────────────────────────────
# Cache de instância de _is_portal_admin
# ─────────────────────────────────────────────

@patch("apps.accounts.policies.user_policy.UserRole")
def test_is_portal_admin_cached(MockUserRole):
    """O ORM deve ser consultado apenas uma vez por instância."""
    MockUserRole.objects.filter.return_value.exists.return_value = False
    user = make_user()
    type(user).profile = PropertyMock(side_effect=AttributeError)
    policy = UserPolicy(user)

    policy.can_create_user()
    policy.can_edit_user()
    policy.can_create_user()

    # UserRole.objects.filter só deve ter sido chamado 1x para _is_portal_admin
    assert MockUserRole.objects.filter.call_count == 1
