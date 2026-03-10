# accounts/services/authorization_service.py
"""
AuthorizationService CENTRALIZADO - Usa APENAS tabelas NATIVAS do Django.

Fluxo:
1. UserRole → Role → codigoperfil
2. codigoperfil → auth_group (ACOES_PNGI_GESTOR_PNGI)
3. auth_group → auth_group_permissions → auth_permission
4. Cache 5min + PORTAL_ADMIN automático

✅ Compatível: Web Views + DRF APIViews
✅ Performance: Cache Redis/Memcached
✅ Seguro: Nunca depende de request/sessão
"""

import logging

from django.contrib.auth.models import Group
from django.core.cache import cache

from accounts.models import Role, UserRole
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AuthorizationService:
    """
    Serviço central de autorização RBAC nativo do Django.

    Interface:
    >>> auth.can(user_id=1, app_code='ACOES_PNGI', active_role_id=3,
                  action='add', model_name='eixo')
    True  # GESTOR pode criar eixo
    """

    CACHE_TTL = 300  # 5 minutos
    PORTAL_ADMIN_CODE = "PORTAL_ADMIN"

    def __init__(self):
        self.cache_prefix = "authz_native"

    def can(
        self,
        user_id: int,
        app_code: str,
        active_role_id: int,
        action: str,
        model_name: str,
    ) -> bool:
        """
        Verifica permissão usando APENAS tabelas nativas:
        UserRole → Role → auth_group → auth_group_permissions → auth_permission

        Args:
            user_id: ID do tblusuario
            app_code: 'ACOES_PNGI'
            active_role_id: ID da accounts_role (3=GESTOR_PNGI)
            action: 'view'|'add'|'change'|'delete'
            model_name: 'eixo'|'acoes'|'situacaoacao'

        Returns:
            True se autorizado
        """
        try:
            # 1. Validar UserRole existe
            if not self._validate_user_role(user_id, app_code, active_role_id):
                logger.warning(
                    f"❌ UserRole inválida: user={user_id}, app={app_code}, role={active_role_id}"
                )
                return False

            # 2. PORTAL_ADMIN tem tudo
            if self._is_portal_admin(active_role_id):
                logger.debug(f"👑 PORTAL_ADMIN autorizado: role={active_role_id}")
                return True

            # 3. Buscar permissões via auth_group NATIVO
            permissions = self._get_native_permissions(app_code, active_role_id)

            # 4. Verificar codename específico
            codename = f"{action}_{model_name.lower()}"
            authorized = codename in permissions

            logger.info(
                f"🔐 [{authorized}] {user_id}:{app_code}:{active_role_id} "
                f"{codename}"
            )

            return authorized

        except Exception as e:
            logger.error(f"💥 Erro AuthorizationService: {e}", exc_info=True)
            return False

    def _validate_user_role(self, user_id: int, app_code: str, role_id: int) -> bool:
        """Verifica se UserRole existe (cache 5min)."""
        cache_key = f"{self.cache_prefix}:userrole:{user_id}:{app_code}:{role_id}"

        cached = cache.get(cache_key)
        if cached is not None:
            return bool(cached)

        exists = UserRole.objects.filter(
            user_id=user_id, role_id=role_id, aplicacao__codigointerno=app_code
        ).exists()

        cache.set(cache_key, exists, self.CACHE_TTL)
        return exists

    def _is_portal_admin(self, role_id: int) -> bool:
        """Verifica role PORTAL_ADMIN (cache 5min)."""
        cache_key = f"{self.cache_prefix}:portal_admin:{role_id}"

        cached = cache.get(cache_key)
        if cached is not None:
            return bool(cached)

        is_admin = Role.objects.filter(
            id=role_id, codigoperfil=self.PORTAL_ADMIN_CODE
        ).exists()

        cache.set(cache_key, is_admin, self.CACHE_TTL)
        return is_admin

    def _get_native_permissions(self, app_code: str, role_id: int) -> set[str]:
        """
        🔑 CORE: Busca permissões via auth_group NATIVO.

        accounts_role → auth_group → auth_group_permissions → auth_permission
        """
        cache_key = f"{self.cache_prefix}:perms:{app_code}:{role_id}"

        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            # 1. Role → codigoperfil
            role = Role.objects.get(id=role_id)

            # 2. auth_group name = "ACOES_PNGI_GESTOR_PNGI"
            group_name = f"{app_code}_{role.codigoperfil}"
            group = Group.objects.prefetch_related("permissions").get(name=group_name)

            # 3. Extrair codenames
            codenames = set(group.permissions.values_list("codename", flat=True))

            cache.set(cache_key, codenames, self.CACHE_TTL)

            logger.debug(f"📥 {role.codigoperfil}: {len(codenames)} perms")
            return codenames

        except Role.DoesNotExist:
            logger.error(f"❌ Role {role_id} não encontrada")
            return set()
        except Group.DoesNotExist:
            logger.error(f"❌ Grupo '{group_name}' não encontrado")
            return set()

    def get_user_permissions(self, user_id: int, app_code: str) -> dict:
        """
        Retorna todas as permissões do usuário por modelo.

        Returns:
        {
            'eixo': {'view', 'add', 'change'},
            'acoes': {'view', 'add', 'change', 'delete'},
            ...
        }
        """
        # Buscar todas as roles do usuário na app
        user_roles = UserRole.objects.filter(
            user_id=user_id, aplicacao__codigointerno=app_code
        ).values_list("role_id", flat=True)

        all_perms = set()
        for role_id in user_roles:
            perms = self._get_native_permissions(app_code, role_id)
            all_perms.update(perms)

        # Agrupar por modelo
        grouped = {}
        for perm in all_perms:
            if "_" in perm:
                action, model = perm.rsplit("_", 1)
                if model not in grouped:
                    grouped[model] = set()
                grouped[model].add(action)

        return grouped

    def invalidate_cache(self, user_id: int | None = None, role_id: int | None = None):
        """Limpa cache de permissões."""
        if role_id:
            # Opção 1: Limpar todos os caches da app (mais simples)
            cache.clear()
            logger.info(f"🧹 Cache limpo completamente")
            
            # Opção 2: Keys específicas (mais preciso, mas complexo)
            # keys = cache.iter_keys(f"{self.cache_prefix}:perms:*:{role_id}")
            # cache.delete_many(keys)

# 🛠️ SINGLETON (Reutilizável)
_authorization_service = None


def get_authorization_service() -> AuthorizationService:
    """Fábrica singleton."""
    global _authorization_service
    if _authorization_service is None:
        _authorization_service = AuthorizationService()
    return _authorization_service


# ============================================================================
# 🆕 PERMISSÕES DRF (Compatibilidade com api_views.py)
# ============================================================================

import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

class HasModelPermission(BasePermission):
    """
    DRF Permission: Usa AuthorizationService nativo - VERSÃO TYPE-SAFE.
    """
    
    def has_permission(self, request, view) -> bool:
        # Superusuários sempre passam
        if request.user and request.user.is_superuser:
            return True

        # ✅ Extrair dados do token_payload com validação rigorosa
        token_payload = getattr(request, "token_payload", {})
        user_id = getattr(request.user, "id", 0)
        app_code: str = token_payload.get("app_code", "ACOES_PNGI")
        active_role_id_raw = token_payload.get("active_role_id")
        
        # ✅ Validação explícita ANTES de chamar can()
        if not user_id or active_role_id_raw is None:
            logger.warning("Token inválido para HasModelPermission - faltam user_id ou active_role_id")
            return False
        
        # ✅ Conversão type-safe com fallback
        try:
            active_role_id: int = int(active_role_id_raw)
        except (ValueError, TypeError):
            logger.warning(f"active_role_id inválido (não é inteiro): {active_role_id_raw}")
            return False

        # Resto do código igual...
        model_name = getattr(view, "permission_model", None)
        if not model_name:
            logger.error(f"View {view.__class__.__name__} sem permission_model")
            return False

        action_map = {
            "GET": "view", "HEAD": "view", "OPTIONS": "view",
            "POST": "add", "PUT": "change", "PATCH": "change", "DELETE": "delete",
        }
        action = action_map.get(request.method, "view")

        auth_service = get_authorization_service()
        
        # ✅ Pylance agora aceita - active_role_id é GUARANTIDO int
        result = auth_service.can(
            user_id=user_id,
            app_code=app_code,
            active_role_id=active_role_id,  # ✅ int garantido
            action=action,
            model_name=model_name,
        )
        
        return result

class ReadOnlyOrHasPermission(BasePermission):
    """
    Leitura para todos PNGI, escrita via AuthorizationService.

    Uso:
    permission_classes = [ReadOnlyOrHasPermission]
    permission_model = 'acoes'
    """

    def has_permission(self, request, view):
        # Leitura: qualquer PNGI role
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return True  # Ou IsAnyPNGIRole() se existir

        # Escrita: AuthorizationService
        return HasModelPermission().has_permission(request, view)


def require_app_permission(permission_codename, app_code="ACOES_PNGI"):
    """
    Decorator compatibilidade - mesma interface das views web.
    """
    from functools import wraps

    from django.core.exceptions import PermissionDenied

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Autenticação necessária.")

            perms = get_authorization_service().get_user_permissions(
                request.user.id, app_code
            )

            if permission_codename not in perms:
                raise PermissionDenied(f"Sem permissão '{permission_codename}'.")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

# ============================================================================
# API DECORATORS (Compatibilidade com views existentes)
# ============================================================================

def require_api_permission(permission_codename, app_code="ACOES_PNGI"):
    """
    Decorator para API views - compatibilidade com código existente.
    """
    from functools import wraps
    from rest_framework.decorators import api_view, permission_classes
    from rest_framework.permissions import BasePermission
    from django.http import JsonResponse
    
    class TempPermission(BasePermission):
        def has_permission(self, request, view):
            auth_service = get_authorization_service()
            user_id = getattr(request.user, 'id', 0)
            
            # Simular token_payload para compatibilidade
            token_payload = getattr(request, 'token_payload', {})
            active_role_id = token_payload.get('active_role_id')
            
            if not active_role_id:
                return False
            
            perms = auth_service.get_user_permissions(user_id, app_code)
            return permission_codename in perms
    
    @wraps
    def decorator(view_func):
        @api_view(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
        @permission_classes([TempPermission])
        def wrapper(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)
        return wrapper
    
    return decorator
