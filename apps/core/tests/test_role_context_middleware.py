"""
Testes para RoleContextMiddleware.
Casos cobertos:
  1. Usuário AnonymousUser → request.user_roles = [] (nunca None)
  2. Roles carregadas do cache corretamente
  3. Cache miss → roles carregadas do banco e ROLES_LOADED logado
  4. ROLE_SWITCH logado quando roles mudam entre requests
  5. request.user_roles é sempre lista (nunca None)
  6. is_portal_admin correto com role PORTAL_ADMIN presente
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.core.middleware.role_context import RoleContextMiddleware


def _make_user_role(codigo):
    ur = MagicMock()
    ur.role.codigoperfil = codigo
    return ur


class RoleContextMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))
        self.middleware = RoleContextMiddleware(self.get_response)

    def _make_request(self, user=None, application=None, path="/api/test/"):
        request = self.factory.get(path)
        request.user = user or AnonymousUser()
        request.application = application
        request.is_portal_admin = False
        return request

    def test_anonymous_user_gets_empty_roles(self):
        """Caso 1: AnonymousUser → user_roles = [], nunca None."""
        request = self._make_request()
        self.middleware(request)
        self.assertEqual(request.user_roles, [])
        self.assertIsNotNone(request.user_roles)

    def test_roles_loaded_from_cache(self):
        """Caso 2: Roles em cache são usadas sem consultar banco."""
        mock_user = MagicMock()
        mock_user.id = 1
        cached_roles = [_make_user_role("GESTOR_PNGI")]
        mock_app = MagicMock()
        mock_app.codigointerno = "ACOES_PNGI"

        request = self._make_request(user=mock_user, application=mock_app)

        with patch("apps.core.middleware.role_context.cache") as mock_cache:
            mock_cache.get.return_value = cached_roles
            self.middleware(request)

        self.assertEqual(request.user_roles, cached_roles)

    def test_roles_loaded_from_db_on_cache_miss(self):
        """Caso 3: Cache miss → roles carregadas do banco e ROLES_LOADED logado."""
        mock_user = MagicMock()
        mock_user.id = 2
        db_roles = [_make_user_role("OPERADOR_ACAO")]
        mock_app = MagicMock()
        mock_app.codigointerno = "ACOES_PNGI"

        request = self._make_request(user=mock_user, application=mock_app)

        def cache_get_side_effect(key):
            return None  # cache miss em todas as chaves

        with patch("apps.core.middleware.role_context.cache") as mock_cache:
            mock_cache.get.side_effect = cache_get_side_effect
            with patch("apps.core.middleware.role_context.UserRole") as mock_ur_model:
                mock_qs = MagicMock()
                mock_qs.filter.return_value = mock_qs
                mock_qs.__or__ = lambda self, other: mock_qs
                mock_qs.distinct.return_value = db_roles
                mock_ur_model.objects.filter.return_value.select_related.return_value = mock_qs
                with self.assertLogs("gpp.security", level="INFO") as log_ctx:
                    self.middleware(request)

        self.assertTrue(any("ROLES_LOADED" in msg for msg in log_ctx.output))

    def test_role_switch_logged(self):
        """Caso 4: Troca de role detectada → ROLE_SWITCH logado."""
        mock_user = MagicMock()
        mock_user.id = 3
        new_roles = [_make_user_role("COORDENADOR_PNGI")]
        mock_app = MagicMock()
        mock_app.codigointerno = "ACOES_PNGI"

        request = self._make_request(user=mock_user, application=mock_app)

        def cache_side_effect(key):
            if "previous" in key:
                return ["GESTOR_PNGI"]  # role anterior diferente
            return None  # cache miss nas roles normais

        with patch("apps.core.middleware.role_context.cache") as mock_cache:
            mock_cache.get.side_effect = cache_side_effect
            with patch("apps.core.middleware.role_context.UserRole") as mock_ur_model:
                mock_qs = MagicMock()
                mock_qs.filter.return_value = mock_qs
                mock_qs.__or__ = lambda self, other: mock_qs
                mock_qs.distinct.return_value = new_roles
                mock_ur_model.objects.filter.return_value.select_related.return_value = mock_qs
                with self.assertLogs("gpp.security", level="INFO") as log_ctx:
                    self.middleware(request)

        self.assertTrue(any("ROLE_SWITCH" in msg for msg in log_ctx.output))

    def test_user_roles_never_none(self):
        """Caso 5: user_roles é sempre lista, nunca None."""
        mock_user = MagicMock()
        mock_user.id = 4
        mock_app = MagicMock()
        mock_app.codigointerno = "PORTAL"

        request = self._make_request(user=mock_user, application=mock_app)

        with patch("apps.core.middleware.role_context.cache") as mock_cache:
            mock_cache.get.return_value = None
            with patch("apps.core.middleware.role_context.UserRole") as mock_ur_model:
                mock_qs = MagicMock()
                mock_qs.filter.return_value = mock_qs
                mock_qs.__or__ = lambda self, other: mock_qs
                mock_qs.distinct.return_value = []
                mock_ur_model.objects.filter.return_value.select_related.return_value = mock_qs
                self.middleware(request)

        self.assertIsNotNone(request.user_roles)
        self.assertIsInstance(request.user_roles, list)

    def test_portal_admin_role_sets_flag(self):
        """Caso 6: Role PORTAL_ADMIN → is_portal_admin = True."""
        mock_user = MagicMock()
        mock_user.id = 5
        admin_role = _make_user_role("PORTAL_ADMIN")
        mock_app = MagicMock()
        mock_app.codigointerno = "PORTAL"

        request = self._make_request(user=mock_user, application=mock_app)
        request.is_portal_admin = False

        with patch("apps.core.middleware.role_context.cache") as mock_cache:
            mock_cache.get.return_value = [admin_role]
            self.middleware(request)

        self.assertTrue(request.is_portal_admin)
