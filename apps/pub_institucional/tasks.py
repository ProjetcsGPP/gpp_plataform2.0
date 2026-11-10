"""Tarefas assíncronas de Publicações Institucionais."""

from celery import shared_task

from apps.pub_institucional.services.edocs_mensal import \
    executar_coleta_mensal_edocs


@shared_task(name="pub_institucional.processar_coleta_mensal_edocs")
def processar_coleta_mensal_edocs(coleta_id):
    coleta = executar_coleta_mensal_edocs(coleta_id)
    return {"coleta_id": str(coleta.pk), "situacao": coleta.situacao}
