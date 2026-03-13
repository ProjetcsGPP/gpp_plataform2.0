"""
GPP Plataform 2.0 — Accounts Tests: UserCreate (GAP-01)
Cobre cenários T-01 a T-10 conforme especificação da Fase 1.

Padrão de autenticação nos testes:
    O JWTAuthenticationMiddleware processa o request antes do DRF e retorna
    401 via JsonResponse caso não encontre token válido — mesmo com
    force_authenticate ativo. Por isso todos os testes autenticados usam
    patch_security(), que faz mock dos 3 middlewares customizados
    (JWT, RoleContext, Authorization), seguindo o padrão de test_views.py.
"""
from unittest.mock import patch

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


# ── Fixtures helpers ───────────────────────────────────────────────────────────

def _bootstrap_lookups():
    """Garante que os registros de lookup PK=1 existam."""
    StatusUsuario.objects.get_or_create(idstatususuario=1, defaults={"strdescricao": "Ativo"})
    TipoUsuario.objects.get_or_create(idtipousuario=1, defaults={"strdescricao": "Padrão"})
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1, defaults={"strdescricao": "Padrão"}
    )


def _make_app(codigo="PORTAL"):
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo, defaults={"nomeaplicacao": codigo, "isshowinportal": True}
    )
    return app


def _make_admin_user(username="admin_gap01"):
    """
    Cria User + UserProfile + Role PORTAL_ADMIN.
    R-06: usa User.objects.create_user() diretamente, sem chamar o endpoint.
    """
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
    app = _make_app()
    role, _ = Role.objects.get_or_create(
        aplicacao=app,
        codigoperfil="PORTAL_ADMIN",
        defaults={"nomeperfil": "Portal Admin"},
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


def _make_plain_user(username="plain_gap01"):
    """
    Cria User + UserProfile com role USER (não-admin).
    R-06: usa User.objects.create_user() diretamente.
    """
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
    app = _make_app()
    role, _ = Role.objects.get_or_create(
        aplicacao=app,
        codigoperfil="USER",
        defaults={"nomeperfil": "Usuário"},
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


# ── Payload padrão válido ──────────────────────────────────────────────────────

VALID_PAYLOAD = {
    "username": "joao.silva",
    "email": "joao@exemplo.com",
    "password": "Segura@2026!",
    "first_name": "João",
    "last_name": "Silva",
    "name": "João Silva",
    "orgao": "SEDU",
}


# ── Test Case ─────────────────────────────────────────────────────────────────

class UserCreateEndpointTest(APITestCase):
    """
    Testes T-01 a T-10 para POST /api/accounts/users/.

    Todos os cenários autenticados utilizam patch_security() para bypassar
    o JWTAuthenticationMiddleware, RoleContextMiddleware e
    AuthorizationMiddleware — sem necessidade de token JWT real.
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("accounts:user-create")
        cls.admin = _make_admin_user()
        cls.plain_user = _make_plain_user()

    def setUp(self):
        self.client = APIClient()

    # ── T-01 — POST válido ─────────────────────────────────────────────────────

    def test_T01_valid_post_creates_user_and_profile(self):
        """T-01: POST válido → 201, User e Profile criados, idusuariocriacao preenchido."""
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Verifica User criado
        user = User.objects.get(username="joao.silva")
        self.assertEqual(user.email, "joao@exemplo.com")

        # Verifica Profile criado com dados corretos
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.name, "João Silva")
        self.assertEqual(profile.orgao, "SEDU")
        self.assertEqual(profile.idusuariocriacao_id, self.admin.id)  # R-02

        # Verifica que UserRole NÃO foi criado (R-07)
        self.assertFalse(UserRole.objects.filter(user=user).exists())

        # Verifica shape da resposta 201
        self.assertEqual(response.data["username"], "joao.silva")
        self.assertEqual(response.data["email"], "joao@exemplo.com")
        self.assertIn("datacriacao", response.data)
        self.assertNotIn("password", response.data)  # write_only

    # ── T-02 — username duplicado ──────────────────────────────────────────────

    def test_T02_duplicate_username_returns_400(self):
        """T-02: username já existente → 400 com mensagem clara."""
        User.objects.create_user(username="joao.duplicado", password="Xyz@2026!")
        payload = {**VALID_PAYLOAD, "username": "joao.duplicado", "email": "unique@test.com"}

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertIn("já está em uso", str(response.data["username"]))

    # ── T-03 — email duplicado ─────────────────────────────────────────────────

    def test_T03_duplicate_email_returns_400(self):
        """T-03: email já existente → 400 com mensagem clara."""
        User.objects.create_user(
            username="outro_user", password="Xyz@2026!", email="dup@test.com"
        )
        payload = {**VALID_PAYLOAD, "username": "unique_user_t03", "email": "dup@test.com"}

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertIn("já está em uso", str(response.data["email"]))

    # ── T-04 — senha fraca ─────────────────────────────────────────────────────

    def test_T04_weak_password_returns_400(self):
        """T-04: senha '123' → 400 com erro de validação de senha."""
        payload = {
            **VALID_PAYLOAD,
            "username": "user_weak_t04",
            "email": "weak_t04@test.com",
            "password": "123",
        }

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    # ── T-05 — orgao ausente ───────────────────────────────────────────────────

    def test_T05_missing_orgao_returns_400(self):
        """T-05: sem orgao → 400 campo obrigatório."""
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "orgao"}
        payload["username"] = "no_orgao_t05"
        payload["email"] = "noorgao_t05@test.com"

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("orgao", response.data)

    # ── T-06 — sem autenticação ────────────────────────────────────────────────

    def test_T06_unauthenticated_returns_401(self):
        """
        T-06: request sem autenticação → 401.
        NÃO usa patch_security — testa o comportamento real do middleware
        quando nenhuma credencial é fornecida.
        """
        response = self.client.post(self.url, VALID_PAYLOAD, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── T-07 — autenticado sem PORTAL_ADMIN ───────────────────────────────────

    def test_T07_non_admin_returns_403(self):
        """
        T-07: usuário autenticado mas sem role PORTAL_ADMIN → 403.
        patch_security com is_portal_admin=False injeta request.is_portal_admin=False,
        fazendo IsPortalAdmin.has_permission() retornar False → 403.
        """
        patches = patch_security(self.plain_user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.plain_user)
            response = self.client.post(self.url, VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── T-08 — rollback atômico ────────────────────────────────────────────────

    def test_T08_rollback_on_profile_save_failure(self):
        """
        T-08: falha simulada no UserProfile.objects.create → rollback total.
        O User criado dentro do transaction.atomic() não deve persistir (R-01).
        """
        payload = {**VALID_PAYLOAD, "username": "atomic_t08", "email": "atomic_t08@test.com"}
        users_before = User.objects.count()

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            with patch(
                "apps.accounts.models.UserProfile.objects.create",
                side_effect=Exception("DB failure simulada"),
            ):
                response = self.client.post(self.url, payload, format="json")

        # View deve retornar qualquer status não-2xx
        self.assertNotEqual(response.status_code, status.HTTP_201_CREATED)
        # User NÃO deve ter sido persistido — rollback garantido pelo atomic() (R-01)
        self.assertEqual(User.objects.count(), users_before)
        self.assertFalse(User.objects.filter(username="atomic_t08").exists())

    # ── T-09 — GET não permitido ───────────────────────────────────────────────

    def test_T09_get_returns_405(self):
        """
        T-09: GET /api/accounts/users/ → 405 Method Not Allowed.
        UserCreateView só implementa .post() — DRF rejeita outros métodos com 405.
        """
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ── T-10 — UserProfileViewSet continua sem POST ────────────────────────────

    def test_T10_profiles_viewset_rejects_post(self):
        """
        T-10: POST /api/accounts/profiles/ → 405.
        UserProfileViewSet tem http_method_names = ['get', 'patch', 'head', 'options'].
        Este teste garante que a adição de UserCreateView não alterou o ViewSet.
        """
        profiles_url = reverse("accounts:userprofile-list")

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(profiles_url, VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
