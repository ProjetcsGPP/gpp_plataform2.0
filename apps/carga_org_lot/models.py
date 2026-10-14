"""
GPP Plataform 2.0 — Carga Organizacional / Lotes
Todos os models usam schema 'carga_org_lot' no PostgreSQL.
"""

from django.db import models

from common.models import AuditableModel


class StatusCarga(models.Model):

    idstatuscarga = models.SmallIntegerField(primary_key=True)

    strdescricao = models.CharField(max_length=150)

    flgsucesso = models.IntegerField()

    class Meta:
        db_table = '"carga_org_lot"."tblstatuscarga"'


class StatusProgresso(models.Model):

    idstatusprogresso = models.SmallIntegerField(primary_key=True)

    strdescricao = models.CharField(max_length=100)

    class Meta:
        db_table = '"carga_org_lot"."tblstatusprogresso"'


class TipoCarga(models.Model):

    idtipocarga = models.SmallIntegerField(primary_key=True)

    strdescricao = models.CharField(max_length=100)

    class Meta:
        db_table = '"carga_org_lot"."tbltipocarga"'


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


class ImportacaoPlanilha(AuditableModel):

    idimportacaoplanilha = models.BigAutoField(primary_key=True)

    idpatriarca = models.ForeignKey(
        Patriarca,
        on_delete=models.PROTECT,
        related_name="importacoes",
    )

    idtipocarga = models.ForeignKey(TipoCarga, on_delete=models.PROTECT)

    idimportacaoorganograma = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="importacoes_lotacao",
    )

    idstatusprogresso = models.ForeignKey(StatusProgresso, on_delete=models.PROTECT)

    strnomearquivo = models.CharField(max_length=255)

    strtipomime = models.CharField(max_length=150)

    inttamanhoarquivo = models.BigIntegerField()

    strhasharquivo = models.CharField(max_length=64)

    strabaimportada = models.CharField(max_length=255, blank=True, default="")

    binconteudo = models.BinaryField(editable=False)

    datimportacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"carga_org_lot"."tblimportacaoplanilha"'


class ItemOrganograma(AuditableModel):

    iditemorganograma = models.BigAutoField(primary_key=True)

    idimportacaoplanilha = models.ForeignKey(
        ImportacaoPlanilha,
        on_delete=models.CASCADE,
        related_name="itens_organograma",
    )

    idpai = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="filhos",
    )

    strnome = models.CharField(max_length=500)

    strsigla = models.CharField(max_length=100)

    strnumero = models.CharField(max_length=100, blank=True, default="")

    strreferenciapai = models.CharField(max_length=500, blank=True, default="")

    strabaorigem = models.CharField(max_length=255)

    intlinhaorigem = models.PositiveIntegerField()

    class Meta:
        db_table = '"carga_org_lot"."tblitemorganograma"'
        ordering = ["strnumero", "intlinhaorigem", "iditemorganograma"]
        constraints = [
            models.UniqueConstraint(
                fields=["idimportacaoplanilha", "strsigla"],
                name="uq_item_org_importacao_sigla",
            ),
            models.UniqueConstraint(
                fields=["idimportacaoplanilha", "strnumero"],
                condition=~models.Q(strnumero=""),
                name="uq_item_org_importacao_numero",
            ),
        ]
        indexes = [
            models.Index(
                fields=["idimportacaoplanilha", "idpai"],
                name="ix_item_org_import_pai",
            ),
        ]


class TokenEnvioCarga(AuditableModel):

    idtokenenviocarga = models.BigAutoField(primary_key=True)

    strtoken = models.CharField(max_length=200)

    idtipocarga = models.ForeignKey(TipoCarga, on_delete=models.PROTECT)

    idstatusprogresso = models.ForeignKey(StatusProgresso, on_delete=models.PROTECT)

    class Meta:
        db_table = '"carga_org_lot"."tbltokenenviocarga"'


class DetalheStatusCarga(AuditableModel):

    iddetalhestatuscarga = models.BigAutoField(primary_key=True)

    idtokenenviocarga = models.ForeignKey(
        TokenEnvioCarga, on_delete=models.CASCADE, related_name="detalhes"
    )

    idstatuscarga = models.ForeignKey(StatusCarga, on_delete=models.PROTECT)

    strmensagem = models.TextField()

    class Meta:
        db_table = '"carga_org_lot"."tbldetalhestatuscarga"'
