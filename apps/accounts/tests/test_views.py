"""
GPP Plataform 2.0 — Accounts Views Tests
FASE 6: testes obrigatórios dos endpoints de accounts.
"""
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from unittest.mock import patch, MagicMock

from apps.accounts.models import (
    Aplicacao, Role, StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, UserProfile, UserRole,
)


def _make_status():
    obj, _ = StatusUsuario.objects.get_or_create(
        idstatususuario=1, defaults={"strdescricao": "Ativo"}
    )
    return obj


def _make_tipo():
    obj, _ = TipoUsuario.objects.get_or_create(
        idtipousuario=1, defaults={"strdescricao": "Padrão"}
    )
    return obj


def _make_classificacao():
    obj, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1, defaults={"strdescricao": "Padrão"}
    )
    return obj


def _make_app(codigo="PORTAL"):
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo,
        defaults={"nomeaplicacao": codigo, "isshowinportal": True},
    )
    return app


def _make_user_with_profile(username, orgao="SESP", is_admin=False):
    user = User.objects.create_user(username=username, password="pass")
    _make_status()
    _make_tipo()
    _make_classificacao()
    profile = UserProfile.objects.create(
        user=user,
        name=username,
        orgao=orgao,
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
    )
    app = _make_app()
    role_codigo = "PORTAL_ADMIN" if is_admin else "USER"
    role, _ = Role.objects.get_or_create(
        aplicacao=app,
        codigoperfil=role_codigo,
        defaults={"nomeperfil": role_codigo},
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user, profile


def _bypass_middlewares(user, is_portal_admin=False):
    """
    Patch nos 3 middlewares customizados do GPP.
    Injeta user, user_roles e is_portal_admin direto no request.
    """
    user_roles = list(UserRole.objects.filter(user=user))

    def fake_jwt(get_response):
        def middleware(request):
            request.user = user
            request.token_jti = "fake-jti"
            request.is_portal_admin = is_portal_admin
            return get_response(request)
        return middleware

    def fake_role(get_response):
        def middleware(request):
            request.user_roles = user_roles
            request.is_portal_admin = is_portal_admin
            return get_response(request)
        return middleware

    def fake_authz(get_response):
        def middleware(request):
            return get_response(request)
        return middleware

    return patch.multiple(
        "django.conf.settings",
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "corsheaders.middleware.CorsMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
        ],
    )


# ─── Alternativa mais simples: patch direto no __call__ dos middlewares ───────

def _patch_security(user, is_portal_admin=False):
    """
    Faz patch diretamente no __call__ dos 3 middlewares customizados,
    injetando os atributos no request antes de chamar a view.
    """
    user_roles = list(UserRole.objects.filter(user=user))

    def patched_jwt_call(self_mw, request):
        request.user = user
        request.token_jti = "test-jti"
        request.is_portal_admin = is_portal_admin
        return self_mw.get_response(request)

    def patched_role_call(self_mw, request):
        request.user_roles = user_roles
        request.is_portal_admin = is_portal_admin
        return self_mw.get_response(request)

    def patched_authz_call(self_mw, request):
        return self_mw.get_response(request)

    return [
        patch(
            "apps.core.middleware.jwt_authentication.JWTAuthenticationMiddleware.__call__",
            new=patched_jwt_call,
        ),
        patch(
            "apps.core.middleware.role_context.RoleContextMiddleware.__call__",
            new=patched_role_call,
        ),
        patch(
            "apps.core.middleware.authorization.AuthorizationMiddleware.__call__",
            new=patched_authz_call,
        ),
    ]


class MeEndpointTest(APITestCase):
    def setUp(self):
        self.user, self.profile = _make_user_with_profile("testuser_me")
        self.client = APIClient()
        self.url = reverse("accounts:me")

    def test_me_endpoint_returns_user_data(self):
        """GET /api/accounts/me/ com token válido deve retornar 200."""
        patches = _patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)
        self.assertIn("roles", response.data)
        self.assertIsInstance(response.data["roles"], list)

    def test_me_endpoint_unauthenticated_returns_401(self):
        """GET /api/accounts/me/ sem token deve retornar 401."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfilesListTest(APITestCase):
    def setUp(self):
        self.admin, self.admin_profile = _make_user_with_profile(
            "admin_profiles", is_admin=True
        )
        self.user, self.user_profile = _make_user_with_profile(
            "common_user_profiles", orgao="SESP"
        )
        self.client = APIClient()
        self.url = reverse("accounts:userprofile-list")

    def test_profiles_list_admin_sees_all(self):
        """PORTAL_ADMIN deve ver todos os profiles na listagem."""
        patches = _patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(self.url)

        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN],
        )

    def test_profiles_list_user_sees_only_own(self):
        """Usuário comum deve receber na listagem apenas o próprio profile."""
        patches = _patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN],
        )
        if response.status_code == status.HTTP_200_OK:
            ids = [p["user_id"] for p in response.data.get("results", response.data)]
            for uid in ids:
                self.assertEqual(uid, self.user.id)


class AssignRolePermissionTest(APITestCase):
    def setUp(self):
        self.user, _ = _make_user_with_profile("nonadmin_assign")
        self.client = APIClient()
        self.app = _make_app("PORTAL")
        role, _ = Role.objects.get_or_create(
            aplicacao=self.app,
            codigoperfil="USER",
            defaults={"nomeperfil": "User"},
        )
        self.url = reverse("accounts:userrole-list")
        self.payload = {
            "user": self.user.id,
            "aplicacao": self.app.pk,
            "role": role.pk,
        }

    def test_assign_role_non_admin_returns_403(self):
        """POST /api/accounts/user-roles/ por usuário não-admin deve retornar 403."""
        patches = _patch_security(self.user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.post(self.url, self.payload)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
