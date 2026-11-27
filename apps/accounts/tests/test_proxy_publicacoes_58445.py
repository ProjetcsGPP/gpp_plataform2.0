"""Ensaio local opt-in do proxy alternativo real, sem cutover.

Uso: GPP_ENSAIO_PROXY_PUBLICACOES_58445=1 pytest -q -o addopts='' --tb=line \
    --reuse-db apps/accounts/tests/test_proxy_publicacoes_58445.py

Usa apenas o banco permanente de testes e ASGI com identidades sintéticas.
Não inicia Beat, worker ou chamada a E-Docs/PRODEST.
"""

import os
import socket
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path

import pytest
import requests
from django.db import connection

from apps.accounts.tests.test_decisao_publicacoes_interna import (  # pylint: disable=unused-import
    sessao_publicacoes,
)
from apps.accounts.tests.test_decisao_interna_banco import _sessao
from apps.accounts.tests.test_isolamento_asgi_proxy import _perfil_asgi, _websocket


INFRA = Path(__file__).resolve().parents[3] / "infra/publicacoes-dev"
PORTA_PROXY = 58445
PORTAS_APLICACAO = (8000, 8001, 8002)
ORIGEM = f"https://localhost:{PORTA_PROXY}"
CERTIFICADO = INFRA / "runtime/tls/dev.crt"


def _compose(*argumentos):
    comando = [
        "docker", "compose", "--project-directory", str(INFRA),
        "-f", str(INFRA / "compose-isolamento-tres.yaml"), *argumentos,
    ]
    return subprocess.run(
        comando, capture_output=True, text=True, check=False, timeout=30,
    )


def _porta_livre(porta):
    with socket.socket() as canal:
        try:
            canal.bind(("127.0.0.1", porta))
        except OSError:
            return False
    return True


@pytest.mark.skipif(
    os.environ.get("GPP_ENSAIO_PROXY_PUBLICACOES_58445") != "1",
    reason="Ensaio Docker local opt-in; não participa da suíte padrão",
)
@pytest.mark.django_db(transaction=True)
def test_proxy_alternativo_58445_sem_corte(  # pylint: disable=too-many-locals,too-many-statements
    tmp_path, sessao_publicacoes, gestor_carga
):
    """Confere roteamento e falha IAM no proxy real mantendo 58443 intacto."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    assert CERTIFICADO.is_file(), "Certificado local da sandbox ausente"
    ocupadas = [
        porta for porta in (*PORTAS_APLICACAO, PORTA_PROXY)
        if not _porta_livre(porta)
    ]
    assert not ocupadas, f"Portas do ensaio ocupadas: {ocupadas}"
    existentes = _compose("ps", "-q", "-a")
    assert existentes.returncode == 0, existentes.stderr
    assert not existentes.stdout.strip(), "Projeto Docker do ensaio já existe"

    banco = "test_gpp_plataform"
    sessao_carga = _sessao(gestor_carga)
    with ExitStack() as processos:
        with ExitStack() as processo_iam:
            origem_iam = processo_iam.enter_context(_perfil_asgi(
                "plataforma_separada", 8000, PORTA_PROXY, banco, "", tmp_path,
            ))
            origem_carga = processos.enter_context(_perfil_asgi(
                "carga", 8001, PORTA_PROXY, banco,
                f"{origem_iam}/interno/iam/v1/decisoes/", tmp_path,
            ))
            origem_publicacoes = processos.enter_context(_perfil_asgi(
                "publicacoes", 8002, PORTA_PROXY, banco,
                f"{origem_iam}/interno/iam/v1/decisoes-publicacoes/", tmp_path,
            ))
            assert origem_carga.endswith(":8001")
            assert origem_publicacoes.endswith(":8002")
            try:
                iniciado = _compose("up", "-d", "--no-deps", "--pull", "never", "proxy")
                assert iniciado.returncode == 0, iniciado.stderr
                for _ in range(50):
                    try:
                        saude = requests.get(
                            f"{ORIGEM}/infra/healthz", verify=str(CERTIFICADO),
                            timeout=0.5,
                        )
                        if saude.status_code == 200:
                            break
                    except requests.RequestException:
                        time.sleep(0.1)
                else:
                    pytest.fail("Proxy alternativo não ficou saudável")

                def consultar(caminho, *, autenticado=False):
                    cookies = None
                    if autenticado:
                        cookies = {
                            sessao_publicacoes.session_cookie_name:
                            sessao_publicacoes.session_key,
                        }
                    return requests.get(
                        f"{ORIGEM}{caminho}", cookies=cookies,
                        verify=str(CERTIFICADO), timeout=8,
                    )

                assert consultar("/api/health/").json()["service"] == "plataforma"
                assert consultar("/api/carga-org-lot/health/").json()["service"] == "carga_org_lot"
                assert consultar("/api/pub-institucional/health/").json()["service"] == "pub_institucional"
                assert consultar("/interno/iam/v1/decisoes-publicacoes/").status_code == 404
                recurso = "/api/pub-institucional/patriarcas/"
                publica = "/api/public/v1/publicacoes-institucionais/vigente/"
                assert consultar(recurso, autenticado=True).status_code == 200
                recurso_carga = "/api/carga-org-lot/patriarcas/"
                cookies_carga = {
                    sessao_carga.session_cookie_name: sessao_carga.session_key,
                }
                assert requests.get(
                    f"{ORIGEM}{recurso_carga}", cookies=cookies_carga,
                    verify=str(CERTIFICADO), timeout=8,
                ).status_code == 200
                assert _websocket(
                    ORIGEM, str(CERTIFICADO), "/ws/pub-institucional/edocs/",
                    sessao_publicacoes,
                ) == 101
                assert _websocket(
                    ORIGEM, str(CERTIFICADO), "/ws/carga-org-lot/dashboard/",
                    sessao_carga,
                ) == 101
                status_publico = consultar(publica).status_code
                assert status_publico in {200, 404}

                processo_iam.close()
                falha = consultar(recurso, autenticado=True)
                assert falha.status_code == 503
                assert falha.json()["errors"]["code"] == "servico_iam_indisponivel"
                falha_carga = requests.get(
                    f"{ORIGEM}{recurso_carga}", cookies=cookies_carga,
                    verify=str(CERTIFICADO), timeout=8,
                )
                assert falha_carga.status_code == 503
                assert falha_carga.json()["errors"]["code"] == (
                    "servico_iam_indisponivel"
                )
                assert consultar(publica).status_code == status_publico
                assert consultar("/api/carga-org-lot/health/").status_code == 200
            finally:
                encerrado = _compose("down")
                assert encerrado.returncode == 0, encerrado.stderr
