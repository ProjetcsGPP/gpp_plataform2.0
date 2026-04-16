"""
GPP Plataform 2.0 — AuthZ Version Endpoint

Endpoint leve para polling de versão de autorização pelo frontend.

IMPORTANTE:
  - Não recalcula permissões.
  - Não executa joins em auth_user_user_permissions.
  - Consulta direta em accounts_userauthzstate — O(1).
  - Usado APENAS para invalidação de cache no frontend.
"""
import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authz_versioning import UserAuthzState

logger = logging.getLogger("gpp.security")


class AuthzVersionView(APIView):
    """
    GET /api/authz/version/

    Retorna a versão de autorização atual do usuário autenticado.

    O frontend usa este endpoint para polling leve. Se o valor de
    ``authz_version`` mudar desde o último check, o frontend deve:
      - refazer GET /me/permissions/
      - refazer GET navigation JSON
      - invalidar caches locais (React Query / Zustand)

    Garantias de performance:
      - O(1): consulta direta por user_id — sem joins, sem RBAC.
      - Sem chamadas a sync_user_permissions.
      - Sem leitura de auth_user_user_permissions.

    Segurança:
      - Requer autenticação.
      - Retorna SOMENTE a versão do usuário autenticado.
      - Não expõe informações de outros usuários.
      - NÃO pode ser usado para decisões de autorização.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Versão de autorização do usuário autenticado",
        description=(
            "Retorna o número de versão de autorização do usuário autenticado. "
            "Usado EXCLUSIVAMENTE pelo frontend para invalidação de cache. "
            "Não representa permissões reais e não deve ser usado em decisões de autorização."
        ),
        responses={
            200: OpenApiResponse(
                description="Versão de autorização retornada com sucesso.",
            ),
            401: OpenApiResponse(description="Não autenticado."),
        },
        tags=["AuthZ Versioning"],
    )
    def get(self, request):
        """
        Consulta direta em UserAuthzState por user_id.
        Se o estado ainda não existe (usuário nunca teve mudança de permissão),
        retorna version=0 sem criar registro — comportamento lazy.
        """
        user_id = request.user.pk

        try:
            state = UserAuthzState.objects.only("authz_version").get(user_id=user_id)
            version = state.authz_version
        except UserAuthzState.DoesNotExist:
            version = 0

        logger.debug("AUTHZ_VERSION_FETCHED user_id=%s version=%s", user_id, version)

        return Response({"authz_version": version})
