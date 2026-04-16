import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils import get_client_ip

security_logger = logging.getLogger("gpp.frontend_log")


class FrontEndLogging(APIView):

    permission_classes = [
        IsAuthenticated
    ]  # AllowAny seria inseguro — qualquer um logaria

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

        security_logger.info(
            "FRONTEND_LOG_ERR: %s - %s",
            remote_address,
            log_data,
        )

        return Response({"status": "ok"})
