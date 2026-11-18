"""Modelos da série histórica mensal dos relatórios quantitativos E-Docs."""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q

from common.models import ModeloAuditavel

from .edocs import AmbienteEdocs, PatriarcaEdocs


class SituacaoColetaMensalEdocs(models.TextChoices):
    SOLICITADA = "SOLICITADA", "Solicitada"
    EXECUTANDO = "EXECUTANDO", "Executando"
    SUCESSO = "SUCESSO", "Sucesso"
    ERRO = "ERRO", "Erro"


class CodigoFonteMensalEdocs(models.TextChoices):
    EDOC_01 = "EDOC-01", "Processos por patriarca"
    EDOC_02 = "EDOC-02", "Processos por organização"
    EDOC_03 = "EDOC-03", "Documentos por patriarca"
    EDOC_04 = "EDOC-04", "Documentos por organização"
    EDOC_05 = "EDOC-05", "Catálogo de patriarcas"


class TipoEventoColetaMensalEdocs(models.TextChoices):
    SOLICITADA = "SOLICITADA", "Coleta solicitada"
    EXECUCAO_INICIADA = "EXECUCAO_INICIADA", "Execução iniciada"
    SUCESSO = "SUCESSO", "Coleta concluída com sucesso"
    ERRO = "ERRO", "Coleta concluída com erro"
    REENCAMINHADA = "REENCAMINHADA", "Solicitação reencaminhada"


class CompetenciaEdocs(ModeloAuditavel):
    """Mês civil da série histórica, independente de qualquer publicação."""

    ano = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()

    class Meta:
        db_table = '"publicacoes"."competencia_edocs"'
        ordering = ("-ano", "-mes")
        constraints = [
            models.UniqueConstraint(
                fields=("ano", "mes"),
                name="edocs_competencia_unica",
            ),
            models.CheckConstraint(
                condition=Q(ano__gte=2000, ano__lte=9999),
                name="edocs_competencia_ano_valido",
            ),
            models.CheckConstraint(
                condition=Q(mes__gte=1, mes__lte=12),
                name="edocs_competencia_mes_valido",
            ),
        ]

    def __str__(self):
        return f"{self.mes:02d}/{self.ano}"


class ColetaMensalEdocs(ModeloAuditavel):
    """Uma revisão imutável da coleta de uma competência."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    competencia = models.ForeignKey(
        CompetenciaEdocs,
        on_delete=models.PROTECT,
        related_name="coletas",
    )
    revisao = models.PositiveIntegerField()
    ambiente = models.CharField(max_length=3, choices=AmbienteEdocs.choices)
    situacao = models.CharField(
        max_length=20,
        choices=SituacaoColetaMensalEdocs.choices,
        default=SituacaoColetaMensalEdocs.SOLICITADA,
    )
    iniciada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    quantidade_patriarcas = models.PositiveIntegerField(default=0)
    quantidade_organizacoes = models.PositiveIntegerField(default=0)
    quantidade_fontes_brutas = models.PositiveIntegerField(default=0)
    patriarcas_solicitados = models.JSONField(default=list, editable=False)
    hash_resultado = models.CharField(max_length=64, blank=True, editable=False)
    codigo_erro = models.CharField(max_length=80, blank=True)
    mensagem_erro = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = '"publicacoes"."coleta_mensal_edocs"'
        ordering = ("-criado_em",)
        constraints = [
            models.UniqueConstraint(
                fields=("competencia", "revisao"),
                name="edocs_coleta_revisao_unica",
            ),
            models.UniqueConstraint(
                fields=("competencia",),
                condition=Q(
                    situacao__in=(
                        SituacaoColetaMensalEdocs.SOLICITADA,
                        SituacaoColetaMensalEdocs.EXECUTANDO,
                    )
                ),
                name="edocs_uma_coleta_mensal_ativa",
            ),
        ]
        indexes = [
            models.Index(fields=("situacao", "criado_em")),
            models.Index(fields=("competencia", "-revisao")),
        ]
        permissions = [
            (
                "solicitar_coleta_mensal_edocs",
                "Pode solicitar uma coleta mensal do E-Docs",
            ),
        ]


class FonteBrutaColetaMensalEdocs(ModeloAuditavel):
    """Resposta JSON integral preservada como evidência da revisão."""

    coleta = models.ForeignKey(
        ColetaMensalEdocs,
        on_delete=models.PROTECT,
        related_name="fontes_brutas",
    )
    codigo_fonte = models.CharField(
        max_length=8,
        choices=CodigoFonteMensalEdocs.choices,
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fontes_brutas_mensais_edocs",
    )
    id_patriarca_externo = models.UUIDField(null=True, blank=True)
    conteudo = models.JSONField()
    hash_sha256 = models.CharField(max_length=64, editable=False)

    class Meta:
        db_table = '"publicacoes"."fonte_bruta_coleta_mensal_edocs"'
        ordering = ("codigo_fonte", "id_patriarca_externo")
        constraints = [
            models.UniqueConstraint(
                fields=("coleta", "codigo_fonte"),
                condition=Q(id_patriarca_externo__isnull=True),
                name="edocs_fonte_global_unica",
            ),
            models.UniqueConstraint(
                fields=("coleta", "codigo_fonte", "id_patriarca_externo"),
                condition=Q(id_patriarca_externo__isnull=False),
                name="edocs_fonte_patriarca_unica",
            ),
        ]


class ResultadoMensalPatriarcaEdocs(ModeloAuditavel):
    """Indicadores mensais consolidados no nível de patriarca."""

    coleta = models.ForeignKey(
        ColetaMensalEdocs,
        on_delete=models.PROTECT,
        related_name="resultados_patriarcas",
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.PROTECT,
        related_name="resultados_mensais_edocs",
    )
    id_patriarca_externo = models.UUIDField()
    sigla_patriarca = models.CharField(max_length=80, blank=True)
    nome_patriarca = models.CharField(max_length=300)
    codigo_municipio = models.PositiveIntegerField(null=True, blank=True)
    total_processos = models.PositiveBigIntegerField(null=True, blank=True)
    total_documentos = models.PositiveBigIntegerField(null=True, blank=True)
    total_paginas = models.PositiveBigIntegerField(null=True, blank=True)
    versao_calculo = models.CharField(
        max_length=40,
        default="PLANILHA_MUNICIPIOS_V1",
        editable=False,
    )
    economia_papel_kg = models.DecimalField(
        max_digits=24,
        decimal_places=5,
        default=Decimal("0"),
        editable=False,
    )
    gases_poluentes_kg = models.DecimalField(
        max_digits=24,
        decimal_places=4,
        default=Decimal("0"),
        editable=False,
    )
    economia_papel_reais = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        default=Decimal("0"),
        editable=False,
    )
    economia_insumos_reais = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        default=Decimal("0"),
        editable=False,
    )
    economia_impressao_reais = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        default=Decimal("0"),
        editable=False,
    )
    economia_total_reais = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        default=Decimal("0"),
        editable=False,
    )
    economia_agua_m3 = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        default=Decimal("0"),
        editable=False,
    )
    arvores_salvas = models.DecimalField(
        max_digits=24,
        decimal_places=4,
        default=Decimal("0"),
        editable=False,
    )

    class Meta:
        db_table = '"publicacoes"."resultado_mensal_patriarca_edocs"'
        ordering = ("nome_patriarca", "id_patriarca_externo")
        constraints = [
            models.UniqueConstraint(
                fields=("coleta", "id_patriarca_externo"),
                name="edocs_resultado_patriarca_unico",
            ),
        ]
        indexes = [models.Index(fields=("patriarca", "coleta"))]


class ResultadoMensalOrganizacaoEdocs(ModeloAuditavel):
    """Indicadores mensais consolidados no nível de organização."""

    coleta = models.ForeignKey(
        ColetaMensalEdocs,
        on_delete=models.PROTECT,
        related_name="resultados_organizacoes",
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.PROTECT,
        related_name="resultados_organizacoes_mensais_edocs",
    )
    id_patriarca_externo = models.UUIDField()
    nome_patriarca = models.CharField(max_length=300)
    id_organizacao_externo = models.UUIDField()
    nome_organizacao = models.CharField(max_length=300)
    total_processos = models.PositiveBigIntegerField(null=True, blank=True)
    total_documentos = models.PositiveBigIntegerField(null=True, blank=True)
    total_paginas = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        db_table = '"publicacoes"."resultado_mensal_organizacao_edocs"'
        ordering = ("nome_patriarca", "nome_organizacao")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "coleta",
                    "id_patriarca_externo",
                    "id_organizacao_externo",
                ),
                name="edocs_resultado_organizacao_unico",
            ),
        ]
        indexes = [models.Index(fields=("patriarca", "coleta"))]


class EventoAuditoriaColetaMensalEdocs(ModeloAuditavel):
    """Trilha append-only da solicitação e execução de cada revisão."""

    coleta = models.ForeignKey(
        ColetaMensalEdocs,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    tipo_evento = models.CharField(
        max_length=20,
        choices=TipoEventoColetaMensalEdocs.choices,
    )
    mensagem = models.CharField(max_length=500)
    metadados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"publicacoes"."evento_auditoria_coleta_mensal_edocs"'
        ordering = ("-criado_em", "-id")
        indexes = [models.Index(fields=("tipo_evento", "criado_em"))]
