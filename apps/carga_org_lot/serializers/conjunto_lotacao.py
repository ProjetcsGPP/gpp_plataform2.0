"""Serializers dos conjuntos versionados de lotação."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import (
    ConjuntoLotacao,
    HistoricoConjuntoLotacao,
    ImportacaoPlanilha,
    Patriarca,
)
from ..services.lotacao_sets import available_set_actions, validate_set_organogram


class HistoricoConjuntoLotacaoSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = HistoricoConjuntoLotacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idhistoricoconjuntolotacao",
            "stracao",
            "strsituacaoanterior",
            "strsituacaonova",
            "strmensagem",
            "jsondetalhes",
        ]
        read_only_fields = fields


class ConjuntoLotacaoSerializer(AuditableModelSerializer):
    idpatriarca_id = serializers.PrimaryKeyRelatedField(
        source="idpatriarca",
        queryset=Patriarca.objects.all(),
    )
    idimportacaoorganograma_id = serializers.PrimaryKeyRelatedField(
        source="idimportacaoorganograma",
        queryset=ImportacaoPlanilha.objects.all(),
    )
    situacao_nome = serializers.CharField(
        source="get_strsituacao_display",
        read_only=True,
    )
    total_importacoes = serializers.SerializerMethodField()
    total_registros = serializers.SerializerMethodField()
    total_casos_pendentes = serializers.SerializerMethodField()
    total_registros_descartados = serializers.SerializerMethodField()
    idconjuntosubstituto = serializers.SerializerMethodField()
    download_consolidado_url = serializers.SerializerMethodField()
    patriarca_resumo = serializers.SerializerMethodField()
    organograma_resumo = serializers.SerializerMethodField()
    acoes_disponiveis = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = ConjuntoLotacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idconjuntolotacao",
            "idpatriarca_id",
            "idimportacaoorganograma_id",
            "idconjuntoanterior_id",
            "strreferencia",
            "strsituacao",
            "situacao_nome",
            "strjustificativaultimaacao",
            "dathomologacao",
            "datativacao",
            "datcancelamento",
            "total_importacoes",
            "total_registros",
            "total_casos_pendentes",
            "total_registros_descartados",
            "idconjuntosubstituto",
            "download_consolidado_url",
            "patriarca_resumo",
            "organograma_resumo",
            "acoes_disponiveis",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idconjuntolotacao",
            "idconjuntoanterior_id",
            "strsituacao",
            "situacao_nome",
            "strjustificativaultimaacao",
            "dathomologacao",
            "datativacao",
            "datcancelamento",
            "total_importacoes",
            "total_registros",
            "total_casos_pendentes",
            "total_registros_descartados",
            "idconjuntosubstituto",
            "download_consolidado_url",
            "patriarca_resumo",
            "organograma_resumo",
            "acoes_disponiveis",
        ]

    def validate(self, attrs):
        if self.instance is not None:
            raise serializers.ValidationError(
                "Os dados estruturais do conjunto são imutáveis. Use as ações do fluxo."
            )
        validate_set_organogram(
            attrs["idpatriarca"],
            attrs["idimportacaoorganograma"],
        )
        return attrs

    @staticmethod
    def get_total_importacoes(instance) -> int:
        return instance.importacoes.count()

    @staticmethod
    def get_total_registros(instance) -> int:
        return sum(
            importacao.itens_lotacao.count()
            for importacao in instance.importacoes.all()
        )

    @staticmethod
    def get_total_casos_pendentes(instance) -> int:
        return sum(
            importacao.relatorio_validacao.casos.filter(strstatus="PENDENTE").count()
            for importacao in instance.importacoes.all()
            if hasattr(importacao, "relatorio_validacao")
        )

    @staticmethod
    def get_total_registros_descartados(instance) -> int:
        return sum(
            importacao.itens_lotacao_importados.filter(
                strsituacao="DESCARTADO"
            ).count()
            for importacao in instance.importacoes.all()
        )

    @staticmethod
    def get_idconjuntosubstituto(instance) -> int | None:
        replacement = next(iter(instance.conjuntos_substitutos.all()), None)
        return replacement.pk if replacement is not None else None

    def get_download_consolidado_url(self, instance) -> str:
        path = (
            f"/api/carga-org-lot/conjuntos-lotacao/{instance.pk}/"
            "download-consolidado/"
        )
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    @staticmethod
    def get_patriarca_resumo(instance) -> dict:
        return {
            "idpatriarca": instance.idpatriarca_id,
            "sigla": instance.idpatriarca.strsiglapatriarca,
            "nome": instance.idpatriarca.strnome,
        }

    @staticmethod
    def get_organograma_resumo(instance) -> dict:
        organogram = instance.idimportacaoorganograma
        return {
            "idimportacaoplanilha": organogram.pk,
            "referencia": organogram.strreferencia,
            "nome_arquivo": organogram.strnomearquivo,
            "status": organogram.strstatusimportacao,
            "data_importacao": organogram.datimportacao,
        }

    @staticmethod
    def get_acoes_disponiveis(instance) -> dict:
        return available_set_actions(instance)


class AcaoConjuntoLotacaoSerializer(serializers.Serializer):
    justificativa = serializers.CharField(allow_blank=False, trim_whitespace=True)
