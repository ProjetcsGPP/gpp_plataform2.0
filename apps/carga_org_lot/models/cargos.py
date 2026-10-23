"""Catálogo global e aprendizado das descrições de cargos importadas."""

from django.db import models

from common.models import AuditableModel

from .choices import StatusCargoReferencia, StatusVariacaoCargo


class CargoReferenciaGlobal(AuditableModel):
    """Cargo canônico compartilhado entre todos os patriarcas."""

    idcargoreferencia = models.BigAutoField(primary_key=True)
    strnome = models.CharField(max_length=100)
    strchave = models.CharField(max_length=255, unique=True)
    strdescricao = models.TextField(blank=True, default="")
    strstatus = models.CharField(
        max_length=20,
        choices=StatusCargoReferencia.choices,
        default=StatusCargoReferencia.NOVO,
    )
    strorigem = models.CharField(max_length=30, default="IMPORTACAO")
    flgativo = models.BooleanField(default=True)

    class Meta:
        db_table = '"carga_org_lot"."tblcargoreferenciaglobal"'
        ordering = ["strnome", "idcargoreferencia"]
        indexes = [
            models.Index(fields=["strstatus", "flgativo"], name="ix_cargo_ref_status"),
        ]


class VariacaoCargoGlobal(AuditableModel):
    """Forma textual encontrada em uma ou mais planilhas."""

    idvariacaocargo = models.BigAutoField(primary_key=True)
    idcargoreferencia = models.ForeignKey(
        CargoReferenciaGlobal,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="variacoes",
    )
    strdescricao = models.CharField(max_length=255)
    strchave = models.CharField(max_length=255, unique=True)
    strstatus = models.CharField(
        max_length=20,
        choices=StatusVariacaoCargo.choices,
        default=StatusVariacaoCargo.NOVA,
    )
    inttotalocorrencias = models.PositiveBigIntegerField(default=0)
    inttotalimportacoes = models.PositiveIntegerField(default=0)
    inttotalpatriarcas = models.PositiveIntegerField(default=0)
    datprimeiraocorrencia = models.DateTimeField(auto_now_add=True)
    datultimaocorrencia = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"carga_org_lot"."tblvariacaocargoglobal"'
        ordering = ["strdescricao", "idvariacaocargo"]
        indexes = [
            models.Index(fields=["strstatus"], name="ix_var_cargo_status"),
        ]


class OcorrenciaCargoImportacao(AuditableModel):
    """Estatística de uma variação dentro de uma importação específica."""

    idocorrenciacargo = models.BigAutoField(primary_key=True)
    idvariacaocargo = models.ForeignKey(
        VariacaoCargoGlobal,
        on_delete=models.PROTECT,
        related_name="ocorrencias",
    )
    idimportacaoplanilha = models.ForeignKey(
        "carga_org_lot.ImportacaoPlanilha",
        on_delete=models.CASCADE,
        related_name="ocorrencias_cargo",
    )
    idpatriarca = models.ForeignKey(
        "carga_org_lot.Patriarca",
        on_delete=models.PROTECT,
        related_name="ocorrencias_cargo",
    )
    intquantidade = models.PositiveIntegerField(default=1)
    jsonlocalizacoes = models.JSONField(default=list)

    class Meta:
        db_table = '"carga_org_lot"."tblocorrenciacargoimportacao"'
        ordering = ["-created_at", "-idocorrenciacargo"]
        constraints = [
            models.UniqueConstraint(
                fields=["idvariacaocargo", "idimportacaoplanilha"],
                name="uq_ocorr_cargo_variacao_import",
            )
        ]
        indexes = [
            models.Index(
                fields=["idpatriarca", "idvariacaocargo"],
                name="ix_ocorr_cargo_patri_var",
            ),
        ]


class MapeamentoCargoPatriarca(AuditableModel):
    """Exceção local que tem precedência sobre o mapeamento global."""

    idmapeamentocargo = models.BigAutoField(primary_key=True)
    idpatriarca = models.ForeignKey(
        "carga_org_lot.Patriarca",
        on_delete=models.CASCADE,
        related_name="mapeamentos_cargo",
    )
    idvariacaocargo = models.ForeignKey(
        VariacaoCargoGlobal,
        on_delete=models.PROTECT,
        related_name="mapeamentos_patriarca",
    )
    idcargoreferencia = models.ForeignKey(
        CargoReferenciaGlobal,
        on_delete=models.PROTECT,
        related_name="mapeamentos_patriarca",
    )
    flgativo = models.BooleanField(default=True)

    class Meta:
        db_table = '"carga_org_lot"."tblmapeamentocargopatriarca"'
        ordering = ["idpatriarca_id", "idvariacaocargo_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["idpatriarca", "idvariacaocargo"],
                name="uq_map_cargo_patri_variacao",
            )
        ]
