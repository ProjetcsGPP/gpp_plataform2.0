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


# ── Cache Keys ────────────────────────────────────────────────────────────────

class TestAuthorizationServiceCacheKeys(TestCase):
    """
    Cobre o comportamento de cache do AuthorizationService:
      - Chaves distintas por aplicação para o mesmo usuário
      - Mudança de chave quando a versão é incrementada
      - Cache de instância evita novo acesso ao banco
    """

    # 1. Chaves distintas por aplicação ──────────────────────────────────────

    def test_same_user_different_apps_have_different_cache_keys(self):
        """
        _permissions_cache_key() deve produzir valores distintos para
        app_code diferentes do mesmo usuário.
        Não usa banco — user e application são MagicMock.
        """
        user = MagicMock()
        user.id = 99

        app_a = MagicMock()
        app_a.codigointerno = "APP_A"

        app_b = MagicMock()
        app_b.codigointerno = "APP_B"

        with patch("apps.accounts.services.authorization_service.cache") as mock_cache:
            # version key não existe → retorna None → fallback para 1
            mock_cache.get.return_value = None

            key_a = AuthorizationService(user, app_a)._permissions_cache_key()
            key_b = AuthorizationService(user, app_b)._permissions_cache_key()

        self.assertNotEqual(key_a, key_b)
        # garante que o app_code está de fato embutido na chave
        self.assertIn("APP_A", key_a)
        self.assertIn("APP_B", key_b)

    # 2. Mudança de chave com incremento de versão ───────────────────────────

    def test_cache_key_changes_when_version_increments(self):
        """
        Quando authz_version:{user_id} é incrementado no cache,
        _permissions_cache_key() deve retornar uma chave diferente.
        Usa banco real para criar o User.
        """
        import django.test
        from django.contrib.auth import get_user_model
        from django.core.cache import cache

        User = get_user_model()
        user = User.objects.create_user(
            username="cache_version_test_user",
            password="testpass123",
        )

        # versão inicial ausente → fallback 1
        cache.delete(f"authz_version:{user.id}")
        service_v1 = AuthorizationService(user)
        key_v1 = service_v1._permissions_cache_key()

        # incrementa versão para 2
        cache.set(f"authz_version:{user.id}", 2)
        service_v2 = AuthorizationService(user)
        key_v2 = service_v2._permissions_cache_key()

        self.assertNotEqual(key_v1, key_v2)
        self.assertIn(":v1:", key_v1)
        self.assertIn(":v2:", key_v2)

    # 3. Cache de instância evita nova consulta ao banco ─────────────────────

    def test_instance_cache_avoids_repeated_db_query(self):
        """
        Se self._permissions já está populado, _load_permissions() deve
        retornar o mesmo objeto sem acessar o cache externo ou o banco.
        Não usa banco — user é MagicMock.
        """
        user = MagicMock()
        user.id = 42

        service = AuthorizationService(user)

        # Injeta diretamente o cache de instância
        expected = {"fake_perm"}
        service._permissions = expected

        result_first = service._load_permissions()
        result_second = service._load_permissions()

        # Ambas as chamadas devem retornar o mesmo objeto (identidade)
        self.assertIs(result_first, expected)
        self.assertIs(result_second, expected)
        self.assertIs(result_first, result_second)
