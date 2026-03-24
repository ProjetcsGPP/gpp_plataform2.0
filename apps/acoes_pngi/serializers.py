"""
GPP Plataform 2.0 — Ações PNGI Serializers

Regras:
- Models que herdam AuditableModel → herdam AuditableModelSerializer
- Models de referência simples       → herdam ModelSerializer
- Campos de auditoria são read-only, preenchidos pelo AuditableMixin
- Nenhuma FK para auth_user neste módulo
"""
from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from .models import (
    Acoes,
    AcaoAnotacaoAlinhamento,
    AcaoDestaque,
    AcaoPrazo,
    Eixo,
    SituacaoAcao,
    TipoAnotacaoAlinhamento,
    TipoEntraveAlerta,
    VigenciaPNGI,
)


# ---------------------------------------------------------------------------
# Serializers de referência (sem AuditableModel)
# ---------------------------------------------------------------------------

class EixoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Eixo
        fields = [
            "ideixo",
            "strdescricaoeixo",
            "stralias",
            "created_by_id",
            "created_by_name",
            "updated_by_id",
            "updated_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_by_id",
            "created_by_name",
            "updated_by_id",
            "updated_by_name",
            "created_at",
            "updated_at",
        ]


class SituacaoAcaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SituacaoAcao
        fields = ["idsituacaoacao", "strdescricaosituacao"]


class TipoEntraveAlertaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoEntraveAlerta
        fields = ["idtipoentravealerta", "strdescricaotipoentravealerta"]


class TipoAnotacaoAlinhamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoAnotacaoAlinhamento
        fields = ["idtipoanotacaoalinhamento", "strdescricaotipoanotacaoalinhamento"]


# ---------------------------------------------------------------------------
# Serializers de domínio (herdam AuditableModel)
# ---------------------------------------------------------------------------

class VigenciaPNGISerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = VigenciaPNGI
        fields = AuditableModelSerializer.Meta.fields + [
            "idvigenciapngi",
            "strdescricao",
            "datiniciovigencia",
            "datfinalvigencia",
        ]


class AcoesSerializer(AuditableModelSerializer):
    """
    Serializer principal de Acoes.

    FKs (idvigenciapngi, idtipoentravealerta, idsituacaoacao, ideixo) aceitam
    escrita via PK inteiro e expondo o id no output.
    Campos de auditoria são read-only (herdados de AuditableModelSerializer).
    orgao NÃO aparece aqui — Ações são independentes de orgão.
    """

    class Meta(AuditableModelSerializer.Meta):
        model = Acoes
        fields = AuditableModelSerializer.Meta.fields + [
            "idacao",
            "strapelido",
            "strdescricaoacao",
            "strdescricaoentrega",
            "datdataentrega",
            "idvigenciapngi_id",
            "idtipoentravealerta_id",
            "idsituacaoacao_id",
            "ideixo_id",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idacao",
        ]


class AcaoPrazoSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = AcaoPrazo
        fields = AuditableModelSerializer.Meta.fields + [
            "idacaoprazo",
            "idacao_id",
            "isacaoprazoativo",
            "strprazo",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idacaoprazo",
        ]


class AcaoDestaqueSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = AcaoDestaque
        fields = AuditableModelSerializer.Meta.fields + [
            "idacaodestaque",
            "idacao_id",
            "datdatadestaque",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idacaodestaque",
        ]


class AcaoAnotacaoAlinhamentoSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = AcaoAnotacaoAlinhamento
        fields = AuditableModelSerializer.Meta.fields + [
            "idacaoanotacaoalinhamento",
            "idacao_id",
            "idtipoanotacaoalinhamento_id",
            "strdescricao",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idacaoanotacaoalinhamento",
        ]
