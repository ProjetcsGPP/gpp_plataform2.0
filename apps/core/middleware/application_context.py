"""
ApplicationContextMiddleware

Responsabilidade:
  Identifica qual Aplicacao da plataforma está sendo acessada
  e armazena em request.application.

Ordem de resolução:
  1. Header X-Application-Code
  2. Prefixo da URL  (/api/acoes-pngi/ → acoes_pngi)
  3. Domínio da request (pngi.api.gov.br → acoes_pngi)
  4. Fallback: "portal"
"""
import logging

from django.conf import settings

from apps.accounts.services.application_registry import ApplicationRegistry

security_logger = logging.getLogger("gpp.security")

# Mapeamento de prefixo de URL → codigointerno da Aplicacao
URL_PREFIX_MAP = {
    "acoes-pngi": "acoes_pngi",
    "carga-org-lot": "carga_org_lot",
    "portal": "portal",
    "accounts": "accounts",
}


class ApplicationContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.application = self._resolve_application(request)
        response = self.get_response(request)
        return response

    def _resolve_application(self, request):
        """
        Retorna o objeto Aplicacao correspondente à request,
        ou None se não identificado.
        """
        registry = ApplicationRegistry()

        # 1. Header explícito (maior prioridade)
        app_code = request.META.get("HTTP_X_APPLICATION_CODE", "").strip()
        if app_code:
            return registry.get(app_code)

        # 2. Prefixo da URL  /api/{prefix}/...
        path_parts = request.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "api":
            prefix = path_parts[1]
            app_code = URL_PREFIX_MAP.get(prefix)
            if app_code:
                app = registry.get(app_code)
                if app:
                    return app

        # 3. Domínio (header Host ou SERVER_NAME)
        domain_map = getattr(settings, "APPLICATION_DOMAIN_MAP", {})
        host = request.META.get("HTTP_HOST", "").split(":")[0].lower()
        app_code = domain_map.get(host)
        if app_code:
            return registry.get(app_code)

        # 4. Fallback: portal
        return registry.get("portal")
