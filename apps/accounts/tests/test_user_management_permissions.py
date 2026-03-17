"""
GPP Plataform 2.0 — Testes de Autorização: User Management Permissions

Cobre AuthorizationService.user_can_create_users() e user_can_edit_users()
com base em ClassificacaoUsuario.pode_criar_usuario / pode_editar_usuario.

Padrão de testes:
  - Unitários (TestCase + MagicMock): testam AuthorizationService isolado.
  - Integração (APITestCase + DB real): testam comportamento fim-a-fim.
"""
from unittest.mock import MagicMock, patch, PropertyMock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.accounts.models import (
    ClassificacaoUsuario,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
)
from apps.accounts.services.authorization_service import AuthorizationService
from apps.core.tests.utils import patch_security


# ─── Helpers compartilhados ─────────────────────────────────────────────────────

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


def _make_user_with_classificacao(username, pk_classificacao, pode_criar, pode_editar):
    _bootstrap_lookups()
    classificacao, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=pk_classificacao,
        defaults={
            "strdescricao": f"Classificacao_{pk_classificacao}",
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


# ─── Testes Unitários — AuthorizationService ─────────────────────────────────────

class AuthorizationServiceUserManagementUnitTests(TestCase):
    """
    Testa user_can_create_users() e user_can_edit_users() com MagicMock.
    Não depende de banco de dados — rápido e isolado.
    """

    def _make_mock_user(self, user_id=99, authenticated=True):
        user = MagicMock()
        user.id = user_id
        user.is_authenticated = authenticated
        return user

    def _make_classificacao_mock(self, pode_criar=False, pode_editar=False):
        c = MagicMock()
        c.pk = 1
        c.strdescricao = "MockClassificacao"
        c.pode_criar_usuario = pode_criar
        c.pode_editar_usuario = pode_editar
        return c

    # ── user_can_create_users ────────────────────────────────────────────────

    def test_portal_admin_pode_criar(self):
        """PORTAL_ADMIN bypass → True independente de classificacao."""
        user = self._make_mock_user()
        service = AuthorizationService(user)
        with patch.object(service, "_is_portal_admin", return_value=True):
            self.assertTrue(service.user_can_create_users())

    def test_pode_criar_quando_flag_true(self):
        """pode_criar_usuario=True → True."""
        user = self._make_mock_user()
        service = AuthorizationService(user)
        classificacao = self._make_classificacao_mock(pode_criar=True)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=classificacao):
            self.assertTrue(service.user_can_create_users())

    def test_nao_pode_criar_quando_flag_false(self):
        """pode_criar_usuario=False → False."""
        user = self._make_mock_user()
        service = AuthorizationService(user)
        classificacao = self._make_classificacao_mock(pode_criar=False)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=classificacao):
            self.assertFalse(service.user_can_create_users())

    def test_nao_pode_criar_sem_classificacao(self):
        """Sem classificacao → False (fail-closed)."""
        user = self._make_mock_user()
        service = AuthorizationService(user)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=None):
            self.assertFalse(service.user_can_create_users())

    # ── user_can_edit_users ─────────────────────────────────────────────────

    def test_portal_admin_pode_editar(self):
        user = self._make_mock_user()
        service = AuthorizationService(user)
        with patch.object(service, "_is_portal_admin", return_value=True):
            self.assertTrue(service.user_can_edit_users())

    def test_pode_editar_quando_flag_true(self):
        user = self._make_mock_user()
        service = AuthorizationService(user)
        classificacao = self._make_classificacao_mock(pode_editar=True)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=classificacao):
            self.assertTrue(service.user_can_edit_users())

    def test_nao_pode_editar_quando_flag_false(self):
        user = self._make_mock_user()
        service = AuthorizationService(user)
        classificacao = self._make_classificacao_mock(pode_editar=False)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=classificacao):
            self.assertFalse(service.user_can_edit_users())

    def test_nao_pode_editar_sem_classificacao(self):
        user = self._make_mock_user()
        service = AuthorizationService(user)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=None):
            self.assertFalse(service.user_can_edit_users())

    def test_nao_pode_criar_usuario_nao_autenticado(self):
        """Usuário não autenticado não deve passar pelo _is_portal_admin."""
        user = MagicMock()
        user.id = 99
        user.is_authenticated = True  # autenticado, mas sem profile
        service = AuthorizationService(user)
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_get_classificacao", return_value=None):
            self.assertFalse(service.user_can_create_users())


# ─── Testes de Integração — API ────────────────────────────────────────────────

class UserCreatePermissionIntegrationTests(APITestCase):
    """
    Testa o endpoint POST /api/accounts/users/ com DB real.
    Verifica que CanCreateUser respeita ClassificacaoUsuario.
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("accounts:user-create")
        cls.gestor = _make_user_with_classificacao(
            "gestor_int", pk_classificacao=10,
            pode_criar=True, pode_editar=True,
        )
        cls.coordenador = _make_user_with_classificacao(
            "coord_int", pk_classificacao=11,
            pode_criar=False, pode_editar=False,
        )
        cls.usuario_comum = _make_user_with_classificacao(
            "usuario_int", pk_classificacao=12,
            pode_criar=False, pode_editar=False,
        )

    def setUp(self):
        self.client = APIClient(raise_request_exception=False)

    def _payload(self, suffix):
        return {
            "username": f"novo_{suffix}",
            "email": f"{suffix}@test.com",
            "password": "Segura@2026!",
            "first_name": "Novo",
            "last_name": "Usuario",
            "name": f"Novo Usuario {suffix}",
            "orgao": "SEDU",
        }

    def test_gestor_acessa_endpoint_sem_portal_admin(self):
        """Gestor (pode_criar=True, sem PORTAL_ADMIN role) → 201 ou 400, nunca 403."""
        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.gestor)
            response = self.client.post(self.url, self._payload("gestor"), format="json")
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_coordenador_nao_acessa_endpoint(self):
        """Coordenador (pode_criar=False) → 403."""
        patches = patch_security(self.coordenador, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.coordenador)
            response = self.client.post(self.url, self._payload("coord"), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_comum_nao_acessa_endpoint(self):
        """Usuário comum (pode_criar=False) → 403."""
        patches = patch_security(self.usuario_comum, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.usuario_comum)
            response = self.client.post(self.url, self._payload("usuario"), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sem_autenticacao_retorna_401(self):
        """Sem token → 401. NÃO usa patch_security."""
        response = self.client.post(self.url, self._payload("noauth"), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
