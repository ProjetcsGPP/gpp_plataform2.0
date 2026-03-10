"""
GPP Plataform 2.0 — Exception Handler customizado para DRF.
Padroniza todas as respostas de erro da API.
"""
import logging

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, AuthenticationFailed, NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import exception_handler

security_logger = logging.getLogger("gpp.security")


def gpp_exception_handler(exc, context):
    """Handler centralizado. Padroniza erros e loga eventos de segurança."""
    response = exception_handler(exc, context)

    request = context.get("request")
    user_id = getattr(getattr(request, "user", None), "id", "anonymous")
    path = getattr(request, "path", "unknown")

    if isinstance(exc, (PermissionDenied,)):
        security_logger.warning(
            "403_FORBIDDEN user_id=%s path=%s detail=%s",
            user_id, path, str(exc.detail),
        )

    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        security_logger.warning(
            "401_UNAUTHORIZED user_id=%s path=%s",
            user_id, path,
        )

    if response is not None:
        response.data = {
            "success": False,
            "status_code": response.status_code,
            "errors": response.data,
        }

    return response
