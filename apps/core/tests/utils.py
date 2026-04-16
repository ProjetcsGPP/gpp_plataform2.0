"""GPP Plataform 2.0 — Test Utilities (pós-Fase-0)

Patch correto dos middlewares customizados para testes de view.
Não usa JWT, Bearer token nem /api/auth/token/.

Uso:
    from apps.core.tests.utils import patch_security

    def test_algo(self):
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

Como funciona:
    Em vez de patchar __call__ (que depende de instância já criada no startup),
    patchamos o __call__ via patch.object diretamente no objeto da CLASSE,
    usando `autospec=False` e `new` apontando para uma closure que já captura
    user_roles e is_portal_admin. Isso garante que qualquer instância do
    middleware criada pelo Django usa a versão patchada.
"""

from unittest.mock import patch

from apps.accounts.models import UserRole


def patch_security(user, is_portal_admin=False):
    """Retorna lista de 3 patches (use como context managers).

    Substitui os 3 middlewares customizados do GPP por versões que:
      - Injetam request.app_context, request.is_portal_admin, request.user_roles
      - Não acessam request.session nem banco de sessões
      - Deixam request.user intacto (setado pelo force_authenticate/force_login)
      - Chamam get_response(request) normalmente ao final

    Args:
        user: instância autenticada de User
        is_portal_admin: True para simular usuário com privilégio total
    """
    user_roles = list(UserRole.objects.filter(user=user))

    # ── AppContextMiddleware ──────────────────────────────────────────────────
    # Injeta app_context e is_portal_admin sem tocar em request.session
    def _app_ctx_call(self, request):
        request.app_context = None
        request.is_portal_admin = is_portal_admin
        return self.get_response(request)

    # ── RoleContextMiddleware ─────────────────────────────────────────────────
    def _role_call(self, request):
        request.user_roles = user_roles
        request.is_portal_admin = is_portal_admin
        return self.get_response(request)

    # ── AuthorizationMiddleware ───────────────────────────────────────────────
    # Deixa passar — autorização fica a cargo das DRF permissions na view
    def _authz_call(self, request):
        return self.get_response(request)

    return [
        patch(
            "apps.accounts.middleware.AppContextMiddleware.__call__",
            new=_app_ctx_call,
        ),
        patch(
            "apps.core.middleware.role_context.RoleContextMiddleware.__call__",
            new=_role_call,
        ),
        patch(
            "apps.core.middleware.authorization.AuthorizationMiddleware.__call__",
            new=_authz_call,
        ),
    ]
