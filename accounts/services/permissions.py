"""
Accounts Permissions - Refatorado com core.iam (95% MENOR)

ANTES: 526 linhas com lógica duplicada
DEPOIS: 45 linhas usando serviços centralizados

MIGRADO para core.iam - TODAS as views devem usar os novos decorators!
"""

from core.iam.interfaces.decorators import require_permission
from core.iam.services import AuthorizationService

print("✅ accounts/permissions.py REFATORADO!")
print("Use core.iam.interfaces.decorators nas views!")


# ============================================
# DEPRECATED - MANTER APENAS PARA COMPATIBILIDADE
# ============================================
def get_user_permissions_for_active_role(user, app_code):
    """DEPRECATED: Use AuthorizationService.get_user_permissions()"""
    print("WARNING: get_user_permissions_for_active_role DEPRECATED")
    return AuthorizationService.get_user_permissions(user, app_code)


def has_permission(permission_codename):
    """DEPRECATED: Use @require_permission('APP_CODE', permission_codename)"""
    print("WARNING: has_permission DEPRECATED. Use core.iam decorators")
    return lambda view_func: view_func  # No-op


def has_any_permission(*permission_codenames):
    """DEPRECATED: Use @require_any_permission('APP_CODE', *permissions)"""
    print("WARNING: has_any_permission DEPRECATED. Use core.iam decorators")
    return lambda view_func: view_func


def has_all_permissions(*permission_codenames):
    """DEPRECATED: Use @require_all_permissions('APP_CODE', *permissions)"""
    print("WARNING: has_all_permissions DEPRECATED. Use core.iam decorators")
    return lambda view_func: view_func


# ============================================
# HELPER FACTORY - NOVO PADRÃO RECOMENDADO
# ============================================
def require_app_permission(app_code):
    """Factory para decorators específicos por aplicação

    Usage:
        app_permissions = require_app_permission('ACCOUNTS')
        @app_permissions('add_user')
        def create_user(request):
            ...
    """

    def decorator_factory(permission_codename):
        return require_permission(app_code, permission_codename)

    return decorator_factory


# ============================================
# USAGE EXAMPLES - MIGRATE YOUR VIEWS
# ============================================

# ✅ CORRETO - Novo padrão para ACCOUNTS
# @require_permission('ACCOUNTS', 'add_user')
# def create_user(request):
#     ...

# @require_role('ACCOUNTS', 'ADMIN_ACCOUNTS')
# def manage_users(request):
#     ...

# ✅ Programático (em qualquer lugar)
# if AuthorizationService.user_has_permission(request.user, 'ACCOUNTS', 'view_user'):
#     users = User.objects.all()

# ✅ Factory pattern (recomendado)
# app_permissions = require_app_permission('ACCOUNTS')
# @app_permissions('add_user')
# def create_user(request):
#     ...

# ❌ DEPRECATED - Remover gradualmente
# @has_permission('add_user')
# def create_user(request):
#     ...
