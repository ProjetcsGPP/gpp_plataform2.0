"""Tarefas assíncronas de Publicações Institucionais."""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.pub_institucional.models import (ColetaMensalEdocs,
                                           SituacaoColetaMensalEdocs)
from apps.pub_institucional.services.edocs_mensal import (
    ErroColetaMensalEdocs, executar_coleta_mensal_edocs,
    reencaminhar_coleta_mensal_edocs)


@shared_task(name="pub_institucional.processar_coleta_mensal_edocs")
def processar_coleta_mensal_edocs(coleta_id):
    coleta = executar_coleta_mensal_edocs(coleta_id)
    return {"coleta_id": str(coleta.pk), "situacao": coleta.situacao}


@shared_task(name="pub_institucional.recuperar_coletas_mensais_edocs")
def recuperar_coletas_mensais_edocs():
    """Reencaminha solicitações antigas que não chegaram a iniciar."""

    limite = timezone.now() - timedelta(
        seconds=settings.GPP_EDOCS_REQUEST_STALE_SECONDS
    )
    ids = list(
        ColetaMensalEdocs.objects.filter(
            situacao=SituacaoColetaMensalEdocs.SOLICITADA,
            atualizado_em__lte=limite,
        ).values_list("pk", flat=True)
    )
    recuperadas = 0
    for coleta_id in ids:
        try:
            reencaminhar_coleta_mensal_edocs(coleta_id)
        except (ColetaMensalEdocs.DoesNotExist, ErroColetaMensalEdocs):
            continue
        recuperadas += 1
    return {"encontradas": len(ids), "reencaminhadas": recuperadas}
