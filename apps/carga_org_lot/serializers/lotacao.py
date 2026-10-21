"""Serializer dos itens de lotação validados."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import (
    AcaoResolucaoValidacao,
    AlternativaResolucaoValidacao,
    CasoValidacaoImportacao,
    ItemLotacao,
    ItemLotacaoImportado,
    ResolucaoValidacao,
)


class AlternativaResolucaoValidacaoSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = AlternativaResolucaoValidacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idalternativaresolucao",
            "stracao",
            "strdescricao",
            "jsonpayload",
            "decconfianca",
            "flgrecomendada",
        ]
        read_only_fields = fields


class ResolucaoValidacaoSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = ResolucaoValidacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idresolucaovalidacao",
            "idalternativaresolucao_id",
            "stracao",
            "strjustificativa",
            "jsonantes",
            "jsondepois",
            "datresolucao",
        ]
        read_only_fields = fields


class ItemLotacaoImportadoSerializer(AuditableModelSerializer):
    situacao_nome = serializers.CharField(
        source="get_strsituacao_display",
        read_only=True,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = ItemLotacaoImportado
        fields = AuditableModelSerializer.Meta.fields + [
            "iditemlotacaoimportado",
            "idimportacaoplanilha_id",
            "idorgaoorganograma_id",
            "idunidadeorganograma_id",
            "strsiglaorgaooriginal",
            "strsiglaorgao",
            "strnomeorgao",
            "strnomeservidor",
            "strcpforiginal",
            "strcpf",
            "strcargooriginal",
            "strcargonormalizado",
            "strsiglaunidadeoriginal",
            "strsiglaunidade",
            "strnomeunidade",
            "strabaorigem",
            "intlinhaorigem",
            "strsituacao",
            "situacao_nome",
        ]
        read_only_fields = fields


class CasoValidacaoImportacaoSerializer(AuditableModelSerializer):
    alternativas = AlternativaResolucaoValidacaoSerializer(many=True, read_only=True)
    resolucoes = ResolucaoValidacaoSerializer(many=True, read_only=True)
    item_ids = serializers.PrimaryKeyRelatedField(
        source="itens",
        many=True,
        read_only=True,
    )
    ocorrencia_ids = serializers.PrimaryKeyRelatedField(
        source="ocorrencias",
        many=True,
        read_only=True,
    )
    status_nome = serializers.CharField(source="get_strstatus_display", read_only=True)
    severidade_nome = serializers.CharField(
        source="get_strseveridade_display",
        read_only=True,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = CasoValidacaoImportacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idcasovalidacao",
            "idrelatoriovalidacao_id",
            "strchaveagrupamento",
            "strcodigo",
            "strseveridade",
            "severidade_nome",
            "strtitulo",
            "strmensagem",
            "strstatus",
            "status_nome",
            "datresolucao",
            "item_ids",
            "ocorrencia_ids",
            "alternativas",
            "resolucoes",
        ]
        read_only_fields = fields


class ResolverCasoValidacaoSerializer(serializers.Serializer):
    acao = serializers.ChoiceField(choices=AcaoResolucaoValidacao.choices)
    alternativa_id = serializers.PrimaryKeyRelatedField(
        source="alternativa",
        queryset=AlternativaResolucaoValidacao.objects.all(),
        required=False,
        allow_null=True,
    )
    justificativa = serializers.CharField(required=False, allow_blank=True, default="")
    alteracoes = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        action = attrs["acao"]
        if (
            action == AcaoResolucaoValidacao.ACEITAR_COMO_INFORMADO
            and not attrs["justificativa"].strip()
        ):
            raise serializers.ValidationError(
                {"justificativa": "Justifique a aceitação deste aviso."}
            )
        if action == AcaoResolucaoValidacao.APLICAR_SUGESTAO and not attrs.get(
            "alternativa"
        ):
            raise serializers.ValidationError(
                {"alternativa_id": "Selecione a sugestão que deve ser aplicada."}
            )
        if (
            action == AcaoResolucaoValidacao.CORRIGIR_MANUALMENTE
            and not attrs["alteracoes"]
        ):
            raise serializers.ValidationError(
                {"alteracoes": "Informe ao menos uma correção manual."}
            )
        normalized_changes = []
        for entry in attrs["alteracoes"]:
            if "iditemlotacaoimportado" not in entry or "campos" not in entry:
                raise serializers.ValidationError(
                    {
                        "alteracoes": (
                            "Cada alteração deve informar "
                            "iditemlotacaoimportado e campos."
                        )
                    }
                )
            try:
                item_id = int(entry["iditemlotacaoimportado"])
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"alteracoes": "O identificador da linha deve ser numérico."}
                ) from exc
            if not isinstance(entry["campos"], dict) or not entry["campos"]:
                raise serializers.ValidationError(
                    {"alteracoes": "Informe ao menos um campo em cada correção."}
                )
            normalized_changes.append(
                {
                    "iditemlotacaoimportado": item_id,
                    "campos": entry["campos"],
                }
            )
        attrs["alteracoes"] = normalized_changes
        return attrs


class ItemLotacaoSerializer(AuditableModelSerializer):
    idimportacaoplanilha_id = serializers.IntegerField(read_only=True)
    idorgaoorganograma_id = serializers.IntegerField(read_only=True)
    idunidadeorganograma_id = serializers.IntegerField(read_only=True)

    class Meta(AuditableModelSerializer.Meta):
        model = ItemLotacao
        fields = AuditableModelSerializer.Meta.fields + [
            "iditemlotacao",
            "idimportacaoplanilha_id",
            "idorgaoorganograma_id",
            "idunidadeorganograma_id",
            "strsiglaorgao",
            "strnomeorgao",
            "strnomeservidor",
            "strcpf",
            "strcargooriginal",
            "strcargonormalizado",
            "strsiglaunidade",
            "strnomeunidade",
            "strabaorigem",
            "intlinhaorigem",
        ]
        read_only_fields = fields
