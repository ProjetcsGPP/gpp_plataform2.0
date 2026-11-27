"""Prontidão local dos processos HTTP, sem decidir autorização de usuários."""

import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe


registrador = logging.getLogger("gpp.health")


def _resposta_prontidao(servico):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        # Não registrar a exceção: drivers podem incluir conninfo com senha.
        registrador.warning("READINESS_FAIL service=%s dependency=database", servico)
        situacao = "indisponivel"
        codigo_http = 503
    else:
        situacao = "pronto"
        codigo_http = 200

    resposta = JsonResponse(
        {"status": situacao, "service": servico}, status=codigo_http
    )
    resposta["Cache-Control"] = "no-store"
    return resposta


@require_safe
def prontidao_monolito(_request):
    """Banco local do processo único, sem consultar IAM ou fontes externas."""
    return _resposta_prontidao("gpp_plataform2")


@require_safe
def prontidao_carga(_request):
    """Prontidão do processo de Carga; IAM é dependência por operação."""
    return _resposta_prontidao("carga_org_lot")


@require_safe
def prontidao_plataforma(_request):
    """Prontidão do processo IAM/Portal autenticado."""
    return _resposta_prontidao("plataforma")


@require_safe
def prontidao_publicacoes(_request):
    """Não remover a API pública do ar por indisponibilidade do IAM."""
    return _resposta_prontidao("pub_institucional")


@require_safe
def prontidao_acoes(_request):
    """Prontidão local de Ações; decisões IAM pertencem a cada operação."""
    return _resposta_prontidao("acoes_pngi")
