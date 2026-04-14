"""
GPP Plataform 2.0 — Portal Views
FASE 6: APIs do hub central — aplicacoes + dashboard.
"""
from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Aplicacao, UserRole
from apps.portal.serializers import AplicacaoPortalSerializer, DashboardSerializer
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from common.schema import tag_all_actions

@tag_all_actions("2 - Portal")
class AplicacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/portal/aplicacoes/         → lista apps visíveis no portal
    GET /api/portal/aplicacoes/{id}/    → detalhe de uma app
    Requer autenticação.
    """
    queryset = Aplicacao.objects.filter(isshowinportal=True).order_by("nomeaplicacao")
    serializer_class = AplicacaoPortalSerializer
    permission_classes = [permissions.IsAuthenticated]


class DashboardView(APIView):
    """
    GET /api/portal/dashboard/
    Retorna as apps visíveis no portal + roles do usuário autenticado.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Dashboard do Portal.",
        description=(
            "Retorna todas as aplicações que o usuário autenticado tem permissão para acessar, "
            "retorna também os perfis do usuário para cada aplicação que está cadastrada."
        ),
        responses={
            200: DashboardSerializer,   # ← passa o serializer diretamente, não OpenApiResponse
            403: OpenApiResponse(description="Usuário não autenticado ou sem permissão"),
        },
        tags=["2 - Portal"],
    )
    
    def get(self, request):
        apps = Aplicacao.objects.filter(isshowinportal=True).order_by("nomeaplicacao")
        user_roles = (
            UserRole.objects
            .filter(user=request.user)
            .select_related("role", "aplicacao")
        )
        data = DashboardSerializer(
            {"aplicacoes": apps, "roles": user_roles},
            context={"request": request},
        ).data
        return Response(data)
