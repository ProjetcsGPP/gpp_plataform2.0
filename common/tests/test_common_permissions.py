"""
test_common_permissions.py
==========================
Cobre common/permissions.py (81% → meta ≥ 95%) — Issue #23 Fase 10.

Classes testadas:
  - HasRolePermission  : unauthenticated, no role, portal_admin bypass, has role
  - IsPortalAdmin      : denied, allowed

Nota: common/permissions.py re-exporta CanCreateUser e CanEditUser de
apps/core/permissions.py; essas classes já são cobertas em test_core_coverage.py.
"""
import pytest
from unittest.mock import MagicMock
from django.contrib.auth.models import AnonymousUser

from apps.accounts.tests.factories import make_user, make_role, make_user_role
from apps.accounts.models import Role
from common.permissions import HasRolePermission, IsPortalAdmin


@pytest.mark.django_db
class TestHasRolePermissionCommon:

    def test_unauthenticated_retorna_false(self):
        """Usuário não autenticado → False (linha 30)."""
        perm = HasRolePermission()
        request = MagicMock()
        request.user = AnonymousUser()
        assert perm.has_permission(request, MagicMock()) is False

    def test_sem_user_roles_retorna_false(self):
        """Usuário autenticado sem roles → False (linhas 35-39)."""
        user = make_user()
        perm = HasRolePermission()
        request = MagicMock()
        request.user = user
        request.user.is_authenticated = True
        request.is_portal_admin = False
        request.user_roles = []
        result = perm.has_permission(request, MagicMock())
        assert result is False

    def test_portal_admin_bypass_retorna_true(self):
        """is_portal_admin=True → True sem verificar roles (linha 33)."""
        user = make_user()
        perm = HasRolePermission()
        request = MagicMock()
        request.user = user
        request.user.is_authenticated = True
        request.is_portal_admin = True
        request.user_roles = []
        result = perm.has_permission(request, MagicMock())
        assert result is True

    def test_com_user_roles_retorna_true(self):
        """Usuário autenticado com roles → True."""
        user = make_user()
        role = make_role()
        perm = HasRolePermission()
        request = MagicMock()
        request.user = user
        request.user.is_authenticated = True
        request.is_portal_admin = False
        request.user_roles = [role]
        result = perm.has_permission(request, MagicMock())
        assert result is True


@pytest.mark.django_db
class TestIsPortalAdminCommon:

    def test_sem_is_portal_admin_retorna_false(self):
        """Atributo is_portal_admin ausente → False."""
        perm = IsPortalAdmin()
        request = MagicMock(spec=[])
        # spec=[] garante que getattr(request, 'is_portal_admin', False) → False
        result = perm.has_permission(request, MagicMock())
        assert result is False

    def test_com_is_portal_admin_true_retorna_true(self):
        perm = IsPortalAdmin()
        request = MagicMock()
        request.is_portal_admin = True
        result = perm.has_permission(request, MagicMock())
        assert result is True

    def test_com_is_portal_admin_false_retorna_false(self):
        perm = IsPortalAdmin()
        request = MagicMock()
        request.is_portal_admin = False
        result = perm.has_permission(request, MagicMock())
        assert result is False
