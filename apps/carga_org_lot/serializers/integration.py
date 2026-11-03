"""Serializers da trilha de integração com a PRODEST."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import EventoIntegracaoProdest
from ..services.integration_event_presentation import build_display_details
from ..services.submission_workflow import canonical_event_phase


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
    fase_exibicao = serializers.SerializerMethodField()
    fase_exibicao_nome = serializers.SerializerMethodField()
    jsondetalhes_exibicao = serializers.SerializerMethodField()

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
            "fase_exibicao",
            "fase_exibicao_nome",
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
            "jsondetalhes_exibicao",
            "datocorrencia",
        ]
        read_only_fields = fields

    def get_sucesso(self, instance) -> bool:
        return instance.strresultado == "SUCESSO"

    def get_fase_exibicao(self, instance) -> str:
        return canonical_event_phase(instance)

    def get_fase_exibicao_nome(self, instance) -> str:
        phase = canonical_event_phase(instance)
        if not phase:
            return ""
        return dict(instance._meta.get_field("strfase").choices).get(phase, phase)

    def get_jsondetalhes_exibicao(self, instance) -> dict:
        return build_display_details(instance.jsondetalhes)
