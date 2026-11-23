"""Ensaio HTTP local de Carga e IAM em processos distintos.

O servidor IAM usa o banco transacional de testes. Não faz cutover de rota,
não ativa flags fora do teste e não cria serviço operacional.
"""

import multiprocessing
from contextlib import contextmanager
from types import SimpleNamespace
from wsgiref.simple_server import make_server

import pytest
from django.core.handlers.wsgi import WSGIHandler
from django.db import connections
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Aplicacao
from apps.accounts.tests.test_decisao_interna_banco import (
    CONFIGURACAO_TESTE,
    PERMISSAO,
    _sessao,
)
from apps.carga_org_lot.permissoes_iam import (
    CanPermissionCarga,
    ServicoIAMIndisponivel,
    SessaoCargaInvalida,
)


def _servidor_iam(canal):
    """Serve requisições reais em loopback com uma conexão DB independente."""
    connections.close_all()
    servidor = None
    try:
        servidor = make_server("127.0.0.1", 0, WSGIHandler())
        servidor.timeout = 0.1
        canal.send(("PRONTO", servidor.server_port))
        while not canal.poll():
            servidor.handle_request()
    except Exception as exc:  # observabilidade da fronteira do processo de teste
        canal.send(("ERRO", type(exc).__name__))
    finally:
        if servidor is not None:
            servidor.server_close()
        connections.close_all()
        canal.close()


@contextmanager
def _iam_http():
    """Inicia e encerra o servidor sem deixar processo ou porta pendente."""
    connections.close_all()
    contexto = multiprocessing.get_context("fork")
    pai, filho = contexto.Pipe()
    processo = contexto.Process(target=_servidor_iam, args=(filho,))
    processo.start()
    filho.close()
    try:
        assert pai.poll(5), "Servidor IAM de teste não iniciou"
        estado, valor = pai.recv()
        assert estado == "PRONTO", f"Servidor IAM de teste falhou: {valor}"
        yield f"http://127.0.0.1:{valor}/interno/iam/v1/decisoes/"
    finally:
        if processo.is_alive():
            pai.send("PARAR")
        processo.join(timeout=5)
        if processo.is_alive():
            processo.terminate()
            processo.join(timeout=5)
        pai.close()
        assert processo.exitcode == 0


def _guardar_carga(usuario, sessao):
    requisicao = APIRequestFactory().get("/api/carga-org-lot/dashboard/")
    requisicao.user = usuario
    requisicao.application = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
    if sessao is not None:
        requisicao.COOKIES[sessao.session_cookie_name] = sessao.session_key
    visao = SimpleNamespace(required_permission=PERMISSAO, permission_context=None)
    return CanPermissionCarga().has_permission(requisicao, visao)


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@override_settings(
    **CONFIGURACAO_TESTE,
    CARGA_IAM_DECISAO_REMOTA_ATIVA=True,
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"],
)
def test_piloto_http_entre_processos_e_reversao(gestor_carga, usuario_sem_role):
    sessao = _sessao(gestor_carga)
    with _iam_http() as url:
        with override_settings(IAM_URL_CARGA=url):
            assert _guardar_carga(gestor_carga, sessao) is True

            with override_settings(IAM_TOKEN_SERVICO_CARGA=""):
                with pytest.raises(ServicoIAMIndisponivel):
                    _guardar_carga(gestor_carga, sessao)

            # Token presente, porém diferente do recebido pelo processo IAM.
            with override_settings(IAM_TOKEN_SERVICO_CARGA="x" * 32):
                with pytest.raises(ServicoIAMIndisponivel):
                    _guardar_carga(gestor_carga, sessao)

            with pytest.raises(ServicoIAMIndisponivel):
                _guardar_carga(usuario_sem_role, sessao)

            with pytest.raises(SessaoCargaInvalida):
                _guardar_carga(gestor_carga, None)

    # O destino ficou inacessível: não há fallback implícito para a decisão local.
    with override_settings(IAM_URL_CARGA=url):
        with pytest.raises(ServicoIAMIndisponivel):
            _guardar_carga(gestor_carga, sessao)

        # Reversão explícita da flag restaura o comportamento anterior.
        with override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=False):
            assert _guardar_carga(gestor_carga, sessao) is True
