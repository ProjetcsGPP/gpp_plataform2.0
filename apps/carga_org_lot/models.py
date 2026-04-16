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
