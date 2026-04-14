from rest_framework import serializers
from apps.accounts.models import Aplicacao, UserRole


class AplicacaoPortalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Aplicacao
        fields = ["idaplicacao", "codigointerno", "nomeaplicacao", "base_url", "isshowinportal"]


class UserRoleDashboardSerializer(serializers.ModelSerializer):
    role_codigo = serializers.CharField(source="role.codigoperfil", read_only=True)
    role_nome = serializers.CharField(source="role.nomeperfil", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "aplicacao_codigo", "role_codigo", "role_nome"]


class DashboardSerializer(serializers.Serializer):
    """
    Serializador para o endpoint /dashboard/.
    Agrega aplicações visíveis no portal e roles do usuário.
    """
    aplicacoes = AplicacaoPortalSerializer(many=True)
    roles = UserRoleDashboardSerializer(many=True)
