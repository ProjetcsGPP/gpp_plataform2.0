"""Serializers da aplicação de carga de organograma e lotação."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from .exceptions import (
    OrganogramSheetSelectionRequired,
    SpreadsheetImportValidationError,
)
from .models import (
    DetalheStatusCarga,
    ImportacaoPlanilha,
    ItemOrganograma,
    Patriarca,
    StatusCarga,
    StatusProgresso,
    TipoCarga,
    TokenEnvioCarga,
)
from .services.organograma import (
    ORGANOGRAMA_TYPE_ID,
    validate_organogram_spreadsheet,
)

DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xls", ".xlsx", ".ods"}


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


class PatriarcaSerializer(AuditableModelSerializer):
    organograma_download_url = serializers.SerializerMethodField()
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
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idpatriarca",
            "datcriacao",
            "datalteracao",
            "status",
            "organograma_download_url",
        ]

    def get_organograma_download_url(self, instance) -> str:
        request = self.context.get("request")
        path = (
            f"/api/carga-org-lot/patriarcas/{instance.pk}/"
            "organograma/download/"
        )
        return request.build_absolute_uri(path) if request else path

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
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["datalteracao"] = timezone.now()
        return super().update(instance, validated_data)


class ImportacaoPlanilhaSerializer(AuditableModelSerializer):
    arquivo = serializers.FileField(write_only=True, required=False)
    aba = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=255,
    )
    idpatriarca_id = serializers.PrimaryKeyRelatedField(
        source="idpatriarca",
        queryset=Patriarca.objects.all(),
    )
    idtipocarga_id = serializers.PrimaryKeyRelatedField(
        source="idtipocarga",
        queryset=TipoCarga.objects.all(),
    )
    idimportacaoorganograma_id = serializers.PrimaryKeyRelatedField(
        source="idimportacaoorganograma",
        queryset=ImportacaoPlanilha.objects.all(),
        required=False,
        allow_null=True,
    )
    idstatusprogresso_id = serializers.PrimaryKeyRelatedField(
        source="idstatusprogresso",
        queryset=StatusProgresso.objects.all(),
        required=False,
    )
    patriarca = PatriarcaSerializer(source="idpatriarca", read_only=True)
    tipo_carga = TipoCargaSerializer(source="idtipocarga", read_only=True)
    status = StatusProgressoSerializer(source="idstatusprogresso", read_only=True)
    download_url = serializers.SerializerMethodField()
    total_itens_organograma = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = ImportacaoPlanilha
        fields = AuditableModelSerializer.Meta.fields + [
            "idimportacaoplanilha",
            "idpatriarca_id",
            "patriarca",
            "idtipocarga_id",
            "tipo_carga",
            "idimportacaoorganograma_id",
            "idstatusprogresso_id",
            "status",
            "arquivo",
            "aba",
            "strnomearquivo",
            "strtipomime",
            "inttamanhoarquivo",
            "strhasharquivo",
            "strabaimportada",
            "datimportacao",
            "download_url",
            "total_itens_organograma",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idimportacaoplanilha",
            "patriarca",
            "tipo_carga",
            "status",
            "strnomearquivo",
            "strtipomime",
            "inttamanhoarquivo",
            "strhasharquivo",
            "strabaimportada",
            "datimportacao",
            "download_url",
            "total_itens_organograma",
        ]

    def get_download_url(self, instance) -> str:
        request = self.context.get("request")
        path = f"/api/carga-org-lot/importacoes/{instance.pk}/download/"
        return request.build_absolute_uri(path) if request else path

    def get_total_itens_organograma(self, instance) -> int:
        annotated = getattr(instance, "total_itens_organograma", None)
        if annotated is not None:
            return annotated
        return instance.itens_organograma.count()

    def validate_arquivo(self, arquivo):
        nome = Path(arquivo.name).name
        if not nome or "\x00" in nome or "\r" in nome or "\n" in nome:
            raise serializers.ValidationError("Nome de arquivo inválido.")
        if Path(nome).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Formato não permitido. Envie um arquivo XLS, XLSX ou ODS."
            )

        max_bytes = getattr(
            settings,
            "CARGA_ORG_LOT_MAX_UPLOAD_BYTES",
            DEFAULT_MAX_UPLOAD_BYTES,
        )
        if arquivo.size > max_bytes:
            max_mb = max_bytes // (1024 * 1024)
            raise serializers.ValidationError(
                f"O arquivo ultrapassa o limite de {max_mb} MB."
            )
        return arquivo

    def validate(self, attrs):
        if self.instance is None and "arquivo" not in attrs:
            raise serializers.ValidationError(
                {"arquivo": "O arquivo da planilha é obrigatório."}
            )

        arquivo = attrs.get("arquivo")
        tipo_carga = attrs.get("idtipocarga") or getattr(
            self.instance, "idtipocarga", None
        )
        patriarca = attrs.get("idpatriarca") or getattr(
            self.instance, "idpatriarca", None
        )
        organograma_referencia = attrs.get("idimportacaoorganograma")
        if "idimportacaoorganograma" not in attrs and self.instance is not None:
            organograma_referencia = self.instance.idimportacaoorganograma

        if tipo_carga is not None and tipo_carga.pk in {4, 5}:
            if organograma_referencia is None:
                raise serializers.ValidationError(
                    {
                        "idimportacaoorganograma_id": (
                            "A importação de lotação deve indicar a versão do "
                            "organograma utilizada."
                        )
                    }
                )
            if organograma_referencia.idtipocarga_id != ORGANOGRAMA_TYPE_ID:
                raise serializers.ValidationError(
                    {
                        "idimportacaoorganograma_id": (
                            "A referência informada não é uma importação de "
                            "organograma."
                        )
                    }
                )
            if patriarca and organograma_referencia.idpatriarca_id != patriarca.pk:
                raise serializers.ValidationError(
                    {
                        "idimportacaoorganograma_id": (
                            "O organograma deve pertencer ao mesmo patriarca "
                            "da lotação."
                        )
                    }
                )
        elif organograma_referencia is not None:
            raise serializers.ValidationError(
                {
                    "idimportacaoorganograma_id": (
                        "Somente importações de lotação podem referenciar um "
                        "organograma."
                    )
                }
            )

        if (
            arquivo is not None
            and tipo_carga is not None
            and tipo_carga.pk == ORGANOGRAMA_TYPE_ID
            and patriarca is not None
        ):
            conteudo = arquivo.read()
            arquivo.seek(0)
            relatorio = validate_organogram_spreadsheet(
                conteudo,
                Path(arquivo.name).suffix,
                patriarca.strsiglapatriarca,
                attrs.get("aba", ""),
            )
            if relatorio.requires_sheet_selection:
                raise OrganogramSheetSelectionRequired(relatorio.as_dict())
            if not relatorio.valid:
                raise SpreadsheetImportValidationError(relatorio.as_dict())
            self._organogram_report = relatorio
        return attrs

    @staticmethod
    def _apply_file(validated_data, arquivo):
        conteudo = arquivo.read()
        validated_data.update(
            strnomearquivo=Path(arquivo.name).name,
            strtipomime=arquivo.content_type or "application/octet-stream",
            inttamanhoarquivo=len(conteudo),
            strhasharquivo=hashlib.sha256(conteudo).hexdigest(),
            binconteudo=conteudo,
        )

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("aba", None)
        arquivo = validated_data.pop("arquivo")
        self._apply_file(validated_data, arquivo)
        relatorio = getattr(self, "_organogram_report", None)
        if relatorio is not None:
            validated_data["strabaimportada"] = relatorio.selected_sheet
        if "idstatusprogresso" not in validated_data:
            validated_data["idstatusprogresso"] = StatusProgresso.objects.get(pk=1)
        instance = super().create(validated_data)
        if relatorio is not None:
            self._create_organogram_items(instance, relatorio.items, validated_data)
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("aba", None)
        arquivo = validated_data.pop("arquivo", None)
        if arquivo is not None:
            self._apply_file(validated_data, arquivo)
        relatorio = getattr(self, "_organogram_report", None)
        if relatorio is not None:
            validated_data["strabaimportada"] = relatorio.selected_sheet
        instance = super().update(instance, validated_data)
        if arquivo is not None:
            instance.itens_organograma.all().delete()
            if relatorio is not None:
                self._create_organogram_items(instance, relatorio.items, validated_data)
        return instance

    @staticmethod
    def _create_organogram_items(importacao, rows, audit_data):
        audit_fields = {
            key: audit_data.get(key)
            for key in (
                "created_by_id",
                "created_by_name",
                "updated_by_id",
                "updated_by_name",
            )
        }
        items = [
            ItemOrganograma(
                idimportacaoplanilha=importacao,
                strnome=row.name,
                strsigla=row.acronym,
                strnumero=row.number,
                strreferenciapai=row.parent,
                strabaorigem=importacao.strabaimportada,
                intlinhaorigem=row.line,
                **audit_fields,
            )
            for row in rows
        ]
        ItemOrganograma.objects.bulk_create(items)
        by_acronym = {item.strsigla: item for item in items}
        changed = []
        for item, row in zip(items, rows, strict=True):
            if row.resolved_parent:
                item.idpai = by_acronym[row.resolved_parent]
                changed.append(item)
        if changed:
            ItemOrganograma.objects.bulk_update(changed, ["idpai"])


class ItemOrganogramaSerializer(AuditableModelSerializer):
    idimportacaoplanilha_id = serializers.PrimaryKeyRelatedField(
        source="idimportacaoplanilha",
        queryset=ImportacaoPlanilha.objects.filter(idtipocarga_id=ORGANOGRAMA_TYPE_ID),
    )
    idpai_id = serializers.PrimaryKeyRelatedField(
        source="idpai",
        queryset=ItemOrganograma.objects.all(),
        required=False,
        allow_null=True,
    )
    pai_sigla = serializers.CharField(source="idpai.strsigla", read_only=True)

    class Meta(AuditableModelSerializer.Meta):
        model = ItemOrganograma
        fields = AuditableModelSerializer.Meta.fields + [
            "iditemorganograma",
            "idimportacaoplanilha_id",
            "idpai_id",
            "pai_sigla",
            "strnome",
            "strsigla",
            "strnumero",
            "strreferenciapai",
            "strabaorigem",
            "intlinhaorigem",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "iditemorganograma",
            "pai_sigla",
        ]

    def validate_strnome(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("O nome é obrigatório.")
        return value

    def validate_strsigla(self, value):
        value = value.strip().upper()
        if not value or " " in value:
            raise serializers.ValidationError(
                "Informe uma sigla sem espaços."
            )
        return value

    def validate(self, attrs):
        importacao = attrs.get("idimportacaoplanilha") or getattr(
            self.instance, "idimportacaoplanilha", None
        )
        pai = attrs.get("idpai")
        if "idpai" not in attrs and self.instance is not None:
            pai = self.instance.idpai
        if pai is not None and importacao is not None:
            if pai.idimportacaoplanilha_id != importacao.pk:
                raise serializers.ValidationError(
                    {"idpai_id": "O pai deve pertencer à mesma importação."}
                )
            if self.instance is not None and pai.pk == self.instance.pk:
                raise serializers.ValidationError(
                    {"idpai_id": "Uma unidade não pode ser pai de si mesma."}
                )
            ancestor = pai
            visited = set()
            while ancestor is not None and ancestor.pk not in visited:
                if self.instance is not None and ancestor.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        {"idpai_id": "A relação informada cria um ciclo hierárquico."}
                    )
                visited.add(ancestor.pk)
                ancestor = ancestor.idpai
        return attrs


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
