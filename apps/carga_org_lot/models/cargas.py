"""Modelos legados de acompanhamento de cargas."""

from django.db import models

from common.models import AuditableModel

from .catalogs import StatusCarga, StatusProgresso, TipoCarga


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
