"""
GPP Plataform 2.0 — Ações PNGI
Todos os models usam schema 'acoes_pngi' no PostgreSQL.
"""
from django.db import models
from common.models import AuditableModel


class Eixo(AuditableModel):

    ideixo = models.AutoField(primary_key=True, db_column="ideixo")

    strdescricaoeixo = models.CharField(
        db_column="strdescricaoeixo",
        max_length=100
    )

    stralias = models.CharField(
        db_column="stralias",
        max_length=5,
        unique=True
    )

    class Meta:
        db_table = '"acoes_pngi"."tbleixos"'
        ordering = ["stralias"]


class SituacaoAcao(models.Model):

    idsituacaoacao = models.AutoField(primary_key=True, db_column="idsituacaoacao")

    strdescricaosituacao = models.CharField(
        db_column="strdescricaosituacao",
        max_length=50,
        unique=True
    )

    class Meta:
        db_table = '"acoes_pngi"."tblsituacaoacao"'
        ordering = ["strdescricaosituacao"]


class TipoEntraveAlerta(models.Model):

    idtipoentravealerta = models.AutoField(
        primary_key=True,
        db_column="idtipoentravealerta"
    )

    strdescricaotipoentravealerta = models.CharField(
        db_column="strdescricaotipoentravealerta",
        max_length=50
    )

    class Meta:
        db_table = '"acoes_pngi"."tbltipoentravealerta"'
        ordering = ["strdescricaotipoentravealerta"]


class TipoAnotacaoAlinhamento(models.Model):

    idtipoanotacaoalinhamento = models.AutoField(
        primary_key=True,
        db_column="idtipoanotacaoalinhamento"
    )

    strdescricaotipoanotacaoalinhamento = models.CharField(
        db_column="strdescricaotipoanotacaoalinhamento",
        max_length=100
    )

    class Meta:
        db_table = '"acoes_pngi"."tbltipoanotacaoalinhamento"'
        ordering = ["strdescricaotipoanotacaoalinhamento"]


class VigenciaPNGI(AuditableModel):

    idvigenciapngi = models.AutoField(
        primary_key=True,
        db_column="idvigenciapngi"
    )

    strdescricao = models.CharField(
        db_column="strdescricao",
        max_length=200
    )

    datiniciovigencia = models.DateField(db_column="datiniciovigencia")

    datfinalvigencia = models.DateField(
        db_column="datfinalvigencia",
        null=True,
        blank=True
    )

    class Meta:
        db_table = '"acoes_pngi"."tblvigenciapngi"'
        ordering = ["-datiniciovigencia"]


class Acoes(AuditableModel):

    idacao = models.AutoField(primary_key=True, db_column="idacao")

    strapelido = models.CharField(
        db_column="strapelido",
        max_length=50
    )

    strdescricaoacao = models.CharField(
        db_column="strdescricaoacao",
        max_length=350
    )

    strdescricaoentrega = models.CharField(
        db_column="strdescricaoentrega",
        max_length=100
    )

    datdataentrega = models.DateTimeField(
        db_column="datdataentrega",
        null=True,
        blank=True
    )

    idvigenciapngi = models.ForeignKey(
        VigenciaPNGI,
        db_column="idvigenciapngi",
        on_delete=models.PROTECT,
        related_name="acoes"
    )

    idtipoentravealerta = models.ForeignKey(
        TipoEntraveAlerta,
        db_column="idtipoentravealerta",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acoes"
    )

    idsituacaoacao = models.ForeignKey(
        SituacaoAcao,
        db_column="idsituacaoacao",
        on_delete=models.PROTECT,
        related_name="acoes",
        null=True,
        blank=True
    )

    ideixo = models.ForeignKey(
        Eixo,
        db_column="ideixo",
        on_delete=models.PROTECT,
        related_name="acoes",
        null=True,
        blank=True
    )

    class Meta:
        db_table = '"acoes_pngi"."tblacoes"'
        ordering = ["strapelido"]


class AcaoPrazo(AuditableModel):

    idacaoprazo = models.AutoField(primary_key=True, db_column="idacaoprazo")

    idacao = models.ForeignKey(
        Acoes,
        db_column="idacao",
        on_delete=models.CASCADE,
        related_name="prazos"
    )

    isacaoprazoativo = models.BooleanField(
        db_column="isacaoprazoativo",
        default=True
    )

    strprazo = models.CharField(
        db_column="strprazo",
        max_length=50
    )

    class Meta:
        db_table = '"acoes_pngi"."tblacaoprazo"'
        ordering = ["idacaoprazo"]


class AcaoDestaque(AuditableModel):

    idacaodestaque = models.AutoField(
        primary_key=True,
        db_column="idacaodestaque"
    )

    idacao = models.ForeignKey(
        Acoes,
        db_column="idacao",
        on_delete=models.CASCADE,
        related_name="destaques"
    )

    datdatadestaque = models.DateTimeField(
        db_column="datdatadestaque"
    )

    class Meta:
        db_table = '"acoes_pngi"."tblacaodestaque"'
        ordering = ["-datdatadestaque"]


class AcaoAnotacaoAlinhamento(AuditableModel):

    idacaoanotacaoalinhamento = models.AutoField(
        primary_key=True,
        db_column="idacaoanotacaoalinhamento"
    )

    idacao = models.ForeignKey(
        Acoes,
        db_column="idacao",
        on_delete=models.CASCADE,
        related_name="anotacoes"
    )

    idtipoanotacaoalinhamento = models.ForeignKey(
        TipoAnotacaoAlinhamento,
        db_column="idtipoanotacaoalinhamento",
        on_delete=models.PROTECT
    )

    strdescricao = models.TextField(
        db_column="strdescricao"
    )

    class Meta:
        db_table = '"acoes_pngi"."tblacaoanotacaoalinhamento"'
        ordering = ["idacaoanotacaoalinhamento"]


class RelacaoAcaoUsuarioResponsavel(models.Model):
    """
    Relação entre uma Ação e um usuário responsável.
    idusuarioresponsavel é uma chave lógica (IntegerField) referenciando
    o id do usuário em accounts.UserProfile — sem FK cross-schema para
    auth_user, evitando conflitos de TRUNCATE no teardown do pytest-django.
    """

    idacao = models.ForeignKey(
        Acoes,
        db_column="idacao",
        on_delete=models.CASCADE
    )

    idusuarioresponsavel = models.IntegerField(
        db_column="idusuarioresponsavel",
        help_text="ID lógico do usuário responsável (sem FK para auth_user)"
    )

    class Meta:
        db_table = '"acoes_pngi"."tblrelacaoacaousuarioresponsavel"'
        unique_together = (("idacao", "idusuarioresponsavel"),)
