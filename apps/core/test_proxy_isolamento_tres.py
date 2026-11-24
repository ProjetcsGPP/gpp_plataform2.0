"""Roteamento estático do proxy opt-in de três processos locais."""

import re
from pathlib import Path


INFRA = Path(__file__).resolve().parents[2] / "infra/publicacoes-dev"


def test_proxy_tres_isola_iam_e_roteia_api_publica_com_publicacoes():
    compose = (INFRA / "compose-isolamento-tres.yaml").read_text(encoding="utf-8")
    nginx = (INFRA / "config/nginx/nginx-isolamento-tres.conf").read_text(
        encoding="utf-8"
    )
    assert "network_mode: host" in compose
    assert "ports:" not in compose
    assert "listen 127.0.0.1:58445 ssl;" in nginx
    assert "location ^~ /interno/ { return 404; }" in nginx
    assert "location / {" in nginx and "return 503" in nginx
    assert "host.docker.internal" not in nginx
    destinos = re.findall(r"proxy_pass\s+(\S+);", nginx)
    assert destinos and all(destino.startswith("http://127.0.0.1:") for destino in destinos)
    for rota, destino in (
        ("/api/carga-org-lot/", "8001"),
        ("/api/pub-institucional/", "8002"),
        ("/api/public/v1/publicacoes-institucionais/", "8002"),
        ("/ws/carga-org-lot/", "8001"),
        ("/ws/pub-institucional/", "8002"),
    ):
        assert re.search(
            rf"location \^~ {re.escape(rota)} \{{[^}}]*proxy_pass http://127\.0\.0\.1:{destino};",
            nginx,
        )
