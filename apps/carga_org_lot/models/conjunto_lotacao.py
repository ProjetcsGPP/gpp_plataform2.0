"""Versões de trabalho e histórico consolidado das lotações."""

from django.db import models

from common.models import AuditableModel

from .choices import SituacaoConjuntoLotacao


class ConjuntoLotacao(AuditableModel):
    """Alternativa de lotação vinculada a uma versão do organograma."""

    idconjuntolotacao = models.BigAutoField(primary_key=True)
    idpatriarca = models.ForeignKey(
        "carga_org_lot.Patriarca",
        on_delete=models.PROTECT,
        related_name="conjuntos_lotacao",
    )
    idimportacaoorganograma = models.ForeignKey(
        "carga_org_lot.ImportacaoPlanilha",
        on_delete=models.PROTECT,
        related_name="conjuntos_lotacao",
    )
    idconjuntoanterior = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conjuntos_substitutos",
    )
    strreferencia = models.TextField(blank=True, default="")
    strsituacao = models.CharField(
        max_length=40,
        choices=SituacaoConjuntoLotacao.choices,
        default=SituacaoConjuntoLotacao.RASCUNHO,
    )
    strjustificativaultimaacao = models.TextField(blank=True, default="")
    dathomologacao = models.DateTimeField(null=True, blank=True)
    datativacao = models.DateTimeField(null=True, blank=True)
    datcancelamento = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = '"carga_org_lot"."tblconjuntolotacao"'
        ordering = ["-created_at", "-idconjuntolotacao"]
        constraints = [
            models.UniqueConstraint(
                fields=["idimportacaoorganograma"],
                condition=models.Q(strsituacao=SituacaoConjuntoLotacao.ATIVO),
                name="uq_conj_lot_ativo_organograma",
            )
        ]
        indexes = [
            models.Index(
                fields=["idpatriarca", "idimportacaoorganograma", "strsituacao"],
                name="ix_conj_lot_org_status",
            )
        ]


class HistoricoConjuntoLotacao(AuditableModel):
    """Trilha imutável das mudanças operacionais de um conjunto."""

    idhistoricoconjuntolotacao = models.BigAutoField(primary_key=True)
    idconjuntolotacao = models.ForeignKey(
        ConjuntoLotacao,
        on_delete=models.CASCADE,
        related_name="historico",
    )
    stracao = models.CharField(max_length=100)
    strsituacaoanterior = models.CharField(max_length=40, blank=True, default="")
    strsituacaonova = models.CharField(max_length=40)
    strmensagem = models.TextField(blank=True, default="")
    jsondetalhes = models.JSONField(default=dict)

    class Meta:
        db_table = '"carga_org_lot"."tblhistoricoconjuntolotacao"'
        ordering = ["created_at", "idhistoricoconjuntolotacao"]
