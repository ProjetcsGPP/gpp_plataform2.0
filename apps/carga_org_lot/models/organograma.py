"""Modelos de organograma e de sua integração com a PRODEST."""

import uuid

from django.db import models
from django.utils import timezone

from common.models import AuditableModel

from .choices import (
    FaseIntegracaoProdest,
    OperacaoIntegracaoProdest,
    ResultadoIntegracaoProdest,
    StatusEnvioOrganograma,
    StatusEventoOperacional,
    TipoCargaIntegracao,
    VisibilidadeEventoIntegracao,
)
from .workflow import ImportacaoPlanilha, Patriarca, ProcessoCargaInicial


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

    strresponsavel = models.CharField(max_length=255, blank=True, default="")

    strcargo = models.CharField(max_length=255, blank=True, default="")

    flggeradoautomaticamente = models.BooleanField(default=False)

    strnumero = models.CharField(max_length=100, blank=True, default="")

    strreferenciapai = models.CharField(max_length=500, blank=True, default="")

    strabaorigem = models.CharField(max_length=255, blank=True, default="")

    intlinhaorigem = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = '"carga_org_lot"."tblitemorganograma"'
        ordering = ["strnumero", "intlinhaorigem", "iditemorganograma"]
        constraints = [
            models.UniqueConstraint(
                fields=["idimportacaoplanilha", "idpai", "strsigla"],
                name="uq_item_org_irmaos_sigla",
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


class EnvioOrganogramaProdest(AuditableModel):

    idenvioorganograma = models.BigAutoField(primary_key=True)

    idimportacaoplanilha = models.ForeignKey(
        ImportacaoPlanilha,
        on_delete=models.PROTECT,
        related_name="envios_organograma_prodest",
    )

    idprocessocargainicial = models.ForeignKey(
        ProcessoCargaInicial,
        on_delete=models.PROTECT,
        related_name="envios_organograma_prodest",
    )

    flgdryrun = models.BooleanField(default=True)

    strambiente = models.CharField(max_length=20)

    idexternocarga = models.UUIDField(null=True, blank=True, db_index=True)

    strstatus = models.CharField(
        max_length=30,
        choices=StatusEnvioOrganograma.choices,
        default=StatusEnvioOrganograma.SOLICITANDO,
    )

    jsonpayloadenviado = models.JSONField(default=dict)

    strhashpayload = models.CharField(max_length=64)

    jsonstatusprodest = models.JSONField(default=dict)

    jsonrelatorioprodest = models.JSONField(default=dict)

    strmensagemerro = models.TextField(blank=True, default="")

    strfaseatual = models.CharField(
        max_length=30,
        choices=FaseIntegracaoProdest.choices,
        default=FaseIntegracaoProdest.PREPARACAO,
    )
    strstatusoperacional = models.CharField(
        max_length=20,
        choices=StatusEventoOperacional.choices,
        default=StatusEventoOperacional.AGUARDANDO,
    )
    strmensagematual = models.TextField(blank=True, default="")
    datultimaatividade = models.DateTimeField(default=timezone.now, db_index=True)
    datproximaconsulta = models.DateTimeField(null=True, blank=True, db_index=True)
    datiniciomonitoramento = models.DateTimeField(null=True, blank=True)
    datfimmonitoramento = models.DateTimeField(null=True, blank=True)

    datsolicitacao = models.DateTimeField(auto_now_add=True)

    datultimaconsulta = models.DateTimeField(null=True, blank=True)

    datfinalizacao = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = '"carga_org_lot"."tblenvioorganogramaprodest"'
        ordering = ["-datsolicitacao", "-idenvioorganograma"]
        constraints = [
            models.UniqueConstraint(
                fields=["idprocessocargainicial"],
                condition=models.Q(
                    strstatus__in=[
                        StatusEnvioOrganograma.SOLICITANDO,
                        StatusEnvioOrganograma.PROCESSANDO,
                    ]
                ),
                name="uq_envio_org_ativo_processo",
            )
        ]
        indexes = [
            models.Index(
                fields=["idimportacaoplanilha", "flgdryrun", "strstatus"],
                name="ix_envio_org_import_modo",
            )
        ]


class EventoIntegracaoProdest(AuditableModel):
    """Trilha segura e imutável das comunicações com a PRODEST."""

    ideventointegracao = models.BigAutoField(primary_key=True)
    idcorrelacao = models.UUIDField(default=uuid.uuid4, db_index=True)
    idpatriarca = models.ForeignKey(
        Patriarca,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_integracao_prodest",
    )
    idprocessocargainicial = models.ForeignKey(
        ProcessoCargaInicial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_integracao_prodest",
    )
    idenvioorganograma = models.ForeignKey(
        EnvioOrganogramaProdest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_integracao_prodest",
    )
    idexternocarga = models.UUIDField(null=True, blank=True, db_index=True)
    strvisibilidade = models.CharField(
        max_length=20,
        choices=VisibilidadeEventoIntegracao.choices,
        default=VisibilidadeEventoIntegracao.TECNICA,
        db_index=True,
    )
    strtipocarga = models.CharField(
        max_length=20,
        choices=TipoCargaIntegracao.choices,
        blank=True,
        default="",
    )
    strfase = models.CharField(
        max_length=30,
        choices=FaseIntegracaoProdest.choices,
        blank=True,
        default="",
    )
    strcodigo = models.CharField(max_length=80, blank=True, default="")
    strstatusoperacional = models.CharField(
        max_length=20,
        choices=StatusEventoOperacional.choices,
        blank=True,
        default="",
    )
    strtitulo = models.CharField(max_length=255, blank=True, default="")
    stroperacao = models.CharField(
        max_length=50,
        choices=OperacaoIntegracaoProdest.choices,
    )
    strmetodo = models.CharField(max_length=10)
    strendpoint = models.CharField(max_length=500)
    inttentativa = models.PositiveSmallIntegerField(default=1)
    strresultado = models.CharField(
        max_length=30,
        choices=ResultadoIntegracaoProdest.choices,
    )
    inthttpstatus = models.PositiveSmallIntegerField(null=True, blank=True)
    intduracaoms = models.PositiveIntegerField(default=0)
    strmensagem = models.TextField()
    jsondetalhes = models.JSONField(default=dict)
    datocorrencia = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = '"carga_org_lot"."tbleventointegracaoprodest"'
        ordering = ["-datocorrencia", "-ideventointegracao"]
        indexes = [
            models.Index(
                fields=["idpatriarca", "-datocorrencia"],
                name="ix_evt_prodest_patriarca",
            ),
            models.Index(
                fields=["idenvioorganograma", "-datocorrencia"],
                name="ix_evt_prodest_envio",
            ),
            models.Index(
                fields=["strvisibilidade", "-datocorrencia"],
                name="ix_evt_prodest_visib",
            ),
        ]
