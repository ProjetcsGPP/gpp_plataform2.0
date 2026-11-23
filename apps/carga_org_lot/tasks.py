import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    EnvioOrganogramaProdest,
    FaseIntegracaoProdest,
    StatusEnvioOrganograma,
    StatusEventoOperacional,
)
from .services.integration_events import record_operational_event
from .services.cliente_iam import (
    IAMIndisponivel,
    PermissaoIAMNegada,
    decidir_atividade_remota,
)
from .services.organogram_submission import (
    OrganogramSubmissionError,
    encerrar_atividade_por_revogacao,
    execute_organogram_submission,
    refresh_submission_status,
)
from .services.workflow import AuditActor

logger = logging.getLogger(__name__)


def _actor(envio):
    return AuditActor(envio.created_by_id, envio.created_by_name)


def _revalidar_atividade(envio):
    if not settings.CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS:
        return "AUTORIZADO"
    try:
        decidir_atividade_remota(
            usuario_id=envio.created_by_id,
            permissao="change_importacaoplanilha",
            correlacao=f"envio-org-{envio.pk}",
        )
    except PermissaoIAMNegada:
        encerrar_atividade_por_revogacao(envio.pk)
        return "REVOGADO"
    except IAMIndisponivel:
        intervalo = settings.CARGA_ORG_LOT_MONITOR_INTERVAL_SECONDS
        EnvioOrganogramaProdest.objects.filter(
            pk=envio.pk,
            strstatus__in=[
                StatusEnvioOrganograma.SOLICITANDO,
                StatusEnvioOrganograma.PROCESSANDO,
            ],
        ).update(datproximaconsulta=timezone.now() + timedelta(seconds=intervalo))
        record_operational_event(
            envio,
            code="IAM_INDISPONIVEL_ATIVIDADE",
            phase=(
                FaseIntegracaoProdest.PREPARACAO
                if envio.strstatus == StatusEnvioOrganograma.SOLICITANDO
                else FaseIntegracaoProdest.PROCESSAMENTO
            ),
            status=StatusEventoOperacional.AVISO,
            title="Aguardando autorização do IAM",
            message=(
                "A autorização não pôde ser revalidada. Nenhuma nova ação "
                "externa será iniciada até a comunicação ser restabelecida."
            ),
            actor=AuditActor(user_name="Serviço IAM / Carga"),
            details={"solicitante_id": envio.created_by_id},
        )
        return "IAM_INDISPONIVEL"
    return "AUTORIZADO"


@shared_task(name="carga_org_lot.processar_envio_organograma")
def processar_envio_organograma(envio_id):  # pylint: disable=too-many-return-statements
    now = timezone.now()
    with transaction.atomic():
        envio = EnvioOrganogramaProdest.objects.select_for_update().get(
            pk=envio_id
        )
        if envio.strstatus not in {
            StatusEnvioOrganograma.SOLICITANDO,
            StatusEnvioOrganograma.PROCESSANDO,
        }:
            return {"ignorado": True}
        if envio.datproximaconsulta and envio.datproximaconsulta > now:
            return {"ignorado": True, "motivo": "ainda_nao_vencido"}
        envio.datproximaconsulta = now + timedelta(minutes=5)
        envio.save(update_fields=["datproximaconsulta", "updated_at"])

    envio = EnvioOrganogramaProdest.objects.select_related(
        "idimportacaoplanilha__idpatriarca",
        "idprocessocargainicial",
    ).get(pk=envio_id)
    actor = _actor(envio)
    decisao = _revalidar_atividade(envio)
    if decisao != "AUTORIZADO":
        return {"processado": False, "motivo": decisao}
    try:
        if envio.strstatus == StatusEnvioOrganograma.SOLICITANDO:
            execute_organogram_submission(envio, actor=actor)
            # A resposta da PRODEST é persistida pela função acima antes de
            # qualquer nova decisão. Se a revogação ocorreu durante a chamada,
            # encerra-se somente o acompanhamento local.
            envio.refresh_from_db()
            if envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA:
                return {"processado": False, "motivo": "ATIVIDADE_ENCERRADA"}
            decisao = _revalidar_atividade(envio)
            if decisao != "AUTORIZADO":
                return {"processado": False, "motivo": decisao}
        else:
            refresh_submission_status(envio, actor=actor)
            envio.refresh_from_db()
            if envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA:
                return {"processado": False, "motivo": "ATIVIDADE_ENCERRADA"}
            if envio.strstatus == StatusEnvioOrganograma.PROCESSANDO:
                decisao = _revalidar_atividade(envio)
                if decisao != "AUTORIZADO":
                    return {"processado": False, "motivo": decisao}
    except OrganogramSubmissionError as exc:
        envio.refresh_from_db()
        if envio.strstatus == StatusEnvioOrganograma.PROCESSANDO:
            envio.datproximaconsulta = timezone.now() + timedelta(
                seconds=settings.CARGA_ORG_LOT_MONITOR_INTERVAL_SECONDS
            )
            envio.save(update_fields=["datproximaconsulta", "updated_at"])
            record_operational_event(
                envio,
                code="CONSULTA_TEMPORARIAMENTE_INDISPONIVEL",
                phase=FaseIntegracaoProdest.PROCESSAMENTO,
                status=StatusEventoOperacional.AVISO,
                title="Consulta temporariamente indisponível",
                message=str(exc),
                actor=actor,
                details={"tipo": exc.kind},
            )
        logger.warning("Falha ao processar envio %s: %s", envio_id, exc)
        return {"erro": str(exc)}
    return {"processado": True}


@shared_task(name="carga_org_lot.monitorar_envios_organograma")
def monitorar_envios_organograma():
    now = timezone.now()
    ids = list(
        EnvioOrganogramaProdest.objects.filter(
            strstatus__in=[
                StatusEnvioOrganograma.SOLICITANDO,
                StatusEnvioOrganograma.PROCESSANDO,
            ]
        )
        .filter(Q(datproximaconsulta__isnull=True) | Q(datproximaconsulta__lte=now))
        .values_list("pk", flat=True)
    )
    for envio_id in ids:
        processar_envio_organograma.delay(envio_id)
    return {"agendados": len(ids)}
