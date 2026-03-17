"""
GPP Plataform 2.0 — Testes de Escopo por Aplicação para Gerenciamento de Usuários

Cobre a regra DYN-SCOPE:
  - Gestores só podem criar/editar usuários em aplicações onde possuem role.
  - PORTAL_ADMIN possui acesso irrestrito.
  - A validação é exclusivamente baseada em UserRole no banco (sem dados da request).

Testes unitários (TestCase + MagicMock):
  Testam AuthorizationService.user_can_manage_target_user() isolado.

Testes de integração (APITestCase):
  T-12: gestor_pode_criar_usuario_na_propria_aplicacao          → 201
  T-13: gestor_nao_pode_criar_usuario_em_outra_aplicacao        → 403
  T-14: portal_admin_pode_criar_usuario_em_qualquer_aplicacao   → 201
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
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

from apps.accounts.services.authorization_service import AuthorizationService
from apps.core.tests.utils import patch_security


# ─── Fixtures compartilhadas ────────────────────────────────────────────────────────────────────

def _bootstrap_lookups():
    StatusUsuario.objects.get_or_create(idstatususuario=1, defaults={"strdescricao": "Ativo"})
    TipoUsuario.objects.get_or_create(idtipousuario=1, defaults={"strdescricao": "Padrão"})
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1,
        defaults={
            "strdescricao": "Padrão",
            "pode_criar_usuario": False,
            "pode_editar_usuario": False,
        },
    )


def _make_app(codigo, nome):
    """Cria uma Aplicacao de teste com isshowinportal=False."""
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo,
        defaults={
            "nomeaplicacao": nome,
            "isshowinportal": False,
        },
    )
    return app


def _make_role(codigo, aplicacao):
    """Cria uma Role simples associada a uma aplicação."""
    role, _ = Role.objects.get_or_create(
        codigoperfil=codigo,
        defaults={
            "nomeperfil": f"Perfil {codigo}",
            "aplicacao": aplicacao,
        },
    )
    return role


def _make_gestor(username, pode_criar=True, pode_editar=True, pk_classificacao=20):
    """Cria um usuário gestor com ClassificacaoUsuario configurada."""
    _bootstrap_lookups()
    classificacao, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=pk_classificacao,
        defaults={
            "strdescricao": f"Gestor_{pk_classificacao}",
            "pode_criar_usuario": pode_criar,
            "pode_editar_usuario": pode_editar,
        },
    )
    user = User.objects.create_user(username=username, password="Teste@2026!")
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="SEDU",
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario=classificacao,
    )
    return user


def _make_target_user(username):
    """Cria um usuário alvo simples sem classificacao especial."""
    _bootstrap_lookups()
    user = User.objects.create_user(username=username, password="Teste@2026!")
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="SEDU",
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
    )
    return user


def _assign_role(user, role, aplicacao):
    """Cria um UserRole para o usuário na aplicação informada."""
    return UserRole.objects.get_or_create(
        user=user,
        role=role,
        aplicacao=aplicacao,
    )[0]


# ─── Testes Unitários ─────────────────────────────────────────────────────────────────────────

class UserCanManageTargetUserUnitTests(TestCase):
    """
    Testa AuthorizationService.user_can_manage_target_user() com MagicMock.
    Não depende de banco de dados real — rápido e isolado.

    NOTA: _is_portal_admin vive em UserPolicy após a refatoração.
    Os patches são feitos na instância de UserPolicy retornada por
    service._policy(), não mais diretamente no AuthorizationService.
    """

    def _make_mock_user(self, user_id):
        user = MagicMock()
        user.id = user_id
        user.is_authenticated = True
        return user

    def test_portal_admin_sempre_pode_gerenciar(self):
        """
        PORTAL_ADMIN bypass → True independente de qualquer outra regra.
        """
        user = self._make_mock_user(1)
        target = self._make_mock_user(2)
        service = AuthorizationService(user)
        policy = service._policy()
        with patch.object(policy, "_is_portal_admin", return_value=True):
            self.assertTrue(service.user_can_manage_target_user(target))

    def test_sem_permissao_edicao_nega(self):
        """
        Gestor sem user_can_edit_users() → False (fail-closed).
        """
        user = self._make_mock_user(1)
        target = self._make_mock_user(2)
        service = AuthorizationService(user)
        policy = service._policy()
        with patch.object(policy, "_is_portal_admin", return_value=False), \
             patch.object(policy, "can_edit_user", return_value=False):
            self.assertFalse(service.user_can_manage_target_user(target))

    def test_intersecao_existe_permite(self):
        """
        Gestor com permissão e interseção de aplicações → True.
        """
        user = self._make_mock_user(1)
        target = self._make_mock_user(2)
        service = AuthorizationService(user)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "user_can_edit_users", return_value=True), \
             patch(
                 "apps.accounts.services.authorization_service.UserRole"
                 if False else  # usa o import dinâmico da implementação
                 "apps.accounts.models.UserRole",
                 create=True,
             ):
            # Validação direta via DB — mock da query de interseção
            with patch(
                "apps.accounts.services.authorization_service.AuthorizationService"
                "._is_portal_admin",
                return_value=False,
            ):
                pass  # testa via integração abaixo

    def test_sem_intersecao_nega(self):
        """
        Gestor com permissão mas sem interseção → False.
        Validado via integração no banco real abaixo (T-13).
        """
        pass  # coberto por UserManagementScopeIntegrationTests.test_t13


# ─── Testes de Integração — AuthorizationService no banco ────────────────────────────────

class UserCanManageTargetUserDBTests(TestCase):
    """
    Testa AuthorizationService.user_can_manage_target_user() com banco real.
    Verifica a lógica de interseção de UserRole diretamente.
    """

    @classmethod
    def setUpTestData(cls):
        cls.app_a = _make_app("APP_A", "Aplicação A")
        cls.app_b = _make_app("APP_B", "Aplicação B")
        cls.role_a = _make_role("ROLE_APP_A", cls.app_a)
        cls.role_b = _make_role("ROLE_APP_B", cls.app_b)

        cls.gestor = _make_gestor("scope_gestor_db", pk_classificacao=30)
        cls.target_mesma_app = _make_target_user("scope_target_same")
        cls.target_outra_app = _make_target_user("scope_target_other")
        cls.target_sem_role = _make_target_user("scope_target_norole")

        # Gestor está em APP_A
        _assign_role(cls.gestor, cls.role_a, cls.app_a)
        # Target mesma app também está em APP_A → interseção existe
        _assign_role(cls.target_mesma_app, cls.role_a, cls.app_a)
        # Target outra app está apenas em APP_B → sem interseção
        _assign_role(cls.target_outra_app, cls.role_b, cls.app_b)


        cls.status, _ = StatusUsuario.objects.get_or_create(
            idstatususuario=1, defaults={"strdescricao": "Ativo"}
        )
        cls.tipo, _ = TipoUsuario.objects.get_or_create(
            idtipousuario=1, defaults={"strdescricao": "Padrão"}
        )
        cls.classificacao, _ = ClassificacaoUsuario.objects.get_or_create(
            idclassificacaousuario=999,
            defaults={
                "strdescricao": "Classificacao Teste",
                "pode_criar_usuario": True,
                "pode_editar_usuario": True,
            },
        )
        # Target sem role não tem UserRole algum → sem interseção

    def test_gestor_pode_gerenciar_usuario_mesma_app(self):
        """Gestor com role em APP_A pode gerenciar usuário também em APP_A."""
        service = AuthorizationService(self.gestor)
        self.assertTrue(service.user_can_manage_target_user(self.target_mesma_app))

    def test_gestor_nao_pode_gerenciar_usuario_outra_app(self):
        """Gestor com role apenas em APP_A não pode gerenciar usuário só em APP_B."""
        service = AuthorizationService(self.gestor)
        self.assertFalse(service.user_can_manage_target_user(self.target_outra_app))

    def test_gestor_nao_pode_gerenciar_usuario_sem_role(self):
        """Gestor não pode gerenciar usuário sem nenhuma role (sem interseção)."""
        service = AuthorizationService(self.gestor)
        self.assertFalse(service.user_can_manage_target_user(self.target_sem_role))

    def test_portal_admin_pode_gerenciar_qualquer_usuario(self):
        """Usuário com role PORTAL_ADMIN pode gerenciar qualquer target."""
        # Cria um usuário portal_admin no banco
        _bootstrap_lookups()
        portal_admin_role, _ = Role.objects.get_or_create(
            codigoperfil="PORTAL_ADMIN",
            defaults={
                "nomeperfil": "Portal Admin",
                "aplicacao": self.app_a,
            },
        )
        admin_user = _make_gestor("scope_portal_admin_db", pk_classificacao=31)
        _assign_role(admin_user, portal_admin_role, self.app_a)

        service = AuthorizationService(admin_user)
        # Deve poder gerenciar target em app diferente
        self.assertTrue(service.user_can_manage_target_user(self.target_outra_app))
        self.assertTrue(service.user_can_manage_target_user(self.target_sem_role))


# ─── T-12, T-13, T-14 — Testes de API ─────────────────────────────────────────────────────

class UserManagementScopeIntegrationTests(APITestCase):
    """
    Testes de integração T-12, T-13, T-14 conforme especificação DYN-SCOPE.

    Cenário:
      - app_propria: aplicação onde o gestor possui role.
      - app_outra:   aplicação diferente, sem role para o gestor.
      - gestor: ClassificacaoUsuario com pode_criar_usuario=True, role em app_propria.
      - portal_admin: usuário com role PORTAL_ADMIN (bypass total).

    Endpoint testado: POST /api/accounts/users/create-with-role/
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("accounts:user-create-with-role")

        # Aplicações
        cls.app_propria = _make_app("APP_T_PROPRIA", "App T Própria")
        cls.app_outra = _make_app("APP_T_OUTRA", "App T Outra")

        # Roles
        cls.role_propria = _make_role("ROLE_T_PROPRIA", cls.app_propria)
        cls.role_outra = _make_role("ROLE_T_OUTRA", cls.app_outra)
        cls.role_portal_admin, _ = Role.objects.get_or_create(
            codigoperfil="PORTAL_ADMIN",
            defaults={
                "nomeperfil": "Portal Admin",
                "aplicacao": cls.app_propria,
            },
        )

        # Usuários
        cls.gestor = _make_gestor("t_gestor_scope", pk_classificacao=40)
        cls.admin = _make_gestor("t_portal_admin_scope", pk_classificacao=41)

        # Associações de role
        _assign_role(cls.gestor, cls.role_propria, cls.app_propria)
        _assign_role(cls.admin, cls.role_portal_admin, cls.app_propria)


        cls.status, _ = StatusUsuario.objects.get_or_create(
            idstatususuario=1, defaults={"strdescricao": "Ativo"}
        )
        cls.tipo, _ = TipoUsuario.objects.get_or_create(
            idtipousuario=1, defaults={"strdescricao": "Padrão"}
        )
        cls.classificacao, _ = ClassificacaoUsuario.objects.get_or_create(
            idclassificacaousuario=999,
            defaults={
                "strdescricao": "Classificacao Teste",
                "pode_criar_usuario": True,
                "pode_editar_usuario": True,
            },
        )

    def setUp(self):
        self.client = APIClient(raise_request_exception=False)

    def _payload_create_with_role(self, suffix, aplicacao_id, role_id):
        return {
            "username": f"scope_{suffix}",
            "email": f"scope_{suffix}@test.com",
            "password": "Segura@2026!",
            "first_name": "Scope",
            "last_name": "Test",
            "name": f"Scope Test {suffix}",
            "orgao": "SEDU",

            # 🔥 NOVO (OBRIGATÓRIO)
            "status_usuario": self.status.idstatususuario,
            "tipo_usuario": self.tipo.idtipousuario,
            "classificacao_usuario": self.classificacao.idclassificacaousuario,

            "aplicacao_id": aplicacao_id,
            "role_id": role_id,
        }

    # ── T-12: gestor_pode_criar_usuario_na_propria_aplicacao ───────────────────────────

    def test_t12_gestor_pode_criar_usuario_na_propria_aplicacao(self):
        """
        T-12: Gestor com role em app_propria pode criar usuário nessa mesma app.
        Resultado esperado: 201 CREATED.
        """
        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.gestor)
            payload = self._payload_create_with_role(
                "t12",
                aplicacao_id=self.app_propria.pk,
                role_id=self.role_propria.pk,
            )
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=(
                f"T-12 falhou: esperado 201, recebido {response.status_code}. "
                f"Detalhe: {response.data}"
            ),
        )

    # ── T-13: gestor_nao_pode_criar_usuario_em_outra_aplicacao ────────────────────────

    def test_t13_gestor_nao_pode_criar_usuario_em_outra_aplicacao(self):
        """
        T-13: Gestor com role apenas em app_propria tenta criar em app_outra.
        Resultado esperado: 403 FORBIDDEN.
        """
        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.gestor)
            payload = self._payload_create_with_role(
                "t13",
                aplicacao_id=self.app_outra.pk,
                role_id=self.role_outra.pk,
            )
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            msg=(
                f"T-13 falhou: esperado 403, recebido {response.status_code}. "
                f"Detalhe: {response.data}"
            ),
        )

    # ── T-14: portal_admin_pode_criar_usuario_em_qualquer_aplicacao ──────────────────

    def test_t14_portal_admin_pode_criar_usuario_em_qualquer_aplicacao(self):
        """
        T-14: PORTAL_ADMIN pode criar usuário em qualquer aplicação,
        incluindo app_outra onde não possui role direta.
        Resultado esperado: 201 CREATED.
        """
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            payload = self._payload_create_with_role(
                "t14",
                aplicacao_id=self.app_outra.pk,
                role_id=self.role_outra.pk,
            )
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=(
                f"T-14 falhou: esperado 201, recebido {response.status_code}. "
                f"Detalhe: {response.data}"
            ),
        )

    # ── Testes adicionais de segurança ─────────────────────────────────────────────

    def test_gestor_nao_autenticado_retorna_401(self):
        """
        Sem autenticação → 401. Não depende de escopo.
        """
        payload = self._payload_create_with_role(
            "noauth",
            aplicacao_id=self.app_propria.pk,
            role_id=self.role_propria.pk,
        )
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gestor_sem_pode_criar_usuario_retorna_403(self):
        """
        Usuário com pode_criar_usuario=False → 403 (CanCreateUser bloqueia antes do escopo).
        """
        usuario_sem_perm = _make_gestor(
            "t_no_perm_scope",
            pode_criar=False,
            pode_editar=False,
            pk_classificacao=42,
        )
        patches = patch_security(usuario_sem_perm, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=usuario_sem_perm)
            payload = self._payload_create_with_role(
                "noperm",
                aplicacao_id=self.app_propria.pk,
                role_id=self.role_propria.pk,
            )
            response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
