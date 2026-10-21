"""Serializers do processo de carga inicial e do patriarca."""

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import (
    HistoricoProcessoCargaInicial,
    Patriarca,
    ProcessoCargaInicial,
    StatusProgresso,
)
from ..services.workflow import AuditActor, get_or_create_active_process
from .catalogs import StatusProgressoSerializer


class HistoricoProcessoCargaInicialSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = HistoricoProcessoCargaInicial
        fields = AuditableModelSerializer.Meta.fields + [
            "idhistoricoprocesso",
            "stracao",
            "strfaseanterior",
            "strfasenova",
            "strstatusorganogramaanterior",
            "strstatusorganogramanovo",
            "strstatuslotacaoanterior",
            "strstatuslotacaonovo",
            "strmensagem",
            "jsondetalhes",
        ]
        read_only_fields = fields


class ProcessoCargaInicialSerializer(AuditableModelSerializer):
    idpatriarca_id = serializers.IntegerField(read_only=True)
    fase_nome = serializers.CharField(source="get_strfaseatual_display", read_only=True)
    status_organograma_nome = serializers.CharField(
        source="get_strstatusorganograma_display",
        read_only=True,
    )
    status_lotacao_nome = serializers.CharField(
        source="get_strstatuslotacao_display",
        read_only=True,
    )
    historico = HistoricoProcessoCargaInicialSerializer(many=True, read_only=True)

    class Meta(AuditableModelSerializer.Meta):
        model = ProcessoCargaInicial
        fields = AuditableModelSerializer.Meta.fields + [
            "idprocessocargainicial",
            "idpatriarca_id",
            "strfaseatual",
            "fase_nome",
            "strstatusorganograma",
            "status_organograma_nome",
            "strstatuslotacao",
            "status_lotacao_nome",
            "flgativo",
            "databertura",
            "dataconclusao",
            "historico",
        ]
        read_only_fields = fields


class PatriarcaSerializer(AuditableModelSerializer):
    organograma_download_url = serializers.SerializerMethodField()
    processo_ativo = serializers.SerializerMethodField()
    idstatusprogresso_id = serializers.PrimaryKeyRelatedField(
        source="idstatusprogresso",
        queryset=StatusProgresso.objects.all(),
        required=False,
    )
    status = StatusProgressoSerializer(source="idstatusprogresso", read_only=True)

    class Meta(AuditableModelSerializer.Meta):
        model = Patriarca
        fields = AuditableModelSerializer.Meta.fields + [
            "idpatriarca",
            "idexternopatriarca",
            "strsiglapatriarca",
            "strnome",
            "datcriacao",
            "datalteracao",
            "idstatusprogresso_id",
            "status",
            "organograma_download_url",
            "processo_ativo",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idpatriarca",
            "datcriacao",
            "datalteracao",
            "status",
            "organograma_download_url",
            "processo_ativo",
        ]

    def get_organograma_download_url(self, instance) -> str:
        request = self.context.get("request")
        path = f"/api/carga-org-lot/patriarcas/{instance.pk}/" "organograma/download/"
        return request.build_absolute_uri(path) if request else path

    @extend_schema_field(ProcessoCargaInicialSerializer(allow_null=True))
    def get_processo_ativo(self, instance):
        process = instance.processos_carga_inicial.filter(flgativo=True).first()
        if process is None:
            return None
        return ProcessoCargaInicialSerializer(process, context=self.context).data

    def validate_strsiglapatriarca(self, value):
        sigla = value.strip().upper()
        if not sigla:
            raise serializers.ValidationError("A sigla do patriarca é obrigatória.")

        existentes = Patriarca.objects.filter(strsiglapatriarca__iexact=sigla)
        if self.instance is not None:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise serializers.ValidationError(
                "Já existe um patriarca cadastrado com esta sigla."
            )
        return sigla

    def validate_strnome(self, value):
        nome = value.strip()
        if not nome:
            raise serializers.ValidationError("O nome do patriarca é obrigatório.")
        return nome

    def create(self, validated_data):
        if "idstatusprogresso" not in validated_data:
            validated_data["idstatusprogresso"] = StatusProgresso.objects.get(pk=1)
        validated_data["datcriacao"] = timezone.now()
        actor = AuditActor.from_validated_data(validated_data)
        instance = super().create(validated_data)
        get_or_create_active_process(instance, actor)
        return instance

    def update(self, instance, validated_data):
        validated_data["datalteracao"] = timezone.now()
        return super().update(instance, validated_data)
