"""Serializer dos itens de lotação validados."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import (
    AcaoResolucaoValidacao,
    AlternativaResolucaoValidacao,
    CasoValidacaoImportacao,
    EscopoMapeamentoCargo,
    ItemLotacao,
    ItemLotacaoImportado,
    ResolucaoValidacao,
)


class AlternativaResolucaoValidacaoSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = AlternativaResolucaoValidacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idalternativaresolucao",
            "idcargoreferencia_id",
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
    cargo_referencia_nome = serializers.CharField(
        source="idcargoreferencia.strnome",
        read_only=True,
        default=None,
    )
    contexto = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = ItemLotacaoImportado
        fields = AuditableModelSerializer.Meta.fields + [
            "iditemlotacaoimportado",
            "idimportacaoplanilha_id",
            "idorgaoorganograma_id",
            "idunidadeorganograma_id",
            "idvariacaocargo_id",
            "idcargoreferencia_id",
            "cargo_referencia_nome",
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
            "contexto",
        ]
        read_only_fields = fields

    @staticmethod
    def get_contexto(instance) -> dict:
        importation = instance.idimportacaoplanilha
        patriarch = importation.idpatriarca
        organogram = importation.idimportacaoorganograma
        lotation_set = importation.idconjuntolotacao
        return {
            "importacao": {
                "id": importation.pk,
                "referencia": importation.strreferencia,
                "nome_arquivo": importation.strnomearquivo,
            },
            "patriarca": {
                "id": patriarch.pk,
                "sigla": patriarch.strsiglapatriarca,
                "nome": patriarch.strnome,
            },
            "organograma": (
                {
                    "id": organogram.pk,
                    "referencia": organogram.strreferencia,
                    "nome_arquivo": organogram.strnomearquivo,
                }
                if organogram is not None
                else None
            ),
            "conjunto": (
                {
                    "id": lotation_set.pk,
                    "referencia": lotation_set.strreferencia,
                    "situacao": lotation_set.strsituacao,
                }
                if lotation_set is not None
                else None
            ),
        }


class ItemLotacaoDescartadoSerializer(ItemLotacaoImportadoSerializer):
    descartes = serializers.SerializerMethodField()

    class Meta(ItemLotacaoImportadoSerializer.Meta):
        fields = ItemLotacaoImportadoSerializer.Meta.fields + ["descartes"]
        read_only_fields = fields

    @staticmethod
    def get_descartes(instance) -> list[dict]:
        entries = []
        for case in instance.casos_validacao.all():
            for resolution in case.resolucoes.all():
                if resolution.stracao != AcaoResolucaoValidacao.DESCARTAR_LINHAS:
                    continue
                entries.append(
                    {
                        "idcasovalidacao": case.pk,
                        "codigo_critica": case.strcodigo,
                        "idresolucaovalidacao": resolution.pk,
                        "motivo": resolution.strjustificativa,
                        "descartado_por_id": resolution.created_by_id,
                        "descartado_por_nome": resolution.created_by_name,
                        "data_descarte": resolution.datresolucao,
                    }
                )
        return entries


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
    contexto = serializers.SerializerMethodField()
    assunto = serializers.SerializerMethodField()
    assunto_nome = serializers.SerializerMethodField()

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
            "assunto",
            "assunto_nome",
            "contexto",
            "item_ids",
            "ocorrencia_ids",
            "alternativas",
            "resolucoes",
        ]
        read_only_fields = fields

    @staticmethod
    def get_assunto(instance) -> str:
        from ..services.validation_cases import validation_case_subject

        return validation_case_subject(instance.strcodigo)

    def get_assunto_nome(self, instance) -> str:
        from ..services.validation_cases import SUBJECT_LABELS

        return SUBJECT_LABELS[self.get_assunto(instance)]

    @staticmethod
    def get_contexto(instance) -> dict:
        importation = instance.idrelatoriovalidacao.idimportacaoplanilha
        patriarch = importation.idpatriarca
        organogram = importation.idimportacaoorganograma
        lotation_set = importation.idconjuntolotacao
        return {
            "importacao": {
                "id": importation.pk,
                "referencia": importation.strreferencia,
                "nome_arquivo": importation.strnomearquivo,
            },
            "patriarca": {
                "id": patriarch.pk,
                "sigla": patriarch.strsiglapatriarca,
                "nome": patriarch.strnome,
            },
            "organograma": (
                {
                    "id": organogram.pk,
                    "referencia": organogram.strreferencia,
                    "nome_arquivo": organogram.strnomearquivo,
                }
                if organogram is not None
                else None
            ),
            "conjunto": (
                {
                    "id": lotation_set.pk,
                    "referencia": lotation_set.strreferencia,
                    "situacao": lotation_set.strsituacao,
                }
                if lotation_set is not None
                else None
            ),
        }


class ResolverCasoValidacaoSerializer(serializers.Serializer):
    acao = serializers.ChoiceField(choices=AcaoResolucaoValidacao.choices)
    alternativa_id = serializers.PrimaryKeyRelatedField(
        source="alternativa",
        queryset=AlternativaResolucaoValidacao.objects.all(),
        required=False,
        allow_null=True,
    )
    justificativa = serializers.CharField(required=False, allow_blank=True, default="")
    escopo_cargo = serializers.ChoiceField(
        choices=EscopoMapeamentoCargo.choices,
        required=False,
        default=EscopoMapeamentoCargo.GLOBAL,
    )
    memorizar_cargo = serializers.BooleanField(required=False, default=False)
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
    cargo_referencia_nome = serializers.CharField(
        source="idcargoreferencia.strnome",
        read_only=True,
        default=None,
    )
    contexto = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = ItemLotacao
        fields = AuditableModelSerializer.Meta.fields + [
            "iditemlotacao",
            "idimportacaoplanilha_id",
            "idorgaoorganograma_id",
            "idunidadeorganograma_id",
            "idcargoreferencia_id",
            "cargo_referencia_nome",
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
            "contexto",
        ]
        read_only_fields = fields

    @staticmethod
    def get_contexto(instance) -> dict:
        return ItemLotacaoImportadoSerializer.get_contexto(instance)
