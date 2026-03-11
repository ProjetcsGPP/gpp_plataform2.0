"""
Testes unitários do AuthorizationService.

Cobre:
  - PORTAL_ADMIN sempre retorna True
  - Sem role retorna False
  - RBAC encontra permissão
  - RBAC não encontra permissão
  - ABAC passa com atributos corretos
  - ABAC bloqueia com atributo errado / ausente
"""
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase

from apps.accounts.services.authorization_service import AuthorizationService


class AuthorizationServiceTests(TestCase):

    def _make_user(self, user_id=1, authenticated=True):
        """Cria um mock de usuário autenticado."""
        user = MagicMock()
        user.id = user_id
        user.is_authenticated = authenticated
        return user

    def _make_service(self, user=None, application=None):
        if user is None:
            user = self._make_user()
        return AuthorizationService(user, application)

    # ── PORTAL_ADMIN ─────────────────────────────────────────────────────────

    def test_can_portal_admin_always_true(self):
        """PORTAL_ADMIN deve ter acesso irrestrito a qualquer permissão."""
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=True):
            self.assertTrue(service.can("view_acao"))
            self.assertTrue(service.can("delete_acao"))
            self.assertTrue(service.can("qualquer_coisa"))

    # ── Sem role válida ───────────────────────────────────────────────────────

    def test_can_no_role_returns_false(self):
        """Sem UserRole na aplicação, can() deve retornar False."""
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_has_valid_role", return_value=False):
            self.assertFalse(service.can("view_acao"))

    # ── RBAC ──────────────────────────────────────────────────────────────────

    def test_can_rbac_permission_found(self):
        """Se a permissão existe no set RBAC, can() retorna True."""
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_has_valid_role", return_value=True), \
             patch.object(service, "_load_permissions", return_value={"view_acao", "add_acao"}):
            self.assertTrue(service.can("view_acao"))

    def test_can_rbac_permission_not_found(self):
        """Se a permissão NÃO existe no set RBAC, can() retorna False."""
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_has_valid_role", return_value=True), \
             patch.object(service, "_load_permissions", return_value={"add_acao"}):
            self.assertFalse(service.can("delete_acao"))

    # ── ABAC ──────────────────────────────────────────────────────────────────

    def test_can_abac_filter_passes(self):
        """
        Se o atributo ABAC do usuário corresponde ao contexto fornecido,
        can() deve retornar True.
        """
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_has_valid_role", return_value=True), \
             patch.object(service, "_load_permissions", return_value={"view_acao"}), \
             patch.object(service, "_load_attributes", return_value={"eixo": "A", "orgao": "SEGES"}):
            self.assertTrue(service.can("view_acao", context={"eixo": "A"}))

    def test_can_abac_filter_blocks(self):
        """
        Se o atributo ABAC do usuário NÃO corresponde ao contexto,
        can() deve retornar False.
        """
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_has_valid_role", return_value=True), \
             patch.object(service, "_load_permissions", return_value={"view_acao"}), \
             patch.object(service, "_load_attributes", return_value={"eixo": "B"}):
            # Usuário tem eixo=B mas o contexto exige eixo=A
            self.assertFalse(service.can("view_acao", context={"eixo": "A"}))

    def test_can_abac_missing_attribute_blocks(self):
        """
        Se o atributo ABAC não está definido para o usuário (fail-closed),
        can() deve retornar False.
        """
        service = self._make_service()
        with patch.object(service, "_is_portal_admin", return_value=False), \
             patch.object(service, "_has_valid_role", return_value=True), \
             patch.object(service, "_load_permissions", return_value={"view_acao"}), \
             patch.object(service, "_load_attributes", return_value={}):
            self.assertFalse(service.can("view_acao", context={"eixo": "A"}))

    # ── Usuário não autenticado ───────────────────────────────────────────────

    def test_can_unauthenticated_user_returns_false(self):
        """Usuário não autenticado deve receber False independente da permissão."""
        user = self._make_user(authenticated=False)
        service = self._make_service(user=user)
        self.assertFalse(service.can("view_acao"))

    def test_can_none_user_returns_false(self):
        """User=None deve retornar False sem lançar exceção."""
        service = AuthorizationService(user=None)
        self.assertFalse(service.can("view_acao"))
