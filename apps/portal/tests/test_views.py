"""
GPP Plataform 2.0 — Portal Views Tests
FASE 6: testes obrigatórios dos endpoints do portal.
Usa _patch_security para bypassar os middlewares JWT/Role/Authz.
"""
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from unittest.mock import patch

from apps.accounts.models import (
    Aplicacao, Role, StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, UserProfile, UserRole,
)


def _ensure_lookups():
    StatusUsuario.objects.get_or_create(idstatususuario=1, defaults={"strdescricao": "Ativo"})
    TipoUsuario.objects.get_or_create(idtipousuario=1, defaults={"strdescricao": "Padrão"})
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1, defaults={"strdescricao": "Padrão"}
    )


def _make_user_with_role(username):
    _ensure_lookups()
    user = User.objects.create_user(username=username, password="pass")
    UserProfile.objects.create(
        user=user, name=username, orgao="SESP",
        status_usuario_id=1, tipo_usuario_id=1, classificacao_usuario_id=1,
    )
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno="PORTAL",
        defaults={"nomeaplicacao": "Portal", "isshowinportal": True},
    )
    role, _ = Role.objects.get_or_create(
        aplicacao=app, codigoperfil="USER", defaults={"nomeperfil": "User"}
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


def _patch_security(user, is_portal_admin=False):
    """
    Faz patch nos 3 middlewares customizados do GPP, injetando
    request.user, request.user_roles e request.is_portal_admin
    antes de chegar na view — sem depender de token JWT real.
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


class AplicacoesListTest(APITestCase):
    def setUp(self):
        self.user = _make_user_with_role("portal_user_list")
        Aplicacao.objects.get_or_create(
            codigointerno="APP_TESTE",
            defaults={"nomeaplicacao": "App de Teste", "isshowinportal": True},
        )
        self.client = APIClient()
        self.url = reverse("portal:aplicacao-list")

    def test_aplicacoes_list_authenticated(self):
        """
        GET /api/portal/aplicacoes/ autenticado deve retornar 200
        e uma lista de aplicações com isshowinportal=True.
        """
        patches = _patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertGreaterEqual(len(results), 1)
        for app in results:
            self.assertTrue(app["isshowinportal"])

    def test_aplicacoes_list_unauthenticated_returns_401(self):
        """
        GET /api/portal/aplicacoes/ sem token deve retornar 401.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DashboardTest(APITestCase):
    def setUp(self):
        self.user = _make_user_with_role("dashboard_user")
        self.client = APIClient()
        self.url = reverse("portal:dashboard")

    def test_dashboard_returns_user_roles(self):
        """
        GET /api/portal/dashboard/ deve retornar 'aplicacoes' e 'roles'.
        'roles' deve conter ao menos a role do usuário criado no setUp.
        """
        patches = _patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("aplicacoes", response.data)
        self.assertIn("roles", response.data)
        self.assertGreaterEqual(len(response.data["roles"]), 1)
        role_codigos = [r["role_codigo"] for r in response.data["roles"]]
        self.assertIn("USER", role_codigos)
