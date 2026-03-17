"""
Testes de integração de delegação: garante que AuthorizationService
delega corretamente para UserPolicy sem chamar lógica duplicada.
"""

from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_user(user_id=99):
    user = MagicMock()
    user.id = user_id
    return user


# ─────────────────────────────────────────────
# Testes de delegação
# ─────────────────────────────────────────────

@patch("apps.accounts.services.authorization_service.UserPolicy")
def test_service_delegates_user_can_create_users(MockUserPolicy):
    """user_can_create_users delega para policy.can_create_user."""
    from apps.accounts.services.authorization_service import AuthorizationService

    mock_policy_instance = MagicMock()
    mock_policy_instance.can_create_user.return_value = True
    MockUserPolicy.return_value = mock_policy_instance

    user = make_user()
    service = AuthorizationService(user)
    result = service.user_can_create_users()

    MockUserPolicy.assert_called_once_with(user)
    mock_policy_instance.can_create_user.assert_called_once()
    assert result is True


@patch("apps.accounts.services.authorization_service.UserPolicy")
def test_service_delegates_user_can_edit_users(MockUserPolicy):
    """user_can_edit_users delega para policy.can_edit_user."""
    from apps.accounts.services.authorization_service import AuthorizationService

    mock_policy_instance = MagicMock()
    mock_policy_instance.can_edit_user.return_value = False
    MockUserPolicy.return_value = mock_policy_instance

    user = make_user()
    service = AuthorizationService(user)
    result = service.user_can_edit_users()

    MockUserPolicy.assert_called_once_with(user)
    mock_policy_instance.can_edit_user.assert_called_once()
    assert result is False


@patch("apps.accounts.services.authorization_service.UserPolicy")
def test_service_delegates_create_user_in_application(MockUserPolicy):
    """user_can_create_user_in_application delega para policy.can_create_user_in_application."""
    from apps.accounts.services.authorization_service import AuthorizationService

    mock_policy_instance = MagicMock()
    mock_policy_instance.can_create_user_in_application.return_value = True
    MockUserPolicy.return_value = mock_policy_instance

    user = make_user()
    aplicacao = MagicMock(codigointerno="APP1")
    service = AuthorizationService(user)
    result = service.user_can_create_user_in_application(aplicacao)

    mock_policy_instance.can_create_user_in_application.assert_called_once_with(aplicacao)
    assert result is True


@patch("apps.accounts.services.authorization_service.UserPolicy")
def test_service_delegates_edit_target_user(MockUserPolicy):
    """user_can_edit_target_user delega para policy.can_edit_target_user."""
    from apps.accounts.services.authorization_service import AuthorizationService

    mock_policy_instance = MagicMock()
    mock_policy_instance.can_edit_target_user.return_value = True
    MockUserPolicy.return_value = mock_policy_instance

    user = make_user()
    target = make_user(2)
    service = AuthorizationService(user)
    result = service.user_can_edit_target_user(target)

    mock_policy_instance.can_edit_target_user.assert_called_once_with(target)
    assert result is True


@patch("apps.accounts.services.authorization_service.UserPolicy")
def test_service_delegates_manage_target_user(MockUserPolicy):
    """user_can_manage_target_user delega para policy.can_manage_target_user."""
    from apps.accounts.services.authorization_service import AuthorizationService

    mock_policy_instance = MagicMock()
    mock_policy_instance.can_manage_target_user.return_value = False
    MockUserPolicy.return_value = mock_policy_instance

    user = make_user()
    target = make_user(2)
    service = AuthorizationService(user)
    result = service.user_can_manage_target_user(target)

    mock_policy_instance.can_manage_target_user.assert_called_once_with(target)
    assert result is False


@patch("apps.accounts.services.authorization_service.UserPolicy")
def test_service_policy_instance_is_cached(MockUserPolicy):
    """_policy() deve instanciar UserPolicy apenas uma vez por service."""
    from apps.accounts.services.authorization_service import AuthorizationService

    mock_policy_instance = MagicMock()
    mock_policy_instance.can_create_user.return_value = True
    mock_policy_instance.can_edit_user.return_value = True
    MockUserPolicy.return_value = mock_policy_instance

    user = make_user()
    service = AuthorizationService(user)
    service.user_can_create_users()
    service.user_can_edit_users()
    service.user_can_create_users()  # chamada repetida

    # UserPolicy só deve ter sido instanciada uma vez
    MockUserPolicy.assert_called_once_with(user)
