"""Ensaio opt-in de Carga e plataforma HTTP em processos distintos.

Usa somente o PostgreSQL transacional de testes e portas efêmeras de loopback.
Não modifica o proxy, o launcher ou as flags da instalação em uso.
"""

import multiprocessing
from contextlib import contextmanager
from wsgiref.simple_server import make_server

import pytest
import requests
from django.core.handlers.wsgi import WSGIHandler
from django.db import connections
from django.test import override_settings

from apps.accounts.models import UserRole
from apps.accounts.tests.test_decisao_interna_banco import (
    CONFIGURACAO_TESTE,
    _sessao,
)
from config.settings import carga_piloto


def _servidor_perfil(canal, perfil, iam_url):
    """Inicia superfície HTTP específica, sem conexão herdada do pytest."""
    connections.close_all()
    servidor = None
    ajustes = {
        "ROOT_URLCONF": f"config.urls_{perfil}_piloto",
        "ALLOWED_HOSTS": ["127.0.0.1", "localhost"],
        "DEBUG": False,
        **CONFIGURACAO_TESTE,
    }
    if perfil == "carga":
        ajustes.update(
            MIDDLEWARE=carga_piloto.MIDDLEWARE,
            CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True,
            IAM_URL_CARGA=iam_url,
        )
    try:
        with override_settings(**ajustes):
            servidor = make_server("127.0.0.1", 0, WSGIHandler())
            servidor.timeout = 0.1
            canal.send(("PRONTO", servidor.server_port))
            while not canal.poll():
                servidor.handle_request()
    except Exception as exc:  # falha do subprocesso deve aparecer no teste
        canal.send(("ERRO", f"{type(exc).__name__}: {exc}"))
    finally:
        if servidor is not None:
            servidor.server_close()
        connections.close_all()
        canal.close()


@contextmanager
def _perfil_http(perfil, iam_url=""):
    connections.close_all()
    contexto = multiprocessing.get_context("fork")
    pai, filho = contexto.Pipe()
    processo = contexto.Process(
        target=_servidor_perfil,
        args=(filho, perfil, iam_url),
    )
    processo.start()
    filho.close()
    try:
        assert pai.poll(5), f"Servidor {perfil} não iniciou"
        estado, detalhe = pai.recv()
        assert estado == "PRONTO", detalhe
        yield f"http://127.0.0.1:{detalhe}"
    finally:
        if processo.is_alive():
            pai.send("PARAR")
        processo.join(timeout=5)
        if processo.is_alive():
            processo.terminate()
            processo.join(timeout=5)
        pai.close()
        assert processo.exitcode == 0


def _consultar(url, *, sessao=None):
    cookies = None
    if sessao is not None:
        cookies = {sessao.session_cookie_name: sessao.session_key}
    return requests.get(url, cookies=cookies, timeout=(1, 3))


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
def test_carga_independente_iam_e_api_publica(gestor_carga):
    sessao = _sessao(gestor_carga)
    with _perfil_http("plataforma") as plataforma:
        url_iam = f"{plataforma}/interno/iam/v1/decisoes/"
        url_publica = (
            f"{plataforma}/api/public/v1/"
            "publicacoes-institucionais/vigente/"
        )
        publica_antes = _consultar(url_publica)
        assert publica_antes.status_code in {200, 404}

        with _perfil_http("carga", url_iam) as carga:
            assert _consultar(f"{carga}/api/health/").json()[
                "service"
            ] == "carga_org_lot"
            autorizado = _consultar(
                f"{carga}/api/carga-org-lot/patriarcas/",
                sessao=sessao,
            )
            assert autorizado.status_code == 200
            assert _consultar(
                f"{carga}/api/carga-org-lot/patriarcas/"
            ).status_code == 401
            UserRole.objects.filter(
                user=gestor_carga,
                role__codigoperfil="GESTOR_CARGA",
            ).delete()
            revogado = _consultar(
                f"{carga}/api/carga-org-lot/patriarcas/",
                sessao=sessao,
            )
            assert revogado.status_code == 403
            assert revogado.json()["errors"]["code"] == "permission_denied"

        # O encerramento do processo Carga não interrompe a vitrine pública.
        publica_depois = _consultar(url_publica)
        assert publica_depois.status_code == publica_antes.status_code
        assert publica_depois.content == publica_antes.content
        assert _consultar(f"{plataforma}/api/health/").json()[
            "service"
        ] == "plataforma"

    # Carga continua viva, mas a operação protegida falha fechada sem IAM.
    with _perfil_http("carga", url_iam) as carga:
        assert _consultar(f"{carga}/api/health/").status_code == 200
        indisponivel = _consultar(
            f"{carga}/api/carga-org-lot/patriarcas/",
            sessao=sessao,
        )
        assert indisponivel.status_code == 503
        assert indisponivel.json()["errors"]["code"] == (
            "servico_iam_indisponivel"
        )
        assert "Set-Cookie" not in indisponivel.headers
