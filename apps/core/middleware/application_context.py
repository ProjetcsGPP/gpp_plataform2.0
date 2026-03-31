"""
ApplicationContextMiddleware

Responsabilidade:
  Identifica qual Aplicacao da plataforma está sendo acessada
  e armazena em request.application.

Ordem de resolução:
  1. Header X-Application-Code
  2. Prefixo da URL  (/api/acoes-pngi/ → ACOES_PNGI)
  3. Domínio da request (pngi.api.gov.br → ACOES_PNGI)
  4. Fallback: "portal"

NOTA: /api/accounts/ NÃO é bypassado aqui — o AppContextMiddleware
      cuida de autenticar esses endpoints via _authenticate_any_cookie.
"""
import logging

from django.conf import settings

from apps.accounts.services.application_registry import ApplicationRegistry

security_logger = logging.getLogger("gpp.security")

# Mapeamento de prefixo de URL → codigointerno da Aplicacao
URL_PREFIX_MAP = {
    "acoes-pngi":    "ACOES_PNGI",
    "carga-org-lot": "CARGA_ORG_LOT",
    "portal":        "PORTAL",
    "accounts":      "accounts",
}


class ApplicationContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Bypass APENAS para requests de logout explícito
        # (is_logout_request é setado pelo LogoutMiddleware antes desta camada)
        if getattr(request, "is_logout_request", False):
            security_logger.debug(
                "LOGOUT_REQUEST — skipping application resolution path=%s",
                request.path,
            )
            request.application = None
            return self.get_response(request)

        request.application = self._resolve_application(request)
        if request.application is None:
            security_logger.warning(
                "APP_CONTEXT_NONE path=%s — application could not be resolved, leaving as None",
                request.path,
            )
        return self.get_response(request)

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
        security_logger.debug(
            "APP_CONTEXT_FALLBACK path=%s resolved=portal",
            request.path,
        )
        return registry.get("portal")
