"""Contratos estáticos do proxy opt-in de isolamento no host local."""

import re
from pathlib import Path


INFRA = Path(__file__).resolve().parents[2] / "infra/publicacoes-dev"


def test_proxy_local_nao_expoe_portas_nem_iam_interno():
    composicao = (INFRA / "compose-isolamento-loopback.yaml").read_text(
        encoding="utf-8"
    )
    configuracao = (
        INFRA / "config/nginx/nginx-isolamento-loopback.conf"
    ).read_text(encoding="utf-8")

    assert "network_mode: host" in composicao
    assert "ports:" not in composicao
    assert "listen 127.0.0.1:58444 ssl;" in configuracao
    assert "location / {" in configuracao
    assert "location ^~ /interno/ {" in configuracao
    assert 'return 503 "superficie nao habilitada neste piloto' in configuracao
    assert "host.docker.internal" not in configuracao
    assert "127.0.0.1:3000" not in configuracao
    assert "proxy_pass http://127.0.0.1:8000/interno/" not in configuracao

    destinos = re.findall(r"proxy_pass\s+(\S+);", configuracao)
    assert destinos
    assert all(
        destino.startswith(("http://127.0.0.1:8000", "http://127.0.0.1:8001"))
        for destino in destinos
    )
    for rota in (
        "location = /api/carga-org-lot/health/",
        "location ^~ /api/carga-org-lot/",
        "location ^~ /ws/carga-org-lot/",
        "location ^~ /ws/pub-institucional/",
        "location /api/",
    ):
        assert rota in configuracao
