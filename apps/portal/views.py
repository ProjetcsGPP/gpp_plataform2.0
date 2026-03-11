"""
GPP Plataform 2.0 — Portal Views
FASE 6: APIs do hub central — aplicacoes + dashboard.
"""
from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Aplicacao, UserRole
from apps.portal.serializers import AplicacaoSerializer, DashboardSerializer


class AplicacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/portal/aplicacoes/         → lista apps visíveis no portal
    GET /api/portal/aplicacoes/{id}/    → detalhe de uma app
    Requer autenticação.
    """
    queryset = Aplicacao.objects.filter(isshowinportal=True).order_by("nomeaplicacao")
    serializer_class = AplicacaoSerializer
    permission_classes = [permissions.IsAuthenticated]


class DashboardView(APIView):
    """
    GET /api/portal/dashboard/
    Retorna as apps visíveis no portal + roles do usuário autenticado.
    """
    permission_classes = [permissions.IsAuthenticated]

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
