"""
GPP Plataform 2.0 — DRF Permission Classes

Integração entre DRF e o AuthorizationService.

Classes disponíveis:
  - HasRolePermission   : verifica se o user tem ao menos 1 UserRole na app atual
  - CanPermission       : delega ao AuthorizationService.can(required_permission)
  - IsPortalAdmin       : verifica se o user tem role PORTAL_ADMIN
  - ObjectPermission    : has_object_permission para proteção anti-IDOR

Uso nas views:
    class MinhaView(APIView):
        permission_classes = [IsAuthenticated, CanPermission]
        required_permission = "view_acao"
        # Opcional — contexto ABAC passado como atributo da view:
        permission_context = {"eixo": "A"}
"""
import logging
from functools import wraps

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from apps.accounts.services.authorization_service import AuthorizationService
from apps.accounts.services.application_registry import ApplicationRegistry

security_logger = logging.getLogger("gpp.security")

_registry = ApplicationRegistry()


def _resolve_application(request: Request):
    """
    Tenta identificar a Aplicacao a partir do header X-App-Code ou
    do atributo `application` já injetado pelo ApplicationMiddleware.
    Retorna instância de Aplicacao ou None.
    """
    # 1. Já resolvido pelo middleware
    app = getattr(request, "application", None)
    if app is not None:
        return app
    # 2. Tenta pelo header customizado
    app_code = request.headers.get("X-App-Code")
    if app_code:
        return _registry.get(app_code)
    return None


# ─── HasRolePermission ──────────────────────────────────────────────────────

class HasRolePermission(BasePermission):
    """
    Permite acesso somente se o usuário possui ao menos 1 UserRole
    na aplicação atual.

    Não exige permission específica — apenas a existência de role.
    Use como guarda de porta antes de permissões mais granulares.
    """
    message = "Você não possui um perfil de acesso para esta aplicação."

    def has_permission(self, request: Request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        application = _resolve_application(request)
        service = AuthorizationService(request.user, application)
        result = service._has_valid_role()
        if not result:
            security_logger.warning(
                "DRF_DENY HasRolePermission user_id=%s path=%s",
                request.user.id, request.path,
            )
        return result


# ─── CanPermission ──────────────────────────────────────────────────────────

class CanPermission(BasePermission):
    """
    Delega ao AuthorizationService.can() para verificar uma permissão
    específica declarada na view via `required_permission`.

    Opcionalmente lê `permission_context` (dict) da view para ABAC.

    Exemplo:
        class AcaoListView(ListAPIView):
            permission_classes = [IsAuthenticated, CanPermission]
            required_permission = "view_acao"
    """
    message = "Você não tem permissão para executar esta ação."

    def has_permission(self, request: Request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        permission_codename = getattr(view, "required_permission", None)
        if not permission_codename:
            security_logger.error(
                "DRF_CONFIG_ERROR CanPermission sem required_permission view=%s",
                view.__class__.__name__,
            )
            return False

        application = _resolve_application(request)
        context = getattr(view, "permission_context", None)
        service = AuthorizationService(request.user, application)
        result = service.can(permission_codename, context=context)
        if not result:
            security_logger.warning(
                "DRF_DENY CanPermission user_id=%s perm=%s path=%s",
                request.user.id, permission_codename, request.path,
            )
        return result


# ─── IsPortalAdmin ──────────────────────────────────────────────────────────

class IsPortalAdmin(BasePermission):
    """
    Permite acesso somente a usuários com role PORTAL_ADMIN.
    Adequado para views administrativas da plataforma.
    """
    message = "Acesso restrito a administradores da plataforma."

    def has_permission(self, request: Request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        service = AuthorizationService(request.user)
        result = service._is_portal_admin()
        if not result:
            security_logger.warning(
                "DRF_DENY IsPortalAdmin user_id=%s path=%s",
                request.user.id, request.path,
            )
        return result


# ─── ObjectPermission (anti-IDOR) ───────────────────────────────────────────

class ObjectPermission(BasePermission):
    """
    Proteção anti-IDOR via has_object_permission.

    Exige que a view defina `object_owner_field` (default: 'user'),
    indicando o campo do objeto que deve corresponder ao request.user.

    Para PORTAL_ADMIN o acesso é sempre permitido.

    Exemplo:
        class AcaoDetailView(RetrieveUpdateAPIView):
            permission_classes = [IsAuthenticated, CanPermission, ObjectPermission]
            required_permission = "change_acao"
            object_owner_field = "responsavel"   # campo do modelo
    """
    message = "Acesso negado: você não é o proprietário deste recurso."

    def has_permission(self, request: Request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        # PORTAL_ADMIN sempre passa
        service = AuthorizationService(request.user)
        if service._is_portal_admin():
            return True

        owner_field = getattr(view, "object_owner_field", "user")
        owner = getattr(obj, owner_field, None)

        # Suporta FK (User instance) ou apenas user_id
        if hasattr(owner, "pk"):
            result = owner.pk == request.user.pk
        else:
            result = owner == request.user.pk

        if not result:
            security_logger.warning(
                "DRF_DENY ObjectPermission user_id=%s obj=%s.%s path=%s",
                request.user.id,
                obj.__class__.__name__,
                getattr(obj, "pk", "?"),
                request.path,
            )
        return result


# ─── Decorator para views funcionais ────────────────────────────────────────

def require_permission(permission_codename: str, context: dict = None):
    """
    Decorator para views funcionais (function-based views) do Django/DRF.

    Lê a aplicação do request.application (injetado pelo ApplicationMiddleware)
    ou do header X-App-Code.

    Uso:
        @api_view(["GET"])
        @require_permission("view_acao")
        def list_acoes(request):
            ...

        # Com contexto ABAC:
        @api_view(["GET"])
        @require_permission("view_acao", context={"eixo": "A"})
        def list_acoes_eixo_a(request):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                raise PermissionDenied("Autenticação necessária.")

            application = _resolve_application(request)
            service = AuthorizationService(request.user, application)

            if not service.can(permission_codename, context=context):
                security_logger.warning(
                    "DRF_DENY require_permission user_id=%s perm=%s path=%s",
                    request.user.id, permission_codename, request.path,
                )
                raise PermissionDenied(
                    f"Permissão '{permission_codename}' necessária para este recurso."
                )
            return func(request, *args, **kwargs)
        return wrapper
    return decorator
