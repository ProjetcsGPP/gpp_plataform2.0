"""Reserva durável de uma tentativa externa de envio do organograma."""

from django.db import transaction

from apps.carga_org_lot.models import (
    EnvioOrganogramaProdest,
    EventoIntegracaoProdest,
    FaseIntegracaoProdest,
    StatusEnvioOrganograma,
    StatusEventoOperacional,
)

from .integration_events import record_operational_event
from .workflow import AuditActor


def reservar_tentativa_externa(envio_id: int, actor: AuditActor) -> str | None:
    """Garante que apenas uma execução possa iniciar contato com a PRODEST.

    A reserva de cinco minutos da task é só agendamento; esta marca durável
    impede reenvio mesmo quando o primeiro worker ainda está em voo ou caiu.
    """
    with transaction.atomic():
        envio = EnvioOrganogramaProdest.objects.select_for_update().get(
            pk=envio_id
        )
        if envio.strstatus != StatusEnvioOrganograma.SOLICITANDO:
            return "estado_alterado"
        if EventoIntegracaoProdest.objects.filter(
            idenvioorganograma_id=envio_id,
            strcodigo="ENVIO_EXTERNO_INICIADO",
        ).exists():
            record_operational_event(
                envio,
                code="REENVIO_AUTOMATICO_BLOQUEADO",
                phase=FaseIntegracaoProdest.ENVIO,
                status=StatusEventoOperacional.AVISO,
                title="Reenvio automático bloqueado",
                message=(
                    "Já existe uma tentativa externa iniciada sem conclusão "
                    "local. Verifique a situação antes de qualquer novo envio."
                ),
                actor=AuditActor(user_name="Serviço IAM / Carga"),
                details={"tentativa_externa_iniciada": True},
            )
            return "tentativa_externa_ja_iniciada"
        record_operational_event(
            envio,
            code="ENVIO_EXTERNO_INICIADO",
            phase=FaseIntegracaoProdest.ENVIO,
            status=StatusEventoOperacional.EM_ANDAMENTO,
            title="Iniciando envio à PRODEST",
            message=(
                "A tentativa de envio externo foi iniciada. O aceite pela "
                "PRODEST ainda não está confirmado."
            ),
            actor=actor,
            deduplicate=False,
        )
    return None
