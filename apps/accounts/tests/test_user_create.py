"""
GPP Plataform 2.0 — Accounts Tests: UserCreate (GAP-01)
Cobre cenários T-01 a T-11 conforme especificação das Fases 1 e 7.

Padrão de autenticação:
    O JWTAuthenticationMiddleware processa o request antes do DRF e retorna
    401 via JsonResponse sem token válido — mesmo com force_authenticate.
    Todos os testes autenticados usam patch_security() para bypassar os 3
    middlewares customizados (JWT, RoleContext, Authorization).

Padrão de resposta de erro (400):
    O gpp_exception_handler envolve todos os erros DRF no envelope:
        {"success": False, "status_code": <N>, "errors": <detalhe>}
    Os asserts de T-02/03/04/05 acessam response.data["errors"].

T-08 (rollback):
    A view captura Exception genérica e relênça como APIException(500),
    que o gpp_exception_handler processa sem re-levantar no TestClient.
    O teste usa raise_request_exception=False como garantia extra.

T-07 (sem permissão — FASE 7):
    Após migração para CanCreateUser, a permissão é determinada por
    ClassificacaoUsuario.pode_criar_usuario. plain_user tem classificacao_id=1
    com pode_criar_usuario=False → 403.

T-11 (gestor sem PORTAL_ADMIN — FASE 7):
    Gestor com ClassificacaoUsuario.pode_criar_usuario=True pode criar usuário
    sem possuir a role PORTAL_ADMIN — confirma que o acesso não depende mais
    de is_portal_admin.
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
        idclassificacaousuario=1,
        defaults={
            "strdescricao": "Padrão",
            "pode_criar_usuario": False,   # default seguro
            "pode_editar_usuario": False,
        },
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
    ClassificacaoUsuario PK=1 tem pode_criar_usuario=False (default seguro).
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


def _make_gestor_user(username="gestor_gap01"):
    """
    Cria usuário com ClassificacaoUsuario.pode_criar_usuario=True.
    Substitui a dependência de PORTAL_ADMIN para testes de criação de usuário.
    """
    _bootstrap_lookups()
    classificacao_gestor, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=10,
        defaults={
            "strdescricao": "Gestor",
            "pode_criar_usuario": True,
            "pode_editar_usuario": True,
        },
    )
    user = User.objects.create_user(username=username, password="Gestor@2026!")
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="SEDU",
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario=classificacao_gestor,
    )
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
    Testes T-01 a T-11 para POST /api/accounts/users/.
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("accounts:user-create")
        cls.admin = _make_admin_user()       # PORTAL_ADMIN — mantido para T-01 (bootstrap)
        cls.gestor = _make_gestor_user()     # Novo: ClassificacaoUsuario.pode_criar_usuario=True
        cls.plain_user = _make_plain_user()  # pode_criar_usuario=False

    def setUp(self):
        self.client = APIClient(raise_request_exception=False)

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

        # Verifica shape da resposta 201 (sem envelope — sucesso não é envolvido)
        self.assertEqual(response.data["username"], "joao.silva")
        self.assertEqual(response.data["email"], "joao@exemplo.com")
        self.assertIn("datacriacao", response.data)
        self.assertNotIn("password", response.data)  # write_only

    # ── T-02 — username duplicado ──────────────────────────────────────────────

    def test_T02_duplicate_username_returns_400(self):
        """T-02: username já existente → 400 com mensagem clara."""
        User.objects.create_user(username="joao.duplicado", password="Xyz@2026!")
        payload = {**VALID_PAYLOAD, "username": "joao.duplicado", "email": "unique_t02@test.com"}

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # gpp_exception_handler envolve erros em {"success": False, "errors": {...}}
        errors = response.data["errors"]
        self.assertIn("username", errors)
        self.assertIn("já está em uso", str(errors["username"]))

    # ── T-03 — email duplicado ─────────────────────────────────────────────────

    def test_T03_duplicate_email_returns_400(self):
        """T-03: email já existente → 400 com mensagem clara."""
        User.objects.create_user(
            username="outro_user_t03", password="Xyz@2026!", email="dup_t03@test.com"
        )
        payload = {**VALID_PAYLOAD, "username": "unique_user_t03", "email": "dup_t03@test.com"}

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data["errors"]
        self.assertIn("email", errors)
        self.assertIn("já está em uso", str(errors["email"]))

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
        errors = response.data["errors"]
        self.assertIn("password", errors)

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
        errors = response.data["errors"]
        self.assertIn("orgao", errors)

    # ── T-06 — sem autenticação ────────────────────────────────────────────────

    def test_T06_unauthenticated_returns_401(self):
        """
        T-06: request sem autenticação → 401.
        NÃO usa patch_security — testa o middleware real sem credencial.
        """
        response = self.client.post(self.url, VALID_PAYLOAD, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── T-07 — usuário sem permissão (CanCreateUser) ───────────────────────────

    def test_T07_usuario_sem_permissao_retorna_403(self):
        """
        T-07: usuário com ClassificacaoUsuario.pode_criar_usuario=False → 403.
        CanCreateUser lê a flag do banco via AuthorizationService.
        patch_security não injeta is_portal_admin=True para não fazer bypass.
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
        A view captura Exception genérica e relênça como APIException(500),
        que o gpp_exception_handler processa sem re-levantar no TestClient.
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

        # View converte Exception → APIException(500)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # User NÃO deve ter persistido — rollback garantido pelo atomic() (R-01)
        self.assertEqual(User.objects.count(), users_before)
        self.assertFalse(User.objects.filter(username="atomic_t08").exists())

    # ── T-09 — GET não permitido ───────────────────────────────────────────────

    def test_T09_get_returns_405(self):
        """
        T-09: GET /api/accounts/users/ → 405 Method Not Allowed.
        UserCreateView só implementa .post() — DRF rejeita outros métodos.
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
        http_method_names = ['get', 'patch', 'head', 'options'] — POST bloqueado.
        Garante que a adição de UserCreateView não alterou o ViewSet existente.
        """
        profiles_url = reverse("accounts:userprofile-list")

        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.post(profiles_url, VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ── T-11 — Gestor (sem PORTAL_ADMIN) pode criar usuário ───────────────────

    def test_T11_gestor_pode_criar_usuario(self):
        """
        T-11: Gestor com pode_criar_usuario=True → 201 (ou 400 de validação).
        Confirma que o acesso NÃO depende mais de PORTAL_ADMIN.
        """
        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.gestor)
            payload = {**VALID_PAYLOAD, "username": "novo_t11", "email": "t11@test.com"}
            response = self.client.post(self.url, payload, format="json")
        # 201 criado ou 400 validação — nunca 403
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(
            response.status_code,
            [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST],
        )
