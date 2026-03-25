"""
Testes de cobertura para AuthorizationService.

Objetivo: cobrir as linhas 49-98, 101, 104, 107, 115-118, 130, 164, 180-275
que ficaram descobertas por os testes existentes usarem mocks nas policies.

Estratégia:
  - Instanciar AuthorizationService com objetos reais do banco (sem mock)
  - Exercitar can(), _is_portal_admin(), _has_valid_role(), _check_abac(),
    _load_permissions(), _load_roles(), _load_attributes()
  - Cobrir os caminhos de cache hit e cache miss
  - Cobrir os aliases can_create_user() e can_edit_user()
  - Cobrir user_can_create_user_in_application(), user_can_edit_target_user(),
    user_can_manage_target_user() e get_user_roles_for_app()
"""
import pytest
from django.core.cache import cache

from apps.accounts.models import Aplicacao, Attribute, Role, UserRole
from apps.accounts.services.authorization_service import AuthorizationService


# ---------------------------------------------------------------------------
# TestCanUnauthenticated
# ---------------------------------------------------------------------------

class TestCanUnauthenticated:
    """can() retorna False para usuários não autenticados."""

    def test_can_returns_false_for_none_user(self, db):
        service = AuthorizationService(user=None)
        assert service.can("view_acao") is False

    def test_can_returns_false_for_anonymous(self, db):
        from django.contrib.auth.models import AnonymousUser
        service = AuthorizationService(user=AnonymousUser())
        assert service.can("view_acao") is False


# ---------------------------------------------------------------------------
# TestCanPortalAdmin
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCanPortalAdmin:
    """portal_admin tem acesso irrestrito via can()."""

    def test_portal_admin_can_any_permission(self, portal_admin):
        service = AuthorizationService(portal_admin)
        assert service.can("view_acao") is True
        assert service.can("delete_acao") is True
        assert service.can("qualquer_coisa_inventada") is True

    def test_portal_admin_cache_is_hit_on_second_call(self, portal_admin):
        service = AuthorizationService(portal_admin)
        # primeira chamada popula _is_admin
        service.can("view_acao")
        # segunda usa cache de instância (não bate no banco)
        result = service._is_portal_admin()
        assert result is True


# ---------------------------------------------------------------------------
# TestCanNoValidRole
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCanNoValidRole:
    """can() retorna False quando o usuário não tem role para a aplicação."""

    def test_user_without_role_is_denied(self, usuario_sem_role):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(usuario_sem_role, application=app)
        assert service.can("view_acao") is False

    def test_user_with_role_in_other_app_is_denied(self, gestor_carga):
        """gestor_carga tem role em CARGA_ORG_LOT mas não em ACOES_PNGI."""
        app_pngi = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_carga, application=app_pngi)
        assert service.can("view_acao") is False


# ---------------------------------------------------------------------------
# TestCanNoPermission
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCanNoPermission:
    """can() retorna False quando a permissão não está no grupo do usuário."""

    def test_user_with_role_but_no_django_permission(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        # gestor_pngi tem role GESTOR_PNGI mas o grupo não tem a permissão django
        # 'permissao_inexistente_xyz' — deve retornar False
        service = AuthorizationService(gestor_pngi, application=app)
        assert service.can("permissao_inexistente_xyz") is False


# ---------------------------------------------------------------------------
# TestCanABAC
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCanABAC:
    """_check_abac() valida atributos do usuário contra o contexto da permissão."""

    def test_abac_passes_when_attribute_matches(self, portal_admin):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        Attribute.objects.get_or_create(
            user=portal_admin,
            aplicacao=app,
            key="eixo",
            defaults={"value": "A"},
        )
        service = AuthorizationService(portal_admin, application=app)
        # portal_admin passa pelo shortcircuit — can() retorna True sem chegar no ABAC
        # Testar _check_abac() diretamente com atributo carregado
        service._load_attributes()  # popula o cache de instância
        assert service._check_abac("view_acao", {"eixo": "A"}) is True

    def test_abac_fails_when_attribute_wrong_value(self, portal_admin):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        Attribute.objects.get_or_create(
            user=portal_admin,
            aplicacao=app,
            key="eixo",
            defaults={"value": "A"},
        )
        service = AuthorizationService(portal_admin, application=app)
        service._load_attributes()
        assert service._check_abac("view_acao", {"eixo": "B"}) is False

    def test_abac_fails_when_attribute_missing(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        service._load_attributes()
        assert service._check_abac("view_acao", {"eixo_inexistente": "X"}) is False


# ---------------------------------------------------------------------------
# TestLoadPermissionsCacheHit
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoadPermissionsCacheHit:
    """_load_permissions() usa cache na segunda chamada."""

    def test_cache_miss_populates_permissions(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        cache.clear()
        service = AuthorizationService(gestor_pngi, application=app)
        perms = service._load_permissions()
        assert isinstance(perms, set)

    def test_cache_hit_returns_same_set(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        cache.clear()
        service = AuthorizationService(gestor_pngi, application=app)
        perms_first = service._load_permissions()
        # segundo call usa cache de instância (_permissions not None)
        perms_second = service._load_permissions()
        assert perms_first is perms_second

    def test_cache_hit_from_memcache(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        cache.clear()
        # primeira instância popula o cache externo
        service1 = AuthorizationService(gestor_pngi, application=app)
        service1._load_permissions()
        # segunda instância deve ler do cache externo
        service2 = AuthorizationService(gestor_pngi, application=app)
        perms = service2._load_permissions()
        assert isinstance(perms, set)

    def test_user_without_group_has_empty_permissions(self, usuario_sem_role):
        cache.clear()
        service = AuthorizationService(usuario_sem_role)
        perms = service._load_permissions()
        assert perms == set()


# ---------------------------------------------------------------------------
# TestLoadRoles
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoadRoles:
    """_load_roles() filtra por application quando fornecida."""

    def test_load_roles_without_application_returns_all(self, gestor_pngi):
        service = AuthorizationService(gestor_pngi)
        roles = service._load_roles()
        assert len(roles) >= 1

    def test_load_roles_with_application_filters(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        roles = service._load_roles()
        assert all(r.aplicacao_id == app.pk for r in roles)

    def test_load_roles_cache_hit_on_second_call(self, gestor_pngi):
        service = AuthorizationService(gestor_pngi)
        roles1 = service._load_roles()
        roles2 = service._load_roles()
        assert roles1 is roles2


# ---------------------------------------------------------------------------
# TestLoadAttributes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoadAttributes:
    """_load_attributes() retorna dict de atributos do usuário."""

    def test_returns_empty_dict_when_no_attributes(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        attrs = service._load_attributes()
        assert isinstance(attrs, dict)

    def test_returns_attributes_when_present(self, portal_admin):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        Attribute.objects.get_or_create(
            user=portal_admin,
            aplicacao=app,
            key="setor",
            defaults={"value": "RH"},
        )
        service = AuthorizationService(portal_admin, application=app)
        attrs = service._load_attributes()
        assert "setor" in attrs

    def test_load_attributes_cache_hit(self, gestor_pngi):
        service = AuthorizationService(gestor_pngi)
        attrs1 = service._load_attributes()
        attrs2 = service._load_attributes()
        assert attrs1 is attrs2


# ---------------------------------------------------------------------------
# TestGetUserRolesForApp
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGetUserRolesForApp:
    """get_user_roles_for_app() retorna UserRoles reais do banco."""

    def test_returns_userroles_for_correct_app(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi)
        roles = service.get_user_roles_for_app(app)
        assert len(roles) == 1
        assert roles[0].role.codigoperfil == "GESTOR_PNGI"

    def test_returns_empty_for_unassigned_app(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        service = AuthorizationService(gestor_pngi)
        roles = service.get_user_roles_for_app(app)
        assert roles == []


# ---------------------------------------------------------------------------
# TestUserCanAliases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserCanAliases:
    """Aliases can_create_user() e can_edit_user() delegam corretamente."""

    def test_portal_admin_can_create_user(self, portal_admin):
        service = AuthorizationService(portal_admin)
        assert service.can_create_user() is True
        assert service.can_edit_user() is True

    def test_user_without_classificacao_cannot_create(self, usuario_sem_role):
        service = AuthorizationService(usuario_sem_role)
        # ClassificacaoUsuario pk=1 tem pode_criar_usuario=False
        assert service.can_create_user() is False
        assert service.can_edit_user() is False

    def test_gestor_com_classificacao_pode_criar(self, gestor_pngi):
        # gestor_pngi usa classificacao_pk=2 (pode_criar=True, pode_editar=True)
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_create_users() is True
        assert service.user_can_edit_users() is True


# ---------------------------------------------------------------------------
# TestUserCanManageTarget
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserCanManageTarget:
    """user_can_edit_target_user() e user_can_manage_target_user() com objetos reais."""

    def test_portal_admin_can_edit_any_target(self, portal_admin, usuario_alvo):
        service = AuthorizationService(portal_admin)
        assert service.user_can_edit_target_user(usuario_alvo) is True

    def test_portal_admin_can_manage_any_target(self, portal_admin, usuario_alvo):
        service = AuthorizationService(portal_admin)
        assert service.user_can_manage_target_user(usuario_alvo) is True

    def test_user_without_edit_perm_cannot_edit_target(self, usuario_sem_role, usuario_alvo):
        service = AuthorizationService(usuario_sem_role)
        assert service.user_can_edit_target_user(usuario_alvo) is False

    def test_user_can_create_in_application(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_create_user_in_application(app) is True

    def test_user_without_role_cannot_create_in_application(self, usuario_sem_role):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(usuario_sem_role)
        assert service.user_can_create_user_in_application(app) is False


# ---------------------------------------------------------------------------
# TestGetPermissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGetPermissions:
    """get_permissions() e get_attributes() são API pública do service."""

    def test_get_permissions_returns_set(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        result = service.get_permissions()
        assert isinstance(result, set)

    def test_get_attributes_returns_dict(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        result = service.get_attributes()
        assert isinstance(result, dict)

    def test_get_roles_returns_list(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        result = service.get_roles()
        assert isinstance(result, list)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# TestPermissionsCacheKey
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPermissionsCacheKey:
    """_permissions_cache_key() gera chave consistente."""

    def test_key_includes_user_id_and_app(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi, application=app)
        key = service._permissions_cache_key()
        assert str(gestor_pngi.id) in key
        assert "ACOES_PNGI" in key

    def test_key_uses_all_when_no_application(self, gestor_pngi):
        service = AuthorizationService(gestor_pngi, application=None)
        key = service._permissions_cache_key()
        assert ":all" in key
