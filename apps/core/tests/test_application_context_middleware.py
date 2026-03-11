"""
Testes para ApplicationContextMiddleware.
Casos cobertos:
  1. Resolução por header X-Application-Code
  2. Resolução por prefixo de URL /api/acoes-pngi/
  3. Resolução por domínio (APPLICATION_DOMAIN_MAP)
  4. Fallback para portal quando nenhum método resolve
  5. request.application nunca é None quando portal existe
  6. Log APP_CONTEXT_FALLBACK emitido no fallback
"""
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase, override_settings

from apps.core.middleware.application_context import ApplicationContextMiddleware


class FakeApp:
    def __init__(self, code):
        self.codigointerno = code

    def __repr__(self):
        return f"<FakeApp {self.codigointerno}>"


class FakeRegistry:
    def __init__(self, apps):
        self._apps = apps

    def get(self, code):
        return self._apps.get(code)


class ApplicationContextMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.portal_app = FakeApp("portal")
        self.acoes_app = FakeApp("ACOES_PNGI")
        self.registry = FakeRegistry({
            "portal": self.portal_app,
            "ACOES_PNGI": self.acoes_app,
            "PORTAL": self.portal_app,
        })
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))
        self.middleware = ApplicationContextMiddleware(self.get_response)

    def _patch_registry(self):
        return patch(
            "apps.core.middleware.application_context.ApplicationRegistry",
            return_value=self.registry,
        )

    def test_resolve_by_header(self):
        """Caso 1: Header X-Application-Code define a aplicação."""
        request = self.factory.get("/api/qualquer/")
        request.META["HTTP_X_APPLICATION_CODE"] = "ACOES_PNGI"
        with self._patch_registry():
            self.middleware(request)
        self.assertIsNotNone(request.application)
        self.assertEqual(request.application.codigointerno, "ACOES_PNGI")

    def test_resolve_by_url_prefix(self):
        """Caso 2: Prefixo da URL /api/acoes-pngi/ → ACOES_PNGI."""
        request = self.factory.get("/api/acoes-pngi/listar/")
        with self._patch_registry():
            self.middleware(request)
        self.assertIsNotNone(request.application)
        self.assertEqual(request.application.codigointerno, "ACOES_PNGI")

    @override_settings(APPLICATION_DOMAIN_MAP={"pngi.api.gov.br": "ACOES_PNGI"})
    def test_resolve_by_domain(self):
        """Caso 3: Domínio mapeado em APPLICATION_DOMAIN_MAP."""
        request = self.factory.get("/api/anything/")
        request.META["HTTP_HOST"] = "pngi.api.gov.br"
        with self._patch_registry():
            self.middleware(request)
        self.assertIsNotNone(request.application)
        self.assertEqual(request.application.codigointerno, "ACOES_PNGI")

    def test_fallback_to_portal(self):
        """Caso 4: Sem header, URL ou domínio → fallback portal."""
        request = self.factory.get("/pagina-desconhecida/")
        with self._patch_registry():
            self.middleware(request)
        self.assertIsNotNone(request.application)
        self.assertEqual(request.application.codigointerno, "portal")

    def test_application_never_none_when_portal_exists(self):
        """Caso 5: Sem nenhuma pista, request.application nunca é None se portal existe."""
        request = self.factory.get("/rota-sem-contexto/")
        with self._patch_registry():
            self.middleware(request)
        self.assertIsNotNone(request.application)

    def test_fallback_log_emitted(self):
        """Caso 6: Log APP_CONTEXT_FALLBACK é emitido quando fallback é acionado."""
        request = self.factory.get("/rota-desconhecida/")
        with self._patch_registry():
            with self.assertLogs("gpp.security", level="DEBUG") as log_ctx:
                self.middleware(request)
        self.assertTrue(
            any("APP_CONTEXT_FALLBACK" in msg for msg in log_ctx.output),
            "Expected APP_CONTEXT_FALLBACK log in gpp.security",
        )
