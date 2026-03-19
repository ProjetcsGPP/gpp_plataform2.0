"""
Testes de Facade — AuthorizationService → UserPolicy

Verifica que os 5 métodos de facade do AuthorizationService delegam
corretamente para os métodos correspondentes de UserPolicy, e que a
instância de UserPolicy é cacheada entre chamadas na mesma instância
do serviço.

Padrão:
- pytest puro (sem unittest.TestCase, sem herança Django)
- Sem model_bakery
- Sem banco de dados (sem @pytest.mark.django_db)
- Todos os colaboradores são MagicMock
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.services.authorization_service import AuthorizationService

POLICY_PATH = "apps.accounts.services.authorization_service.UserPolicy"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_service() -> tuple[MagicMock, AuthorizationService]:
    """Retorna (user_mock, service) prontos para uso nos testes de facade."""
    user = MagicMock()
    user.is_authenticated = True
    service = AuthorizationService(user)
    return user, service


# ─────────────────────────────────────────────────────────────────────────────
# class TestFacadeDelegation
# ─────────────────────────────────────────────────────────────────────────────

class TestFacadeDelegation:
    """
    Para cada método de facade verifica:
      - retorna True quando UserPolicy retorna True
      - retorna False quando UserPolicy retorna False
      - UserPolicy é instanciada com o user correto
      - o método de policy correspondente é chamado (com args quando aplicável)
    """

    # ── user_can_create_users ────────────────────────────────────────────────

    def test_user_can_create_users_returns_true_when_policy_returns_true(self):
        user, service = _make_service()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_create_user.return_value = True
            result = service.user_can_create_users()
        assert result is True
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_create_user.assert_called_once()

    def test_user_can_create_users_returns_false_when_policy_returns_false(self):
        user, service = _make_service()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_create_user.return_value = False
            result = service.user_can_create_users()
        assert result is False
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_create_user.assert_called_once()

    # ── user_can_edit_users ──────────────────────────────────────────────────

    def test_user_can_edit_users_returns_true_when_policy_returns_true(self):
        user, service = _make_service()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_edit_user.return_value = True
            result = service.user_can_edit_users()
        assert result is True
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_edit_user.assert_called_once()

    def test_user_can_edit_users_returns_false_when_policy_returns_false(self):
        user, service = _make_service()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_edit_user.return_value = False
            result = service.user_can_edit_users()
        assert result is False
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_edit_user.assert_called_once()

    # ── user_can_create_user_in_application ─────────────────────────────────

    def test_user_can_create_user_in_application_returns_true_when_policy_returns_true(self):
        user, service = _make_service()
        aplicacao = MagicMock()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_create_user_in_application.return_value = True
            result = service.user_can_create_user_in_application(aplicacao)
        assert result is True
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_create_user_in_application.assert_called_once_with(aplicacao)

    def test_user_can_create_user_in_application_returns_false_when_policy_returns_false(self):
        user, service = _make_service()
        aplicacao = MagicMock()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_create_user_in_application.return_value = False
            result = service.user_can_create_user_in_application(aplicacao)
        assert result is False
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_create_user_in_application.assert_called_once_with(aplicacao)

    # ── user_can_edit_target_user ────────────────────────────────────────────

    def test_user_can_edit_target_user_returns_true_when_policy_returns_true(self):
        user, service = _make_service()
        target = MagicMock()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_edit_target_user.return_value = True
            result = service.user_can_edit_target_user(target)
        assert result is True
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_edit_target_user.assert_called_once_with(target)

    def test_user_can_edit_target_user_returns_false_when_policy_returns_false(self):
        user, service = _make_service()
        target = MagicMock()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_edit_target_user.return_value = False
            result = service.user_can_edit_target_user(target)
        assert result is False
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_edit_target_user.assert_called_once_with(target)

    # ── user_can_manage_target_user ──────────────────────────────────────────

    def test_user_can_manage_target_user_returns_true_when_policy_returns_true(self):
        user, service = _make_service()
        target = MagicMock()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_manage_target_user.return_value = True
            result = service.user_can_manage_target_user(target)
        assert result is True
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_manage_target_user.assert_called_once_with(target)

    def test_user_can_manage_target_user_returns_false_when_policy_returns_false(self):
        user, service = _make_service()
        target = MagicMock()
        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_manage_target_user.return_value = False
            result = service.user_can_manage_target_user(target)
        assert result is False
        MockPolicy.assert_called_once_with(user)
        MockPolicy.return_value.can_manage_target_user.assert_called_once_with(target)


# ─────────────────────────────────────────────────────────────────────────────
# class TestPolicyCacheInstance
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyCacheInstance:
    """
    Verifica o comportamento de cache interno (_user_policy):
    a instância de UserPolicy deve ser criada apenas uma vez por instância
    de AuthorizationService, independentemente de quantos métodos de facade
    sejam chamados.
    """

    def test_policy_instance_is_reused_across_facade_calls(self):
        """
        Dois métodos de facade chamados na mesma instância de AuthorizationService
        devem instanciar UserPolicy apenas uma vez (cache via _user_policy).
        """
        user = MagicMock()
        service = AuthorizationService(user)

        with patch(POLICY_PATH) as MockPolicy:
            MockPolicy.return_value.can_create_user.return_value = True
            MockPolicy.return_value.can_edit_user.return_value = True

            service.user_can_create_users()
            service.user_can_edit_users()

        # UserPolicy deve ter sido instanciada apenas uma vez
        assert MockPolicy.call_count == 1
