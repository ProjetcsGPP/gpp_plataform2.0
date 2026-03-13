"""
GPP Plataform 2.0 — Accounts Tests: AplicacoesList (GAP-02)
Cobre cenários T-01 a T-09 conforme especificação da Fase 2.

Padrão de autenticação:
    O JWTAuthenticationMiddleware processa o request antes do DRF e retorna
    401 via JsonResponse sem token válido — mesmo com force_authenticate.
    Todos os testes autenticados usam patch_security() para bypassar os 3
    middlewares customizados (JWT, RoleContext, Authorization).
    T-02 é a única exceção: testa o middleware real sem credencial alguma.
"""
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.accounts.models import (
    Aplicacao,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
)
from apps.core.tests.utils import patch_security


# ─── Helpers ─────────────────────────────────────────────────────────────────────

def _bootstrap_lookups():
    StatusUsuario.objects.get_or_create(idstatususuario=1, defaults={"strdescricao": "Ativo"})
    TipoUsuario.objects.get_or_create(idtipousuario=1, defaults={"strdescricao": "Padrão"})
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1, defaults={"strdescricao": "Padrão"}
    )


def _make_portal_app(codigo="PORTAL"):
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo,
        defaults={"nomeaplicacao": "Portal GPP", "isshowinportal": True},
    )
    return app


def _make_admin_user(username="admin_gap02"):
    """Cria User + UserProfile + Role PORTAL_ADMIN."""
    _bootstrap_lookups()
    user = User.objects.create_user(username=username, password="Admin@2026!")
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="SEDU",
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
    )
    app = _make_portal_app()
    role, _ = Role.objects.get_or_create(
        aplicacao=app,
        codigoperfil="PORTAL_ADMIN",
        defaults={"nomeperfil": "Portal Admin"},
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


def _make_plain_user(username="plain_gap02"):
    """Cria User + UserProfile sem role PORTAL_ADMIN."""
    _bootstrap_lookups()
    user = User.objects.create_user(username=username, password="Plain@2026!")
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="SEDU",
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
    )
    app = _make_portal_app()
    role, _ = Role.objects.get_or_create(
        aplicacao=app,
        codigoperfil="USER",
        defaults={"nomeperfil": "Usuário"},
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


def _make_aplicacao(codigo, nome, show_in_portal):
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo,
        defaults={"nomeaplicacao": nome, "isshowinportal": show_in_portal},
    )
    return app


# ─── Test Case ───────────────────────────────────────────────────────────────────

class AplicacoesListEndpointTest(APITestCase):
    """
    Testes T-01 a T-09 para GET /api/accounts/aplicacoes/.
    """

    @classmethod
    def setUpTestData(cls):
        cls.list_url = reverse("accounts:aplicacao-list")
        cls.admin = _make_admin_user()
        cls.plain_user = _make_plain_user()

        # Fixture: 2 apps elegíveis (isshowinportal=False) + 1 de portal (isshowinportal=True)
        # Criadas propositalmente fora de ordem alfabética para validar T-09
        cls.app_zeus = _make_aplicacao("ZEUS", "Zeus Gestão", show_in_portal=False)
        cls.app_ares = _make_aplicacao("ARES", "Ares Controle", show_in_portal=False)
        cls.app_portal = _make_aplicacao("PORTAL_VIS", "Portal Visualização", show_in_portal=True)

    def setUp(self):
        self.client = APIClient(raise_request_exception=False)

    # ── T-01 — GET autenticado como PORTAL_ADMIN ──────────────────

    def test_T01_admin_list_returns_200(self):
        """T-01: PORTAL_ADMIN → 200 com lista de apps isshowinportal=False."""
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── T-02 — GET sem autenticação ───────────────────────────────

    def test_T02_unauthenticated_returns_401(self):
        """
        T-02: sem autenticação → 401 Unauthorized.
        NÃO usa patch_security — testa o middleware real sem nenhuma credencial.
        """
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── T-03 — GET autenticado sem role PORTAL_ADMIN ──────────────

    def test_T03_non_admin_returns_403(self):
        """
        T-03: autenticado sem PORTAL_ADMIN → 403 Forbidden.
        patch_security com is_portal_admin=False injeta request.is_portal_admin=False;
        IsPortalAdmin.has_permission() lê esse atributo e retorna False → 403.
        """
        patches = patch_security(self.plain_user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.plain_user)
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── T-04 — Fixture: somente 2 apps elegíveis retornadas ───────

    def test_T04_list_returns_only_non_portal_apps(self):
        """T-04: fixture com 2 isshowinportal=False e 1 True → resposta contém exatamente 2."""
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Suporte a paginação (DRF DefaultRouter pode paginar)
        data = response.data.get("results", response.data)
        ids_retornados = {item["idaplicacao"] for item in data}

        self.assertIn(self.app_zeus.pk, ids_retornados)
        self.assertIn(self.app_ares.pk, ids_retornados)
        self.assertNotIn(self.app_portal.pk, ids_retornados)

        # R-01 — isshowinportal nunca exposto na resposta
        for item in data:
            self.assertNotIn("isshowinportal", item, "isshowinportal não deve ser exposto")

    # ── T-05 — Retrieve de app com isshowinportal=True → 404 ─────

    def test_T05_retrieve_portal_app_returns_404(self):
        """T-05: GET /aplicacoes/{id}/ onde app tem isshowinportal=True → 404 (R-04)."""
        detail_url = reverse("accounts:aplicacao-detail", kwargs={"pk": self.app_portal.pk})
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── T-06 — Retrieve de app elegível → 200 ────────────────────

    def test_T06_retrieve_eligible_app_returns_200(self):
        """T-06: GET /aplicacoes/{id}/ onde app tem isshowinportal=False → 200 com dados."""
        detail_url = reverse("accounts:aplicacao-detail", kwargs={"pk": self.app_ares.pk})
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["idaplicacao"], self.app_ares.pk)
        self.assertEqual(response.data["codigointerno"], "ARES")
        self.assertIn("nomeaplicacao", response.data)
        self.assertNotIn("isshowinportal", response.data)

    # ── T-07 — POST → 405 ────────────────────────────────────────

    def test_T07_post_returns_405(self):
        """T-07: POST /api/accounts/aplicacoes/ → 405 Method Not Allowed (R-03)."""
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.list_url, {"codigointerno": "NOVO"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ── T-08 — DELETE → 405 ──────────────────────────────────────

    def test_T08_delete_returns_405(self):
        """T-08: DELETE /api/accounts/aplicacoes/{id}/ → 405 Method Not Allowed (R-03)."""
        detail_url = reverse("accounts:aplicacao-detail", kwargs={"pk": self.app_ares.pk})
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ── T-09 — Ordenação alfabética por nomeaplicacao ─────────────

    def test_T09_list_is_ordered_alphabetically(self):
        """T-09: lista retornada em ordem alfabética por nomeaplicacao (R-05)."""
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data.get("results", response.data)
        nomes = [item["nomeaplicacao"] for item in data]
        self.assertEqual(nomes, sorted(nomes), "Lista deve estar em ordem alfabética por nomeaplicacao")
