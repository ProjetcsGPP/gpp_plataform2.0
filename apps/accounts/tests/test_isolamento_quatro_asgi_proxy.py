"""Ensaio TLS opt-in dos quatro processos no banco permanente de testes."""

from contextlib import ExitStack

import pytest
import requests
from django.contrib.auth.models import Permission
from django.db import connection

from apps.accounts.models import UserRole
from apps.accounts.tests.test_decisao_interna_banco import _sessao
from apps.accounts.tests.test_isolamento_asgi_proxy import _perfil_asgi
from apps.accounts.tests.test_isolamento_proxy_tls import _porta_livre, _proxy_tls
from apps.acoes_pngi.models import VigenciaPNGI


@pytest.mark.django_db(transaction=True)
def test_quatro_processos_rotas_revogacao_e_parada_individual(  # pylint: disable=too-many-locals
    tmp_path, gestor_pngi, gestor_carga,
):
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform"
    # O ensaio depende da permissão técnica efetiva, não apenas do nome da Role.
    gestor_pngi.user_permissions.add(Permission.objects.get(
        codename="view_eixo", content_type__app_label="acoes_pngi",
    ))
    sessao_acoes = _sessao(gestor_pngi, "ACOES_PNGI")
    sessao_carga = _sessao(gestor_carga)
    porta_proxy, porta_iam, porta_carga, porta_publicacoes, porta_acoes = (
        _porta_livre(), _porta_livre(), _porta_livre(), _porta_livre(), _porta_livre()
    )
    with ExitStack() as processos:
        iam = processos.enter_context(_perfil_asgi(
            "plataforma_quatro", porta_iam, porta_proxy, banco, "", tmp_path,
        ))
        carga = processos.enter_context(_perfil_asgi(
            "carga", porta_carga, porta_proxy, banco,
            f"{iam}/interno/iam/v1/decisoes/", tmp_path,
        ))
        publicacoes = processos.enter_context(_perfil_asgi(
            "publicacoes", porta_publicacoes, porta_proxy, banco,
            f"{iam}/interno/iam/v1/decisoes-publicacoes/", tmp_path,
        ))
        with ExitStack() as processo_acoes:
            acoes = processo_acoes.enter_context(_perfil_asgi(
                "acoes", porta_acoes, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes-acoes/", tmp_path,
            ))
            origem, certificado = processos.enter_context(_proxy_tls(
                tmp_path, iam, carga, "nginx-isolamento-quatro.conf",
                porta=porta_proxy, publicacoes=publicacoes, acoes=acoes,
            ))

            def consultar(caminho, sessao=None):
                cookies = None
                if sessao is not None:
                    cookies = {sessao.session_cookie_name: sessao.session_key}
                return requests.get(
                    f"{origem}{caminho}", cookies=cookies,
                    verify=certificado, timeout=8,
                )

            for caminho, servico in (
                ("/api/health/", "plataforma"),
                ("/api/carga-org-lot/health/", "carga_org_lot"),
                ("/api/pub-institucional/health/", "pub_institucional"),
                ("/api/acoes-pngi/health/", "acoes_pngi"),
                ("/api/acoes-pngi/ready/", "acoes_pngi"),
            ):
                resposta = consultar(caminho)
                assert resposta.status_code == 200
                assert resposta.json()["service"] == servico
            assert consultar("/interno/iam/v1/decisoes-acoes/").status_code == 404
            assert consultar("/api/acoes-pngi/eixos/").status_code == 401
            assert consultar(
                "/api/acoes-pngi/eixos/", sessao_carga,
            ).status_code == 401
            autorizado = consultar("/api/acoes-pngi/eixos/", sessao_acoes)
            assert autorizado.status_code == 200, autorizado.text[:500]
            assert consultar(
                "/api/carga-org-lot/patriarcas/", sessao_carga,
            ).status_code == 200
            assert consultar(
                "/api/public/v1/publicacoes-institucionais/vigente/"
            ).status_code in {200, 404}

            UserRole.objects.filter(user_id=gestor_pngi.pk).delete()
            revogado = consultar("/api/acoes-pngi/eixos/", sessao_acoes)
            assert revogado.status_code == 403
            assert revogado.json()["errors"]["code"] == "permission_denied"

            processo_acoes.close()
            assert consultar("/api/acoes-pngi/health/").status_code == 502
            assert consultar("/api/health/").status_code == 200
            assert consultar("/api/carga-org-lot/health/").status_code == 200
            assert consultar("/api/pub-institucional/health/").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_quatro_processos_falham_fechado_sem_iam_e_preservam_vitrine(
    tmp_path, gestor_pngi,
):  # pylint: disable=too-many-locals
    banco = connection.settings_dict["NAME"]
    assert banco == "test_gpp_plataform"
    sessao_acoes = _sessao(gestor_pngi, "ACOES_PNGI")
    gestor_pngi.user_permissions.add(Permission.objects.get(
        codename="view_eixo", content_type__app_label="acoes_pngi",
    ))
    portas = [_porta_livre() for _ in range(5)]
    porta_proxy, porta_iam, porta_carga, porta_publicacoes, porta_acoes = portas
    with ExitStack() as processos:
        with ExitStack() as processo_iam:
            iam = processo_iam.enter_context(_perfil_asgi(
                "plataforma_quatro", porta_iam, porta_proxy, banco, "", tmp_path,
            ))
            carga = processos.enter_context(_perfil_asgi(
                "carga", porta_carga, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes/", tmp_path,
            ))
            publicacoes = processos.enter_context(_perfil_asgi(
                "publicacoes", porta_publicacoes, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes-publicacoes/", tmp_path,
            ))
            acoes = processos.enter_context(_perfil_asgi(
                "acoes", porta_acoes, porta_proxy, banco,
                f"{iam}/interno/iam/v1/decisoes-acoes/", tmp_path,
            ))
            origem, certificado = processos.enter_context(_proxy_tls(
                tmp_path, iam, carga, "nginx-isolamento-quatro.conf",
                porta=porta_proxy, publicacoes=publicacoes, acoes=acoes,
            ))
            cookies = {
                sessao_acoes.session_cookie_name: sessao_acoes.session_key
            }
            recurso = f"{origem}/api/acoes-pngi/eixos/"
            assert requests.get(
                recurso, cookies=cookies, verify=certificado, timeout=8,
            ).status_code == 200
            publico = f"{origem}/api/public/v1/publicacoes-institucionais/vigente/"
            antes = requests.get(publico, verify=certificado, timeout=8)
            assert antes.status_code in {200, 404}

        quantidade = VigenciaPNGI.objects.count()
        falha = requests.get(
            recurso, cookies=cookies, verify=certificado, timeout=8,
        )
        assert falha.status_code == 503
        assert falha.json()["errors"]["code"] == "servico_iam_indisponivel"
        mutacao = requests.post(
            f"{origem}/api/acoes-pngi/vigencias/", json={},
            cookies=cookies, verify=certificado, timeout=8,
        )
        assert mutacao.status_code == 503
        assert VigenciaPNGI.objects.count() == quantidade
        assert requests.get(
            f"{origem}/api/acoes-pngi/health/",
            verify=certificado, timeout=8,
        ).status_code == 200
        depois = requests.get(publico, verify=certificado, timeout=8)
        assert depois.status_code == antes.status_code
        assert depois.content == antes.content
