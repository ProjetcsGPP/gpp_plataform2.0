"""Visibilidade de revogações para uma decisão IAM em outro processo.

Usa o banco transacional de testes, nunca o banco operacional. O processo
IAM mantém sua própria conexão PostgreSQL entre as decisões.
"""

import multiprocessing
from contextlib import contextmanager

import pytest
from django.db import connections, transaction
from django.test import Client, override_settings

from apps.accounts.models import UserRole
from apps.accounts.tests.test_decisao_interna_banco import (
    CAMINHO,
    CONFIGURACAO_TESTE,
    PERMISSAO,
    TOKEN_TESTE,
    _sessao,
)


def _processo_iam(canal, cookie, chave_sessao):
    """Responde a consultas em conexão própria, sem herdar a conexão do pai."""
    connections.close_all()
    try:
        while canal.recv() == "CONSULTAR":
            resposta = Client().post(
                CAMINHO,
                data={
                    "acao": PERMISSAO,
                    "credenciais_usuario": [
                        {"nome_cookie": cookie, "valor": chave_sessao}
                    ],
                },
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {TOKEN_TESTE}",
            )
            canal.send((resposta.status_code, resposta.json()))
    finally:
        connections.close_all()
        canal.close()


@contextmanager
def _iam_em_outro_processo(sessao):
    """Fecha conexões herdáveis antes do fork e garante limpeza do filho."""
    connections.close_all()
    contexto = multiprocessing.get_context("fork")
    pai, filho = contexto.Pipe()
    processo = contexto.Process(
        target=_processo_iam,
        args=(filho, sessao.session_cookie_name, sessao.session_key),
    )
    processo.start()
    filho.close()
    try:
        yield pai
    finally:
        if processo.is_alive():
            pai.send("PARAR")
        processo.join(timeout=5)
        if processo.is_alive():
            processo.terminate()
            processo.join(timeout=5)
        pai.close()
        assert processo.exitcode == 0


def _resultado(canal):
    canal.send("CONSULTAR")
    assert canal.poll(5), "Processo IAM não respondeu dentro do prazo"
    codigo, corpo = canal.recv()
    assert codigo == 200
    return corpo["resultado"]


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("revogacao", ["role", "permissao"])
@override_settings(**CONFIGURACAO_TESTE)
def test_revogacao_confirmada_visivel_em_outro_processo(gestor_carga, revogacao):
    """Uma decisão nova vê o commit; uma mudança não confirmada não vaza."""
    sessao = _sessao(gestor_carga)
    with _iam_em_outro_processo(sessao) as canal:
        assert _resultado(canal) == "AUTORIZADO"

        with transaction.atomic():
            if revogacao == "role":
                UserRole.objects.filter(
                    user=gestor_carga, role__codigoperfil="GESTOR_CARGA"
                ).delete()
            else:
                gestor_carga.user_permissions.through.objects.filter(
                    user_id=gestor_carga.pk,
                    permission__codename=PERMISSAO,
                ).delete()
            assert _resultado(canal) == "AUTORIZADO"

        assert _resultado(canal) == "NEGADO"
