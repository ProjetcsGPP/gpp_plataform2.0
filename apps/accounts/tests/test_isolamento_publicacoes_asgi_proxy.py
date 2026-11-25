"""Ensaio TLS de três perfis ASGI opt-in no banco permanente de testes."""

from contextlib import ExitStack

import pytest
import requests
from django.db import connection

from apps.accounts.models import UserRole
from apps.accounts.tests.test_decisao_publicacoes_interna import (  # pylint: disable=unused-import
    sessao_publicacoes,
)
from apps.accounts.tests.test_isolamento_asgi_proxy import _perfil_asgi, _websocket
from apps.accounts.tests.test_isolamento_proxy_tls import _porta_livre, _proxy_tls


@pytest.mark.django_db(transaction=True)
def test_publicacoes_para_sem_derrubar_iam_ou_carga(  # pylint: disable=too-many-locals
    tmp_path, sessao_publicacoes
):
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
                "publicacoes", porta_publicacoes, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes-publicacoes/", tmp_path
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
            anonimo = consultar("/api/pub-institucional/patriarcas/")
            assert anonimo.status_code == 401
            assert anonimo.json()["errors"]["code"] == "session_invalid"
            recurso = f"{origem}/api/pub-institucional/patriarcas/"
            credenciais = {
                sessao_publicacoes.session_cookie_name: sessao_publicacoes.session_key
            }
            autorizado = requests.get(
                recurso, cookies=credenciais, verify=certificado, timeout=8
            )
            assert autorizado.status_code == 200, autorizado.text[:500]
            caminho_ws = "/ws/pub-institucional/edocs/"
            assert _websocket(origem, certificado, caminho_ws, sessao_publicacoes) == 101
            cookie_outra_app = requests.get(
                recurso,
                cookies={"gpp_session_PORTAL": sessao_publicacoes.session_key},
                verify=certificado, timeout=8,
            )
            assert cookie_outra_app.status_code == 401
            sem_csrf = requests.post(
                f"{origem}/api/pub-institucional/coletas/",
                cookies=credenciais, verify=certificado, timeout=8,
            )
            assert sem_csrf.status_code == 403
            assert "CSRF" in sem_csrf.text
            UserRole.objects.filter(user_id=sessao_publicacoes.user_id).delete()
            revogado = requests.get(
                recurso, cookies=credenciais, verify=certificado, timeout=8
            )
            assert revogado.status_code == 403, revogado.text[:500]
            assert revogado.json()["errors"]["code"] == "permission_denied"
            assert _websocket(origem, certificado, caminho_ws, sessao_publicacoes) == 403
            assert consultar("/interno/iam/v1/decisoes/").status_code == 404
            assert _websocket(origem, certificado, caminho_ws) == 403

            processo_publicacoes.close()

            assert consultar(publica).status_code == 502
            assert consultar("/api/pub-institucional/health/").status_code == 502
            assert consultar("/api/health/").status_code == 200
            assert consultar("/api/carga-org-lot/health/").status_code == 200
            assert consultar("/api/accounts/auth/csrf/").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_publicacoes_falha_fechada_sem_iam_e_preserva_api_publica(
    tmp_path, sessao_publicacoes
):
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform"
    porta_proxy, porta_iam, porta_carga, porta_publicacoes = (
        _porta_livre(), _porta_livre(), _porta_livre(), _porta_livre()
    )
    with ExitStack() as processos:
        with ExitStack() as processo_iam:
            iam = processo_iam.enter_context(_perfil_asgi(
                "plataforma_separada", porta_iam, porta_proxy, banco, "", tmp_path
            ))
            carga = processos.enter_context(_perfil_asgi(
                "carga", porta_carga, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes/", tmp_path
            ))
            publicacoes = processos.enter_context(_perfil_asgi(
                "publicacoes", porta_publicacoes, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes-publicacoes/", tmp_path
            ))
            origem, certificado = processos.enter_context(_proxy_tls(
                tmp_path, iam, carga, "nginx-isolamento-tres.conf",
                porta=porta_proxy, publicacoes=publicacoes,
            ))
            recurso = f"{origem}/api/pub-institucional/patriarcas/"
            credenciais = {
                sessao_publicacoes.session_cookie_name: sessao_publicacoes.session_key
            }
            assert requests.get(
                recurso, cookies=credenciais, verify=certificado, timeout=8
            ).status_code == 200

        falha = requests.get(
            recurso, cookies=credenciais, verify=certificado, timeout=8
        )
        assert falha.status_code == 503, falha.text[:500]
        assert falha.json()["errors"]["code"] == "servico_iam_indisponivel"
        assert falha.json()["errors"]["detail"] == (
            "Serviço de autorização temporariamente indisponível."
        )
        assert "Set-Cookie" not in falha.headers
        assert _websocket(
            origem, certificado, "/ws/pub-institucional/edocs/", sessao_publicacoes
        ) == 403
        publica = requests.get(
            f"{origem}/api/public/v1/publicacoes-institucionais/vigente/",
            verify=certificado, timeout=8,
        )
        assert publica.status_code in {200, 404}


@pytest.mark.django_db(transaction=True)
def test_reinicio_individual_dos_tres_processos_preserva_isolamento(  # pylint: disable=too-many-locals
    tmp_path, sessao_publicacoes
):
    """Cada processo volta sem reiniciar o proxy nem os outros serviços."""
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform"
    porta_proxy, porta_iam, porta_carga, porta_publicacoes = (
        _porta_livre(), _porta_livre(), _porta_livre(), _porta_livre()
    )
    origem_iam = f"http://127.0.0.1:{porta_iam}"
    origem_carga = f"http://127.0.0.1:{porta_carga}"
    origem_publicacoes = f"http://127.0.0.1:{porta_publicacoes}"
    url_iam_carga = f"{origem_iam}/interno/iam/v1/decisoes/"
    url_iam_publicacoes = f"{origem_iam}/interno/iam/v1/decisoes-publicacoes/"

    with ExitStack() as infraestrutura:
        with ExitStack() as processo_iam:
            processo_iam.enter_context(_perfil_asgi(
                "plataforma_separada", porta_iam, porta_proxy, banco, "", tmp_path
            ))
            with ExitStack() as processo_carga:
                processo_carga.enter_context(_perfil_asgi(
                    "carga", porta_carga, porta_proxy, banco, url_iam_carga,
                    tmp_path,
                ))
                with ExitStack() as processo_publicacoes:
                    processo_publicacoes.enter_context(_perfil_asgi(
                        "publicacoes", porta_publicacoes, porta_proxy, banco,
                        url_iam_publicacoes, tmp_path,
                    ))
                    origem, certificado = infraestrutura.enter_context(_proxy_tls(
                        tmp_path, origem_iam, origem_carga,
                        "nginx-isolamento-tres.conf", porta=porta_proxy,
                        publicacoes=origem_publicacoes,
                    ))

                    def consultar(caminho, *, autenticado=False):
                        cookies = None
                        if autenticado:
                            cookies = {
                                sessao_publicacoes.session_cookie_name:
                                sessao_publicacoes.session_key,
                            }
                        return requests.get(
                            f"{origem}{caminho}", cookies=cookies,
                            verify=certificado, timeout=8,
                        )

                    recurso = "/api/pub-institucional/patriarcas/"
                    publica = "/api/public/v1/publicacoes-institucionais/vigente/"
                    assert consultar(recurso, autenticado=True).status_code == 200
                    assert consultar("/api/carga-org-lot/health/").status_code == 200
                    assert consultar("/api/health/").status_code == 200
                    publica_antes = consultar(publica).status_code
                    assert publica_antes in {200, 404}

                    processo_iam.close()
                    falha_iam = consultar(recurso, autenticado=True)
                    assert falha_iam.status_code == 503
                    assert falha_iam.json()["errors"]["code"] == (
                        "servico_iam_indisponivel"
                    )
                    assert consultar(publica).status_code == publica_antes
                    assert consultar("/api/carga-org-lot/health/").status_code == 200
                    processo_iam.enter_context(_perfil_asgi(
                        "plataforma_separada", porta_iam, porta_proxy, banco, "",
                        tmp_path,
                    ))
                    assert consultar(recurso, autenticado=True).status_code == 200

                    processo_publicacoes.close()
                    assert consultar(recurso, autenticado=True).status_code == 502
                    assert consultar(publica).status_code == 502
                    assert consultar("/api/health/").status_code == 200
                    assert consultar("/api/carga-org-lot/health/").status_code == 200
                    processo_publicacoes.enter_context(_perfil_asgi(
                        "publicacoes", porta_publicacoes, porta_proxy, banco,
                        url_iam_publicacoes, tmp_path,
                    ))
                    assert consultar(recurso, autenticado=True).status_code == 200
                    assert consultar(publica).status_code == publica_antes

                    processo_carga.close()
                    assert consultar("/api/carga-org-lot/health/").status_code == 502
                    assert consultar("/api/health/").status_code == 200
                    assert consultar(recurso, autenticado=True).status_code == 200
                    processo_carga.enter_context(_perfil_asgi(
                        "carga", porta_carga, porta_proxy, banco, url_iam_carga,
                        tmp_path,
                    ))
                    assert consultar("/api/carga-org-lot/health/").status_code == 200
