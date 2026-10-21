"""Tabelas de domínio legadas usadas pelas cargas."""

from django.db import models


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
