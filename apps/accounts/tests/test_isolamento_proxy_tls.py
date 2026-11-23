"""Ensaio HTTPS do proxy opt-in com processos e banco de testes isolados."""

import multiprocessing
import os
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests

from apps.accounts.models import UserRole
from apps.accounts.tests.test_decisao_interna_banco import _sessao
from apps.accounts.tests.test_isolamento_http_processos import _perfil_http


CONFIGURACAO_NGINX = (
    Path(__file__).resolve().parents[3]
    / "infra/publicacoes-dev/config/nginx/nginx-isolamento.conf"
)


def _porta_livre():
    with socket.socket() as canal:
        canal.bind(("127.0.0.1", 0))
        return canal.getsockname()[1]


@contextmanager
def _proxy_tls(tmp_path, plataforma, carga):
    """Sobe Nginx temporário; jamais altera o contêiner ou proxy em uso."""
    porta = _porta_livre()
    certificado = tmp_path / "ensaio.crt"
    chave = tmp_path / "ensaio.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-sha256", "-nodes", "-days", "1", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", str(chave), "-out", str(certificado),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    os.chmod(chave, 0o600)
    configuracao = CONFIGURACAO_NGINX.read_text(encoding="utf-8")
    configuracao = configuracao.replace("listen 8443 ssl;", f"listen {porta} ssl;")
    configuracao = configuracao.replace(
        "/etc/nginx/tls/dev.crt", "/etc/nginx/ensaio/ensaio.crt"
    ).replace(
        "/etc/nginx/tls/dev.key", "/etc/nginx/ensaio/ensaio.key"
    )
    configuracao = configuracao.replace(
        "host.docker.internal:8000", plataforma.removeprefix("http://")
    ).replace(
        "host.docker.internal:8001", carga.removeprefix("http://")
    ).replace(
        "host.docker.internal:3000", "127.0.0.1:1"
    )
    caminho = tmp_path / "nginx.conf"
    caminho.write_text(configuracao, encoding="utf-8")
    nome = f"gpp-ensaio-tls-{uuid.uuid4().hex[:12]}"
    imagem = subprocess.run(
        ["docker", "image", "ls", "--format", "{{.ID}}", "nginx"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.splitlines()[0]
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--network", "host",
            "--name", nome, "--mount",
            f"type=bind,source={tmp_path},target=/etc/nginx/ensaio,readonly",
            imagem, "nginx", "-c", "/etc/nginx/ensaio/nginx.conf",
            "-g", "daemon off;",
        ],
        check=True, capture_output=True, timeout=15,
    )
    origem = f"https://localhost:{porta}"
    try:
        for _ in range(50):
            try:
                resposta = requests.get(
                    f"{origem}/infra/healthz", verify=str(certificado), timeout=1
                )
                if resposta.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            raise AssertionError("Proxy HTTPS temporário não ficou disponível")
        yield origem, str(certificado)
    finally:
        subprocess.run(
            ["docker", "stop", "--time", "1", nome],
            check=True, capture_output=True, timeout=10,
        )


def _get(origem, caminho, certificado, sessao=None):
    cookies = None
    if sessao is not None:
        cookies = {sessao.session_cookie_name: sessao.session_key}
    return requests.get(
        f"{origem}{caminho}", cookies=cookies,
        verify=certificado, timeout=(1, 4),
    )


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="O ensaio requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
def test_proxy_https_autorizacao_revogacao_e_falha_iam(tmp_path, gestor_carga):
    sessao = _sessao(gestor_carga)
    with _perfil_http("plataforma") as plataforma:
        decisao = f"{plataforma}/interno/iam/v1/decisoes/"
        with _perfil_http("carga", decisao) as carga:
            with _proxy_tls(tmp_path, plataforma, carga) as (origem, certificado):
                recurso = "/api/carga-org-lot/patriarcas/"
                assert _get(origem, recurso, certificado, sessao).status_code == 200
                assert _get(origem, recurso, certificado).status_code == 401
                publica = "/api/public/v1/publicacoes-institucionais/vigente/"
                assert _get(origem, publica, certificado).status_code in {200, 404}
                assert _get(origem, "/api/health/", certificado).json()[
                    "service"
                ] == "plataforma"
                assert _get(
                    origem, "/api/carga-org-lot/health/", certificado
                ).json()["service"] == "carga_org_lot"

                UserRole.objects.filter(
                    user=gestor_carga, role__codigoperfil="GESTOR_CARGA"
                ).delete()
                revogada = _get(origem, recurso, certificado, sessao)
                assert revogada.status_code == 403
                assert revogada.json()["errors"]["code"] == "permission_denied"

    with _perfil_http("carga", decisao) as carga:
        with _proxy_tls(tmp_path, plataforma, carga) as (origem, certificado):
            falha = _get(
                origem, "/api/carga-org-lot/patriarcas/", certificado, sessao
            )
            assert falha.status_code == 503
            assert falha.json()["errors"]["code"] == "servico_iam_indisponivel"
            assert "Set-Cookie" not in falha.headers
