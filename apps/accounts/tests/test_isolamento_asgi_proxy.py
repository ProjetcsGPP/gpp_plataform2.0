"""Ensaio de perfis ASGI reais via proxy TLS e banco permanente de testes."""

import base64
import os
import socket
import ssl
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager

import pytest
import requests
from django.db import connection

from apps.accounts.tests.test_decisao_interna_banco import _sessao
from apps.accounts.tests.test_isolamento_proxy_tls import _porta_livre, _proxy_tls


@contextmanager
def _perfil_asgi(perfil, porta, porta_proxy, banco, iam_url, tmp_path):
    ambiente = os.environ.copy()
    ambiente.update({
        "GPP_ENSAIO_TEST_DB_NAME": banco,
        "GPP_ENSAIO_IAM_URL": iam_url,
    })
    caminho_log = tmp_path / f"asgi-{perfil}.log"
    with caminho_log.open("w", encoding="utf-8") as log:
        processo = subprocess.Popen(
            [sys.executable, "-m", "apps.accounts.tests.asgi_ensaio_runner",
             perfil, str(porta), str(porta_proxy)],
            env=ambiente, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            origem = f"http://127.0.0.1:{porta}"
            for _ in range(100):
                if processo.poll() is not None:
                    break
                try:
                    if requests.get(f"{origem}/api/health/", timeout=0.3).status_code == 200:
                        yield origem
                        return
                except requests.RequestException:
                    time.sleep(0.1)
            raise AssertionError(
                f"ASGI {perfil} não iniciou: {caminho_log.read_text(encoding='utf-8')[-3000:]}"
            )
        finally:
            if processo.poll() is None:
                processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)


def _websocket(origem, certificado, caminho, cookie=None):
    porta = int(origem.rsplit(":", 1)[1])
    contexto = ssl.create_default_context(cafile=certificado)
    with socket.create_connection(("127.0.0.1", porta), timeout=5) as bruto:
        with contexto.wrap_socket(bruto, server_hostname="localhost") as canal:
            canal.settimeout(8)
            chave = base64.b64encode(os.urandom(16)).decode("ascii")
            linhas = [
                f"GET {caminho} HTTP/1.1", f"Host: localhost:{porta}",
                "Upgrade: websocket", "Connection: Upgrade",
                f"Sec-WebSocket-Key: {chave}", "Sec-WebSocket-Version: 13",
                f"Origin: {origem}",
            ]
            if cookie:
                linhas.append(f"Cookie: {cookie.session_cookie_name}={cookie.session_key}")
            canal.sendall(("\r\n".join(linhas) + "\r\n\r\n").encode("ascii"))
            resposta = b""
            while b"\r\n\r\n" not in resposta and len(resposta) < 16384:
                parte = canal.recv(4096)
                if not parte:
                    break
                resposta += parte
            return int(resposta.split(b" ", 2)[1])


@pytest.mark.django_db(transaction=True)
def test_asgi_proxy_tls_http_websocket_csrf_e_isolamento(tmp_path, gestor_carga):
    """Executa perfis reais sem tocar nos serviços, banco ou proxy operacionais."""
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform", "Ensaio reservado ao banco permanente de testes"
    sessao = _sessao(gestor_carga)
    porta_proxy, porta_plataforma, porta_carga = (
        _porta_livre(), _porta_livre(), _porta_livre()
    )
    with ExitStack() as pilha:
        plataforma = pilha.enter_context(_perfil_asgi(
            "plataforma", porta_plataforma, porta_proxy, banco, "", tmp_path
        ))
        carga = pilha.enter_context(_perfil_asgi(
            "carga", porta_carga, porta_proxy, banco,
            f"{plataforma}/interno/iam/v1/decisoes/", tmp_path
        ))
        origem, certificado = pilha.enter_context(_proxy_tls(
            tmp_path, plataforma, carga, "nginx-isolamento-loopback.conf",
            porta=porta_proxy,
        ))
        recurso = f"{origem}/api/carga-org-lot/patriarcas/"
        autorizado = requests.get(
            recurso, cookies={sessao.session_cookie_name: sessao.session_key},
            verify=certificado, timeout=8,
        )
        assert autorizado.status_code == 200, autorizado.text[:500]
        assert requests.get(recurso, verify=certificado, timeout=8).status_code == 401
        assert requests.get(
            f"{origem}/api/health/", verify=certificado, timeout=8
        ).json()["service"] == "plataforma"
        assert requests.get(
            f"{origem}/api/carga-org-lot/health/", verify=certificado, timeout=8
        ).json()["service"] == "carga_org_lot"
        assert _websocket(
            origem, certificado, "/ws/carga-org-lot/dashboard/", sessao
        ) == 101
        assert _websocket(
            origem, certificado, "/ws/carga-org-lot/dashboard/"
        ) == 403

        navegador = requests.Session()
        navegador.verify = certificado
        csrf = navegador.get(f"{origem}/api/accounts/auth/csrf/", timeout=8)
        assert csrf.status_code == 200
        token = navegador.cookies.get("csrftoken")
        assert token
        sem_csrf = navegador.post(
            f"{origem}/api/accounts/login/", json={}, timeout=8
        )
        assert sem_csrf.status_code == 403
        com_csrf = navegador.post(
            f"{origem}/api/accounts/login/", json={},
            headers={"X-CSRFToken": token, "Referer": f"{origem}/portal/"},
            timeout=8,
        )
        assert com_csrf.status_code in {400, 401}, com_csrf.text[:500]

        assert requests.get(
            f"{origem}/interno/iam/v1/decisoes/",
            verify=certificado, timeout=8,
        ).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_asgi_proxy_isola_parada_da_carga_e_falha_do_iam(tmp_path, gestor_carga):
    """Falhas parciais não expõem dados nem derrubam a API pública da plataforma."""
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform"
    sessao = _sessao(gestor_carga)
    porta_proxy, porta_plataforma, porta_carga = (
        _porta_livre(), _porta_livre(), _porta_livre()
    )
    with ExitStack() as pilha_plataforma:
        plataforma = pilha_plataforma.enter_context(_perfil_asgi(
            "plataforma", porta_plataforma, porta_proxy, banco, "", tmp_path
        ))
        with ExitStack() as pilha_carga:
            carga = pilha_carga.enter_context(_perfil_asgi(
                "carga", porta_carga, porta_proxy, banco,
                f"{plataforma}/interno/iam/v1/decisoes/", tmp_path
            ))
            with _proxy_tls(
                tmp_path, plataforma, carga, "nginx-isolamento-loopback.conf",
                porta=porta_proxy,
            ) as (origem, certificado):
                publica = f"{origem}/api/public/v1/publicacoes-institucionais/vigente/"
                antes = requests.get(publica, verify=certificado, timeout=8)
                assert antes.status_code in {200, 404}
                pilha_carga.close()
                depois = requests.get(publica, verify=certificado, timeout=8)
                assert depois.status_code == antes.status_code
                assert depois.content == antes.content
                assert requests.get(
                    f"{origem}/api/carga-org-lot/health/",
                    verify=certificado, timeout=8,
                ).status_code == 502

    # Carga permanece de pé sem IAM: acesso protegido falha fechado.
    with _perfil_asgi(
        "carga", porta_carga, porta_proxy, banco,
        f"http://127.0.0.1:{porta_plataforma}/interno/iam/v1/decisoes/", tmp_path
    ) as carga:
        with _proxy_tls(
            tmp_path, f"http://127.0.0.1:{porta_plataforma}", carga,
            "nginx-isolamento-loopback.conf", porta=porta_proxy,
        ) as (origem, certificado):
            falha = requests.get(
                f"{origem}/api/carga-org-lot/patriarcas/",
                cookies={sessao.session_cookie_name: sessao.session_key},
                verify=certificado, timeout=8,
            )
            assert falha.status_code == 503, falha.text[:500]
            assert falha.json()["errors"]["code"] == "servico_iam_indisponivel"
            assert "Set-Cookie" not in falha.headers
