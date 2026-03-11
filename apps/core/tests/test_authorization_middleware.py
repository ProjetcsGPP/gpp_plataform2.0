"""
Testes para AuthorizationMiddleware.
Casos cobertos:
  1. Rota isenta → passa sem verificação
  2. PORTAL_ADMIN → acesso irrestrito
  3. Usuário não autenticado → 401 not_authenticated
  4. Usuário sem roles → 403 permission_denied (no_role)
  5. AUTHORIZATION_REQUIRED_ROLES: usuário com role correta → passa
  6. AUTHORIZATION_REQUIRED_ROLES: usuário sem role requerida → 403
  7. Usuário autenticado com roles → passa normalmente
"""
from unittest.mock import MagicMock

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings

from apps.core.middleware.authorization import AuthorizationMiddleware


def _make_user_role(codigo):
    ur = MagicMock()
    ur.role.codigoperfil = codigo
    return ur


class AuthorizationMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))
        self.middleware = AuthorizationMiddleware(self.get_response)

    def _make_request(self, path="/api/alguma/", user=None, user_roles=None, is_portal_admin=False):
        request = self.factory.get(path)
        request.user = user or AnonymousUser()
        request.user_roles = user_roles if user_roles is not None else []
        request.is_portal_admin = is_portal_admin
        request.application = MagicMock()
        request.application.codigointerno = "ACOES_PNGI"
        return request

    def test_exempt_path_always_passes(self):
        """Caso 1: Rotas isentas não são bloqueadas."""
        request = self._make_request(path="/api/auth/token/")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_portal_admin_always_passes(self):
        """Caso 2: PORTAL_ADMIN passa mesmo sem roles na app."""
        mock_user = MagicMock()
        mock_user.id = 1
        request = self._make_request(user=mock_user, user_roles=[], is_portal_admin=True)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_anonymous_user_returns_401(self):
        """Caso 3: AnonymousUser → 401."""
        request = self._make_request()
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            response = self.middleware(request)
        self.assertEqual(response.status_code, 401)
        self.assertTrue(any("401_UNAUTHORIZED" in msg for msg in log_ctx.output))

    def test_no_roles_returns_403(self):
        """Caso 4: Usuário autenticado sem roles → 403."""
        mock_user = MagicMock()
        mock_user.id = 2
        request = self._make_request(user=mock_user, user_roles=[])
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            response = self.middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(any("403_FORBIDDEN" in msg for msg in log_ctx.output))

    @override_settings(AUTHORIZATION_REQUIRED_ROLES={"/api/acoes-pngi/": ["GESTOR_PNGI", "COORDENADOR_PNGI"]})
    def test_required_roles_passes_when_user_has_role(self):
        """Caso 5: Usuário com role requerida → passa."""
        mock_user = MagicMock()
        mock_user.id = 3
        roles = [_make_user_role("GESTOR_PNGI")]
        request = self._make_request(path="/api/acoes-pngi/listar/", user=mock_user, user_roles=roles)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(AUTHORIZATION_REQUIRED_ROLES={"/api/acoes-pngi/": ["GESTOR_PNGI", "COORDENADOR_PNGI"]})
    def test_required_roles_blocks_when_user_lacks_role(self):
        """Caso 6: Usuário sem nenhuma role requerida → 403."""
        mock_user = MagicMock()
        mock_user.id = 4
        roles = [_make_user_role("CONSULTOR_PNGI")]  # não está na lista requerida
        request = self._make_request(path="/api/acoes-pngi/listar/", user=mock_user, user_roles=roles)
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            response = self.middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(any("403_FORBIDDEN_ROLE" in msg for msg in log_ctx.output))

    def test_authenticated_user_with_roles_passes(self):
        """Caso 7: Usuário autenticado com roles → passa normalmente."""
        mock_user = MagicMock()
        mock_user.id = 5
        roles = [_make_user_role("OPERADOR_ACAO")]
        request = self._make_request(user=mock_user, user_roles=roles)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
