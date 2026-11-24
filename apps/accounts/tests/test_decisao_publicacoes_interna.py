"""Contrato M2M de Publicações com aplicação fixa e banco de testes."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.accounts.models import AccountsSession, Aplicacao, Role, UserRole
from apps.pub_institucional.services.recursos_funcionais import (
    semear_recursos_funcionais_publicacoes,
)

pytestmark = pytest.mark.django_db

CAMINHO = "/interno/iam/v1/decisoes-publicacoes/"
TOKEN_PUBLICACOES = "credencial-publicacoes-sintetica-de-integracao"
TOKEN_CARGA = "credencial-carga-sintetica-de-integracao"
CONFIGURACAO = {
    "IAM_DECISOES_INTERNAS_ATIVAS": True,
    "IAM_TOKEN_SERVICO_CARGA": TOKEN_CARGA,
    "IAM_TOKEN_SERVICO_PUBLICACOES": TOKEN_PUBLICACOES,
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


@override_settings(IAM_DECISOES_INTERNAS_ATIVAS=True, IAM_TOKEN_SERVICO_PUBLICACOES="")
def test_sem_credencial_propria_retorna_404(sessao_publicacoes):
    assert _consultar(sessao_publicacoes).status_code == 404


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
