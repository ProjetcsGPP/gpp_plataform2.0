"""Evidência da primeira implantação E-Docs observada na API oficial."""

from django.db import models

from common.models import ModeloAuditavel


class CriterioImplantacaoEdocs(models.TextChoices):
    ATIVIDADE_API = "ATIVIDADE_API", "Atividade observada na API oficial"


class ImplantacaoPatriarcaEdocs(ModeloAuditavel):
    """Primeira competência positiva observada, preservada sem sobrescrita."""

    patriarca = models.OneToOneField(
        "pub_institucional.PatriarcaEdocs",
        on_delete=models.PROTECT,
        related_name="implantacao_edocs_observada",
    )
    ano = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    coleta_evidencia = models.ForeignKey(
        "pub_institucional.ColetaMensalEdocs",
        on_delete=models.PROTECT,
        related_name="implantacoes_observadas",
    )
    criterio = models.CharField(
        max_length=30,
        choices=CriterioImplantacaoEdocs.choices,
        default=CriterioImplantacaoEdocs.ATIVIDADE_API,
    )
    totais_evidencia = models.JSONField(default=dict, editable=False)

    class Meta:
        db_table = '"publicacoes"."implantacao_patriarca_edocs"'
        ordering = ("ano", "mes", "patriarca_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ano__gte=2024, ano__lte=9999),
                name="edocs_implantacao_ano_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(mes__gte=1, mes__lte=12),
                name="edocs_implantacao_mes_valido",
            ),
        ]


class EventoAuditoriaImplantacaoEdocs(ModeloAuditavel):
    """Registro append-only da inferência de implantação."""

    implantacao = models.ForeignKey(
        ImplantacaoPatriarcaEdocs,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    mensagem = models.CharField(max_length=500)
    metadados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"publicacoes"."evento_auditoria_implantacao_edocs"'
        ordering = ("-criado_em", "-id")
