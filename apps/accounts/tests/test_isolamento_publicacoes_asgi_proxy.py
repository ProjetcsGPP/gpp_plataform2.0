"""Ensaio TLS de três perfis ASGI opt-in no banco permanente de testes."""

from contextlib import ExitStack

import pytest
import requests
from django.db import connection

from apps.accounts.tests.test_isolamento_asgi_proxy import _perfil_asgi, _websocket
from apps.accounts.tests.test_isolamento_proxy_tls import _porta_livre, _proxy_tls


@pytest.mark.django_db(transaction=True)
def test_publicacoes_para_sem_derrubar_iam_ou_carga(tmp_path):
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform"
    porta_proxy, porta_iam, porta_carga, porta_publicacoes = (
        _porta_livre(), _porta_livre(), _porta_livre(), _porta_livre()
    )
    with ExitStack() as pilha:
        iam = pilha.enter_context(_perfil_asgi(
            "plataforma_separada", porta_iam, porta_proxy, banco, "", tmp_path
        ))
        carga = pilha.enter_context(_perfil_asgi(
            "carga", porta_carga, porta_proxy, banco,
            f"{iam}/interno/iam/v1/decisoes/", tmp_path
        ))
        with ExitStack() as processo_publicacoes:
            publicacoes = processo_publicacoes.enter_context(_perfil_asgi(
                "publicacoes", porta_publicacoes, porta_proxy, banco, "", tmp_path
            ))
            origem, certificado = pilha.enter_context(_proxy_tls(
                tmp_path, iam, carga, "nginx-isolamento-tres.conf",
                porta=porta_proxy, publicacoes=publicacoes,
            ))

            def consultar(caminho):
                return requests.get(
                    f"{origem}{caminho}", verify=certificado, timeout=8
                )

            assert consultar("/api/health/").json()["service"] == "plataforma"
            assert consultar("/api/carga-org-lot/health/").json()["service"] == "carga_org_lot"
            assert consultar("/api/pub-institucional/health/").json()["service"] == "pub_institucional"
            publica = "/api/public/v1/publicacoes-institucionais/vigente/"
            antes = consultar(publica)
            assert antes.status_code in {200, 404}
            assert consultar("/api/pub-institucional/patriarcas/").status_code == 401
            assert consultar("/interno/iam/v1/decisoes/").status_code == 404
            assert _websocket(origem, certificado, "/ws/pub-institucional/edocs/") == 403

            processo_publicacoes.close()

            assert consultar(publica).status_code == 502
            assert consultar("/api/pub-institucional/health/").status_code == 502
            assert consultar("/api/health/").status_code == 200
            assert consultar("/api/carga-org-lot/health/").status_code == 200
            assert consultar("/api/accounts/auth/csrf/").status_code == 200
