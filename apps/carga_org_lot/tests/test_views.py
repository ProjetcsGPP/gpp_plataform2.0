"""
Testes de cobertura para apps/carga_org_lot/views.py.

Estrutura:
  TestAutenticacaoBasica  — endpoints exigem autenticação (401 para anônimo)
  TestSemRole             — usuário sem role recebe 401 (login bloqueado)
  TestGestorCarga         — GESTOR_CARGA recebe 200 em list/retrieve e 501 em write
  TestPortalAdminBypass   — PORTAL_ADMIN bypassa a verificação de role
  TestLoadCargaRoles      — _load_carga_roles() consulta banco e usa cache
  TestEmptyQueryset       — _EmptyQueryset se comporta como queryset vazio
  TestCheckCargaRoleDirect — _check_carga_role() lança ou não PermissionDenied
"""
import pytest
from unittest.mock import MagicMock, patch
from rest_framework.exceptions import PermissionDenied

from apps.carga_org_lot.views import (
    _APP_CODE,
    _EmptyQueryset,
    _check_carga_role,
    _load_carga_roles,
)

CARGAS_URL = "/api/carga-org-lot/cargas/"
CARGAS_DETAIL_URL = "/api/carga-org-lot/cargas/1/"


@pytest.fixture(autouse=True)
def _clear_carga_cache():
    """Garante que _load_carga_roles() releia do banco em cada teste."""
    _load_carga_roles.cache_clear()
    yield
    _load_carga_roles.cache_clear()


# ---------------------------------------------------------------------------
# TestAutenticacaoBasica
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAutenticacaoBasica:
    """Todos os endpoints exigem autenticação — anônimo recebe 401."""

    def test_list_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.get(CARGAS_URL)
        assert resp.status_code == 401

    def test_retrieve_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.get(CARGAS_DETAIL_URL)
        assert resp.status_code == 401

    def test_create_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.post(CARGAS_URL, {}, format="json")
        assert resp.status_code == 401

    def test_update_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.put(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 401

    def test_patch_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.patch(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 401

    def test_delete_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.delete(CARGAS_DETAIL_URL)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestSemRole
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSemRole:
    """
    Usuário sem role em CARGA_ORG_LOT — acesso negado.

    O login é bloqueado pelo middleware (reason=no_role), portanto
    client_sem_role_carga é um APIClient sem credenciais e os endpoints
    retornam 401 (não autenticado).
    """

    def test_list_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.get(CARGAS_URL)
        assert resp.status_code in (401, 403)

    def test_retrieve_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.get(CARGAS_DETAIL_URL)
        assert resp.status_code in (401, 403)

    def test_create_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.post(CARGAS_URL, {}, format="json")
        assert resp.status_code in (401, 403)

    def test_update_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.put(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code in (401, 403)

    def test_patch_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.patch(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code in (401, 403)

    def test_delete_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.delete(CARGAS_DETAIL_URL)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# TestGestorCarga
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGestorCarga:
    """GESTOR_CARGA — list/retrieve retornam 200; write retorna 501."""

    def test_list_retorna_200(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.get(CARGAS_URL)
        assert resp.status_code == 200

    def test_retrieve_retorna_200(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.get(CARGAS_DETAIL_URL)
        assert resp.status_code == 200

    def test_create_retorna_501(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.post(CARGAS_URL, {}, format="json")
        assert resp.status_code == 501

    def test_update_retorna_501(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.put(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 501

    def test_patch_retorna_501(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.patch(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 501

    def test_delete_retorna_501(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.delete(CARGAS_DETAIL_URL)
        assert resp.status_code == 501


# ---------------------------------------------------------------------------
# TestPortalAdminBypass
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPortalAdminBypass:
    """PORTAL_ADMIN bypassa _check_carga_role() — is_portal_admin=True."""

    def test_portal_admin_pode_listar(self, client_portal_admin):
        resp = client_portal_admin.get(CARGAS_URL)
        assert resp.status_code == 200

    def test_portal_admin_pode_retrieve(self, client_portal_admin):
        resp = client_portal_admin.get(CARGAS_DETAIL_URL)
        assert resp.status_code == 200

    def test_portal_admin_create_retorna_501(self, client_portal_admin):
        resp = client_portal_admin.post(CARGAS_URL, {}, format="json")
        assert resp.status_code == 501

    def test_portal_admin_update_retorna_501(self, client_portal_admin):
        resp = client_portal_admin.put(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 501

    def test_portal_admin_patch_retorna_501(self, client_portal_admin):
        resp = client_portal_admin.patch(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 501

    def test_portal_admin_delete_retorna_501(self, client_portal_admin):
        resp = client_portal_admin.delete(CARGAS_DETAIL_URL)
        assert resp.status_code == 501


# ---------------------------------------------------------------------------
# TestLoadCargaRoles
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoadCargaRoles:
    """_load_carga_roles() deve retornar frozenset com a role do banco."""

    def test_retorna_frozenset(self):
        roles = _load_carga_roles()
        assert isinstance(roles, frozenset)

    def test_contem_gestor_carga(self):
        roles = _load_carga_roles()
        assert "GESTOR_CARGA" in roles

    def test_cache_hit_retorna_mesmo_objeto(self):
        r1 = _load_carga_roles()
        r2 = _load_carga_roles()
        assert r1 is r2

    def test_cache_clear_permite_nova_query(self):
        r1 = _load_carga_roles()
        _load_carga_roles.cache_clear()
        r2 = _load_carga_roles()
        assert r1 == r2


# ---------------------------------------------------------------------------
# TestEmptyQueryset
# ---------------------------------------------------------------------------

class TestEmptyQueryset:
    """_EmptyQueryset se comporta como queryset vazio."""

    def test_none_retorna_self(self):
        qs = _EmptyQueryset()
        assert qs.none() is qs

    def test_filter_retorna_self(self):
        qs = _EmptyQueryset()
        assert qs.filter(x=1) is qs

    def test_iter_retorna_vazio(self):
        assert list(_EmptyQueryset()) == []

    def test_len_retorna_zero(self):
        assert len(_EmptyQueryset()) == 0

    def test_encadeamento_none_filter(self):
        qs = _EmptyQueryset()
        assert list(qs.none().filter(x=1)) == []


# ---------------------------------------------------------------------------
# TestCheckCargaRoleDirect
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCheckCargaRoleDirect:
    """_check_carga_role() — testa o caminho direto sem HTTP."""

    def test_portal_admin_shortcircuit(self):
        """Se is_portal_admin=True, retorna sem checar roles."""
        request = MagicMock()
        request.is_portal_admin = True
        request.user_roles = []
        _check_carga_role(request)  # não deve lançar

    def test_sem_role_lanca_permission_denied(self):
        """Usuário sem nenhuma role → PermissionDenied."""
        request = MagicMock()
        request.is_portal_admin = False
        request.user_roles = []
        with pytest.raises(PermissionDenied):
            _check_carga_role(request)

    def test_role_correta_nao_lanca(self):
        """Usuário com GESTOR_CARGA → não lança PermissionDenied."""
        roles = _load_carga_roles()  # lê do banco — contém GESTOR_CARGA
        assert "GESTOR_CARGA" in roles, "GESTOR_CARGA deve estar no banco de teste"

        role_mock = MagicMock()
        role_mock.role.codigoperfil = "GESTOR_CARGA"

        request = MagicMock()
        request.is_portal_admin = False
        request.user_roles = [role_mock]
        _check_carga_role(request)  # não deve lançar
