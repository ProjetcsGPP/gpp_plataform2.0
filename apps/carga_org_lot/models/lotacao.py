"""Itens de lotação importados e vinculados ao organograma."""

from django.db import models

from common.models import AuditableModel

from .choices import (
    AcaoResolucaoValidacao,
    SeveridadeOcorrenciaValidacao,
    StatusCasoValidacao,
    StatusItemLotacaoImportado,
)
from .organograma import ItemOrganograma
from .workflow import ImportacaoPlanilha, RelatorioValidacaoImportacao


class ItemLotacaoImportado(AuditableModel):
    """Linha de trabalho preservada antes da incorporação definitiva."""

    iditemlotacaoimportado = models.BigAutoField(primary_key=True)
    idimportacaoplanilha = models.ForeignKey(
        ImportacaoPlanilha,
        on_delete=models.CASCADE,
        related_name="itens_lotacao_importados",
    )
    idorgaoorganograma = models.ForeignKey(
        ItemOrganograma,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lotacoes_importadas_como_orgao",
    )
    idunidadeorganograma = models.ForeignKey(
        ItemOrganograma,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lotacoes_importadas_como_unidade",
    )
    strsiglaorgaooriginal = models.TextField(blank=True, default="")
    strsiglaorgao = models.TextField(blank=True, default="")
    strnomeorgao = models.TextField(blank=True, default="")
    strnomeservidor = models.TextField(blank=True, default="")
    strcpforiginal = models.TextField(blank=True, default="")
    strcpf = models.TextField(blank=True, default="")
    strcargooriginal = models.TextField(blank=True, default="")
    strcargonormalizado = models.TextField(blank=True, default="")
    strsiglaunidadeoriginal = models.TextField(blank=True, default="")
    strsiglaunidade = models.TextField(blank=True, default="")
    strnomeunidade = models.TextField(blank=True, default="")
    strabaorigem = models.CharField(max_length=255)
    intlinhaorigem = models.PositiveIntegerField()
    strsituacao = models.CharField(
        max_length=30,
        choices=StatusItemLotacaoImportado.choices,
        default=StatusItemLotacaoImportado.ACEITO,
    )

    class Meta:
        db_table = '"carga_org_lot"."tblitemlotacaoimportado"'
        ordering = ["strabaorigem", "intlinhaorigem", "iditemlotacaoimportado"]
        constraints = [
            models.UniqueConstraint(
                fields=["idimportacaoplanilha", "strabaorigem", "intlinhaorigem"],
                name="uq_item_lot_imp_aba_linha",
            )
        ]
        indexes = [
            models.Index(
                fields=["idimportacaoplanilha", "strsituacao"],
                name="ix_item_lot_imp_status",
            ),
            models.Index(fields=["strcpf"], name="ix_item_lot_imp_cpf"),
        ]


class ItemLotacao(AuditableModel):
    """Lotação validada e vinculada à versão do organograma utilizada."""

    iditemlotacao = models.BigAutoField(primary_key=True)

    iditemlotacaoimportado = models.OneToOneField(
        ItemLotacaoImportado,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="item_incorporado",
    )

    idimportacaoplanilha = models.ForeignKey(
        ImportacaoPlanilha,
        on_delete=models.CASCADE,
        related_name="itens_lotacao",
    )

    idorgaoorganograma = models.ForeignKey(
        ItemOrganograma,
        on_delete=models.PROTECT,
        related_name="lotacoes_como_orgao",
    )

    idunidadeorganograma = models.ForeignKey(
        ItemOrganograma,
        on_delete=models.PROTECT,
        related_name="lotacoes_como_unidade",
    )

    strsiglaorgao = models.CharField(max_length=20)
    strnomeorgao = models.CharField(max_length=500, blank=True, default="")
    strnomeservidor = models.CharField(max_length=255, blank=True, default="")
    strcpf = models.CharField(max_length=11)
    strcargooriginal = models.CharField(max_length=255)
    strcargonormalizado = models.CharField(max_length=100)
    strsiglaunidade = models.CharField(max_length=25)
    strnomeunidade = models.CharField(max_length=500, blank=True, default="")
    strabaorigem = models.CharField(max_length=255)
    intlinhaorigem = models.PositiveIntegerField()

    class Meta:
        db_table = '"carga_org_lot"."tblitemlotacao"'
        ordering = ["strabaorigem", "intlinhaorigem", "iditemlotacao"]
        indexes = [
            models.Index(
                fields=["idimportacaoplanilha", "strabaorigem"],
                name="ix_item_lot_import_aba",
            ),
            models.Index(
                fields=["idorgaoorganograma", "idunidadeorganograma"],
                name="ix_item_lot_org_unid",
            ),
            models.Index(fields=["strcpf"], name="ix_item_lot_cpf"),
        ]


class CasoValidacaoImportacao(AuditableModel):
    """Agrupa uma crítica que pode atingir uma ou várias linhas."""

    idcasovalidacao = models.BigAutoField(primary_key=True)
    idrelatoriovalidacao = models.ForeignKey(
        RelatorioValidacaoImportacao,
        on_delete=models.CASCADE,
        related_name="casos",
    )
    strchaveagrupamento = models.CharField(max_length=255)
    strcodigo = models.CharField(max_length=100)
    strseveridade = models.CharField(
        max_length=20,
        choices=SeveridadeOcorrenciaValidacao.choices,
    )
    strtitulo = models.CharField(max_length=255)
    strmensagem = models.TextField()
    strstatus = models.CharField(
        max_length=30,
        choices=StatusCasoValidacao.choices,
        default=StatusCasoValidacao.PENDENTE,
    )
    datresolucao = models.DateTimeField(null=True, blank=True)
    itens = models.ManyToManyField(
        ItemLotacaoImportado,
        related_name="casos_validacao",
        blank=True,
    )
    ocorrencias = models.ManyToManyField(
        "carga_org_lot.OcorrenciaValidacaoImportacao",
        related_name="casos_validacao",
        blank=True,
    )

    class Meta:
        db_table = '"carga_org_lot"."tblcasovalidacaoimportacao"'
        ordering = ["strseveridade", "idcasovalidacao"]
        constraints = [
            models.UniqueConstraint(
                fields=["idrelatoriovalidacao", "strchaveagrupamento"],
                name="uq_caso_valid_rel_chave",
            )
        ]


class AlternativaResolucaoValidacao(AuditableModel):
    idalternativaresolucao = models.BigAutoField(primary_key=True)
    idcasovalidacao = models.ForeignKey(
        CasoValidacaoImportacao,
        on_delete=models.CASCADE,
        related_name="alternativas",
    )
    stracao = models.CharField(max_length=50, choices=AcaoResolucaoValidacao.choices)
    strdescricao = models.CharField(max_length=500)
    jsonpayload = models.JSONField(default=dict)
    decconfianca = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    flgrecomendada = models.BooleanField(default=False)

    class Meta:
        db_table = '"carga_org_lot"."tblalternativaresolucaovalidacao"'
        ordering = ["-flgrecomendada", "idalternativaresolucao"]


class ResolucaoValidacao(AuditableModel):
    """Histórico imutável das decisões tomadas para um caso."""

    idresolucaovalidacao = models.BigAutoField(primary_key=True)
    idcasovalidacao = models.ForeignKey(
        CasoValidacaoImportacao,
        on_delete=models.PROTECT,
        related_name="resolucoes",
    )
    idalternativaresolucao = models.ForeignKey(
        AlternativaResolucaoValidacao,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolucoes",
    )
    stracao = models.CharField(max_length=50, choices=AcaoResolucaoValidacao.choices)
    strjustificativa = models.TextField(blank=True, default="")
    jsonantes = models.JSONField(default=dict)
    jsondepois = models.JSONField(default=dict)
    datresolucao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"carga_org_lot"."tblresolucaovalidacao"'
        ordering = ["-datresolucao", "-idresolucaovalidacao"]
