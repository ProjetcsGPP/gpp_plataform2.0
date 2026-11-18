"""Notificações resumidas da integração E-Docs; o banco segue canônico."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)

GRUPO_EDOCS = "pub_institucional.edocs"


def publicar_evento_edocs(evento: str, dados: dict) -> None:
    """Publica após commit, sem transformar WebSocket em fonte de verdade."""

    def _publicar():
        camada_canais = get_channel_layer()
        if camada_canais is None:
            return
        try:
            async_to_sync(camada_canais.group_send)(
                GRUPO_EDOCS,
                {
                    "type": "publicacoes.evento",
                    "evento": evento,
                    "dados": dados,
                },
            )
        except Exception:  # pragma: no cover - disponibilidade não afeta o dado
            logger.exception("Falha ao publicar evento resumido do E-Docs")

    transaction.on_commit(_publicar)
