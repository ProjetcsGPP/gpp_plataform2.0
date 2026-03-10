"""
GPP Plataform 2.0 — DRF Permission Classes customizadas.
"""
import logging

from rest_framework.permissions import BasePermission

security_logger = logging.getLogger("gpp.security")


class HasRolePermission(BasePermission):
    """
    Verifica se o usuário tem ao menos uma role ativa para
    a aplicação identificada no request (via middleware).
    """

    message = "Você não possui um perfil de acesso para esta aplicação."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # PORTAL_ADMIN tem acesso irrestrito
        if getattr(request, "is_portal_admin", False):
            return True

        user_roles = getattr(request, "user_roles", [])
        if not user_roles:
            security_logger.warning(
                "PERMISSION_DENIED user_id=%s path=%s reason=no_role",
                request.user.id,
                request.path,
            )
            return False

        return True


class IsPortalAdmin(BasePermission):
    """Acesso exclusivo para PORTAL_ADMIN."""

    message = "Acesso restrito a administradores da plataforma."

    def has_permission(self, request, view):
        return getattr(request, "is_portal_admin", False)
