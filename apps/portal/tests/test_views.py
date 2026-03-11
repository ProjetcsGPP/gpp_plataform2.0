"""
GPP Plataform 2.0 — Portal Views Tests
FASE 6: testes obrigatórios dos endpoints do portal.
"""
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.accounts.models import (
    Aplicacao, Role, StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, UserProfile, UserRole,
)
from apps.core.tests.utils import patch_security


def _ensure_lookups():
    StatusUsuario.objects.get_or_create(idstatususuario=1, defaults={"strdescricao": "Ativo"})
    TipoUsuario.objects.get_or_create(idtipousuario=1, defaults={"strdescricao": "Padrão"})
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1, defaults={"strdescricao": "Padrão"}
    )


def _make_user_with_role(username):
    """Cria User + UserProfile + role USER no PORTAL."""
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
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertGreaterEqual(len(results), 1)
        for app in results:
            self.assertTrue(app["isshowinportal"])

    def test_aplicacoes_list_unauthenticated_returns_401(self):
        """GET /api/portal/aplicacoes/ sem token deve retornar 401."""
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
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("aplicacoes", response.data)
        self.assertIn("roles", response.data)
        self.assertGreaterEqual(len(response.data["roles"]), 1)
        role_codigos = [r["role_codigo"] for r in response.data["roles"]]
        self.assertIn("USER", role_codigos)
