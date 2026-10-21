import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)


def publish_submission_update(payload, *, patriarch_id, submission_id):
    """Publica somente depois do commit; o banco continua sendo autoritativo."""

    def send():
        try:
            layer = get_channel_layer()
            message = {"type": "carga.event", "payload": payload}
            for group in (
                "carga_org_lot.dashboard",
                f"carga_org_lot.patriarca.{patriarch_id}",
                f"carga_org_lot.envio.{submission_id}",
            ):
                async_to_sync(layer.group_send)(group, message)
        except Exception:  # pragma: no cover - indisponibilidade externa
            logger.exception(
                "Falha ao publicar atualização em tempo real do envio %s",
                submission_id,
            )

    transaction.on_commit(send)
