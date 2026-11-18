"""Valores de eventos preparados para apresentação a usuários."""

from datetime import UTC

from django.utils import timezone
from django.utils.dateparse import parse_datetime


PRODEST_UPDATED_AT_KEY = "ultima_atualizacao_prodest"


def build_display_details(details: dict | None) -> dict:
    """Copia detalhes técnicos e converte datas conhecidas para o fuso local."""
    display_details = dict(details or {})
    raw_updated_at = display_details.get(PRODEST_UPDATED_AT_KEY)
    if not isinstance(raw_updated_at, str) or not raw_updated_at:
        return display_details

    try:
        updated_at = parse_datetime(raw_updated_at)
    except ValueError:
        updated_at = None
    if updated_at is None:
        return display_details
    if timezone.is_naive(updated_at):
        updated_at = updated_at.replace(tzinfo=UTC)

    display_details[PRODEST_UPDATED_AT_KEY] = timezone.localtime(
        updated_at
    ).strftime("%d/%m/%Y %H:%M:%S")
    return display_details
