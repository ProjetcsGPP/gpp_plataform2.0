"""Vivacidade local por processo; não substitui prontidão nem autorização."""

from django.http import JsonResponse


def _vivo(servico):
    resposta = JsonResponse({"status": "ok", "service": servico})
    resposta["Cache-Control"] = "no-store"
    return resposta


def carga_viva(_request):
    """Informa apenas que o processo HTTP de Carga respondeu."""
    return _vivo("carga_org_lot")


def plataforma_viva(_request):
    """Informa apenas que o processo HTTP da plataforma respondeu."""
    return _vivo("plataforma")


def publicacoes_vivas(_request):
    """Informa apenas que o processo HTTP de Publicações respondeu."""
    return _vivo("pub_institucional")
