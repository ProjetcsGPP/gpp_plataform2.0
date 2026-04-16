import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AccountsSession

from .utils import get_client_ip

security_logger = logging.getLogger("gpp.frontend_log")


def _resolve_app_context(request) -> str:
    """
    Tenta obter o app_context da sessão ativa do usuário.
    O AppContextMiddleware não seta app_context para o path /api/core/,
    por isso resolvemos diretamente via AccountsSession.
    """
    app_context = getattr(request, "app_context", None)
    if app_context:
        return app_context

    gpp_cookies = {
        name: value
        for name, value in request.COOKIES.items()
        if name.startswith("gpp_session_")
    }
    if not gpp_cookies:
        return "UNKNOWN"

    session = (
        AccountsSession.objects.filter(
            session_key__in=list(gpp_cookies.values()),
            session_cookie_name__in=list(gpp_cookies.keys()),
            revoked=False,
            app_context__isnull=False,
            user=request.user,
        )
        .only("app_context")
        .order_by("-created_at")
        .first()
    )
    return session.app_context if session else "UNKNOWN"


class FrontEndLogging(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Log de erros do frontend",
        description=(
            "Recebe eventos de erro/log gerados pelo frontend e os registra "
            "no logger de segurança do servidor. Requer autenticação."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "example": "error",
                        "enum": ["debug", "info", "warn", "error"],
                    },
                    "message": {
                        "type": "string",
                        "example": "TypeError: Cannot read properties of null",
                    },
                    "context": {
                        "type": "object",
                        "example": {"page": "/dashboard", "user_agent": "Mozilla/5.0"},
                    },
                },
                "required": ["level", "message"],
            }
        },
        responses={
            200: OpenApiResponse(description='{"status": "ok"}'),
            401: OpenApiResponse(description="Não autenticado"),
        },
        tags=["5 - Utilitários"],
    )
    def post(self, request):
        log_data = request.data
        remote_address = get_client_ip(request)
        user = request.user
        app_context = _resolve_app_context(request)

        security_logger.info(
            "FRONTEND_LOG user=%s(%s) app=%s ip=%s | %s",
            user.username,
            user.id,
            app_context,
            remote_address,
            log_data,
        )

        return Response({"status": "ok"})
