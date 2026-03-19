"""
Testes unitários dos métodos INTERNOS do AuthorizationService.

Cobre os blocos descobertos nas linhas 142–254 de authorization_service.py:
  - _is_portal_admin()         linhas 142–154
  - _has_valid_role()          linhas 156–158
  - _check_abac()              linhas 160–173
  - _load_permissions()        linhas 187–214
  - _load_roles()              linhas 216–237
  - _load_attributes()         linhas 239–249
  - _permissions_cache_key()   linhas 251–254
  - Delegações UserPolicy      linhas 112–133

Regras:
  - pytest puro — sem unittest.TestCase, sem herança de Django TestCase
  - sem model_bakery
  - @pytest.mark.django_db apenas onde há acesso real ao banco
  - MagicMock para isolar camadas sem banco
"""
from unittest.mock import MagicMock, patch, call

import pytest

from apps.accounts.services.authorization_service import AuthorizationService


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _user(uid=1, authenticated=True):
    u = MagicMock()
    u.id = uid
    u.is_authenticated = authenticated
    return u


def _app(codigo="APP_TEST"):
    a = MagicMock()
    a.codigointerno = codigo
    return a


# ─── _is_portal_admin() ───────────────────────────────────────────────────────

class TestIsPortalAdmin:

    @pytest.mark.django_db
    def test_returns_true_when_userrole_portal_admin_exists(self, django_user_model):
        from apps.accounts.models import Aplicacao, Role, UserRole

        user = django_user_model.objects.create_user(
            username="pa_user_intern", password="pass"
        )
        app, _ = Aplicacao.objects.get_or_create(
            codigointerno="PORTAL_TEST_INTERN",
            defaults={"nomeaplicacao": "Portal Test Intern"},
        )
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="PORTAL_ADMIN",
            defaults={"nomeperfil": "Portal Admin"},
        )
        UserRole.objects.create(user=user, aplicacao=app, role=role)

        service = AuthorizationService(user)
        assert service._is_portal_admin() is True

    @pytest.mark.django_db
    def test_returns_false_when_no_portal_admin_role(self, django_user_model):
        user = django_user_model.objects.create_user(
            username="regular_intern", password="pass"
        )
        service = AuthorizationService(user)
        assert service._is_portal_admin() is False

    def test_caches_result_in_instance(self):
        """Segunda chamada não deve consultar o banco — usa self._is_admin."""
        service = AuthorizationService(_user())
        service._is_admin = True
        with patch("apps.accounts.models.UserRole") as mock_ur:
            result = service._is_portal_admin()
        mock_ur.objects.filter.assert_not_called()
        assert result is True

    def test_caches_false_result_in_instance(self):
        service = AuthorizationService(_user())
        service._is_admin = False
        with patch("apps.accounts.models.UserRole") as mock_ur:
            result = service._is_portal_admin()
        mock_ur.objects.filter.assert_not_called()
        assert result is False


# ─── _has_valid_role() ────────────────────────────────────────────────────────

class TestHasValidRole:

    def test_returns_true_when_roles_not_empty(self):
        service = AuthorizationService(_user())
        with patch.object(service, "_load_roles", return_value=[MagicMock()]):
            assert service._has_valid_role() is True

    def test_returns_false_when_roles_empty(self):
        service = AuthorizationService(_user())
        with patch.object(service, "_load_roles", return_value=[]):
            assert service._has_valid_role() is False


# ─── _check_abac() ────────────────────────────────────────────────────────────

class TestCheckAbac:

    def test_passes_when_all_attributes_match(self):
        service = AuthorizationService(_user())
        with patch.object(service, "_load_attributes", return_value={"eixo": "A", "orgao": "SEGES"}):
            assert service._check_abac("view_acao", {"eixo": "A", "orgao": "SEGES"}) is True

    def test_fails_when_attribute_value_differs(self):
        service = AuthorizationService(_user())
        with patch.object(service, "_load_attributes", return_value={"eixo": "B"}):
            assert service._check_abac("view_acao", {"eixo": "A"}) is False

    def test_fails_when_attribute_key_missing(self):
        service = AuthorizationService(_user())
        with patch.object(service, "_load_attributes", return_value={}):
            assert service._check_abac("view_acao", {"eixo": "A"}) is False

    def test_type_coercion_str_vs_int_matches(self):
        """Valores são comparados como str — '1' deve casar com 1."""
        service = AuthorizationService(_user())
        with patch.object(service, "_load_attributes", return_value={"nivel": "1"}):
            assert service._check_abac("view_acao", {"nivel": 1}) is True

    def test_type_coercion_int_attribute_vs_str_context(self):
        service = AuthorizationService(_user())
        with patch.object(service, "_load_attributes", return_value={"nivel": 2}):
            assert service._check_abac("view_acao", {"nivel": "2"}) is True

    def test_passes_with_multiple_keys_all_matching(self):
        service = AuthorizationService(_user())
        attrs = {"eixo": "A", "orgao": "SEGES", "nivel": "3"}
        with patch.object(service, "_load_attributes", return_value=attrs):
            assert service._check_abac("view_acao", {"eixo": "A", "nivel": "3"}) is True

    def test_fails_on_first_mismatching_key_in_multi_key_context(self):
        service = AuthorizationService(_user())
        attrs = {"eixo": "A", "orgao": "OUTRO"}
        with patch.object(service, "_load_attributes", return_value=attrs):
            assert service._check_abac("view_acao", {"eixo": "A", "orgao": "SEGES"}) is False


# ─── _load_roles() ────────────────────────────────────────────────────────────

class TestLoadRoles:

    def test_instance_cache_returns_same_object(self):
        service = AuthorizationService(_user())
        expected = [MagicMock()]
        service._roles = expected
        result = service._load_roles()
        assert result is expected

    @pytest.mark.django_db
    def test_loads_roles_without_application_filter(self, django_user_model):
        from apps.accounts.models import Aplicacao, Role, UserRole

        user = django_user_model.objects.create_user(
            username="roles_no_app_filter", password="pass"
        )
        app, _ = Aplicacao.objects.get_or_create(
            codigointerno="APP_ROLES_NO_FILTER",
            defaults={"nomeaplicacao": "App Roles No Filter"},
        )
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="USER_NF",
            defaults={"nomeperfil": "User NF"},
        )
        UserRole.objects.create(user=user, aplicacao=app, role=role)

        service = AuthorizationService(user)  # sem application
        roles = service._load_roles()
        assert len(roles) >= 1
        assert all(ur.user_id == user.pk for ur in roles)

    @pytest.mark.django_db
    def test_loads_roles_with_application_filter(self, django_user_model):
        from apps.accounts.models import Aplicacao, Role, UserRole

        user = django_user_model.objects.create_user(
            username="roles_app_filter", password="pass"
        )
        app_a, _ = Aplicacao.objects.get_or_create(
            codigointerno="APP_FILTER_A",
            defaults={"nomeaplicacao": "App Filter A"},
        )
        app_b, _ = Aplicacao.objects.get_or_create(
            codigointerno="APP_FILTER_B",
            defaults={"nomeaplicacao": "App Filter B"},
        )
        role_a, _ = Role.objects.get_or_create(
            aplicacao=app_a, codigoperfil="USER_FA", defaults={"nomeperfil": "User FA"}
        )
        role_b, _ = Role.objects.get_or_create(
            aplicacao=app_b, codigoperfil="USER_FB", defaults={"nomeperfil": "User FB"}
        )
        UserRole.objects.create(user=user, aplicacao=app_a, role=role_a)
        UserRole.objects.create(user=user, aplicacao=app_b, role=role_b)

        service = AuthorizationService(user, application=app_a)
        roles = service._load_roles()
        assert all(ur.aplicacao_id == app_a.pk for ur in roles)

    @pytest.mark.django_db
    def test_returns_empty_list_when_no_roles(self, django_user_model):
        user = django_user_model.objects.create_user(
            username="roles_empty_user", password="pass"
        )
        service = AuthorizationService(user)
        assert service._load_roles() == []


# ─── _load_permissions() ─────────────────────────────────────────────────────

class TestLoadPermissions:

    def test_instance_cache_returns_same_object(self):
        service = AuthorizationService(_user())
        expected = {"view_acao", "add_acao"}
        service._permissions = expected
        result = service._load_permissions()
        assert result is expected

    def test_returns_from_external_cache_when_hit(self):
        service = AuthorizationService(_user())
        cached_perms = {"cached_perm"}
        with patch(
            "apps.accounts.services.authorization_service.cache"
        ) as mock_cache:
            mock_cache.get.return_value = cached_perms
            with patch.object(service, "_permissions_cache_key", return_value="k"):
                result = service._load_permissions()
        assert result == cached_perms
        assert service._permissions is cached_perms

    def test_returns_empty_set_when_no_groups(self):
        """Roles sem group_id → permissions = set vazio, sem consulta ao banco."""
        service = AuthorizationService(_user())
        role_mock = MagicMock()
        role_mock.role.group_id = None
        with patch(
            "apps.accounts.services.authorization_service.cache"
        ) as mock_cache:
            mock_cache.get.return_value = None
            with patch.object(service, "_permissions_cache_key", return_value="k"), \
                 patch.object(service, "_load_roles", return_value=[role_mock]):
                result = service._load_permissions()
        assert result == set()
        mock_cache.set.assert_called_once()

    @pytest.mark.django_db
    def test_loads_permissions_from_group(self, django_user_model):
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType
        from apps.accounts.models import Aplicacao, Role, UserRole
        from django.core.cache import cache as real_cache

        user = django_user_model.objects.create_user(
            username="perm_load_user", password="pass"
        )
        app, _ = Aplicacao.objects.get_or_create(
            codigointerno="APP_PERM_LOAD",
            defaults={"nomeaplicacao": "App Perm Load"},
        )
        group = Group.objects.create(name="group_perm_load_test")
        ct = ContentType.objects.first()
        perm = Permission.objects.create(
            codename="test_perm_load",
            name="Test Perm Load",
            content_type=ct,
        )
        group.permissions.add(perm)
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="PERM_LOAD_ROLE",
            defaults={"nomeperfil": "Perm Load Role", "group": group},
        )
        role.group = group
        role.save()
        UserRole.objects.create(user=user, aplicacao=app, role=role)

        real_cache.delete(f"authz_version:{user.id}")
        service = AuthorizationService(user)
        perms = service._load_permissions()
        assert "test_perm_load" in perms


# ─── _load_attributes() ──────────────────────────────────────────────────────

class TestLoadAttributes:

    def test_instance_cache_returns_same_object(self):
        service = AuthorizationService(_user())
        expected = {"eixo": "X"}
        service._attributes = expected
        result = service._load_attributes()
        assert result is expected

    @pytest.mark.django_db
    def test_loads_attributes_without_app_filter(self, django_user_model):
        from apps.accounts.models import Attribute

        user = django_user_model.objects.create_user(
            username="attr_no_filter", password="pass"
        )
        Attribute.objects.create(user=user, key="eixo", value="A")
        Attribute.objects.create(user=user, key="orgao", value="SEGES")

        service = AuthorizationService(user)
        attrs = service._load_attributes()
        assert attrs["eixo"] == "A"
        assert attrs["orgao"] == "SEGES"

    @pytest.mark.django_db
    def test_loads_attributes_with_app_filter(self, django_user_model):
        from apps.accounts.models import Aplicacao, Attribute

        user = django_user_model.objects.create_user(
            username="attr_app_filter", password="pass"
        )
        app_a, _ = Aplicacao.objects.get_or_create(
            codigointerno="APP_ATTR_A",
            defaults={"nomeaplicacao": "App Attr A"},
        )
        app_b, _ = Aplicacao.objects.get_or_create(
            codigointerno="APP_ATTR_B",
            defaults={"nomeaplicacao": "App Attr B"},
        )
        Attribute.objects.create(user=user, aplicacao=app_a, key="eixo", value="X")
        Attribute.objects.create(user=user, aplicacao=app_b, key="eixo", value="Y")

        service = AuthorizationService(user, application=app_a)
        attrs = service._load_attributes()
        assert attrs.get("eixo") == "X"

    @pytest.mark.django_db
    def test_returns_empty_dict_when_no_attributes(self, django_user_model):
        user = django_user_model.objects.create_user(
            username="attr_empty_user", password="pass"
        )
        service = AuthorizationService(user)
        assert service._load_attributes() == {}


# ─── _permissions_cache_key() ─────────────────────────────────────────────────

class TestPermissionsCacheKey:

    def test_key_contains_user_id(self):
        service = AuthorizationService(_user(uid=77))
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            key = service._permissions_cache_key()
        assert "77" in key

    def test_key_contains_app_code(self):
        service = AuthorizationService(_user(uid=5), _app("MY_APP"))
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            key = service._permissions_cache_key()
        assert "MY_APP" in key

    def test_key_uses_all_when_no_app(self):
        service = AuthorizationService(_user(uid=5))
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            key = service._permissions_cache_key()
        assert "all" in key

    def test_key_uses_version_fallback_1(self):
        service = AuthorizationService(_user(uid=10))
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = None  # versão ausente → fallback 1
            key = service._permissions_cache_key()
        assert ":v1:" in key

    def test_key_uses_version_from_cache(self):
        service = AuthorizationService(_user(uid=10))
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = 7
            key = service._permissions_cache_key()
        assert ":v7:" in key

    def test_different_users_produce_different_keys(self):
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            key_a = AuthorizationService(_user(uid=1))._permissions_cache_key()
            key_b = AuthorizationService(_user(uid=2))._permissions_cache_key()
        assert key_a != key_b

    def test_different_apps_produce_different_keys(self):
        u = _user(uid=1)
        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            key_a = AuthorizationService(u, _app("A"))._permissions_cache_key()
            key_b = AuthorizationService(u, _app("B"))._permissions_cache_key()
        assert key_a != key_b


# ─── Delegações UserPolicy ────────────────────────────────────────────────────

class TestUserPolicyDelegations:
    """
    Garante que os métodos delegados chamam exatamente o método
    correspondente de UserPolicy — sem tocar no banco.
    """

    def _service_with_policy_mock(self):
        service = AuthorizationService(_user())
        policy_mock = MagicMock()
        service._user_policy = policy_mock
        return service, policy_mock

    def test_user_can_create_users_delegates(self):
        service, policy = self._service_with_policy_mock()
        policy.can_create_user.return_value = True
        assert service.user_can_create_users() is True
        policy.can_create_user.assert_called_once()

    def test_user_can_edit_users_delegates(self):
        service, policy = self._service_with_policy_mock()
        policy.can_edit_user.return_value = False
        assert service.user_can_edit_users() is False
        policy.can_edit_user.assert_called_once()

    def test_user_can_create_user_in_application_delegates(self):
        service, policy = self._service_with_policy_mock()
        aplicacao = MagicMock()
        policy.can_create_user_in_application.return_value = True
        result = service.user_can_create_user_in_application(aplicacao)
        assert result is True
        policy.can_create_user_in_application.assert_called_once_with(aplicacao)

    def test_user_can_edit_target_user_delegates(self):
        service, policy = self._service_with_policy_mock()
        target = MagicMock()
        policy.can_edit_target_user.return_value = False
        result = service.user_can_edit_target_user(target)
        assert result is False
        policy.can_edit_target_user.assert_called_once_with(target)

    def test_user_can_manage_target_user_delegates(self):
        service, policy = self._service_with_policy_mock()
        target = MagicMock()
        policy.can_manage_target_user.return_value = True
        result = service.user_can_manage_target_user(target)
        assert result is True
        policy.can_manage_target_user.assert_called_once_with(target)

    def test_policy_instance_is_cached(self):
        """_policy() deve retornar sempre a mesma instância dentro do service."""
        service = AuthorizationService(_user())
        with patch("apps.accounts.policies.UserPolicy") as MockPolicy:
            MockPolicy.return_value = MagicMock()
            p1 = service._policy()
            p2 = service._policy()
        assert p1 is p2
        MockPolicy.assert_called_once()


# ─── get_permissions / get_attributes / get_roles (API pública) ───────────────

class TestPublicGetters:
    """
    get_permissions(), get_attributes() e get_roles() são wrappers diretos
    dos loaders — verificamos que delegam corretamente.
    """

    def test_get_permissions_delegates_to_load(self):
        service = AuthorizationService(_user())
        expected = {"view_x"}
        with patch.object(service, "_load_permissions", return_value=expected) as m:
            result = service.get_permissions()
        assert result is expected
        m.assert_called_once()

    def test_get_attributes_delegates_to_load(self):
        service = AuthorizationService(_user())
        expected = {"k": "v"}
        with patch.object(service, "_load_attributes", return_value=expected) as m:
            result = service.get_attributes()
        assert result is expected
        m.assert_called_once()

    def test_get_roles_delegates_to_load(self):
        service = AuthorizationService(_user())
        expected = [MagicMock()]
        with patch.object(service, "_load_roles", return_value=expected) as m:
            result = service.get_roles()
        assert result is expected
        m.assert_called_once()
