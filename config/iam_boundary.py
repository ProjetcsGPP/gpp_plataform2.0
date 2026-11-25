"""Roteamento do piloto HTTP de identidade remota, no ponto de composição."""

from django.conf import settings


def carga_http_iam_remoto(caminho):
    """Restringe o bypass local ao prefixo exato da API de Carga."""
    return bool(
        settings.CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA
        and caminho.startswith("/api/carga-org-lot/")
    )


def publicacoes_http_iam_remoto(caminho):
    """Restringe o IAM remoto à API administrativa, nunca à API pública."""
    return bool(
        settings.PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA
        and caminho.startswith("/api/pub-institucional/")
    )


def dominio_http_iam_remoto(caminho):
    """Retorna o código do domínio remoto ou None para o fluxo local."""
    if carga_http_iam_remoto(caminho):
        return "CARGA_ORG_LOT"
    if publicacoes_http_iam_remoto(caminho):
        return "PUB_INSTITUCIONAL"
    return None
