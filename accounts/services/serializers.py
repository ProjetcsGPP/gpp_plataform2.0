from rest_framework import serializers


class UserManagementSerializer(serializers.Serializer):
    cpf = serializers.CharField(max_length=14)
    nome = serializers.CharField(max_length=200)
    role_codigo_aplicacao = serializers.CharField()  # GESTORPNGI
    aplicacao_destino = serializers.CharField()  # pngi
