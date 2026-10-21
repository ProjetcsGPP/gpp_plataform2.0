"""Modelos do fluxo local de importação e validação."""

from django.db import models

from common.models import AuditableModel

from .catalogs import StatusProgresso, TipoCarga
from .choices import (
    FaseProcessoCargaInicial,
    ResultadoRelatorioValidacao,
    SeveridadeOcorrenciaValidacao,
    StatusImportacaoLocal,
    StatusLotacaoProcesso,
    StatusOrganogramaProcesso,
    TipoOperacaoImportacaoLotacao,
)


class Patriarca(AuditableModel):

    idpatriarca = models.BigAutoField(primary_key=True)

    idexternopatriarca = models.UUIDField(unique=True)

    strsiglapatriarca = models.CharField(max_length=20)

    strnome = models.CharField(max_length=255)

    datcriacao = models.DateTimeField()

    datalteracao = models.DateTimeField(null=True, blank=True)

    idstatusprogresso = models.ForeignKey(StatusProgresso, on_delete=models.PROTECT)

    class Meta:
        db_table = '"carga_org_lot"."tblpatriarca"'


class ProcessoCargaInicial(AuditableModel):

    idprocessocargainicial = models.BigAutoField(primary_key=True)

    idpatriarca = models.ForeignKey(
        Patriarca,
        on_delete=models.CASCADE,
        related_name="processos_carga_inicial",
    )

    strfaseatual = models.CharField(
        max_length=40,
        choices=FaseProcessoCargaInicial.choices,
        default=FaseProcessoCargaInicial.NOVO,
    )

    strstatusorganograma = models.CharField(
        max_length=40,
        choices=StatusOrganogramaProcesso.choices,
        default=StatusOrganogramaProcesso.NAO_INICIADO,
    )

    strstatuslotacao = models.CharField(
        max_length=40,
        choices=StatusLotacaoProcesso.choices,
        default=StatusLotacaoProcesso.BLOQUEADA,
    )

    flgativo = models.BooleanField(default=True)

    databertura = models.DateTimeField(auto_now_add=True)

    dataconclusao = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = '"carga_org_lot"."tblprocessocargainicial"'
        constraints = [
            models.UniqueConstraint(
                fields=["idpatriarca"],
                condition=models.Q(flgativo=True),
                name="uq_processo_carga_inicial_ativo",
            )
        ]


class HistoricoProcessoCargaInicial(AuditableModel):

    idhistoricoprocesso = models.BigAutoField(primary_key=True)

    idprocessocargainicial = models.ForeignKey(
        ProcessoCargaInicial,
        on_delete=models.CASCADE,
        related_name="historico",
    )

    stracao = models.CharField(max_length=100)

    strfaseanterior = models.CharField(max_length=40, blank=True, default="")

    strfasenova = models.CharField(max_length=40)

    strstatusorganogramaanterior = models.CharField(
        max_length=40,
        blank=True,
        default="",
    )

    strstatusorganogramanovo = models.CharField(max_length=40)

    strstatuslotacaoanterior = models.CharField(
        max_length=40,
        blank=True,
        default="",
    )

    strstatuslotacaonovo = models.CharField(max_length=40)

    strmensagem = models.TextField(blank=True, default="")

    jsondetalhes = models.JSONField(default=dict)

    class Meta:
        db_table = '"carga_org_lot"."tblhistoricoprocessocargainicial"'
        ordering = ["created_at", "idhistoricoprocesso"]


class ImportacaoPlanilha(AuditableModel):

    idimportacaoplanilha = models.BigAutoField(primary_key=True)

    idpatriarca = models.ForeignKey(
        Patriarca,
        on_delete=models.PROTECT,
        related_name="importacoes",
    )

    idtipocarga = models.ForeignKey(TipoCarga, on_delete=models.PROTECT)

    idprocessocargainicial = models.ForeignKey(
        ProcessoCargaInicial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="importacoes",
    )

    idimportacaoorganograma = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="importacoes_lotacao",
    )

    idconjuntolotacao = models.ForeignKey(
        "carga_org_lot.ConjuntoLotacao",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="importacoes",
    )

    strtipooperacaolotacao = models.CharField(
        max_length=20,
        choices=TipoOperacaoImportacaoLotacao.choices,
        blank=True,
        default="",
    )

    idstatusprogresso = models.ForeignKey(StatusProgresso, on_delete=models.PROTECT)

    strnomearquivo = models.CharField(max_length=255)

    strtipomime = models.CharField(max_length=150)

    inttamanhoarquivo = models.BigIntegerField()

    strhasharquivo = models.CharField(max_length=64)

    strabaimportada = models.CharField(max_length=255, blank=True, default="")

    strreferencia = models.TextField(blank=True, default="")

    strstatusimportacao = models.CharField(
        max_length=40,
        choices=StatusImportacaoLocal.choices,
        default=StatusImportacaoLocal.RECEBIDA,
    )

    flgpossuialteracoes = models.BooleanField(default=False)

    flgcriarunidadesespelho = models.BooleanField(default=False)

    datprimeiraalteracao = models.DateTimeField(null=True, blank=True)

    datultimaalteracao = models.DateTimeField(null=True, blank=True)

    binconteudo = models.BinaryField(editable=False)

    datimportacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"carga_org_lot"."tblimportacaoplanilha"'


class RelatorioValidacaoImportacao(AuditableModel):

    idrelatoriovalidacao = models.BigAutoField(primary_key=True)

    idimportacaoplanilha = models.OneToOneField(
        ImportacaoPlanilha,
        on_delete=models.CASCADE,
        related_name="relatorio_validacao",
    )

    strresultado = models.CharField(
        max_length=30,
        choices=ResultadoRelatorioValidacao.choices,
    )

    flgleituracompleta = models.BooleanField(default=True)

    inttotalabas = models.PositiveIntegerField(default=0)

    inttotallinhas = models.PositiveIntegerField(default=0)

    inttotalvalidas = models.PositiveIntegerField(default=0)

    inttotalerros = models.PositiveIntegerField(default=0)

    inttotalavisos = models.PositiveIntegerField(default=0)

    inttotalnormalizacoes = models.PositiveIntegerField(default=0)

    strversaoregras = models.CharField(max_length=100, default="organograma-v1")

    jsonresumo = models.JSONField(default=dict)

    datprocessamento = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"carga_org_lot"."tblrelatoriovalidacaoimportacao"'


class OcorrenciaValidacaoImportacao(AuditableModel):

    idocorrenciavalidacao = models.BigAutoField(primary_key=True)

    idrelatoriovalidacao = models.ForeignKey(
        RelatorioValidacaoImportacao,
        on_delete=models.CASCADE,
        related_name="ocorrencias",
    )

    strseveridade = models.CharField(
        max_length=20,
        choices=SeveridadeOcorrenciaValidacao.choices,
    )

    strcodigo = models.CharField(max_length=100)

    straba = models.CharField(max_length=255, blank=True, default="")

    intlinha = models.PositiveIntegerField(null=True, blank=True)

    strcampo = models.CharField(max_length=255, blank=True, default="")

    strvalororiginal = models.TextField(blank=True, default="")

    strvalornormalizado = models.TextField(blank=True, default="")

    strmensagem = models.TextField()

    strregraaplicada = models.CharField(max_length=255, blank=True, default="")

    jsonsugestoes = models.JSONField(default=list)

    class Meta:
        db_table = '"carga_org_lot"."tblocorrenciavalidacaoimportacao"'
        ordering = ["strseveridade", "straba", "intlinha", "idocorrenciavalidacao"]
