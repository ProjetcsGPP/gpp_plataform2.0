"""Cadastro municipal independente do catálogo de patriarcas do E-Docs."""

from django.db import models
from django.db.models import Q

from common.models import ModeloAuditavel


class SituacaoMunicipioEdocs(models.TextChoices):
    SEM_DADOS = "SEM_DADOS", "Sem dados"
    MANIFESTOU_INTERESSE = (
        "MANIFESTOU_INTERESSE",
        "Manifestou interesse",
    )
    EM_IMPLANTACAO = "EM_IMPLANTACAO", "Em implantação"
    IMPLANTADO_SEM_USO_EDOCS = (
        "IMPLANTADO_SEM_USO_EDOCS",
        "Implantado sem uso do E-Docs",
    )


class MunicipioEdocs(ModeloAuditavel):
    """Município conhecido pelo gestor, exista ou não na API do E-Docs."""

    codigo_ibge = models.PositiveIntegerField(
        unique=True,
        verbose_name="Código IBGE do município",
    )
    nome = models.CharField(max_length=200, verbose_name="Nome do município")
    ativo = models.BooleanField(default=True)
    versao = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        db_table = '"publicacoes"."municipio_edocs"'
        ordering = ("nome", "codigo_ibge")
        constraints = [
            models.CheckConstraint(
                condition=Q(codigo_ibge__gte=3_200_000, codigo_ibge__lte=3_299_999),
                name="municipio_edocs_codigo_ibge_valido",
            )
        ]
        permissions = [
            (
                "alterar_situacao_municipio_edocs",
                "Pode alterar a situação municipal do E-Docs",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_ibge} - {self.nome}"


class VigenciaSituacaoMunicipioEdocs(ModeloAuditavel):
    """Situação manual efetiva em um intervalo de competências mensais."""

    municipio = models.ForeignKey(
        MunicipioEdocs,
        on_delete=models.PROTECT,
        related_name="vigencias_situacao",
    )
    situacao = models.CharField(
        max_length=40,
        choices=SituacaoMunicipioEdocs.choices,
    )
    ano_inicio = models.PositiveSmallIntegerField()
    mes_inicio = models.PositiveSmallIntegerField()
    ano_fim = models.PositiveSmallIntegerField(null=True, blank=True)
    mes_fim = models.PositiveSmallIntegerField(null=True, blank=True)
    justificativa = models.TextField()

    class Meta:
        db_table = '"publicacoes"."vigencia_situacao_municipio_edocs"'
        ordering = ("municipio_id", "-ano_inicio", "-mes_inicio")
        constraints = [
            models.CheckConstraint(
                condition=Q(ano_inicio__gte=2024),
                name="municipio_edocs_vigencia_ano_inicio_valido",
            ),
            models.CheckConstraint(
                condition=Q(mes_inicio__gte=1, mes_inicio__lte=12),
                name="municipio_edocs_vigencia_mes_inicio_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(ano_fim__isnull=True, mes_fim__isnull=True)
                    | Q(
                        ano_fim__isnull=False,
                        ano_fim__gte=2024,
                        mes_fim__isnull=False,
                        mes_fim__gte=1,
                        mes_fim__lte=12,
                    )
                ),
                name="municipio_edocs_vigencia_fim_coerente",
            ),
            models.UniqueConstraint(
                fields=("municipio", "ano_inicio", "mes_inicio"),
                name="municipio_edocs_vigencia_inicio_unico",
            ),
            models.UniqueConstraint(
                fields=("municipio",),
                condition=Q(ano_fim__isnull=True, mes_fim__isnull=True),
                name="municipio_edocs_uma_vigencia_aberta",
            ),
        ]


class EventoAuditoriaMunicipioEdocs(ModeloAuditavel):
    """Trilha append-only das decisões manuais sobre municípios."""

    municipio = models.ForeignKey(
        MunicipioEdocs,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    tipo_evento = models.CharField(max_length=50)
    mensagem = models.CharField(max_length=500)
    dados_anteriores = models.JSONField(default=dict, blank=True)
    dados_atuais = models.JSONField(default=dict, blank=True)
    metadados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"publicacoes"."evento_auditoria_municipio_edocs"'
        ordering = ("-criado_em", "-id")
