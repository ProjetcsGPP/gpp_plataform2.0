"""
Testes para apps/carga_org_lot/views.py.

Objetivo:
  - Cobrir as 49% de linhas descobertas do módulo (51% → ~85%)
  - Testar autenticação básica em todos os endpoints (GET list/retrieve,
    POST, PUT, PATCH, DELETE)
  - Testar a matriz de roles: GESTOR_CARGA passa, sem-role retorna 403,
    anônimo retorna 401/403
  - Cobrir o branch portal_admin bypass em _check_carga_role()
  - Cobrir _load_carga_roles() e seu lru_cache
  - Cobrir todos os métodos do _EmptyQueryset

Estratégia:
  - Autenticação real via sessão Django (client_* fixtures do conftest)
  - _load_carga_roles.cache_clear() antes de cada teste para garantir
    que a query seja refeita a partir do banco de teste
  - portal_admin bypass testado via client_portal_admin do conftest de accounts
  - TestLoadCargaRoles.test_contem_gestor_carga depende de gestor_carga_lot
    para garantir que Role pk=6/GESTOR_CARGA exista no banco antes da query
"""
import pytest
from apps.carga_org_lot.views import _load_carga_roles, _EmptyQueryset

# URL base (registrada como "carga" pelo DefaultRouter)
CARGAS_URL = "/api/carga-org-lot/cargas/"
CARGAS_DETAIL_URL = "/api/carga-org-lot/cargas/1/"


@pytest.fixture(autouse=True)
def _clear_carga_cache():
    """Garante que _load_carga_roles() releia do banco em cada teste."""
    _load_carga_roles.cache_clear()
    yield
    _load_carga_roles.cache_clear()


# ---------------------------------------------------------------------------
# TestAutenticacaoBasica — 401 para anônimos
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAutenticacaoBasica:
    """Todos os endpoints exigem autenticação. Anônimos recebem 401/403."""

    def test_list_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.get(CARGAS_URL)
        assert resp.status_code in (401, 403)

    def test_retrieve_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.get(CARGAS_DETAIL_URL)
        assert resp.status_code in (401, 403)

    def test_create_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.post(CARGAS_URL, {}, format="json")
        assert resp.status_code in (401, 403)

    def test_update_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.put(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code in (401, 403)

    def test_patch_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.patch(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code in (401, 403)

    def test_delete_anonimo_negado(self, client_anonimo_carga):
        resp = client_anonimo_carga.delete(CARGAS_DETAIL_URL)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# TestSemRole — usuário autenticado sem role retorna 403
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSemRole:
    """Usuário sem role na app carga_org_lot é bloqueado em todos os métodos."""

    def test_list_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.get(CARGAS_URL)
        assert resp.status_code == 403

    def test_retrieve_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.get(CARGAS_DETAIL_URL)
        assert resp.status_code == 403

    def test_create_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.post(CARGAS_URL, {}, format="json")
        assert resp.status_code == 403

    def test_update_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.put(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 403

    def test_patch_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.patch(CARGAS_DETAIL_URL, {}, format="json")
        assert resp.status_code == 403

    def test_delete_sem_role_negado(self, client_sem_role_carga):
        resp = client_sem_role_carga.delete(CARGAS_DETAIL_URL)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestGestorCarga — GESTOR_CARGA tem acesso a todos os endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGestorCarga:
    """GESTOR_CARGA pode acessar todos os endpoints (retornos são 200 ou 501)."""

    def test_list_retorna_200(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.get(CARGAS_URL)
        assert resp.status_code == 200
        assert resp.data == []

    def test_retrieve_retorna_200(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.get(CARGAS_DETAIL_URL)
        assert resp.status_code == 200
        assert resp.data == {}

    def test_create_retorna_501(self, client_gestor_carga_lot):
        resp = client_gestor_carga_lot.post(CARGAS_URL, {}, format="json")
        assert resp.status_code == 501
        assert "detail" in resp.data

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
# TestPortalAdminBypass — portal_admin bypassa _check_carga_role()
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPortalAdminBypass:
    """
    portal_admin tem is_portal_admin=True injetado pelo middleware.
    O shortcircuit em _check_carga_role() deve deixá-lo passar.
    """

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
# TestLoadCargaRoles — cobre _load_carga_roles() e seu lru_cache
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoadCargaRoles:
    """_load_carga_roles() retorna frozenset com os codigoperfil da app."""

    def test_retorna_frozenset(self):
        roles = _load_carga_roles()
        assert isinstance(roles, frozenset)

    def test_contem_gestor_carga(self, gestor_carga_lot):
        """
        Depende de gestor_carga_lot para garantir que Role pk=6 / GESTOR_CARGA
        exista no banco antes de _load_carga_roles() executar a query.
        _ensure_base_data_carga (autouse) garante os dados base, mas a Role
        de GESTOR_CARGA é criada pelo próprio fixture gestor_carga_lot via
        _assign_role — portanto o fixture é necessário aqui.
        """
        roles = _load_carga_roles()
        assert "GESTOR_CARGA" in roles

    def test_cache_hit_retorna_mesmo_objeto(self):
        roles1 = _load_carga_roles()
        roles2 = _load_carga_roles()
        assert roles1 is roles2

    def test_cache_clear_permite_nova_query(self):
        roles1 = _load_carga_roles()
        _load_carga_roles.cache_clear()
        roles2 = _load_carga_roles()
        # Objetos diferentes mas conteúdo igual
        assert roles1 == roles2


# ---------------------------------------------------------------------------
# TestEmptyQueryset — cobre todos os métodos do _EmptyQueryset
# ---------------------------------------------------------------------------

class TestEmptyQueryset:
    """_EmptyQueryset é um placeholder que nunca acessa banco."""

    def test_none_retorna_self(self):
        qs = _EmptyQueryset()
        assert qs.none() is qs

    def test_filter_retorna_self(self):
        qs = _EmptyQueryset()
        assert qs.filter(orgao=1) is qs

    def test_iter_retorna_vazio(self):
        qs = _EmptyQueryset()
        assert list(qs) == []

    def test_len_retorna_zero(self):
        qs = _EmptyQueryset()
        assert len(qs) == 0

    def test_encadeamento_none_filter(self):
        qs = _EmptyQueryset()
        resultado = qs.none().filter(orgao=99)
        assert list(resultado) == []


# ---------------------------------------------------------------------------
# TestCheckCargaRole (unitário direto) — cobre _check_carga_role()
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCheckCargaRoleDirect:
    """
    Testa _check_carga_role() diretamente sem passar pelo stack HTTP completo,
    cobrindo o branch is_portal_admin=True (shortcircuit) e o
    branch de interseção vazia (PermissionDenied).
    """

    def test_portal_admin_shortcircuit(self):
        from unittest.mock import MagicMock
        from apps.carga_org_lot.views import _check_carga_role

        request = MagicMock()
        request.is_portal_admin = True
        request.user_roles = []
        # Não deve lançar exceção
        _check_carga_role(request)

    def test_sem_role_lanca_permission_denied(self):
        from unittest.mock import MagicMock
        from rest_framework.exceptions import PermissionDenied
        from apps.carga_org_lot.views import _check_carga_role

        request = MagicMock()
        request.is_portal_admin = False
        request.user_roles = []  # sem roles
        with pytest.raises(PermissionDenied):
            _check_carga_role(request)

    def test_role_correta_nao_lanca(self, gestor_carga_lot):
        from unittest.mock import MagicMock
        from apps.carga_org_lot.views import _check_carga_role
        from apps.accounts.models import UserRole

        user_roles = list(UserRole.objects.filter(user=gestor_carga_lot).select_related("role"))

        request = MagicMock()
        request.is_portal_admin = False
        request.user_roles = user_roles
        # Não deve lançar exceção
        _check_carga_role(request)
