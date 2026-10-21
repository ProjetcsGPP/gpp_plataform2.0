"""Serializers das tabelas de domínio."""

from rest_framework import serializers

from ..models import StatusCarga, StatusProgresso, TipoCarga


class StatusCargaSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusCarga
        fields = ["idstatuscarga", "strdescricao", "flgsucesso"]


class StatusProgressoSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusProgresso
        fields = ["idstatusprogresso", "strdescricao"]


class TipoCargaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoCarga
        fields = ["idtipocarga", "strdescricao"]
