"""Testes do cliente compartilhado de localidades do IBGE."""

from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from requests import RequestException

from common.services.ibge import (ClienteIbge, ErroIbge, listar_estados_ibge,
                                  listar_municipios_ibge)


@pytest.fixture(autouse=True)
def limpar_cache_ibge():
    cache.delete("common:ibge:localidades:estados:v1")
    for codigo_uf in (31, 32):
        cache.delete(
            f"common:ibge:localidades:municipios:{codigo_uf}:v1"
        )


def _sessao_com_resposta(dados):
    resposta = Mock()
    resposta.raise_for_status.return_value = None
    resposta.json.return_value = dados
    sessao = Mock()
    sessao.get.return_value = resposta
    return sessao


def test_lista_estados_normalizada_e_cacheada():
    sessao = _sessao_com_resposta(
        [
            {
                "id": 32,
                "sigla": "ES",
                "nome": "Espírito Santo",
                "regiao": {
                    "id": 3,
                    "sigla": "SE",
                    "nome": "Sudeste",
                },
            }
        ]
    )
    cliente = ClienteIbge(sessao=sessao)

    primeira = listar_estados_ibge(cliente=cliente)
    segunda = listar_estados_ibge(cliente=cliente)

    assert primeira == segunda
    assert primeira[0]["id"] == 32
    sessao.get.assert_called_once()
    assert sessao.get.call_args.kwargs["params"] == {"orderBy": "nome"}


@patch("common.services.ibge.cache.set", wraps=cache.set)
def test_lista_municipios_da_uf_normalizada_e_cacheada_sem_expiracao(
    gravar_cache,
):
    sessao = _sessao_com_resposta(
        [{"id": 3200102, "nome": "Afonso Cláudio"}]
    )
    cliente = ClienteIbge(sessao=sessao)

    primeira = listar_municipios_ibge(32, cliente=cliente)
    segunda = listar_municipios_ibge(32, cliente=cliente)

    assert primeira == [
        {"id": 3200102, "nome": "Afonso Cláudio", "codigo_uf": 32}
    ]
    assert segunda == primeira
    sessao.get.assert_called_once()
    gravar_cache.assert_called_once_with(
        "common:ibge:localidades:municipios:32:v1",
        primeira,
        timeout=None,
    )
    assert sessao.get.call_args.args[0].endswith(
        "/api/v1/localidades/estados/32/municipios"
    )


@pytest.mark.parametrize("codigo_uf", [True, "32", 0, 100])
def test_rejeita_codigo_uf_invalido(codigo_uf):
    with pytest.raises(ValueError):
        listar_municipios_ibge(codigo_uf)


def test_converte_falha_remota_em_erro_estavel():
    sessao = Mock()
    sessao.get.side_effect = RequestException("falha de rede")

    with pytest.raises(ErroIbge, match="indisponível"):
        ClienteIbge(sessao=sessao).listar_estados()


def test_rejeita_resposta_fora_do_contrato():
    sessao = _sessao_com_resposta({"id": 32})

    with pytest.raises(ErroIbge, match="formato"):
        ClienteIbge(sessao=sessao).listar_estados()
