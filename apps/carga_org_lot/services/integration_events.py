from django.db import transaction
from django.utils import timezone

from apps.carga_org_lot.models import (
    EventoIntegracaoProdest,
    OperacaoIntegracaoProdest,
    ResultadoIntegracaoProdest,
    StatusEventoOperacional,
    TipoCargaIntegracao,
    VisibilidadeEventoIntegracao,
)
from apps.carga_org_lot.realtime import publish_submission_update
from apps.carga_org_lot.services.integration_event_presentation import (
    build_display_details,
)
from apps.carga_org_lot.services.submission_workflow import (
    build_submission_workflow,
)


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
    method="INTERNAL",
    endpoint="local",
    http_status=None,
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
        and latest.strmetodo == method
        and latest.strendpoint == endpoint
        and latest.inthttpstatus == http_status
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
        strmetodo=method,
        strendpoint=endpoint,
        strresultado=(
            ResultadoIntegracaoProdest.ERRO_HTTP
            if status == StatusEventoOperacional.ERRO
            else ResultadoIntegracaoProdest.SUCESSO
        ),
        inthttpstatus=http_status,
        strmensagem=message,
        jsondetalhes=details,
        created_by_id=actor.user_id,
        created_by_name=actor.user_name,
        updated_by_id=actor.user_id,
        updated_by_name=actor.user_name,
    )
    workflow = build_submission_workflow(envio)
    payload = {
        "tipo": "processo_atualizado",
        "processo": {
            "processo_id": envio.idprocessocargainicial_id,
            "patriarca_id": envio.idimportacaoplanilha.idpatriarca_id,
            "tipo_carga": TipoCargaIntegracao.ORGANOGRAMA,
            "envio_id": envio.pk,
            "fase_atual": workflow["fase_atual"],
            "fase_atual_nome": workflow["fase_atual_nome"],
            "status_atual": workflow["status_atual"],
            "status_atual_nome": workflow["status_atual_nome"],
            "mensagem_atual": workflow["mensagem_atual"],
            "fluxo_operacional": workflow,
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
            "detalhes": details,
            "detalhes_exibicao": build_display_details(details),
            "datocorrencia": event.datocorrencia.isoformat(),
        },
    }
    publish_submission_update(
        payload,
        patriarch_id=envio.idimportacaoplanilha.idpatriarca_id,
        submission_id=envio.pk,
    )
    return event
