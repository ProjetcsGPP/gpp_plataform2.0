"""Serializers da trilha de integração com a PRODEST."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import EventoIntegracaoProdest


class EventoIntegracaoProdestSerializer(AuditableModelSerializer):
    idpatriarca_id = serializers.IntegerField(read_only=True)
    idprocessocargainicial_id = serializers.IntegerField(read_only=True)
    idenvioorganograma_id = serializers.IntegerField(read_only=True)
    operacao_nome = serializers.CharField(
        source="get_stroperacao_display",
        read_only=True,
    )
    resultado_nome = serializers.CharField(
        source="get_strresultado_display",
        read_only=True,
    )
    sucesso = serializers.SerializerMethodField()
    fase_nome = serializers.CharField(source="get_strfase_display", read_only=True)
    status_operacional_nome = serializers.CharField(
        source="get_strstatusoperacional_display", read_only=True
    )

    class Meta(AuditableModelSerializer.Meta):
        model = EventoIntegracaoProdest
        fields = AuditableModelSerializer.Meta.fields + [
            "ideventointegracao",
            "idcorrelacao",
            "idpatriarca_id",
            "idprocessocargainicial_id",
            "idenvioorganograma_id",
            "idexternocarga",
            "strvisibilidade",
            "strtipocarga",
            "strfase",
            "fase_nome",
            "strcodigo",
            "strstatusoperacional",
            "status_operacional_nome",
            "strtitulo",
            "stroperacao",
            "operacao_nome",
            "strmetodo",
            "strendpoint",
            "inttentativa",
            "strresultado",
            "resultado_nome",
            "sucesso",
            "inthttpstatus",
            "intduracaoms",
            "strmensagem",
            "jsondetalhes",
            "datocorrencia",
        ]
        read_only_fields = fields

    def get_sucesso(self, instance) -> bool:
        return instance.strresultado == "SUCESSO"
