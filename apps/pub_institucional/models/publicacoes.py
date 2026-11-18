"""Agregado editorial versionado de Publicações Institucionais."""

import uuid

from django.db import models
from django.db.models import Q

from common.models import ModeloAuditavel


class FonteVisaoPublicacao(models.TextChoices):
    EDOCS = "EDOCS", "E-Docs"
    EFLOW = "EFLOW", "E-Flow"


class EscopoVisaoPublicacao(models.TextChoices):
    TODOS = "TODOS", "Todos os patriarcas"
    MUNICIPIOS = "MUNICIPIOS", "Municípios"
    PERSONALIZADO = "PERSONALIZADO", "Seleção personalizada"


class SituacaoPublicacao(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_VALIDACAO = "EM_VALIDACAO", "Em validação"
    AGUARDANDO_PUBLICACAO = "AGUARDANDO_PUBLICACAO", "Aguardando publicação"
    PUBLICADA = "PUBLICADA", "Publicada"
    SUBSTITUIDA = "SUBSTITUIDA", "Substituída"
    CANCELADA = "CANCELADA", "Cancelada"
    REVOGADA = "REVOGADA", "Revogada"


class TipoEventoPublicacao(models.TextChoices):
    CRIADA = "CRIADA", "Criada"
    ALTERADA = "ALTERADA", "Alterada"
    RECALCULADA = "RECALCULADA", "Recalculada"
    VALIDADA = "VALIDADA", "Validada"
    PUBLICADA = "PUBLICADA", "Publicada"
    SUBSTITUICAO_INICIADA = "SUBSTITUICAO_INICIADA", "Substituição iniciada"
    SUBSTITUIDA = "SUBSTITUIDA", "Substituída"
    CANCELADA = "CANCELADA", "Cancelada"
    REVOGADA = "REVOGADA", "Revogada"


class ConfiguracaoVisaoPublicacao(ModeloAuditavel):
    """Filtro editorial reutilizável; a publicação congela uma cópia dele."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codigo = models.CharField(max_length=80, unique=True)
    nome = models.CharField(max_length=200)
    descricao = models.CharField(max_length=500, blank=True)
    fonte = models.CharField(max_length=10, choices=FonteVisaoPublicacao.choices)
    escopo = models.CharField(max_length=20, choices=EscopoVisaoPublicacao.choices)
    perfil_calculo_eflow = models.CharField(max_length=30, blank=True, default="")
    ativa = models.BooleanField(default=True)
    versao = models.PositiveIntegerField(default=1, editable=False)
    patriarcas = models.ManyToManyField(
        "pub_institucional.PatriarcaEdocs",
        through="PatriarcaVisaoPublicacao",
        related_name="visoes_publicacao",
    )

    class Meta:
        db_table = '"publicacoes"."configuracao_visao_publicacao"'
        ordering = ("nome", "codigo")
        permissions = [
            ("configurar_visao_publicacao", "Pode configurar visão de publicação"),
        ]


class PatriarcaVisaoPublicacao(ModeloAuditavel):
    configuracao = models.ForeignKey(
        ConfiguracaoVisaoPublicacao,
        on_delete=models.PROTECT,
        related_name="selecoes_patriarcas",
    )
    patriarca = models.ForeignKey(
        "pub_institucional.PatriarcaEdocs",
        on_delete=models.PROTECT,
        related_name="selecoes_visao_publicacao",
    )

    class Meta:
        db_table = '"publicacoes"."patriarca_visao_publicacao"'
        constraints = [
            models.UniqueConstraint(
                fields=("configuracao", "patriarca"),
                name="publicacao_patriarca_unico_por_visao",
            )
        ]


class Publicacao(ModeloAuditavel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    serie_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    versao = models.PositiveIntegerField(default=1, editable=False)
    titulo = models.CharField(max_length=250)
    ano_referencia = models.PositiveSmallIntegerField()
    mes_referencia = models.PositiveSmallIntegerField()
    situacao = models.CharField(
        max_length=30,
        choices=SituacaoPublicacao.choices,
        default=SituacaoPublicacao.RASCUNHO,
    )
    versao_registro = models.PositiveIntegerField(default=1, editable=False)
    publicacao_anterior = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="versoes_substitutas",
    )
    justificativa_publicacao = models.TextField(blank=True, default="")
    publicada_em = models.DateTimeField(null=True, blank=True)
    publicada_por_id = models.IntegerField(null=True, blank=True, editable=False)
    publicada_por_nome = models.CharField(
        max_length=200, blank=True, default="", editable=False
    )
    hash_conteudo = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        db_table = '"publicacoes"."publicacao"'
        ordering = ("-ano_referencia", "-mes_referencia", "-versao")
        constraints = [
            models.CheckConstraint(
                condition=Q(ano_referencia__gte=2024, ano_referencia__lte=9999),
                name="publicacao_ano_referencia_valido",
            ),
            models.CheckConstraint(
                condition=Q(mes_referencia__gte=1, mes_referencia__lte=12),
                name="publicacao_mes_referencia_valido",
            ),
            models.UniqueConstraint(
                fields=("serie_id", "versao"),
                name="publicacao_versao_unica_na_serie",
            ),
            models.UniqueConstraint(
                fields=("serie_id",),
                condition=Q(situacao=SituacaoPublicacao.PUBLICADA),
                name="publicacao_uma_vigente_por_serie",
            ),
        ]
        permissions = [
            ("calcular_publicacao", "Pode calcular publicação"),
            ("validar_publicacao", "Pode validar publicação"),
            ("visualizar_previa_publicacao", "Pode visualizar prévia"),
            ("publicar_publicacao", "Pode publicar"),
            ("substituir_publicacao", "Pode iniciar substituição"),
            ("revogar_publicacao", "Pode revogar publicação"),
        ]


class SecaoPublicacao(ModeloAuditavel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publicacao = models.ForeignKey(
        Publicacao,
        on_delete=models.PROTECT,
        related_name="secoes",
    )
    ordem = models.PositiveSmallIntegerField()
    titulo = models.CharField(max_length=200)
    fonte = models.CharField(max_length=10, choices=FonteVisaoPublicacao.choices)
    configuracao_visao = models.ForeignKey(
        ConfiguracaoVisaoPublicacao,
        on_delete=models.PROTECT,
        related_name="secoes_publicacao",
    )
    coleta_edocs = models.ForeignKey(
        "pub_institucional.ColetaMensalEdocs",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="secoes_publicacao",
    )
    coleta_eflow = models.ForeignKey(
        "pub_institucional.ColetaEflow",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="secoes_publicacao",
    )
    perfil_calculo = models.CharField(max_length=40, blank=True, default="")
    configuracao_congelada = models.JSONField(default=dict, editable=False)
    resultado = models.JSONField(default=dict, editable=False)
    calculada_em = models.DateTimeField(null=True, blank=True, editable=False)
    hash_resultado = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        db_table = '"publicacoes"."secao_publicacao"'
        ordering = ("ordem", "criado_em")
        constraints = [
            models.UniqueConstraint(
                fields=("publicacao", "ordem"),
                name="publicacao_ordem_secao_unica",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        fonte=FonteVisaoPublicacao.EDOCS,
                        coleta_edocs__isnull=False,
                        coleta_eflow__isnull=True,
                    )
                    | Q(
                        fonte=FonteVisaoPublicacao.EFLOW,
                        coleta_edocs__isnull=True,
                        coleta_eflow__isnull=False,
                    )
                ),
                name="publicacao_secao_fonte_coleta_coerente",
            ),
        ]


class HistoricoPublicacao(ModeloAuditavel):
    publicacao = models.ForeignKey(
        Publicacao,
        on_delete=models.PROTECT,
        related_name="historico",
    )
    tipo_evento = models.CharField(max_length=30, choices=TipoEventoPublicacao.choices)
    situacao_anterior = models.CharField(max_length=30, blank=True, default="")
    situacao_atual = models.CharField(max_length=30, choices=SituacaoPublicacao.choices)
    justificativa = models.TextField(blank=True, default="")
    metadados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"publicacoes"."historico_publicacao"'
        ordering = ("-criado_em", "-id")
