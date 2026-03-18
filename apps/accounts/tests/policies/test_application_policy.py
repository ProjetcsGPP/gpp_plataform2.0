"""
Testes unitários para ApplicationPolicy.

Estratégia:
  - Mockar APENAS dependências externas (ORM / UserRole)
  - NUNCA mockar métodos da própria Policy
  - Zero banco de dados — MagicMock puro
  - Cobrir todos os cenários: privileged, regular_user, flags de app

PATCH_TARGET aponta para o import tardio dentro do módulo da policy,
identicamente ao padrão de test_user_policy.py.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.policies import ApplicationPolicy
from apps.accounts.tests.policies.conftest import (
    make_aplicacao,
    make_user,
    make_user_role,
)

PATCH_TARGET = "apps.accounts.models.UserRole"


# ── Helpers de configuração do mock ORM ──────────────────────────────────────

def _setup_portal_admin(MockUserRole, is_admin=True):
    """
    Configura o primeiro filter().exists() — usado por _is_portal_admin.
    Retorna o mock_filter para reaproveitamento quando necessário.
    """
    mock_filter = MagicMock()
    mock_filter.exists.return_value = is_admin
    MockUserRole.objects.filter.return_value = mock_filter
    return mock_filter


def _setup_call_sequence(MockUserRole, responses):
    """
    Configura respostas sequenciais para múltiplas chamadas a filter().
    responses: lista de dicts com chaves 'exists' e/ou 'first'.

    Exemplo:
        _setup_call_sequence(MockUserRole, [
            {"exists": False},   # 1ª call → _is_portal_admin
            {"first": role_mock} # 2ª call → _get_user_role_in_app
        ])
    """
    call_count = [0]

    def side_effect(**kwargs):
        idx = call_count[0]
        call_count[0] += 1
        mock = MagicMock()
        response = responses[idx] if idx < len(responses) else {}
        if "exists" in response:
            mock.exists.return_value = response["exists"]
        if "first" in response:
            mock.select_related.return_value.first.return_value = response["first"]
        return mock

    MockUserRole.objects.filter.side_effect = side_effect


# ══════════════════════════════════════════════════════════════════════════════
# can_view_application
# ══════════════════════════════════════════════════════════════════════════════

class TestCanViewApplication:

    @patch(PATCH_TARGET)
    def test_portal_admin_can_view_blocked_app(self, MockUserRole):
        """Admin vê app bloqueada — necessário para gestão."""
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(isappbloqueada=True, isappproductionready=True)
        policy = ApplicationPolicy(user, app)
        assert policy.can_view_application() is True

    @patch(PATCH_TARGET)
    def test_portal_admin_can_view_not_ready_app(self, MockUserRole):
        """Admin vê app em homologação."""
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(isappbloqueada=False, isappproductionready=False)
        policy = ApplicationPolicy(user, app)
        assert policy.can_view_application() is True

    @patch(PATCH_TARGET)
    def test_superuser_can_view_blocked_app(self, MockUserRole):
        """SuperUser tem bypass total — sem consulta ORM."""
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=True)
        app = make_aplicacao(isappbloqueada=True)
        policy = ApplicationPolicy(user, app)
        assert policy.can_view_application() is True

    @patch(PATCH_TARGET)
    def test_regular_user_with_role_can_view_ready_app(self, MockUserRole):
        """Usuário comum com role em app pronta e não bloqueada pode ver."""
        role_mock = make_user_role()
        _setup_call_sequence(MockUserRole, [
            {"exists": False},        # _is_portal_admin
            {"first": role_mock},     # _get_user_role_in_app
        ])
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=False, isappproductionready=True)
        policy = ApplicationPolicy(user, app)
        assert policy.can_view_application() is True

    @patch(PATCH_TARGET)
    def test_regular_user_cannot_view_blocked_app(self, MockUserRole, caplog):
        """App bloqueada → deny, log reason=app_blocked."""
        import logging
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=True, isappproductionready=True)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_view_application()
        assert result is False
        assert "reason=app_blocked" in caplog.text

    @patch(PATCH_TARGET)
    def test_regular_user_cannot_view_not_ready_app(self, MockUserRole, caplog):
        """App não production-ready → deny, log reason=app_not_production_ready."""
        import logging
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=False, isappproductionready=False)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_view_application()
        assert result is False
        assert "reason=app_not_production_ready" in caplog.text

    @patch(PATCH_TARGET)
    def test_regular_user_without_role_cannot_view_app(self, MockUserRole, caplog):
        """Usuário sem role na app → deny, log reason=no_role_in_app."""
        import logging
        _setup_call_sequence(MockUserRole, [
            {"exists": False},   # _is_portal_admin
            {"first": None},     # _get_user_role_in_app → None
        ])
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=False, isappproductionready=True)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_view_application()
        assert result is False
        assert "reason=no_role_in_app" in caplog.text


# ══════════════════════════════════════════════════════════════════════════════
# can_manage_application
# ══════════════════════════════════════════════════════════════════════════════

class TestCanManageApplication:

    @patch(PATCH_TARGET)
    def test_portal_admin_can_manage(self, MockUserRole):
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao()
        policy = ApplicationPolicy(user, app)
        assert policy.can_manage_application() is True

    @patch(PATCH_TARGET)
    def test_superuser_can_manage(self, MockUserRole):
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=True)
        app = make_aplicacao()
        policy = ApplicationPolicy(user, app)
        assert policy.can_manage_application() is True

    @patch(PATCH_TARGET)
    def test_regular_user_cannot_manage(self, MockUserRole, caplog):
        import logging
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao()
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_manage_application()
        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ══════════════════════════════════════════════════════════════════════════════
# can_block_application
# ══════════════════════════════════════════════════════════════════════════════

class TestCanBlockApplication:

    @patch(PATCH_TARGET)
    def test_portal_admin_can_block_regular_app(self, MockUserRole):
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(codigointerno="SIGEF")
        policy = ApplicationPolicy(user, app)
        assert policy.can_block_application() is True

    @patch(PATCH_TARGET)
    def test_superuser_can_block_regular_app(self, MockUserRole):
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=True)
        app = make_aplicacao(codigointerno="SIGEF")
        policy = ApplicationPolicy(user, app)
        assert policy.can_block_application() is True

    @patch(PATCH_TARGET)
    def test_cannot_block_portal_app(self, MockUserRole, caplog):
        """Bloqueio da app PORTAL vetado mesmo para admin — reason=cannot_block_portal_app."""
        import logging
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(codigointerno="PORTAL")
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_block_application()
        assert result is False
        assert "reason=cannot_block_portal_app" in caplog.text

    @patch(PATCH_TARGET)
    def test_regular_user_cannot_block(self, MockUserRole, caplog):
        import logging
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao(codigointerno="SIGEF")
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_block_application()
        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ══════════════════════════════════════════════════════════════════════════════
# can_assign_role_in_application
# ══════════════════════════════════════════════════════════════════════════════

class TestCanAssignRole:

    @patch(PATCH_TARGET)
    def test_portal_admin_can_assign_role_in_ready_app(self, MockUserRole):
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(isappbloqueada=False, isappproductionready=True)
        policy = ApplicationPolicy(user, app)
        assert policy.can_assign_role_in_application() is True

    @patch(PATCH_TARGET)
    def test_portal_admin_cannot_assign_role_in_blocked_app(
        self, MockUserRole, caplog
    ):
        """Admin privilegiado, mas app bloqueada → reason=app_blocked."""
        import logging
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(isappbloqueada=True, isappproductionready=True)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_assign_role_in_application()
        assert result is False
        assert "reason=app_blocked" in caplog.text

    @patch(PATCH_TARGET)
    def test_portal_admin_cannot_assign_role_in_not_ready_app(
        self, MockUserRole, caplog
    ):
        """Admin privilegiado, mas app não production-ready → reason=app_not_production_ready."""
        import logging
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(isappbloqueada=False, isappproductionready=False)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_assign_role_in_application()
        assert result is False
        assert "reason=app_not_production_ready" in caplog.text

    @patch(PATCH_TARGET)
    def test_regular_user_cannot_assign_role(self, MockUserRole, caplog):
        import logging
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=False, isappproductionready=True)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_assign_role_in_application()
        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ══════════════════════════════════════════════════════════════════════════════
# can_remove_role_from_application
# ══════════════════════════════════════════════════════════════════════════════

class TestCanRemoveRole:

    @patch(PATCH_TARGET)
    def test_portal_admin_can_remove_role_even_from_blocked_app(
        self, MockUserRole
    ):
        """Remoção de acesso possível mesmo com app bloqueada."""
        _setup_portal_admin(MockUserRole, is_admin=True)
        user = make_user()
        app = make_aplicacao(isappbloqueada=True)
        policy = ApplicationPolicy(user, app)
        assert policy.can_remove_role_from_application() is True

    @patch(PATCH_TARGET)
    def test_regular_user_cannot_remove_role(self, MockUserRole, caplog):
        import logging
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao()
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user, app)
            result = policy.can_remove_role_from_application()
        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ══════════════════════════════════════════════════════════════════════════════
# Cache de instância
# ══════════════════════════════════════════════════════════════════════════════

class TestInstanceCache:

    @patch(PATCH_TARGET)
    def test_is_portal_admin_consulted_only_once(self, MockUserRole):
        """
        ORM deve ser consultado apenas 1x por instância para _is_portal_admin,
        mesmo chamando múltiplos métodos públicos.
        """
        _setup_portal_admin(MockUserRole, is_admin=False)
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=True)  # early-return antes de role
        policy = ApplicationPolicy(user, app)

        policy.can_view_application()     # dispara _is_portal_admin
        policy.can_manage_application()   # deve usar cache
        policy.can_block_application()    # deve usar cache

        assert MockUserRole.objects.filter.call_count == 1

    @patch(PATCH_TARGET)
    def test_user_role_in_app_consulted_only_once(self, MockUserRole):
        """
        _get_user_role_in_app deve consultar ORM apenas 1x por instância.
        """
        role_mock = make_user_role()
        _setup_call_sequence(MockUserRole, [
            {"exists": False},      # _is_portal_admin (1ª call)
            {"first": role_mock},   # _get_user_role_in_app (2ª call)
        ])
        user = make_user(is_superuser=False)
        app = make_aplicacao(isappbloqueada=False, isappproductionready=True)
        policy = ApplicationPolicy(user, app)

        policy.can_view_application()  # dispara ambas as queries
        policy.can_view_application()  # segunda call — _is_admin e role em cache

        # filter chamado apenas 2x no total (1x admin + 1x role)
        assert MockUserRole.objects.filter.call_count == 2
