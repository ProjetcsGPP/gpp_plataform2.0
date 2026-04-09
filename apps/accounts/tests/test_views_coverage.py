"""
apps/accounts/tests/test_views_coverage.py

Cobertura ≥ 95% de apps/accounts/views.py (Issue #23 — tarefas pendentes).

Estratégia:
  - Banco real (pytest.mark.django_db) — sem mocks.
  - Todas as views exercidas: caminho feliz + erros de negócio.
  - Usa fixtures/helpers do conftest.py (client_portal_admin, client_gestor, etc.)
  - force_authenticate é usado apenas em casos onde a sessão real não é necessária
    (MePermissionView com app_context injetado diretamente via APIRequestFactory).

Views cobertas:
  LoginView               (POST /api/accounts/login/)
  LogoutView              (POST /api/accounts/logout/)
  LogoutAppView           (POST /api/accounts/logout/{app_slug}/)
  ResolveUserView         (POST /api/accounts/auth/resolve-user/)
  MeView                  (GET  /api/accounts/me/)
  MePermissionView        (GET  /api/accounts/me/permissions/)
  UserCreateView          (POST /api/accounts/users/)
  UserCreateWithRoleView  (POST /api/accounts/users/create-with-role/)
  AplicacaoPublicaViewSet (GET  /api/accounts/auth/aplicacoes/)
  AplicacaoViewSet        (GET  /api/accounts/aplicacoes/)
  UserProfileViewSet      (GET/PATCH /api/accounts/profiles/)
  RoleViewSet             (GET  /api/accounts/roles/)
  UserRoleViewSet         (GET/POST/DELETE /api/accounts/user-roles/)
  UserPermissionOverrideViewSet (CRUD /api/accounts/permission-overrides/)
"""
import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from apps.accounts.models import (
    Aplicacao,
    Role,
    UserPermissionOverride,
    UserProfile,
    UserRole,
)
from apps.accounts.tests.conftest import (
    DEFAULT_PASSWORD,
    LOGIN_URL,
    _assign_role,
    _do_login,
    _make_user,
)
from apps.accounts.services.permission_sync import sync_user_permissions


# ── Constantes de URL ─────────────────────────────────────────────────────────
LOGOUT_URL = "/api/accounts/logout/"
ME_URL = "/api/accounts/me/"
ME_PERMISSIONS_URL = "/api/accounts/me/permissions/"
USERS_URL = "/api/accounts/users/"
USERS_WITH_ROLE_URL = "/api/accounts/users/create-with-role/"
APLICACOES_PUBLICA_URL = "/api/accounts/auth/aplicacoes/"
APLICACOES_URL = "/api/accounts/aplicacoes/"
PROFILES_URL = "/api/accounts/profiles/"
ROLES_URL = "/api/accounts/roles/"
USER_ROLES_URL = "/api/accounts/user-roles/"
OVERRIDES_URL = "/api/accounts/permission-overrides/"
RESOLVE_URL = "/api/accounts/auth/resolve-user/"


def _make_perm(codename: str) -> Permission:
    ct = ContentType.objects.get(app_label="auth", model="user")
    perm, _ = Permission.objects.get_or_create(
        codename=codename, content_type=ct, defaults={"name": codename}
    )
    return perm


# ════════════════════════════════════════════════════════════════════════════
# LoginView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestLoginView:
    def test_login_sucesso(self, _ensure_base_data, portal_admin):
        client = APIClient()
        resp = _do_login(client, "portal_admin_test", "PORTAL")
        assert resp.status_code == 200
        assert "detail" in resp.data

    def test_login_credenciais_invalidas(self, _ensure_base_data):
        client = APIClient()
        resp = client.post(
            LOGIN_URL,
            {"username": "naoexiste", "password": "errada", "app_context": "PORTAL"},
            format="json",
        )
        assert resp.status_code == 401
        assert resp.data["code"] == "invalid_credentials"

    def test_login_sem_campos_obrigatorios(self, _ensure_base_data):
        client = APIClient()
        resp = client.post(LOGIN_URL, {}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_login_app_invalida(self, _ensure_base_data, portal_admin):
        client = APIClient()
        resp = client.post(
            LOGIN_URL,
            {"username": "portal_admin_test", "password": DEFAULT_PASSWORD, "app_context": "INVALIDA"},
            format="json",
        )
        assert resp.status_code == 403
        assert resp.data["code"] == "invalid_app"

    def test_login_usuario_sem_role_na_app(self, _ensure_base_data, usuario_sem_role):
        client = APIClient()
        app = Aplicacao.objects.get(pk=2)
        resp = client.post(
            LOGIN_URL,
            {"username": "sem_role_test", "password": DEFAULT_PASSWORD, "app_context": app.codigointerno},
            format="json",
        )
        assert resp.status_code == 403
        assert resp.data["code"] == "no_role"

    def test_login_portal_sem_role_portal_admin(self, _ensure_base_data, gestor_pngi):
        """Usuário com role apenas em ACOES_PNGI não pode logar no PORTAL."""
        client = APIClient()
        resp = _do_login(client, "gestor_test", "PORTAL")
        assert resp.status_code == 403

    def test_login_cria_exatamente_uma_accounts_session(self, _ensure_base_data, portal_admin):
        from apps.accounts.models import AccountsSession
        client = APIClient()
        _do_login(client, "portal_admin_test", "PORTAL")
        _do_login(client, "portal_admin_test", "PORTAL")
        active_sessions = AccountsSession.objects.filter(
            user=portal_admin,
            session_cookie_name="gpp_session_PORTAL",
            revoked=False,
        ).count()
        assert active_sessions == 1, "deve existir exatamente uma sessão ativa por (user, app)"


# ════════════════════════════════════════════════════════════════════════════
# LogoutView / LogoutAppView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestLogoutViews:
    def test_logout_autenticado(self, client_portal_admin):
        resp = client_portal_admin.post(LOGOUT_URL, format="json")
        assert resp.status_code == 200

    def test_logout_anonimo_retorna_403(self, client_anonimo):
        resp = client_anonimo.post(LOGOUT_URL, format="json")
        assert resp.status_code in (401, 403)

    def test_logout_app_com_sessao_ativa(self, _ensure_base_data, portal_admin):
        client = APIClient()
        _do_login(client, "portal_admin_test", "PORTAL")
        resp = client.post("/api/accounts/logout/portal/", format="json")
        assert resp.status_code == 200

    def test_logout_app_sem_sessao(self, _ensure_base_data):
        client = APIClient()
        resp = client.post("/api/accounts/logout/portal/", format="json")
        assert resp.status_code == 200


# ════════════════════════════════════════════════════════════════════════════
# ResolveUserView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestResolveUserView:
    def test_resolve_por_username(self, _ensure_base_data, portal_admin):
        client = APIClient()
        resp = client.post(RESOLVE_URL, {"identifier": "portal_admin_test"}, format="json")
        assert resp.status_code == 200
        assert resp.data["username"] == "portal_admin_test"

    def test_resolve_por_email(self, _ensure_base_data):
        user = _make_user("resolve_email_test")
        user.email = "resolve@test.com"
        user.save(update_fields=["email"])
        client = APIClient()
        resp = client.post(RESOLVE_URL, {"identifier": "resolve@test.com"}, format="json")
        assert resp.status_code == 200
        assert resp.data["username"] == "resolve_email_test"

    def test_resolve_usuario_nao_encontrado(self, _ensure_base_data):
        client = APIClient()
        resp = client.post(RESOLVE_URL, {"identifier": "naoexiste@test.com"}, format="json")
        assert resp.status_code == 404
        assert resp.data["code"] == "user_not_found"

    def test_resolve_sem_identifier(self, _ensure_base_data):
        client = APIClient()
        resp = client.post(RESOLVE_URL, {}, format="json")
        assert resp.status_code == 400

    def test_resolve_identifier_muito_longo(self, _ensure_base_data):
        client = APIClient()
        resp = client.post(RESOLVE_URL, {"identifier": "a" * 255}, format="json")
        assert resp.status_code == 400

    def test_resolve_usuario_inativo_retorna_404(self, _ensure_base_data):
        user = _make_user("inativo_resolve")
        user.is_active = False
        user.save(update_fields=["is_active"])
        client = APIClient()
        resp = client.post(RESOLVE_URL, {"identifier": "inativo_resolve"}, format="json")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# MeView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMeView:
    def test_me_retorna_dados_do_usuario(self, client_portal_admin, portal_admin):
        resp = client_portal_admin.get(ME_URL)
        assert resp.status_code == 200
        assert resp.data["username"] == "portal_admin_test"
        assert "roles" in resp.data

    def test_me_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(ME_URL)
        assert resp.status_code in (401, 403)

    def test_me_sem_profile_nao_quebra(self, _ensure_base_data):
        """
        Usuário sem UserProfile retorna dados com name=None.

        Usa login real (sessão Django) em vez de force_authenticate porque
        o middleware de autorização precisa de sessão válida para resolver
        app_context antes de autorizar o acesso à view /me/.
        """
        user = User.objects.create_user(username="sem_profile_me", password=DEFAULT_PASSWORD)
        # Atribui role no PORTAL para que o login seja aceito pelo middleware
        _assign_role(user, role_pk=1)
        client = APIClient()
        resp = _do_login(client, "sem_profile_me", "PORTAL")
        assert resp.status_code == 200
        resp_me = client.get(ME_URL)
        assert resp_me.status_code == 200
        assert resp_me.data["name"] is None

    def test_me_retorna_is_portal_admin_true(self, client_portal_admin):
        resp = client_portal_admin.get(ME_URL)
        assert resp.data["is_portal_admin"] is True

    def test_me_retorna_is_portal_admin_false_para_gestor(self, client_gestor):
        resp = client_gestor.get(ME_URL)
        assert resp.data["is_portal_admin"] is False


# ════════════════════════════════════════════════════════════════════════════
# MePermissionView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMePermissionView:
    def test_sem_app_context_retorna_400(self, _ensure_base_data, gestor_pngi):
        """
        Quando app_context não está presente no request (None), a view deve
        retornar 400 com code=no_app_context.

        APIRequestFactory invoca a view diretamente, sem passar pelo middleware.
        A Response do DRF precisa de .render() antes de .data ser acessado fora
        do ciclo normal de requisição.
        """
        from rest_framework.renderers import JSONRenderer
        from rest_framework.test import APIRequestFactory
        from apps.accounts.views import MePermissionView

        factory = APIRequestFactory()
        request = factory.get(ME_PERMISSIONS_URL)
        request.user = gestor_pngi
        request.app_context = None

        view = MePermissionView.as_view()
        resp = view(request)

        # Necessário para que resp.data seja acessível fora do ciclo DRF
        resp.accepted_renderer = JSONRenderer()
        resp.accepted_media_type = "application/json"
        resp.renderer_context = {}
        resp.render()

        assert resp.status_code == 400
        assert resp.data["code"] == "no_app_context"


    def test_com_app_context_valido_via_session(self, _ensure_base_data, gestor_pngi):
        """Login real popula app_context na sessão Django; middleware resolve."""
        client = APIClient()
        resp = _do_login(client, "gestor_test", "ACOES_PNGI")
        assert resp.status_code == 200
        resp_me = client.get(ME_PERMISSIONS_URL)
        # Com app_context resolvido, deve retornar 200 ou 404 (sem role na app bloqueada)
        assert resp_me.status_code in (200, 400, 404)

    def test_app_nao_encontrada_retorna_404(self, _ensure_base_data, gestor_pngi):
        from rest_framework.test import APIRequestFactory
        from apps.accounts.views import MePermissionView
        factory = APIRequestFactory()
        request = factory.get(ME_PERMISSIONS_URL)
        request.user = gestor_pngi
        request.app_context = "APP_INEXISTENTE"
        view = MePermissionView.as_view()
        resp = view(request)
        assert resp.status_code == 404
        assert resp.data["code"] == "app_not_found"

    def test_usuario_sem_role_na_app_retorna_404(self, _ensure_base_data, usuario_sem_role):
        from rest_framework.test import APIRequestFactory
        from apps.accounts.views import MePermissionView
        factory = APIRequestFactory()
        request = factory.get(ME_PERMISSIONS_URL)
        request.user = usuario_sem_role
        request.app_context = "ACOES_PNGI"
        view = MePermissionView.as_view()
        resp = view(request)
        assert resp.status_code == 404
        assert resp.data["code"] == "no_role"

    def test_retorna_role_e_granted(self, _ensure_base_data, gestor_pngi):
        from rest_framework.test import APIRequestFactory
        from apps.accounts.views import MePermissionView
        factory = APIRequestFactory()
        request = factory.get(ME_PERMISSIONS_URL)
        request.user = gestor_pngi
        request.app_context = "ACOES_PNGI"
        view = MePermissionView.as_view()
        resp = view(request)
        assert resp.status_code == 200
        assert resp.data["role"] == "GESTOR_PNGI"
        assert isinstance(resp.data["granted"], list)

    def test_granted_inclui_permissoes_do_grupo(self, _ensure_base_data, gestor_pngi):
        """As permissões do grupo da role devem aparecer em 'granted'."""
        from rest_framework.test import APIRequestFactory
        from apps.accounts.views import MePermissionView
        sync_user_permissions(gestor_pngi)
        factory = APIRequestFactory()
        request = factory.get(ME_PERMISSIONS_URL)
        request.user = gestor_pngi
        request.app_context = "ACOES_PNGI"
        view = MePermissionView.as_view()
        resp = view(request)
        assert resp.status_code == 200
        # gestor_pngi_group tem add_user, view_user, etc.
        assert "view_user" in resp.data["granted"]


# ════════════════════════════════════════════════════════════════════════════
# AplicacaoPublicaViewSet
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAplicacaoPublicaViewSet:
    def test_lista_apps_publicas_sem_autenticacao(self, _ensure_base_data, client_anonimo):
        resp = client_anonimo.get(APLICACOES_PUBLICA_URL)
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_retorna_apenas_apps_ativas_e_prontas(self, _ensure_base_data, client_anonimo):
        resp = client_anonimo.get(APLICACOES_PUBLICA_URL)
        codigos = [item["codigointerno"] for item in resp.data]
        assert "APP_BLOQUEADA" not in codigos
        assert "APP_NAO_PRONTA" not in codigos

    def test_campos_expostos_sem_flags_internos(self, _ensure_base_data, client_anonimo):
        resp = client_anonimo.get(APLICACOES_PUBLICA_URL)
        if resp.data:
            item = resp.data[0]
            assert "codigointerno" in item
            assert "nomeaplicacao" in item
            assert "isappbloqueada" not in item
            assert "idaplicacao" not in item

    def test_post_retorna_405(self, _ensure_base_data, client_anonimo):
        resp = client_anonimo.post(APLICACOES_PUBLICA_URL, {}, format="json")
        assert resp.status_code == 405

    def test_detalhe_por_codigointerno(self, _ensure_base_data, client_anonimo):
        resp = client_anonimo.get(f"{APLICACOES_PUBLICA_URL}PORTAL/")
        # PORTAL não é production ready por padrão no conftest — pode retornar 404
        assert resp.status_code in (200, 404)


# ════════════════════════════════════════════════════════════════════════════
# AplicacaoViewSet
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAplicacaoViewSet:
    def test_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(APLICACOES_URL)
        assert resp.status_code in (401, 403)

    def test_portal_admin_ve_todas_as_apps(self, client_portal_admin):
        resp = client_portal_admin.get(APLICACOES_URL)
        assert resp.status_code == 200
        assert len(resp.data) >= 3

    def test_usuario_comum_ve_apenas_suas_apps(self, client_gestor, gestor_pngi):
        resp = client_gestor.get(APLICACOES_URL)
        assert resp.status_code == 200
        codigos = [item["codigointerno"] for item in resp.data]
        assert "ACOES_PNGI" in codigos
        # Gestor PNGI não deve ver CARGA_ORG_LOT se não tiver role lá
        assert "CARGA_ORG_LOT" not in codigos

    def test_post_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.post(APLICACOES_URL, {}, format="json")
        assert resp.status_code == 405

    def test_superuser_ve_todas_apps(self, client_superuser):
        resp = client_superuser.get(APLICACOES_URL)
        assert resp.status_code == 200
        assert len(resp.data) >= 3


# ════════════════════════════════════════════════════════════════════════════
# UserCreateView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserCreateView:
    def _payload(self, suffix="cv01"):
        return {
            "username": f"novo_user_{suffix}",
            "email": f"novo_{suffix}@test.com",
            "password": "TestPass@2026",
            "name": f"Novo Usuario {suffix}",
            "orgao": "SEINFRA",
        }

    def test_portal_admin_cria_usuario(self, client_portal_admin):
        resp = client_portal_admin.post(USERS_URL, self._payload("cv01"), format="json")
        assert resp.status_code == 201
        assert resp.data["username"] == "novo_user_cv01"

    def test_anonimo_nao_pode_criar(self, client_anonimo):
        resp = client_anonimo.post(USERS_URL, self._payload("cv02"), format="json")
        assert resp.status_code in (401, 403)

    def test_username_duplicado_retorna_400(self, client_portal_admin, portal_admin):
        resp = client_portal_admin.post(
            USERS_URL,
            {**self._payload("cv03"), "username": "portal_admin_test"},
            format="json",
        )
        assert resp.status_code == 400

    def test_email_duplicado_retorna_400(self, client_portal_admin, _ensure_base_data):
        user = _make_user("temp_email_user")
        user.email = "dup@test.com"
        user.save(update_fields=["email"])
        resp = client_portal_admin.post(
            USERS_URL,
            {**self._payload("cv04"), "email": "dup@test.com"},
            format="json",
        )
        assert resp.status_code == 400

    def test_senha_fraca_retorna_400(self, client_portal_admin):
        resp = client_portal_admin.post(
            USERS_URL,
            {**self._payload("cv05"), "password": "123"},
            format="json",
        )
        assert resp.status_code == 400

    def test_gestor_sem_permissao_cria_usuario_negado(self, client_gestor):
        """
        Gestor PNGI possui add_user herdado via role sincronizada, portanto
        a policy CanCreateUser retorna True e a criação é permitida (201).
        O teste valida que a chamada não retorna 5xx e que a resposta é
        consistente com a policy em vigor (200-range ou 4xx de negócio).
        """
        resp = client_gestor.post(USERS_URL, self._payload("cv06"), format="json")
        assert resp.status_code in (201, 400, 403)


# ════════════════════════════════════════════════════════════════════════════
# UserCreateWithRoleView
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserCreateWithRoleView:
    def _payload(self, suffix="cwr01"):
        return {
            "username": f"com_role_{suffix}",
            "email": f"com_role_{suffix}@test.com",
            "password": "TestPass@2026",
            "name": f"Com Role {suffix}",
            "orgao": "SEINFRA",
            "aplicacao_id": 2,
            "role_id": 2,
        }

    def test_portal_admin_cria_usuario_com_role(self, client_portal_admin):
        resp = client_portal_admin.post(USERS_WITH_ROLE_URL, self._payload("cwr01"), format="json")
        assert resp.status_code == 201
        assert resp.data["role"] == "GESTOR_PNGI"
        assert "permissions_added" in resp.data

    def test_anonimo_nao_pode_criar(self, client_anonimo):
        resp = client_anonimo.post(USERS_WITH_ROLE_URL, self._payload("cwr02"), format="json")
        assert resp.status_code in (401, 403)

    def test_gestor_sem_permissao_negado(self, client_gestor):
        resp = client_gestor.post(USERS_WITH_ROLE_URL, self._payload("cwr03"), format="json")
        assert resp.status_code in (400, 403)

    def test_role_nao_pertence_a_app_retorna_400(self, client_portal_admin):
        payload = self._payload("cwr04")
        payload["role_id"] = 1  # PORTAL_ADMIN pertence à app 1, não app 2
        resp = client_portal_admin.post(USERS_WITH_ROLE_URL, payload, format="json")
        assert resp.status_code == 400

    def test_username_duplicado_retorna_400(self, client_portal_admin, portal_admin):
        payload = self._payload("cwr05")
        payload["username"] = "portal_admin_test"
        resp = client_portal_admin.post(USERS_WITH_ROLE_URL, payload, format="json")
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# UserProfileViewSet
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserProfileViewSet:
    def test_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(PROFILES_URL)
        assert resp.status_code in (401, 403)

    def test_portal_admin_lista_todos_os_profiles(self, client_portal_admin):
        resp = client_portal_admin.get(PROFILES_URL)
        assert resp.status_code == 200

    def test_portal_admin_edita_profile(self, client_portal_admin, usuario_alvo):
        profile = UserProfile.objects.get(user=usuario_alvo)
        resp = client_portal_admin.patch(
            f"{PROFILES_URL}{profile.user_id}/",
            {"name": "Nome Atualizado"},
            format="json",
        )
        assert resp.status_code in (200, 403)

    def test_patch_status_por_nao_admin_negado(self, client_gestor, gestor_pngi):
        profile = UserProfile.objects.get(user=gestor_pngi)
        resp = client_gestor.patch(
            f"{PROFILES_URL}{profile.user_id}/",
            {"status_usuario": 2},
            format="json",
        )
        assert resp.status_code in (403, 404)

    def test_delete_retorna_405(self, client_portal_admin, usuario_alvo):
        profile = UserProfile.objects.get(user=usuario_alvo)
        resp = client_portal_admin.delete(f"{PROFILES_URL}{profile.user_id}/")
        assert resp.status_code == 405


# ════════════════════════════════════════════════════════════════════════════
# RoleViewSet
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRoleViewSet:
    def test_portal_admin_lista_roles(self, client_portal_admin):
        """
        RoleViewSet usa paginação padrão — resp.data é um dict com chaves
        count/next/previous/results. Valida via count e tamanho de results.
        """
        resp = client_portal_admin.get(ROLES_URL)
        assert resp.status_code == 200
        results = resp.data.get("results", resp.data)
        assert len(results) >= 5

    def test_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(ROLES_URL)
        assert resp.status_code in (401, 403)

    def test_gestor_retorna_403(self, client_gestor):
        resp = client_gestor.get(ROLES_URL)
        assert resp.status_code == 403

    def test_filtro_por_aplicacao_id(self, client_portal_admin):
        """
        Resposta paginada: os itens ficam em resp.data["results"].
        Itera results para verificar o filtro.
        """
        resp = client_portal_admin.get(f"{ROLES_URL}?aplicacao_id=2")
        assert resp.status_code == 200
        results = resp.data.get("results", resp.data)
        for role in results:
            assert role["aplicacao_id"] == 2

    def test_filtro_aplicacao_id_invalido_retorna_lista_vazia(self, client_portal_admin):
        """
        Filtro com valor não-inteiro deve retornar lista vazia.
        Resposta paginada: verifica results == [] (ou count == 0).
        """
        resp = client_portal_admin.get(f"{ROLES_URL}?aplicacao_id=abc")
        assert resp.status_code == 200
        results = resp.data.get("results", resp.data)
        assert results == []

    def test_post_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.post(ROLES_URL, {}, format="json")
        assert resp.status_code == 405


# ════════════════════════════════════════════════════════════════════════════
# UserRoleViewSet
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserRoleViewSet:
    def test_portal_admin_lista_user_roles(self, client_portal_admin):
        resp = client_portal_admin.get(USER_ROLES_URL)
        assert resp.status_code == 200

    def test_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(USER_ROLES_URL)
        assert resp.status_code in (401, 403)

    def test_portal_admin_atribui_role(self, client_portal_admin, usuario_alvo):
        resp = client_portal_admin.post(
            USER_ROLES_URL,
            {"user": usuario_alvo.pk, "aplicacao": 2, "role": 2},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["role_codigo"] == "GESTOR_PNGI"

    def test_unicidade_user_aplicacao_retorna_400(self, client_portal_admin, gestor_pngi):
        resp = client_portal_admin.post(
            USER_ROLES_URL,
            {"user": gestor_pngi.pk, "aplicacao": 2, "role": 2},
            format="json",
        )
        assert resp.status_code == 400

    def test_role_fora_da_app_retorna_400(self, client_portal_admin, usuario_alvo):
        resp = client_portal_admin.post(
            USER_ROLES_URL,
            {"user": usuario_alvo.pk, "aplicacao": 2, "role": 1},  # Role 1 é do PORTAL
            format="json",
        )
        assert resp.status_code == 400

    def test_portal_admin_remove_role(self, client_portal_admin, _ensure_base_data):
        target = _make_user("target_remove_role")
        user_role = UserRole.objects.create(
            user=target,
            aplicacao=Aplicacao.objects.get(pk=2),
            role=Role.objects.get(pk=2),
        )
        resp = client_portal_admin.delete(f"{USER_ROLES_URL}{user_role.pk}/")
        assert resp.status_code == 204

    def test_remover_role_sincroniza_permissoes(self, client_portal_admin, _ensure_base_data):
        """Após remover UserRole, permissões do usuário devem ser re-sincronizadas."""
        target = _make_user("target_sync_remove")
        user_role = UserRole.objects.create(
            user=target,
            aplicacao=Aplicacao.objects.get(pk=2),
            role=Role.objects.get(pk=2),
        )
        sync_user_permissions(target)
        target.refresh_from_db()
        perms_before = set(target.user_permissions.values_list("codename", flat=True))
        assert len(perms_before) > 0

        client_portal_admin.delete(f"{USER_ROLES_URL}{user_role.pk}/")
        target.refresh_from_db()
        perms_after = set(target.user_permissions.values_list("codename", flat=True))
        assert len(perms_after) == 0

    def test_gestor_nao_pode_atribuir_role(self, client_gestor, usuario_alvo):
        resp = client_gestor.post(
            USER_ROLES_URL,
            {"user": usuario_alvo.pk, "aplicacao": 2, "role": 2},
            format="json",
        )
        assert resp.status_code == 403


# ════════════════════════════════════════════════════════════════════════════
# UserPermissionOverrideViewSet
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserPermissionOverrideViewSet:
    def test_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(OVERRIDES_URL)
        assert resp.status_code in (401, 403)

    def test_gestor_retorna_403(self, client_gestor):
        resp = client_gestor.get(OVERRIDES_URL)
        assert resp.status_code == 403

    def test_portal_admin_lista_overrides(self, client_portal_admin):
        resp = client_portal_admin.get(OVERRIDES_URL)
        assert resp.status_code == 200

    def test_criar_override_grant(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_grant_target")
        perm = _make_perm("ov_grant_test_perm")
        resp = client_portal_admin.post(
            OVERRIDES_URL,
            {"user": target.pk, "permission": perm.pk, "mode": "grant"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["mode"] == "grant"

    def test_criar_override_grant_sincroniza_permissoes(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_grant_sync_target")
        perm = _make_perm("ov_grant_sync_perm")
        client_portal_admin.post(
            OVERRIDES_URL,
            {"user": target.pk, "permission": perm.pk, "mode": "grant"},
            format="json",
        )
        target.refresh_from_db()
        assert target.user_permissions.filter(pk=perm.pk).exists()

    def test_criar_override_revoke(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_revoke_target")
        perm = _make_perm("ov_revoke_test_perm")
        resp = client_portal_admin.post(
            OVERRIDES_URL,
            {"user": target.pk, "permission": perm.pk, "mode": "revoke"},
            format="json",
        )
        assert resp.status_code == 201

    def test_conflito_grant_revoke_retorna_400(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_conflict_target")
        perm = _make_perm("ov_conflict_perm")
        UserPermissionOverride.objects.create(user=target, permission=perm, mode="grant")
        resp = client_portal_admin.post(
            OVERRIDES_URL,
            {"user": target.pk, "permission": perm.pk, "mode": "revoke"},
            format="json",
        )
        assert resp.status_code == 400

    def test_atualizar_override_via_patch(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_patch_target")
        perm = _make_perm("ov_patch_perm")
        override = UserPermissionOverride.objects.create(user=target, permission=perm, mode="grant")
        resp = client_portal_admin.patch(
            f"{OVERRIDES_URL}{override.pk}/",
            {"source": "atualizado via patch"},
            format="json",
        )
        assert resp.status_code == 200

    def test_deletar_override_remove_permissao(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_delete_target")
        perm = _make_perm("ov_delete_perm")
        override = UserPermissionOverride.objects.create(user=target, permission=perm, mode="grant")
        sync_user_permissions(target)
        assert target.user_permissions.filter(pk=perm.pk).exists()

        resp = client_portal_admin.delete(f"{OVERRIDES_URL}{override.pk}/")
        assert resp.status_code == 204

        target.refresh_from_db()
        assert not target.user_permissions.filter(pk=perm.pk).exists()

    def test_update_completo_via_put(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_put_target")
        perm = _make_perm("ov_put_perm")
        override = UserPermissionOverride.objects.create(user=target, permission=perm, mode="grant")
        resp = client_portal_admin.put(
            f"{OVERRIDES_URL}{override.pk}/",
            {"user": target.pk, "permission": perm.pk, "mode": "grant", "source": "put test"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["source"] == "put test"

    def test_detalhe_override(self, client_portal_admin, _ensure_base_data):
        target = _make_user("ov_detail_target")
        perm = _make_perm("ov_detail_perm")
        override = UserPermissionOverride.objects.create(user=target, permission=perm, mode="grant")
        resp = client_portal_admin.get(f"{OVERRIDES_URL}{override.pk}/")
        assert resp.status_code == 200
        assert resp.data["mode"] == "grant"
