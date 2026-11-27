"""Contrato M2M de Publicações com aplicação fixa e banco de testes."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.accounts.models import AccountsSession, Aplicacao, Role, UserRole
from apps.accounts.middleware import AppContextMiddleware
from apps.core.middleware.application_context import ApplicationContextMiddleware
from apps.core.middleware.role_context import RoleContextMiddleware
from apps.pub_institucional.services.recursos_funcionais import (
    semear_recursos_funcionais_publicacoes,
)
from apps.pub_institucional.models import PreferenciaExibicaoEflow

pytestmark = pytest.mark.django_db

CAMINHO = "/interno/iam/v1/decisoes-publicacoes/"
CAMINHO_ATIVIDADE = "/interno/iam/v1/decisoes-atividade-publicacoes/"
TOKEN_PUBLICACOES = "credencial-publicacoes-sintetica-de-integracao"
TOKEN_CARGA = "credencial-carga-sintetica-de-integracao"
CONFIGURACAO = {
    "IAM_DECISOES_INTERNAS_ATIVAS": True,
    "IAM_DECISOES_PUBLICACOES_ATIVAS": True,
    "IAM_TOKEN_SERVICO_CARGA": TOKEN_CARGA,
    "IAM_TOKEN_SERVICO_PUBLICACOES": TOKEN_PUBLICACOES,
}
CONFIGURACAO_CONSUMIDOR = {
    **CONFIGURACAO,
    "PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA": True,
    "IAM_URL_PUBLICACOES": "http://127.0.0.1:8000/interno/iam/v1/decisoes-publicacoes/",
}


def _consultar(sessao, *, token=TOKEN_PUBLICACOES, acao="view_patriarcaedocs", cliente=None):
    return (cliente or Client()).post(
        CAMINHO,
        data={
            "acao": acao,
            "credenciais_usuario": [{
                "nome_cookie": sessao.session_cookie_name,
                "valor": sessao.session_key,
            }],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


@pytest.fixture
def sessao_publicacoes():
    semear_recursos_funcionais_publicacoes()
    aplicacao = Aplicacao.objects.get(codigointerno="PUB_INSTITUCIONAL")
    perfil = Role.objects.get(aplicacao=aplicacao, codigoperfil="GESTOR_PUBLICACOES")
    usuario = User.objects.create_user(username="gestor_publicacoes_iam")
    UserRole.objects.create(user=usuario, aplicacao=aplicacao, role=perfil)
    return AccountsSession.objects.create(
        user=usuario,
        session_key=f"teste-iam-publicacoes-{usuario.pk}",
        session_cookie_name="gpp_session_PUB_INSTITUCIONAL",
        app_context="PUB_INSTITUCIONAL",
        expires_at=timezone.now() + timedelta(hours=1),
    )


def test_rota_existe_apenas_na_plataforma():
    resolve(CAMINHO, urlconf="config.urls_plataforma_separada_piloto")
    with pytest.raises(Resolver404):
        resolve(CAMINHO, urlconf="config.urls_publicacoes_piloto")


@override_settings(IAM_DECISOES_PUBLICACOES_ATIVAS=True, IAM_TOKEN_SERVICO_PUBLICACOES="")
def test_sem_credencial_propria_retorna_404(sessao_publicacoes):
    assert _consultar(sessao_publicacoes).status_code == 404


@override_settings(**{**CONFIGURACAO, "IAM_DECISOES_PUBLICACOES_ATIVAS": False})
def test_flag_de_carga_nao_liga_produtor_publicacoes(sessao_publicacoes):
    assert _consultar(sessao_publicacoes).status_code == 404
    assert Client().post(CAMINHO_ATIVIDADE).status_code == 404


@override_settings(**{**CONFIGURACAO, "IAM_DECISOES_INTERNAS_ATIVAS": False})
def test_flag_publicacoes_nao_liga_produtor_carga(sessao_publicacoes):
    assert _consultar(sessao_publicacoes).status_code == 200
    assert Client().post("/interno/iam/v1/decisoes/").status_code == 404
    assert Client().post("/interno/iam/v1/decisoes-atividade/").status_code == 404


@override_settings(**CONFIGURACAO)
def test_credencial_de_carga_nao_autoriza_publicacoes(sessao_publicacoes):
    assert _consultar(sessao_publicacoes, token=TOKEN_CARGA).status_code == 401


@override_settings(**{**CONFIGURACAO, "IAM_TOKEN_SERVICO_PUBLICACOES": TOKEN_CARGA})
def test_configuracao_nao_aceita_credencial_compartilhada(sessao_publicacoes):
    assert _consultar(sessao_publicacoes, token=TOKEN_CARGA).status_code == 404


@override_settings(**CONFIGURACAO)
def test_sessao_propria_e_revogacao_de_permissao(sessao_publicacoes):
    resposta = _consultar(
        sessao_publicacoes, cliente=Client(enforce_csrf_checks=True)
    )
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "AUTORIZADO"
    assert resposta.json()["usuario_id"] == sessao_publicacoes.user_id
    UserRole.objects.filter(user_id=sessao_publicacoes.user_id).delete()
    assert _consultar(sessao_publicacoes).json()["resultado"] == "NEGADO"


@override_settings(**CONFIGURACAO)
def test_cookie_portal_admin_nao_autoriza_publicacoes(portal_admin):
    portal = AccountsSession.objects.create(
        user=portal_admin,
        session_key=f"teste-portal-publicacoes-{portal_admin.pk}",
        session_cookie_name="gpp_session_PORTAL",
        app_context="PORTAL",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    assert _consultar(portal).json()["resultado"] == "SESSAO_INVALIDA"


@override_settings(**CONFIGURACAO)
def test_corpo_nao_escolhe_aplicacao_alvo(sessao_publicacoes):
    resposta = Client().post(
        CAMINHO,
        data={
            "acao": "view_patriarcaedocs",
            "aplicacao": "CARGA_ORG_LOT",
            "credenciais_usuario": [{
                "nome_cookie": sessao_publicacoes.session_cookie_name,
                "valor": sessao_publicacoes.session_key,
            }],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {TOKEN_PUBLICACOES}",
    )
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "AUTORIZADO"


def _postar_iam_local(url, **opcoes):
    assert url == CONFIGURACAO_CONSUMIDOR["IAM_URL_PUBLICACOES"]
    resposta = Client().post(
        CAMINHO,
        data=opcoes["json"],
        content_type="application/json",
        HTTP_AUTHORIZATION=opcoes["headers"]["Authorization"],
        HTTP_X_CORRELATION_ID=opcoes["headers"]["X-Correlation-ID"],
    )
    return SimpleNamespace(status_code=resposta.status_code, json=resposta.json)


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_api_administrativa_usa_iam_sem_consultas_locais(sessao_publicacoes):
    cliente = Client()
    cliente.cookies[sessao_publicacoes.session_cookie_name] = sessao_publicacoes.session_key
    with (
        patch("common.services.cliente_iam.requests.post", side_effect=_postar_iam_local),
        patch.object(AppContextMiddleware, "_authenticate_specific_cookie", side_effect=AssertionError("sessão local")),
        patch.object(ApplicationContextMiddleware, "_resolve_application", side_effect=AssertionError("app local")),
        patch.object(RoleContextMiddleware, "_load_roles", side_effect=AssertionError("roles locais")),
        patch("apps.pub_institucional.permissoes_iam.AuthorizationService", side_effect=AssertionError("autorização local")),
    ):
        resposta = cliente.get("/api/pub-institucional/patriarcas/")
    assert resposta.status_code == 200
    assert "results" in resposta.json()


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_correlacao_da_requisicao_chega_ao_log_do_iam(
    sessao_publicacoes, caplog
):
    cliente = Client()
    cliente.cookies[sessao_publicacoes.session_cookie_name] = (
        sessao_publicacoes.session_key
    )
    with patch(
        "common.services.cliente_iam.requests.post",
        side_effect=_postar_iam_local,
    ) as postar:
        resposta = cliente.get(
            "/api/pub-institucional/patriarcas/",
            HTTP_X_CORRELATION_ID="ensaio-publicacoes-123",
        )
    assert resposta.status_code == 200
    assert postar.call_args.kwargs["headers"]["X-Correlation-ID"] == (
        "ensaio-publicacoes-123"
    )
    assert "correlacao=ensaio-publicacoes-123" in caplog.text


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_api_administrativa_falha_fechada_sem_sessao_ou_iam(sessao_publicacoes):
    sem_sessao = Client().get("/api/pub-institucional/patriarcas/")
    assert sem_sessao.status_code == 401
    cliente_outra_app = Client()
    cliente_outra_app.cookies["gpp_session_PORTAL"] = sessao_publicacoes.session_key
    outra_app = cliente_outra_app.get("/api/pub-institucional/patriarcas/")
    assert outra_app.status_code == 401
    assert outra_app.json()["errors"]["code"] == "session_invalid"
    cliente = Client()
    cliente.cookies[sessao_publicacoes.session_cookie_name] = sessao_publicacoes.session_key
    with patch("common.services.cliente_iam.requests.post", side_effect=RequestsConnectionError("IAM parado")):
        indisponivel = cliente.get("/api/pub-institucional/patriarcas/")
    assert indisponivel.status_code == 503
    assert "Set-Cookie" not in indisponivel


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_api_administrativa_reflete_revogacao(sessao_publicacoes):
    cliente = Client()
    cliente.cookies[sessao_publicacoes.session_cookie_name] = sessao_publicacoes.session_key
    with patch("common.services.cliente_iam.requests.post", side_effect=_postar_iam_local):
        assert cliente.get("/api/pub-institucional/patriarcas/").status_code == 200
        UserRole.objects.filter(user_id=sessao_publicacoes.user_id).delete()
        assert cliente.get("/api/pub-institucional/patriarcas/").status_code == 403


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_api_publica_nao_consulta_iam():
    with patch("common.services.cliente_iam.requests.post", side_effect=AssertionError("IAM público")):
        resposta = Client().get(
            "/api/public/v1/publicacoes-institucionais/vigente/"
        )
    assert resposta.status_code == 404


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_mutacao_administrativa_mantem_csrf(sessao_publicacoes):
    cliente = Client(enforce_csrf_checks=True)
    cliente.cookies[sessao_publicacoes.session_cookie_name] = sessao_publicacoes.session_key
    with patch("common.services.cliente_iam.requests.post", side_effect=_postar_iam_local):
        resposta = cliente.post("/api/pub-institucional/coletas/")
    assert resposta.status_code == 403
    assert "CSRF" in str(resposta.content)


@override_settings(**CONFIGURACAO_CONSUMIDOR)
def test_preferencia_eflow_fica_no_escopo_do_usuario_iam(sessao_publicacoes):
    """O ID lógico do IAM, não um ID informado pelo cliente, define o objeto."""
    aplicacao = Aplicacao.objects.get(codigointerno="PUB_INSTITUCIONAL")
    perfil = Role.objects.get(aplicacao=aplicacao, codigoperfil="GESTOR_PUBLICACOES")
    outro = User.objects.create_user(username="outro_gestor_publicacoes")
    UserRole.objects.create(user=outro, aplicacao=aplicacao, role=perfil)
    outra_sessao = AccountsSession.objects.create(
        user=outro,
        session_key=f"teste-iam-publicacoes-{outro.pk}",
        session_cookie_name="gpp_session_PUB_INSTITUCIONAL",
        app_context="PUB_INSTITUCIONAL",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    primeiro = Client()
    primeiro.cookies[sessao_publicacoes.session_cookie_name] = (
        sessao_publicacoes.session_key
    )
    segundo = Client()
    segundo.cookies[outra_sessao.session_cookie_name] = outra_sessao.session_key
    caminho = "/api/pub-institucional/preferencias-eflow/minha/"
    with patch("common.services.cliente_iam.requests.post", side_effect=_postar_iam_local):
        alteracao = primeiro.patch(
            caminho,
            data={"perfil_preferido": "COMPLETO_TECNICO"},
            content_type="application/json",
        )
        consulta = segundo.get(caminho)
    assert alteracao.status_code == 200, alteracao.content[:500]
    assert consulta.status_code == 200, consulta.content[:500]
    assert consulta.json()["perfil_preferido"] == "CONSOLIDADO_PUBLICACAO"
    assert PreferenciaExibicaoEflow.objects.get(
        usuario_id=sessao_publicacoes.user_id
    ).perfil_preferido == "COMPLETO_TECNICO"
    assert PreferenciaExibicaoEflow.objects.get(
        usuario_id=outro.pk
    ).perfil_preferido == "CONSOLIDADO_PUBLICACAO"


def _consultar_atividade(usuario_id, *, token=TOKEN_PUBLICACOES):
    return Client().post(
        CAMINHO_ATIVIDADE,
        data={"usuario_id": usuario_id, "acao": "solicitar_coleta_mensal_edocs"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


@override_settings(**CONFIGURACAO)
def test_atividade_publicacoes_revalida_role_sem_sessao(sessao_publicacoes):
    resolve(CAMINHO_ATIVIDADE, urlconf="config.urls_plataforma_separada_piloto")
    with pytest.raises(Resolver404):
        resolve(CAMINHO_ATIVIDADE, urlconf="config.urls_publicacoes_piloto")
    usuario_id = sessao_publicacoes.user_id
    autorizado = _consultar_atividade(usuario_id)
    assert autorizado.status_code == 200
    assert autorizado.json()["resultado"] == "AUTORIZADO"
    UserRole.objects.filter(user_id=usuario_id).delete()
    negado = _consultar_atividade(usuario_id)
    assert negado.status_code == 200
    assert negado.json()["resultado"] == "NEGADO"


@override_settings(**CONFIGURACAO)
def test_atividade_publicacoes_exige_credencial_exclusiva(sessao_publicacoes):
    usuario_id = sessao_publicacoes.user_id
    assert _consultar_atividade(usuario_id, token=TOKEN_CARGA).status_code == 401
    assert _consultar_atividade(usuario_id, token="").status_code == 401


@override_settings(**{**CONFIGURACAO, "IAM_TOKEN_SERVICO_PUBLICACOES": TOKEN_CARGA})
def test_atividade_publicacoes_recusa_token_compartilhado(sessao_publicacoes):
    assert _consultar_atividade(sessao_publicacoes.user_id, token=TOKEN_CARGA).status_code == 404
