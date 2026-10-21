from django.db import transaction
from django.utils import timezone

from apps.carga_org_lot.models import (
    EventoIntegracaoProdest,
    FaseIntegracaoProdest,
    OperacaoIntegracaoProdest,
    ResultadoIntegracaoProdest,
    StatusEventoOperacional,
    TipoCargaIntegracao,
    VisibilidadeEventoIntegracao,
)
from apps.carga_org_lot.realtime import publish_submission_update


@transaction.atomic
def record_operational_event(
    envio,
    *,
    code,
    phase,
    status,
    title,
    message,
    actor,
    details=None,
    deduplicate=True,
):
    """Persiste uma mudança compreensível; eventos técnicos ficam separados."""
    envio = type(envio).objects.select_for_update().select_related(
        "idimportacaoplanilha"
    ).get(pk=envio.pk)
    details = details or {}
    latest = EventoIntegracaoProdest.objects.filter(
        idenvioorganograma=envio,
        strvisibilidade=VisibilidadeEventoIntegracao.OPERACIONAL,
    ).first()
    if (
        deduplicate
        and latest
        and latest.strcodigo == code
        and latest.strstatusoperacional == status
        and latest.jsondetalhes == details
    ):
        return latest

    now = timezone.now()
    envio.strfaseatual = phase
    envio.strstatusoperacional = status
    envio.strmensagematual = message
    envio.datultimaatividade = now
    envio.updated_by_id = actor.user_id
    envio.updated_by_name = actor.user_name
    envio.save()
    event = EventoIntegracaoProdest.objects.create(
        idpatriarca_id=envio.idimportacaoplanilha.idpatriarca_id,
        idprocessocargainicial_id=envio.idprocessocargainicial_id,
        idenvioorganograma=envio,
        idexternocarga=envio.idexternocarga,
        strvisibilidade=VisibilidadeEventoIntegracao.OPERACIONAL,
        strtipocarga=TipoCargaIntegracao.ORGANOGRAMA,
        strfase=phase,
        strcodigo=code,
        strstatusoperacional=status,
        strtitulo=title,
        stroperacao=OperacaoIntegracaoProdest.FLUXO_OPERACIONAL,
        strmetodo="INTERNAL",
        strendpoint="local",
        strresultado=(
            ResultadoIntegracaoProdest.ERRO_HTTP
            if status == StatusEventoOperacional.ERRO
            else ResultadoIntegracaoProdest.SUCESSO
        ),
        strmensagem=message,
        jsondetalhes=details,
        created_by_id=actor.user_id,
        created_by_name=actor.user_name,
        updated_by_id=actor.user_id,
        updated_by_name=actor.user_name,
    )
    payload = {
        "tipo": "processo_atualizado",
        "processo": {
            "processo_id": envio.idprocessocargainicial_id,
            "patriarca_id": envio.idimportacaoplanilha.idpatriarca_id,
            "tipo_carga": TipoCargaIntegracao.ORGANOGRAMA,
            "envio_id": envio.pk,
            "fase_atual": phase,
            "fase_atual_nome": FaseIntegracaoProdest(phase).label,
            "status_atual": status,
            "status_atual_nome": StatusEventoOperacional(status).label,
            "mensagem_atual": message,
            "datultimaatividade": now.isoformat(),
            "ultimo_evento_id": event.pk,
        },
        "evento": {
            "idevento": event.pk,
            "fase": phase,
            "codigo": code,
            "status": status,
            "titulo": title,
            "mensagem": message,
            "datocorrencia": event.datocorrencia.isoformat(),
        },
    }
    publish_submission_update(
        payload,
        patriarch_id=envio.idimportacaoplanilha.idpatriarca_id,
        submission_id=envio.pk,
    )
    return event
