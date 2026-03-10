from rest_framework import viewsets, permissions
from apps.accounts.models import Aplicacao
from apps.portal.serializers import AplicacaoSerializer


class AplicacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lista as aplicações disponíveis na plataforma.
    Retorna apenas aplicações visíveis no portal.
    """
    queryset = Aplicacao.objects.filter(isshowinportal=True).order_by("nomeaplicacao")
    serializer_class = AplicacaoSerializer
    permission_classes = [permissions.IsAuthenticated]
