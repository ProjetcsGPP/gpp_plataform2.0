"""
Testes para JWTAuthenticationMiddleware.
Casos cobertos:
  1. Rota isenta passa sem validar token
  2. Token ausente → request.user permanece AnonymousUser
  3. Token inválido → warning JWT_INVALID logado
  4. Usuário inativo (status_usuario != 1) → 401 user_inactive
  5. Token válido + usuário ativo → LOGIN_SUCCESS logado, request.user injetado
  6. Token revogado → request.user permanece anônimo
  7. Rota isenta com token presente → token_jti injetado
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.core.middleware.jwt_authentication import JWTAuthenticationMiddleware


class JWTAuthenticationMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))
        self.middleware = JWTAuthenticationMiddleware(self.get_response)

    def _make_request(self, path="/api/alguma-rota/", token=None):
        request = self.factory.get(path)
        request.user = AnonymousUser()
        if token:
            request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return request

    def test_exempt_path_skips_auth(self):
        """Caso 1: Rotas isentas passam sem validação."""
        request = self._make_request(path="/api/auth/token/")
        self.middleware(request)
        self.get_response.assert_called_once()
        self.assertIsInstance(request.user, AnonymousUser)

    def test_no_token_leaves_anonymous(self):
        """Caso 2: Sem token → AnonymousUser mantido."""
        request = self._make_request()
        self.middleware(request)
        self.assertIsInstance(request.user, AnonymousUser)

    def test_invalid_token_logs_warning(self):
        """Caso 3: Token inválido → JWT_INVALID logado."""
        request = self._make_request(token="token.invalido.aqui")
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            self.middleware(request)
        self.assertTrue(any("JWT_INVALID" in msg for msg in log_ctx.output))

    def test_inactive_user_returns_401(self):
        """Caso 4: Usuário com status_usuario != 1 → 401 user_inactive."""
        mock_profile = MagicMock()
        mock_profile.status_usuario = 0  # inativo
        mock_user = MagicMock()
        mock_user.profile = mock_profile
        mock_user.id = 42

        mock_token = MagicMock()
        mock_token.get = lambda key, default=None: {
            "jti": "abc123",
            "user_id": 42,
        }.get(key, default)

        with patch("apps.core.middleware.jwt_authentication.AccessToken", return_value=mock_token):
            with patch(
                "apps.core.middleware.jwt_authentication.User.objects.select_related"
            ) as mock_qs:
                mock_qs.return_value.get.return_value = mock_user
                with patch.object(self.middleware.__class__, "_is_revoked", staticmethod(lambda jti: False)):
                    with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
                        request = self._make_request(token="valid.token.here")
                        response = self.middleware(request)

        self.assertEqual(response.status_code, 401)
        self.assertTrue(any("user_inactive" in msg for msg in log_ctx.output))

    def test_valid_token_logs_login_success(self):
        """Caso 5: Token válido + usuário ativo → LOGIN_SUCCESS."""
        mock_profile = MagicMock()
        mock_profile.status_usuario = 1
        mock_user = MagicMock()
        mock_user.profile = mock_profile
        mock_user.id = 99

        mock_token = MagicMock()
        mock_token.get = lambda key, default=None: {
            "jti": "jti-ok",
            "user_id": 99,
            "is_portal_admin": False,
        }.get(key, default)

        with patch("apps.core.middleware.jwt_authentication.AccessToken", return_value=mock_token):
            with patch(
                "apps.core.middleware.jwt_authentication.User.objects.select_related"
            ) as mock_qs:
                mock_qs.return_value.get.return_value = mock_user
                with patch.object(self.middleware.__class__, "_is_revoked", staticmethod(lambda jti: False)):
                    with self.assertLogs("gpp.security", level="INFO") as log_ctx:
                        request = self._make_request(token="valid.token.here")
                        self.middleware(request)

        self.assertTrue(any("LOGIN_SUCCESS" in msg for msg in log_ctx.output))
        self.assertEqual(request.user, mock_user)
        self.assertEqual(request.token_jti, "jti-ok")

    def test_revoked_token_leaves_anonymous(self):
        """Caso 6: Token revogado → request.user permanece AnonymousUser."""
        mock_token = MagicMock()
        mock_token.get = lambda key, default=None: {
            "jti": "revoked-jti",
            "user_id": 1,
        }.get(key, default)

        with patch("apps.core.middleware.jwt_authentication.AccessToken", return_value=mock_token):
            with patch.object(self.middleware.__class__, "_is_revoked", staticmethod(lambda jti: True)):
                with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
                    request = self._make_request(token="any.token")
                    self.middleware(request)

        self.assertIsInstance(request.user, AnonymousUser)
        self.assertTrue(any("JWT_REVOKED" in msg for msg in log_ctx.output))

    def test_exempt_path_with_token_injects_jti(self):
        """Caso 7: Rota isenta com token válido → token_jti injetado no request."""
        mock_token = MagicMock()
        mock_token.get = lambda key, default=None: {"jti": "jti-exempt"}.get(key, default)

        with patch("apps.core.middleware.jwt_authentication.AccessToken", return_value=mock_token):
            request = self._make_request(path="/api/auth/token/", token="valid.token.here")
            self.middleware(request)

        self.assertEqual(getattr(request, "token_jti", None), "jti-exempt")
