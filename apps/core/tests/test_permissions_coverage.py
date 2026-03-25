"""
Testes de cobertura para apps/core/permissions.py.

Objetivo: cobrir as linhas 43-50, 66-76, 96-116, 129-138, 161, 164-189,
213-232, 254-284 que ficaram descobertas por os testes existentes
testarem as permissions via middleware, não diretamente via has_permission().

Estratégia:
  - Instanciar cada classe DRF diretamente e chamar has_permission()
  - Usar request mockado com user real (não AnonymousUser) e application
    injetado em request.application
  - Usar request mockado com AnonymousUser para cobrir o path False
  - Cobrir has_object_permission() do ObjectPermission
  - Cobrir require_permission() decorator
  - Cobrir CanPermission sem required_permission definido na view
"""
import pytest
from unittest.mock import MagicMock, patch
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory

from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import Aplicacao
from apps.core.permissions import (
    CanCreateUser,
    CanEditUser,
    CanPermission,
    HasRolePermission,
    IsPortalAdmin,
    ObjectPermission,
    require_permission,
)

factory = APIRequestFactory()


def _make_request(user, application=None, path="/api/test/"):
    """Helper: cria request com user e application injetados."""
    request = factory.get(path)
    request.user = user
    request.application = application
    request.user_roles = []
    request.is_portal_admin = False
    return request


# ---------------------------------------------------------------------------
# TestHasRolePermission
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHasRolePermissionDirect:
    """Testa HasRolePermission diretamente via has_permission()."""

    def test_unauthenticated_returns_false(self):
        request = _make_request(AnonymousUser())
        perm = HasRolePermission()
        assert perm.has_permission(request, view=None) is False

    def test_user_without_role_returns_false(self, usuario_sem_role):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        request = _make_request(usuario_sem_role, application=app)
        perm = HasRolePermission()
        assert perm.has_permission(request, view=None) is False

    def test_gestor_with_role_returns_true(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        request = _make_request(gestor_pngi, application=app)
        perm = HasRolePermission()
        assert perm.has_permission(request, view=None) is True

    def test_portal_admin_returns_true(self, portal_admin):
        app = Aplicacao.objects.get(codigointerno="PORTAL")
        request = _make_request(portal_admin, application=app)
        perm = HasRolePermission()
        assert perm.has_permission(request, view=None) is True


# ---------------------------------------------------------------------------
# TestCanPermission
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCanPermissionDirect:
    """Testa CanPermission.has_permission() diretamente."""

    def test_unauthenticated_returns_false(self):
        request = _make_request(AnonymousUser())
        view = MagicMock()
        view.required_permission = "view_acao"
        perm = CanPermission()
        assert perm.has_permission(request, view) is False

    def test_without_required_permission_on_view_returns_false(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        request = _make_request(gestor_pngi, application=app)
        view = MagicMock(spec=[])  # sem atributo required_permission
        perm = CanPermission()
        assert perm.has_permission(request, view) is False

    def test_portal_admin_with_permission_returns_true(self, portal_admin):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        request = _make_request(portal_admin, application=app)
        view = MagicMock()
        view.required_permission = "view_acao"
        view.permission_context = None
        perm = CanPermission()
        assert perm.has_permission(request, view) is True

    def test_user_without_permission_returns_false(self, usuario_sem_role):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        request = _make_request(usuario_sem_role, application=app)
        view = MagicMock()
        view.required_permission = "view_acao"
        view.permission_context = None
        perm = CanPermission()
        assert perm.has_permission(request, view) is False


# ---------------------------------------------------------------------------
# TestIsPortalAdmin
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestIsPortalAdminDirect:
    """Testa IsPortalAdmin.has_permission() diretamente."""

    def test_unauthenticated_returns_false(self):
        request = _make_request(AnonymousUser())
        perm = IsPortalAdmin()
        assert perm.has_permission(request, view=None) is False

    def test_gestor_is_not_portal_admin(self, gestor_pngi):
        request = _make_request(gestor_pngi)
        perm = IsPortalAdmin()
        assert perm.has_permission(request, view=None) is False

    def test_portal_admin_is_portal_admin(self, portal_admin):
        request = _make_request(portal_admin)
        perm = IsPortalAdmin()
        assert perm.has_permission(request, view=None) is True


# ---------------------------------------------------------------------------
# TestObjectPermission
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestObjectPermissionDirect:
    """Testa ObjectPermission.has_object_permission() diretamente."""

    def test_has_permission_requires_authenticated(self):
        request = _make_request(AnonymousUser())
        perm = ObjectPermission()
        assert perm.has_permission(request, view=None) is False

    def test_has_permission_returns_true_for_authenticated(self, gestor_pngi):
        request = _make_request(gestor_pngi)
        perm = ObjectPermission()
        assert perm.has_permission(request, view=None) is True

    def test_portal_admin_passes_object_permission(self, portal_admin):
        request = _make_request(portal_admin)
        view = MagicMock()
        view.object_owner_field = "user"
        obj = MagicMock()
        obj.user = portal_admin
        perm = ObjectPermission()
        assert perm.has_object_permission(request, view, obj) is True

    def test_owner_can_access_own_object(self, gestor_pngi):
        request = _make_request(gestor_pngi)
        view = MagicMock()
        view.object_owner_field = "user"
        obj = MagicMock()
        obj.user = gestor_pngi  # mesmo usuário
        perm = ObjectPermission()
        assert perm.has_object_permission(request, view, obj) is True

    def test_user_cannot_access_other_object(self, gestor_pngi, coordenador_pngi):
        request = _make_request(gestor_pngi)
        view = MagicMock()
        view.object_owner_field = "user"
        obj = MagicMock()
        obj.user = coordenador_pngi  # dono diferente
        perm = ObjectPermission()
        assert perm.has_object_permission(request, view, obj) is False

    def test_object_permission_with_pk_field(self, gestor_pngi):
        """Cobre o branch onde owner não tem .pk (é um int)."""
        request = _make_request(gestor_pngi)
        view = MagicMock()
        view.object_owner_field = "user_id"
        obj = MagicMock()
        obj.user_id = gestor_pngi.pk  # campo de FK armazena int
        perm = ObjectPermission()
        assert perm.has_object_permission(request, view, obj) is True

    def test_unauthenticated_cannot_access_object(self):
        request = _make_request(AnonymousUser())
        view = MagicMock()
        view.object_owner_field = "user"
        perm = ObjectPermission()
        assert perm.has_object_permission(request, view, MagicMock()) is False


# ---------------------------------------------------------------------------
# TestCanCreateUser / TestCanEditUser
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCanCreateUserDirect:
    """Testa CanCreateUser.has_permission() diretamente."""

    def test_unauthenticated_returns_false(self):
        request = _make_request(AnonymousUser())
        assert CanCreateUser().has_permission(request, view=None) is False

    def test_gestor_com_classificacao_pode_criar(self, gestor_pngi):
        request = _make_request(gestor_pngi)
        assert CanCreateUser().has_permission(request, view=None) is True

    def test_usuario_padrao_nao_pode_criar(self, usuario_sem_role):
        # ClassificacaoUsuario pk=1 tem pode_criar_usuario=False
        request = _make_request(usuario_sem_role)
        assert CanCreateUser().has_permission(request, view=None) is False

    def test_portal_admin_pode_criar(self, portal_admin):
        request = _make_request(portal_admin)
        assert CanCreateUser().has_permission(request, view=None) is True


@pytest.mark.django_db
class TestCanEditUserDirect:
    """Testa CanEditUser.has_permission() diretamente."""

    def test_unauthenticated_returns_false(self):
        request = _make_request(AnonymousUser())
        assert CanEditUser().has_permission(request, view=None) is False

    def test_gestor_com_classificacao_pode_editar(self, gestor_pngi):
        request = _make_request(gestor_pngi)
        assert CanEditUser().has_permission(request, view=None) is True

    def test_usuario_padrao_nao_pode_editar(self, usuario_sem_role):
        request = _make_request(usuario_sem_role)
        assert CanEditUser().has_permission(request, view=None) is False

    def test_portal_admin_pode_editar(self, portal_admin):
        request = _make_request(portal_admin)
        assert CanEditUser().has_permission(request, view=None) is True


# ---------------------------------------------------------------------------
# TestRequirePermissionDecorator
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRequirePermissionDecorator:
    """Testa o decorator @require_permission para function-based views."""

    def test_unauthenticated_raises_permission_denied(self):
        @require_permission("view_acao")
        def fake_view(request):
            return "ok"

        request = _make_request(AnonymousUser())
        with pytest.raises(PermissionDenied):
            fake_view(request)

    def test_portal_admin_passes_decorator(self, portal_admin):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")

        @require_permission("qualquer_perm")
        def fake_view(request):
            return "ok"

        request = _make_request(portal_admin, application=app)
        result = fake_view(request)
        assert result == "ok"

    def test_user_without_permission_raises(self, usuario_sem_role):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")

        @require_permission("view_acao")
        def fake_view(request):
            return "ok"  # pragma: no cover

        request = _make_request(usuario_sem_role, application=app)
        with pytest.raises(PermissionDenied):
            fake_view(request)
