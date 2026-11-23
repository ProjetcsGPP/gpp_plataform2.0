"""Roteamento do piloto HTTP de identidade remota, no ponto de composição."""

from django.conf import settings


def carga_http_iam_remoto(caminho):
    """Restringe o bypass local ao prefixo exato da API de Carga."""
    return bool(
        settings.CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA
        and caminho.startswith("/api/carga-org-lot/")
    )
