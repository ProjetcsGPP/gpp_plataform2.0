from rest_framework import serializers
from apps.accounts.models import Aplicacao


class AplicacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Aplicacao
        fields = ["idaplicacao", "codigointerno", "nomeaplicacao", "base_url", "isshowinportal"]
