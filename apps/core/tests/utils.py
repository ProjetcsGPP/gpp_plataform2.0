"""
GPP Plataform 2.0 — Test Utilities

Utilitários compartilhados para testes de views que precisam bypassar
os middlewares de segurança customizados do GPP.

Uso:
    from apps.core.tests.utils import patch_security

    def test_meu_endpoint(self):
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

Para usuário PORTAL_ADMIN:
    patches = patch_security(self.user, is_portal_admin=True)
"""
from unittest.mock import patch

from apps.accounts.models import UserRole


def patch_security(user, is_portal_admin=False):
    """
    Retorna uma lista de 3 context managers que fazem patch nos middlewares
    customizados do GPP (JWT, RoleContext, Authorization), injetando
    diretamente no request:
      - request.user
      - request.token_jti
      - request.user_roles
      - request.is_portal_admin

    Isso permite testar views autenticadas sem depender de token JWT real
    nem do stack completo de middlewares.

    Args:
        user: instância de User autenticado para o teste
        is_portal_admin: bool — define se o usuário tem acesso irrestrito (default False)

    Returns:
        list[ContextManager] — use com: with patches[0], patches[1], patches[2]
    """
    user_roles = list(UserRole.objects.filter(user=user))

    def patched_jwt_call(self_mw, request):
        request.user = user
        request.token_jti = "test-jti"
        request.is_portal_admin = is_portal_admin
        return self_mw.get_response(request)

    def patched_role_call(self_mw, request):
        request.user_roles = user_roles
        request.is_portal_admin = is_portal_admin
        return self_mw.get_response(request)

    def patched_authz_call(self_mw, request):
        return self_mw.get_response(request)

    return [
        patch(
            "apps.core.middleware.jwt_authentication.JWTAuthenticationMiddleware.__call__",
            new=patched_jwt_call,
        ),
        patch(
            "apps.core.middleware.role_context.RoleContextMiddleware.__call__",
            new=patched_role_call,
        ),
        patch(
            "apps.core.middleware.authorization.AuthorizationMiddleware.__call__",
            new=patched_authz_call,
        ),
    ]
