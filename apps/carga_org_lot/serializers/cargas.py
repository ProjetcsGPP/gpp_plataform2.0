"""Serializers legados de acompanhamento de cargas."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import DetalheStatusCarga, StatusCarga, StatusProgresso, TipoCarga, TokenEnvioCarga
from .catalogs import StatusCargaSerializer, StatusProgressoSerializer, TipoCargaSerializer


class DetalheStatusCargaSerializer(AuditableModelSerializer):
    idtokenenviocarga_id = serializers.PrimaryKeyRelatedField(
        source="idtokenenviocarga",
        queryset=TokenEnvioCarga.objects.all(),
    )
    idstatuscarga_id = serializers.PrimaryKeyRelatedField(
        source="idstatuscarga",
        queryset=StatusCarga.objects.all(),
    )
    status = StatusCargaSerializer(source="idstatuscarga", read_only=True)

    class Meta(AuditableModelSerializer.Meta):
        model = DetalheStatusCarga
        fields = AuditableModelSerializer.Meta.fields + [
            "iddetalhestatuscarga",
            "idtokenenviocarga_id",
            "idstatuscarga_id",
            "status",
            "strmensagem",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "iddetalhestatuscarga",
            "status",
        ]


class TokenEnvioCargaSerializer(AuditableModelSerializer):
    """Representação segura do processo, sem retornar o token ao cliente."""

    strtoken = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
    )
    idtipocarga_id = serializers.PrimaryKeyRelatedField(
        source="idtipocarga",
        queryset=TipoCarga.objects.all(),
    )
    idstatusprogresso_id = serializers.PrimaryKeyRelatedField(
        source="idstatusprogresso",
        queryset=StatusProgresso.objects.all(),
    )
    tipo_carga = TipoCargaSerializer(source="idtipocarga", read_only=True)
    status_progresso = StatusProgressoSerializer(
        source="idstatusprogresso", read_only=True
    )
    detalhes = DetalheStatusCargaSerializer(many=True, read_only=True)
    possui_token = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = TokenEnvioCarga
        fields = AuditableModelSerializer.Meta.fields + [
            "idtokenenviocarga",
            "strtoken",
            "possui_token",
            "idtipocarga_id",
            "tipo_carga",
            "idstatusprogresso_id",
            "status_progresso",
            "detalhes",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idtokenenviocarga",
            "possui_token",
            "tipo_carga",
            "status_progresso",
            "detalhes",
        ]

    def get_possui_token(self, instance) -> bool:
        return bool(instance.strtoken)
