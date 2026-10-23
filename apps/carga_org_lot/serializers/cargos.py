"""Serializers do catálogo global de cargos e suas ocorrências."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import (
    CargoReferenciaGlobal,
    MapeamentoCargoPatriarca,
    OcorrenciaCargoImportacao,
    Patriarca,
    StatusCargoReferencia,
    StatusVariacaoCargo,
    VariacaoCargoGlobal,
)
from ..services.cargos import cargo_key


class CargoReferenciaGlobalSerializer(AuditableModelSerializer):
    status_nome = serializers.CharField(source="get_strstatus_display", read_only=True)

    class Meta(AuditableModelSerializer.Meta):
        model = CargoReferenciaGlobal
        fields = AuditableModelSerializer.Meta.fields + [
            "idcargoreferencia",
            "strnome",
            "strchave",
            "strdescricao",
            "strstatus",
            "status_nome",
            "strorigem",
            "flgativo",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idcargoreferencia",
            "strchave",
            "status_nome",
        ]

    def validate_strnome(self, value):
        normalized = " ".join(value.split())
        if not normalized:
            raise serializers.ValidationError("Informe o nome do cargo.")
        return normalized

    def validate(self, attrs):
        name = attrs.get("strnome") or getattr(self.instance, "strnome", "")
        key = cargo_key(name)
        duplicate = CargoReferenciaGlobal.objects.filter(strchave=key)
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"strnome": "Já existe um cargo global com este nome normalizado."}
            )
        attrs["strchave"] = key
        return attrs


class VariacaoCargoGlobalSerializer(AuditableModelSerializer):
    idcargoreferencia_id = serializers.PrimaryKeyRelatedField(
        source="idcargoreferencia",
        queryset=CargoReferenciaGlobal.objects.all(),
        required=False,
        allow_null=True,
    )
    status_nome = serializers.CharField(source="get_strstatus_display", read_only=True)
    cargo_referencia_nome = serializers.CharField(
        source="idcargoreferencia.strnome",
        read_only=True,
        default=None,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = VariacaoCargoGlobal
        fields = AuditableModelSerializer.Meta.fields + [
            "idvariacaocargo",
            "idcargoreferencia_id",
            "cargo_referencia_nome",
            "strdescricao",
            "strchave",
            "strstatus",
            "status_nome",
            "inttotalocorrencias",
            "inttotalimportacoes",
            "inttotalpatriarcas",
            "datprimeiraocorrencia",
            "datultimaocorrencia",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idvariacaocargo",
            "strchave",
            "status_nome",
            "inttotalocorrencias",
            "inttotalimportacoes",
            "inttotalpatriarcas",
            "datprimeiraocorrencia",
            "datultimaocorrencia",
        ]

    def validate_strdescricao(self, value):
        normalized = " ".join(value.split())
        if not normalized:
            raise serializers.ValidationError("Informe a descrição da variação.")
        return normalized

    def validate(self, attrs):
        description = attrs.get("strdescricao") or getattr(
            self.instance,
            "strdescricao",
            "",
        )
        key = cargo_key(description)
        duplicate = VariacaoCargoGlobal.objects.filter(strchave=key)
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"strdescricao": "Esta variação já existe no catálogo global."}
            )
        attrs["strchave"] = key
        reference = attrs.get(
            "idcargoreferencia",
            getattr(self.instance, "idcargoreferencia", None),
        )
        status_value = attrs.get(
            "strstatus",
            getattr(self.instance, "strstatus", StatusVariacaoCargo.NOVA),
        )
        if reference is not None and (
            not reference.flgativo
            or reference.strstatus != StatusCargoReferencia.CONFIRMADO
        ):
            raise serializers.ValidationError(
                {"idcargoreferencia_id": "Selecione um cargo ativo e confirmado."}
            )
        if reference is not None:
            attrs["strstatus"] = StatusVariacaoCargo.CONFIRMADA
        elif status_value == StatusVariacaoCargo.CONFIRMADA:
            raise serializers.ValidationError(
                {
                    "strstatus": (
                        "Uma variação confirmada deve estar vinculada a um cargo."
                    )
                }
            )
        return attrs


class OcorrenciaCargoImportacaoSerializer(AuditableModelSerializer):
    variacao = VariacaoCargoGlobalSerializer(
        source="idvariacaocargo",
        read_only=True,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = OcorrenciaCargoImportacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idocorrenciacargo",
            "idvariacaocargo_id",
            "variacao",
            "idimportacaoplanilha_id",
            "idpatriarca_id",
            "intquantidade",
            "jsonlocalizacoes",
        ]
        read_only_fields = fields


class MapeamentoCargoPatriarcaSerializer(AuditableModelSerializer):
    idpatriarca_id = serializers.PrimaryKeyRelatedField(
        source="idpatriarca",
        queryset=Patriarca.objects.all(),
    )
    idvariacaocargo_id = serializers.PrimaryKeyRelatedField(
        source="idvariacaocargo",
        queryset=VariacaoCargoGlobal.objects.all(),
    )
    idcargoreferencia_id = serializers.PrimaryKeyRelatedField(
        source="idcargoreferencia",
        queryset=CargoReferenciaGlobal.objects.all(),
    )
    cargo_referencia_nome = serializers.CharField(
        source="idcargoreferencia.strnome",
        read_only=True,
    )
    variacao_descricao = serializers.CharField(
        source="idvariacaocargo.strdescricao",
        read_only=True,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = MapeamentoCargoPatriarca
        fields = AuditableModelSerializer.Meta.fields + [
            "idmapeamentocargo",
            "idpatriarca_id",
            "idvariacaocargo_id",
            "variacao_descricao",
            "idcargoreferencia_id",
            "cargo_referencia_nome",
            "flgativo",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idmapeamentocargo",
            "variacao_descricao",
            "cargo_referencia_nome",
        ]

    def validate(self, attrs):
        reference = attrs.get("idcargoreferencia") or getattr(
            self.instance,
            "idcargoreferencia",
            None,
        )
        if reference is not None and (
            not reference.flgativo
            or reference.strstatus != StatusCargoReferencia.CONFIRMADO
        ):
            raise serializers.ValidationError(
                {"idcargoreferencia_id": "Selecione um cargo ativo e confirmado."}
            )
        return attrs
