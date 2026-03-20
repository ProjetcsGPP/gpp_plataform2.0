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

Mudança Fase-0:
    O JWTAuthenticationMiddleware foi removido do stack.
    O middleware que agora precisa de patch é o AppContextMiddleware
    (apps.accounts.middleware.AppContextMiddleware), responsável por
    popular request.app_context. O ApplicationContextMiddleware
    (apps.core.middleware.application_context) também é patchado para
    injetar request.application e request.is_portal_admin.
    RoleContextMiddleware e AuthorizationMiddleware mantêm seus patches.
"""
from unittest.mock import patch

from apps.accounts.models import UserRole


def patch_security(user, is_portal_admin=False):
    """
    Retorna uma lista de 3 context managers que fazem patch nos middlewares
    customizados do GPP (AppContext, RoleContext, Authorization), injetando
    diretamente no request:
      - request.user            (já setado pelo Django SessionMiddleware/
                                 AuthenticationMiddleware + force_authenticate)
      - request.app_context     (populado pelo AppContextMiddleware)
      - request.application     (populado pelo ApplicationContextMiddleware)
      - request.is_portal_admin (populado pelo ApplicationContextMiddleware)
      - request.user_roles      (populado pelo RoleContextMiddleware)

    Isso permite testar views autenticadas sem depender do stack completo
    de middlewares, usando apenas sessão Django (cookie gpp_session).
    NÃO usa Bearer token nem JWT.

    Args:
        user: instância de User autenticado para o teste
        is_portal_admin: bool — define se o usuário tem acesso irrestrito (default False)

    Returns:
        list[ContextManager] — use com: with patches[0], patches[1], patches[2]
    """
    user_roles = list(UserRole.objects.filter(user=user))

    def patched_app_context_call(self_mw, request):
        """
        Substitui AppContextMiddleware.__call__.
        Injeta request.app_context como None (sem contexto de app ativo)
        e preserva request.user já definido pelo force_authenticate/force_login.
        """
        request.app_context = None
        request.is_portal_admin = is_portal_admin
        return self_mw.get_response(request)

    def patched_role_call(self_mw, request):
        """
        Substitui RoleContextMiddleware.__call__.
        Injeta request.user_roles e confirma request.is_portal_admin.
        """
        request.user_roles = user_roles
        request.is_portal_admin = is_portal_admin
        return self_mw.get_response(request)

    def patched_authz_call(self_mw, request):
        """
        Substitui AuthorizationMiddleware.__call__.
        Deixa passar sem verificar — a autorização é responsabilidade
        das permissions DRF no nível da view.
        """
        return self_mw.get_response(request)

    return [
        patch(
            "apps.accounts.middleware.AppContextMiddleware.__call__",
            new=patched_app_context_call,
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
