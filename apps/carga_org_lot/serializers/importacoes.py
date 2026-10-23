"""Serializers do upload, validação e incorporação de planilhas."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..exceptions import (
    OrganogramSheetSelectionRequired,
    SpreadsheetImportValidationError,
)
from ..models import (
    AcaoResolucaoValidacao,
    AlternativaResolucaoValidacao,
    CasoValidacaoImportacao,
    ConjuntoLotacao,
    ImportacaoPlanilha,
    ItemLotacao,
    ItemLotacaoImportado,
    ItemOrganograma,
    OcorrenciaValidacaoImportacao,
    Patriarca,
    ProcessoCargaInicial,
    RelatorioValidacaoImportacao,
    ResultadoRelatorioValidacao,
    SeveridadeOcorrenciaValidacao,
    SituacaoConjuntoLotacao,
    StatusImportacaoLocal,
    StatusItemLotacaoImportado,
    StatusProgresso,
    TipoCarga,
    TipoOperacaoImportacaoLotacao,
)
from ..services.lotacao import (
    LOTACAO_TYPE_IDS,
    LotacaoValidationReport,
    RULES_VERSION as LOTACAO_RULES_VERSION,
    validate_lotation_spreadsheet,
)
from ..services.cargos import analyze_imported_positions
from ..services.lotacao_sets import (
    create_lotation_set,
    ensure_set_accepts_import,
    register_set_import,
    validate_set_organogram,
)
from ..services.organograma import (
    ORGANOGRAMA_TYPE_ID,
    OrganogramaValidationReport,
    validate_organogram_spreadsheet,
)
from ..services.workflow import (
    AuditActor,
    get_or_create_active_process,
    register_lotation_import,
    register_organogram_import,
)
from .catalogs import StatusProgressoSerializer, TipoCargaSerializer
from .workflow import PatriarcaSerializer, ProcessoCargaInicialSerializer

DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xls", ".xlsx", ".ods"}


class OcorrenciaValidacaoImportacaoSerializer(AuditableModelSerializer):
    severidade_nome = serializers.CharField(
        source="get_strseveridade_display",
        read_only=True,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = OcorrenciaValidacaoImportacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idocorrenciavalidacao",
            "strseveridade",
            "severidade_nome",
            "strcodigo",
            "straba",
            "intlinha",
            "strcampo",
            "strvalororiginal",
            "strvalornormalizado",
            "strmensagem",
            "strregraaplicada",
            "jsonsugestoes",
        ]
        read_only_fields = fields


class RelatorioValidacaoImportacaoSerializer(AuditableModelSerializer):
    resultado_nome = serializers.CharField(
        source="get_strresultado_display",
        read_only=True,
    )
    ocorrencias = OcorrenciaValidacaoImportacaoSerializer(many=True, read_only=True)
    casos = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = RelatorioValidacaoImportacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idrelatoriovalidacao",
            "strresultado",
            "resultado_nome",
            "flgleituracompleta",
            "inttotalabas",
            "inttotallinhas",
            "inttotalvalidas",
            "inttotalerros",
            "inttotalavisos",
            "inttotalnormalizacoes",
            "strversaoregras",
            "jsonresumo",
            "datprocessamento",
            "ocorrencias",
            "casos",
        ]
        read_only_fields = fields

    def get_casos(self, instance) -> list[dict]:
        from .lotacao import CasoValidacaoImportacaoSerializer

        return CasoValidacaoImportacaoSerializer(
            instance.casos.all(),
            many=True,
            context=self.context,
        ).data


class RelatorioValidacaoImportacaoResumoSerializer(AuditableModelSerializer):
    """Resumo leve usado em listagens de importações."""

    strresultado = serializers.CharField(read_only=True)
    resultado_nome = serializers.CharField(
        source="get_strresultado_display",
        read_only=True,
    )

    class Meta(AuditableModelSerializer.Meta):
        model = RelatorioValidacaoImportacao
        fields = AuditableModelSerializer.Meta.fields + [
            "idrelatoriovalidacao",
            "strresultado",
            "resultado_nome",
            "flgleituracompleta",
            "inttotalabas",
            "inttotallinhas",
            "inttotalvalidas",
            "inttotalerros",
            "inttotalavisos",
            "inttotalnormalizacoes",
            "strversaoregras",
            "datprocessamento",
        ]
        read_only_fields = fields


class PatriarcaImportacaoResumoSerializer(AuditableModelSerializer):
    """Identifica o patriarca sem expandir seu processo e histórico."""

    status = StatusProgressoSerializer(source="idstatusprogresso", read_only=True)
    organograma_download_url = serializers.SerializerMethodField()

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
        read_only_fields = fields

    def get_organograma_download_url(self, instance) -> str:
        request = self.context.get("request")
        path = f"/api/carga-org-lot/patriarcas/{instance.pk}/organograma/download/"
        return request.build_absolute_uri(path) if request else path


class ProcessoCargaInicialResumoSerializer(AuditableModelSerializer):
    """Situação atual do processo sem expandir todo o histórico."""

    strfaseatual = serializers.CharField(read_only=True)
    strstatusorganograma = serializers.CharField(read_only=True)
    strstatuslotacao = serializers.CharField(read_only=True)
    fase_nome = serializers.CharField(source="get_strfaseatual_display")
    status_organograma_nome = serializers.CharField(
        source="get_strstatusorganograma_display"
    )
    status_lotacao_nome = serializers.CharField(
        source="get_strstatuslotacao_display"
    )

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
        ]
        read_only_fields = fields


class CriarOrganogramaInicialSerializer(serializers.Serializer):
    idpatriarca_id = serializers.PrimaryKeyRelatedField(
        source="idpatriarca",
        queryset=Patriarca.objects.all(),
    )
    strreferencia = serializers.CharField(
        required=False,
        allow_blank=True,
        default="Organograma inicial gerado pelo sistema.",
    )


class ImportacaoPlanilhaSerializer(AuditableModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._organogram_report: OrganogramaValidationReport | None = None
        self._lotation_report: LotacaoValidationReport | None = None

    arquivo = serializers.FileField(write_only=True, required=False)
    aba = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=255,
    )
    criar_unidades_espelho = serializers.BooleanField(
        source="flgcriarunidadesespelho",
        write_only=True,
        required=False,
        default=False,
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
    idconjuntolotacao_id = serializers.PrimaryKeyRelatedField(
        source="idconjuntolotacao",
        queryset=ConjuntoLotacao.objects.all(),
        required=False,
        allow_null=True,
    )
    strtipooperacaolotacao = serializers.ChoiceField(
        choices=TipoOperacaoImportacaoLotacao.choices,
        read_only=True,
    )
    idstatusprogresso_id = serializers.PrimaryKeyRelatedField(
        source="idstatusprogresso",
        queryset=StatusProgresso.objects.all(),
        required=False,
    )
    patriarca = PatriarcaSerializer(source="idpatriarca", read_only=True)
    tipo_carga = TipoCargaSerializer(source="idtipocarga", read_only=True)
    status = StatusProgressoSerializer(source="idstatusprogresso", read_only=True)
    processo = ProcessoCargaInicialSerializer(
        source="idprocessocargainicial",
        read_only=True,
    )
    status_importacao_nome = serializers.CharField(
        source="get_strstatusimportacao_display",
        read_only=True,
    )
    relatorio_validacao = RelatorioValidacaoImportacaoSerializer(read_only=True)
    download_url = serializers.SerializerMethodField()
    organograma_atualizado_download_url = serializers.SerializerMethodField()
    total_itens_organograma = serializers.SerializerMethodField()
    total_itens_lotacao = serializers.SerializerMethodField()
    total_itens_lotacao_importados = serializers.SerializerMethodField()
    total_casos_pendentes = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = ImportacaoPlanilha
        fields = AuditableModelSerializer.Meta.fields + [
            "idimportacaoplanilha",
            "idpatriarca_id",
            "patriarca",
            "idtipocarga_id",
            "tipo_carga",
            "processo",
            "idimportacaoorganograma_id",
            "idconjuntolotacao_id",
            "strtipooperacaolotacao",
            "idstatusprogresso_id",
            "status",
            "arquivo",
            "aba",
            "criar_unidades_espelho",
            "flgcriarunidadesespelho",
            "strnomearquivo",
            "strtipomime",
            "inttamanhoarquivo",
            "strhasharquivo",
            "strabaimportada",
            "strreferencia",
            "strstatusimportacao",
            "status_importacao_nome",
            "flgpossuialteracoes",
            "datprimeiraalteracao",
            "datultimaalteracao",
            "datimportacao",
            "download_url",
            "organograma_atualizado_download_url",
            "total_itens_organograma",
            "total_itens_lotacao",
            "total_itens_lotacao_importados",
            "total_casos_pendentes",
            "relatorio_validacao",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "idimportacaoplanilha",
            "patriarca",
            "tipo_carga",
            "processo",
            "status",
            "strnomearquivo",
            "strtipomime",
            "inttamanhoarquivo",
            "strhasharquivo",
            "strabaimportada",
            "flgcriarunidadesespelho",
            "strstatusimportacao",
            "status_importacao_nome",
            "flgpossuialteracoes",
            "datprimeiraalteracao",
            "datultimaalteracao",
            "datimportacao",
            "download_url",
            "organograma_atualizado_download_url",
            "total_itens_organograma",
            "total_itens_lotacao",
            "total_itens_lotacao_importados",
            "total_casos_pendentes",
            "relatorio_validacao",
        ]

    def get_download_url(self, instance) -> str:
        request = self.context.get("request")
        path = f"/api/carga-org-lot/importacoes/{instance.pk}/download/"
        return request.build_absolute_uri(path) if request else path

    def get_organograma_atualizado_download_url(self, instance) -> str | None:
        if not instance.flgpossuialteracoes:
            return None
        request = self.context.get("request")
        path = (
            f"/api/carga-org-lot/importacoes/{instance.pk}/"
            "organograma-atualizado/download/"
        )
        return request.build_absolute_uri(path) if request else path

    def get_total_itens_organograma(self, instance) -> int:
        annotated = getattr(instance, "total_itens_organograma", None)
        if annotated is not None:
            return annotated
        return instance.itens_organograma.count()

    def get_total_itens_lotacao(self, instance) -> int:
        annotated = getattr(instance, "total_itens_lotacao", None)
        if annotated is not None:
            return annotated
        return instance.itens_lotacao.count()

    def get_total_itens_lotacao_importados(self, instance) -> int:
        annotated = getattr(instance, "total_itens_lotacao_importados", None)
        if annotated is not None:
            return annotated
        return instance.itens_lotacao_importados.count()

    def get_total_casos_pendentes(self, instance) -> int:
        annotated = getattr(instance, "total_casos_pendentes", None)
        if annotated is not None:
            return annotated
        report = getattr(instance, "relatorio_validacao", None)
        if report is None:
            return 0
        return report.casos.filter(strstatus="PENDENTE").count()

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
        if self.instance is not None and "arquivo" in attrs:
            raise serializers.ValidationError(
                {
                    "arquivo": (
                        "O arquivo original é imutável. Faça uma nova importação "
                        "para enviar outra planilha."
                    )
                }
            )
        if self.instance is not None and "flgcriarunidadesespelho" in attrs:
            raise serializers.ValidationError(
                {
                    "criar_unidades_espelho": (
                        "Esta opção pertence ao processamento inicial. Faça "
                        "uma nova importação para alterá-la."
                    )
                }
            )

        arquivo = attrs.get("arquivo")
        tipo_carga = attrs.get("idtipocarga") or getattr(
            self.instance, "idtipocarga", None
        )
        patriarca = attrs.get("idpatriarca") or getattr(
            self.instance, "idpatriarca", None
        )
        criar_unidades_espelho = attrs.get("flgcriarunidadesespelho", False)
        if (
            criar_unidades_espelho
            and tipo_carga is not None
            and tipo_carga.pk != ORGANOGRAMA_TYPE_ID
        ):
            raise serializers.ValidationError(
                {
                    "criar_unidades_espelho": (
                        "Esta opção está disponível somente para importações "
                        "de organograma."
                    )
                }
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
            if (
                organograma_referencia.strstatusimportacao
                == StatusImportacaoLocal.REJEITADA
            ):
                raise serializers.ValidationError(
                    {
                        "idimportacaoorganograma_id": (
                            "Uma importação rejeitada não pode ser usada como "
                            "referência da lotação."
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
            conjunto = attrs.get("idconjuntolotacao")
            if conjunto is not None:
                ensure_set_accepts_import(conjunto)
                validate_set_organogram(patriarca, organograma_referencia)
                if conjunto.idpatriarca_id != patriarca.pk:
                    raise serializers.ValidationError(
                        {
                            "idconjuntolotacao_id": (
                                "O conjunto pertence a outro patriarca."
                            )
                        }
                    )
                if (
                    conjunto.idimportacaoorganograma_id
                    != organograma_referencia.pk
                ):
                    raise serializers.ValidationError(
                        {
                            "idconjuntolotacao_id": (
                                "O conjunto utiliza outro organograma de referência."
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
        elif attrs.get("idconjuntolotacao") is not None:
            raise serializers.ValidationError(
                {
                    "idconjuntolotacao_id": (
                        "Somente importações de lotação pertencem a conjuntos."
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
                criar_unidades_espelho=attrs.get(
                    "flgcriarunidadesespelho",
                    False,
                ),
            )
            if relatorio.requires_sheet_selection:
                raise OrganogramSheetSelectionRequired(relatorio.as_dict())
            if not relatorio.valid:
                if self.instance is not None:
                    raise SpreadsheetImportValidationError(relatorio.as_dict())
            self._organogram_report = relatorio
        elif (
            arquivo is not None
            and tipo_carga is not None
            and tipo_carga.pk in LOTACAO_TYPE_IDS
            and organograma_referencia is not None
        ):
            conteudo = arquivo.read()
            arquivo.seek(0)
            self._lotation_report = validate_lotation_spreadsheet(
                conteudo,
                Path(arquivo.name).suffix,
                organograma_referencia.itens_organograma.select_related("idpai"),
            )
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
        relatorio = self._organogram_report
        relatorio_lotacao = self._lotation_report
        if relatorio is not None:
            validated_data["strabaimportada"] = relatorio.selected_sheet
            if relatorio.valid and relatorio.total_unidades_espelho_criadas:
                now = timezone.now()
                validated_data.update(
                    strstatusimportacao=StatusImportacaoLocal.ALTERADA,
                    flgpossuialteracoes=True,
                    datprimeiraalteracao=now,
                    datultimaalteracao=now,
                )
            else:
                validated_data["strstatusimportacao"] = (
                    StatusImportacaoLocal.INCORPORADA
                    if relatorio.valid
                    else StatusImportacaoLocal.REJEITADA
                )
        elif relatorio_lotacao is not None:
            validated_data["strabaimportada"] = self._lotation_sheet_summary(
                relatorio_lotacao.processed_sheets
            )
            if not relatorio_lotacao.leitura_completa:
                validated_data["strstatusimportacao"] = (
                    StatusImportacaoLocal.REJEITADA
                )
            elif relatorio_lotacao.errors or relatorio_lotacao.warnings:
                validated_data["strstatusimportacao"] = (
                    StatusImportacaoLocal.AGUARDANDO_REVISAO
                )
            else:
                validated_data["strstatusimportacao"] = (
                    StatusImportacaoLocal.INCORPORADA
                )
        if "idstatusprogresso" not in validated_data:
            validated_data["idstatusprogresso"] = StatusProgresso.objects.get(pk=1)
        actor = AuditActor.from_validated_data(validated_data)
        conjunto = validated_data.get("idconjuntolotacao")
        if relatorio_lotacao is not None:
            if conjunto is None:
                conjunto = create_lotation_set(
                    patriarca=validated_data["idpatriarca"],
                    organograma=validated_data["idimportacaoorganograma"],
                    reference=validated_data.get("strreferencia", ""),
                    actor=actor,
                )
                validated_data["idconjuntolotacao"] = conjunto
                has_active_set = ConjuntoLotacao.objects.filter(
                    idimportacaoorganograma=validated_data[
                        "idimportacaoorganograma"
                    ],
                    strsituacao=SituacaoConjuntoLotacao.ATIVO,
                ).exclude(pk=conjunto.pk).exists()
                validated_data["strtipooperacaolotacao"] = (
                    TipoOperacaoImportacaoLotacao.SUBSTITUICAO
                    if has_active_set
                    else TipoOperacaoImportacaoLotacao.INICIAL
                )
            else:
                ensure_set_accepts_import(conjunto)
                has_active_set = ConjuntoLotacao.objects.filter(
                    idimportacaoorganograma=validated_data[
                        "idimportacaoorganograma"
                    ],
                    strsituacao=SituacaoConjuntoLotacao.ATIVO,
                ).exclude(pk=conjunto.pk).exists()
                validated_data["strtipooperacaolotacao"] = (
                    TipoOperacaoImportacaoLotacao.ACRESCIMO
                    if conjunto.importacoes.exists()
                    else (
                        TipoOperacaoImportacaoLotacao.SUBSTITUICAO
                        if has_active_set
                        else TipoOperacaoImportacaoLotacao.INICIAL
                    )
                )
        process = get_or_create_active_process(validated_data["idpatriarca"], actor)
        validated_data["idprocessocargainicial"] = process
        instance = super().create(validated_data)
        if relatorio is not None:
            self._create_validation_report(instance, relatorio, validated_data)
            if relatorio.valid:
                self._create_organogram_items(instance, relatorio.items, validated_data)
            instance.idprocessocargainicial = register_organogram_import(
                process,
                valid=relatorio.valid,
                actor=actor,
                message=(
                    (
                        "Planilha de organograma validada e incorporada com "
                        f"{relatorio.total_unidades_espelho_criadas} unidade(s) "
                        "gerada(s) automaticamente."
                    )
                    if relatorio.valid and relatorio.total_unidades_espelho_criadas
                    else (
                        "Planilha de organograma validada e incorporada."
                        if relatorio.valid
                        else "Planilha de organograma rejeitada pela validação."
                    )
                ),
            )
        elif relatorio_lotacao is not None:
            staged_items = self._create_lotation_staging_items(
                instance,
                relatorio_lotacao,
                validated_data,
            )
            instance.strstatusimportacao = StatusImportacaoLocal.ANALISANDO_CARGOS
            instance.save(update_fields=["strstatusimportacao", "updated_at"])
            analyze_imported_positions(
                instance,
                relatorio_lotacao,
                staged_items,
                validated_data,
            )
            cargo_issues = [
                issue
                for issue in relatorio_lotacao.issues
                if issue.codigo == "cargo_correspondencia_sugerida"
            ]
            other_pending = [
                issue
                for issue in relatorio_lotacao.errors + relatorio_lotacao.warnings
                if issue.codigo != "cargo_correspondencia_sugerida"
            ]
            if other_pending:
                instance.strstatusimportacao = StatusImportacaoLocal.AGUARDANDO_REVISAO
            elif cargo_issues:
                instance.strstatusimportacao = (
                    StatusImportacaoLocal.AGUARDANDO_REVISAO_CARGOS
                )
            else:
                instance.strstatusimportacao = StatusImportacaoLocal.INCORPORADA
            instance.save(update_fields=["strstatusimportacao", "updated_at"])
            self._create_lotation_validation_report(
                instance,
                relatorio_lotacao,
                validated_data,
                staged_items,
            )
            incorporated = not (
                relatorio_lotacao.errors or relatorio_lotacao.warnings
            ) and relatorio_lotacao.leitura_completa
            if incorporated:
                self._create_lotation_items_from_staging(
                    instance,
                    staged_items,
                    validated_data,
                )
            instance.idprocessocargainicial = register_lotation_import(
                process,
                valid=incorporated,
                actor=actor,
                pending_review=(
                    instance.strstatusimportacao
                    in {
                        StatusImportacaoLocal.AGUARDANDO_REVISAO,
                        StatusImportacaoLocal.AGUARDANDO_REVISAO_CARGOS,
                    }
                ),
            )
            register_set_import(conjunto, instance, actor=actor)
        return instance

    @staticmethod
    def _lotation_sheet_summary(sheet_names: list[str]) -> str:
        summary = ", ".join(sheet_names)
        if len(summary) <= 255:
            return summary
        return f"{len(sheet_names)} abas processadas"[:255]

    @staticmethod
    def _create_lotation_staging_items(importacao, report, audit_data):
        audit_fields = {
            key: audit_data.get(key)
            for key in (
                "created_by_id",
                "created_by_name",
                "updated_by_id",
                "updated_by_name",
            )
        }
        issues_by_location = {}
        for issue in report.issues:
            if issue.aba and issue.linha and issue.severidade in {"ERRO", "AVISO"}:
                issues_by_location.setdefault((issue.aba, issue.linha), []).append(
                    issue.severidade
                )
        staged = ItemLotacaoImportado.objects.bulk_create(
            [
                ItemLotacaoImportado(
                    idimportacaoplanilha=importacao,
                    idorgaoorganograma_id=row.organ_id,
                    idunidadeorganograma_id=row.unit_id,
                    strsiglaorgaooriginal=row.original_organ_acronym,
                    strsiglaorgao=row.organ_acronym,
                    strnomeorgao=row.organ_name,
                    strnomeservidor=row.person_name,
                    strcpforiginal=row.original_cpf,
                    strcpf=row.cpf,
                    strcargooriginal=row.original_position,
                    strcargonormalizado=row.normalized_position,
                    strsiglaunidadeoriginal=row.original_unit_acronym,
                    strsiglaunidade=row.unit_acronym,
                    strnomeunidade=row.unit_name,
                    strabaorigem=row.sheet,
                    intlinhaorigem=row.line,
                    strsituacao=(
                        StatusItemLotacaoImportado.COM_ERROS
                        if "ERRO" in issues_by_location.get((row.sheet, row.line), [])
                        else (
                            StatusItemLotacaoImportado.COM_AVISOS
                            if "AVISO"
                            in issues_by_location.get((row.sheet, row.line), [])
                            else StatusItemLotacaoImportado.ACEITO
                        )
                    ),
                    **audit_fields,
                )
                for row in report.items
            ]
        )
        return {(item.strabaorigem, item.intlinhaorigem): item for item in staged}

    @staticmethod
    def _create_lotation_items_from_staging(importacao, staged_items, audit_data):
        audit_fields = {
            key: audit_data.get(key)
            for key in (
                "created_by_id",
                "created_by_name",
                "updated_by_id",
                "updated_by_name",
            )
        }
        source_items = list(staged_items.values())
        ItemLotacao.objects.bulk_create(
            [
                ItemLotacao(
                    iditemlotacaoimportado=item,
                    idimportacaoplanilha=importacao,
                    idorgaoorganograma=item.idorgaoorganograma,
                    idunidadeorganograma=item.idunidadeorganograma,
                    idcargoreferencia=item.idcargoreferencia,
                    strsiglaorgao=item.strsiglaorgao,
                    strnomeorgao=item.strnomeorgao,
                    strnomeservidor=item.strnomeservidor,
                    strcpf=item.strcpf,
                    strcargooriginal=item.strcargooriginal,
                    strcargonormalizado=item.strcargonormalizado,
                    strsiglaunidade=item.strsiglaunidade,
                    strnomeunidade=item.strnomeunidade,
                    strabaorigem=item.strabaorigem,
                    intlinhaorigem=item.intlinhaorigem,
                    **audit_fields,
                )
                for item in source_items
            ]
        )
        ItemLotacaoImportado.objects.filter(
            pk__in=[item.pk for item in source_items]
        ).update(strsituacao=StatusItemLotacaoImportado.INCORPORADO)

    @staticmethod
    def _create_lotation_validation_report(
        importacao,
        report,
        audit_data,
        staged_items,
    ):
        audit_fields = {
            key: audit_data.get(key)
            for key in (
                "created_by_id",
                "created_by_name",
                "updated_by_id",
                "updated_by_name",
            )
        }
        persisted_report = RelatorioValidacaoImportacao.objects.create(
            idimportacaoplanilha=importacao,
            strresultado=(
                ResultadoRelatorioValidacao.INVALIDO
                if report.errors
                else (
                    ResultadoRelatorioValidacao.COM_AVISOS
                    if report.warnings
                    else ResultadoRelatorioValidacao.VALIDO
                )
            ),
            flgleituracompleta=report.leitura_completa,
            inttotalabas=report.total_abas_lidas,
            inttotallinhas=report.total_linhas_lidas,
            inttotalvalidas=report.total_linhas_validas,
            inttotalerros=len(report.errors),
            inttotalavisos=len(report.warnings),
            inttotalnormalizacoes=len(report.normalizations),
            strversaoregras=LOTACAO_RULES_VERSION,
            jsonresumo=report.as_dict(),
            **audit_fields,
        )
        occurrences = OcorrenciaValidacaoImportacao.objects.bulk_create(
            [
                OcorrenciaValidacaoImportacao(
                    idrelatoriovalidacao=persisted_report,
                    strseveridade=issue.severidade,
                    strcodigo=issue.codigo,
                    straba=issue.aba or "",
                    intlinha=issue.linha,
                    strcampo=issue.campo or "",
                    strvalororiginal=issue.valor_original,
                    strvalornormalizado=issue.valor_normalizado,
                    strmensagem=issue.mensagem,
                    strregraaplicada=issue.regra_aplicada,
                    jsonsugestoes=list(issue.sugestoes),
                    **audit_fields,
                )
                for issue in report.issues
            ]
        )
        cases = {}
        for issue, occurrence in zip(report.issues, occurrences, strict=True):
            if issue.severidade not in {"ERRO", "AVISO"}:
                continue
            staged = staged_items.get((issue.aba, issue.linha))
            if issue.codigo == "cpf_duplicado_planilha":
                organ_key = (
                    staged.idorgaoorganograma_id
                    if staged and staged.idorgaoorganograma_id
                    else f"sigla-{staged.strsiglaorgao if staged else ''}"
                )
                unit_key = (
                    staged.idunidadeorganograma_id
                    if staged and staged.idunidadeorganograma_id
                    else f"sigla-{staged.strsiglaunidade if staged else ''}"
                )
                grouping_key = (
                    f"cpf_duplicado:{issue.valor_original}:"
                    f"{organ_key}:{unit_key}"
                )
            elif issue.codigo == "cargo_correspondencia_sugerida":
                grouping_key = f"cargo:{issue.valor_normalizado}"
            else:
                grouping_key = (
                    f"{issue.codigo}:{issue.aba or ''}:{issue.linha or 0}"
                )
            case = cases.get(grouping_key)
            if case is None:
                case = CasoValidacaoImportacao.objects.create(
                    idrelatoriovalidacao=persisted_report,
                    strchaveagrupamento=grouping_key,
                    strcodigo=issue.codigo,
                    strseveridade=issue.severidade,
                    strtitulo=issue.codigo.replace("_", " ").capitalize(),
                    strmensagem=issue.mensagem,
                    **audit_fields,
                )
                cases[grouping_key] = case
                ImportacaoPlanilhaSerializer._create_case_alternatives(
                    case,
                    issue,
                    audit_fields,
                )
            case.ocorrencias.add(occurrence)
            if staged is not None:
                case.itens.add(staged)
        return persisted_report

    @staticmethod
    def _create_case_alternatives(case, issue, audit_fields):
        alternatives = []
        if issue.severidade == "AVISO":
            alternatives.append(
                AlternativaResolucaoValidacao(
                    idcasovalidacao=case,
                    stracao=AcaoResolucaoValidacao.ACEITAR_COMO_INFORMADO,
                    strdescricao="Confirmar que os dados informados estão corretos.",
                    jsonpayload={},
                    **audit_fields,
                )
            )
        for suggestion in issue.sugestoes:
            alternatives.append(
                AlternativaResolucaoValidacao(
                    idcasovalidacao=case,
                    idcargoreferencia_id=suggestion.get("cargo_referencia_id"),
                    stracao=AcaoResolucaoValidacao.APLICAR_SUGESTAO,
                    strdescricao=suggestion["descricao"],
                    jsonpayload=suggestion.get("alteracoes", {}),
                    decconfianca=suggestion.get("confianca"),
                    flgrecomendada=True,
                    **audit_fields,
                )
            )
        alternatives.extend(
            [
                AlternativaResolucaoValidacao(
                    idcasovalidacao=case,
                    stracao=AcaoResolucaoValidacao.CORRIGIR_MANUALMENTE,
                    strdescricao="Corrigir manualmente os campos das linhas.",
                    jsonpayload={},
                    **audit_fields,
                ),
                AlternativaResolucaoValidacao(
                    idcasovalidacao=case,
                    stracao=AcaoResolucaoValidacao.DESCARTAR_LINHAS,
                    strdescricao="Descartar da importação as linhas relacionadas.",
                    jsonpayload={},
                    **audit_fields,
                ),
            ]
        )
        AlternativaResolucaoValidacao.objects.bulk_create(alternatives)

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("aba", None)
        arquivo = validated_data.pop("arquivo", None)
        if arquivo is not None:
            self._apply_file(validated_data, arquivo)
        relatorio = self._organogram_report
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
                strresponsavel=row.responsible,
                strcargo=row.position,
                flggeradoautomaticamente=row.generated_automatically,
                strnumero=row.number,
                strreferenciapai=row.parent,
                strabaorigem=(
                    "Gerada automaticamente"
                    if row.generated_automatically
                    else importacao.strabaimportada
                ),
                intlinhaorigem=(0 if row.generated_automatically else row.line),
                **audit_fields,
            )
            for row in rows
        ]
        ItemOrganograma.objects.bulk_create(items)
        by_line = {row.line: item for item, row in zip(items, rows, strict=True)}
        changed = []
        for item, row in zip(items, rows, strict=True):
            if row.resolved_parent_line is not None:
                item.idpai = by_line[row.resolved_parent_line]
                changed.append(item)
        if changed:
            ItemOrganograma.objects.bulk_update(changed, ["idpai"])

    @staticmethod
    def _create_validation_report(importacao, report, audit_data):
        audit_fields = {
            key: audit_data.get(key)
            for key in (
                "created_by_id",
                "created_by_name",
                "updated_by_id",
                "updated_by_name",
            )
        }
        persisted_report = RelatorioValidacaoImportacao.objects.create(
            idimportacaoplanilha=importacao,
            strresultado=(
                ResultadoRelatorioValidacao.VALIDO
                if report.valid
                else ResultadoRelatorioValidacao.INVALIDO
            ),
            flgleituracompleta=report.leitura_completa,
            inttotalabas=report.total_abas_lidas,
            inttotallinhas=report.total_linhas_lidas,
            inttotalvalidas=(report.total_linhas_lidas if report.valid else 0),
            inttotalerros=len(report.issues),
            jsonresumo=report.as_dict(),
            **audit_fields,
        )
        OcorrenciaValidacaoImportacao.objects.bulk_create(
            [
                OcorrenciaValidacaoImportacao(
                    idrelatoriovalidacao=persisted_report,
                    strseveridade=SeveridadeOcorrenciaValidacao.ERRO,
                    strcodigo=issue.codigo,
                    straba=issue.aba or "",
                    intlinha=issue.linha,
                    strcampo=issue.campo or "",
                    strmensagem=issue.mensagem,
                    **audit_fields,
                )
                for issue in report.issues
            ]
        )


class ImportacaoPlanilhaListSerializer(ImportacaoPlanilhaSerializer):
    """Contrato de listagem sem o relatório de validação expandido."""

    patriarca = PatriarcaImportacaoResumoSerializer(
        source="idpatriarca",
        read_only=True,
    )
    processo = ProcessoCargaInicialResumoSerializer(
        source="idprocessocargainicial",
        read_only=True,
    )
    relatorio_validacao = RelatorioValidacaoImportacaoResumoSerializer(
        read_only=True
    )
