"""Integração do contrato IAM v1 com AccountsSession e RBAC reais.

Requer o PostgreSQL de testes do Django. Não acessa dados operacionais.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from rest_framework.response import Response

from apps.accounts.models import AccountsSession, Aplicacao, UserRole
from apps.accounts.services.authorization_service import AuthorizationService
from apps.carga_org_lot.permissoes_iam import (
    CanPermissionCarga,
    ServicoIAMIndisponivel,
    SessaoCargaInvalida,
    PermissaoCargaNegada,
)

pytestmark = pytest.mark.django_db

CAMINHO = "/interno/iam/v1/decisoes/"
TOKEN_TESTE = "credencial-m2m-sintetica-para-testes-de-integracao"
PERMISSAO = "view_importacaoplanilha"
CONFIGURACAO_TESTE = {
    "IAM_DECISOES_INTERNAS_ATIVAS": True,
    "IAM_TOKEN_SERVICO_CARGA": TOKEN_TESTE,
}
CONFIGURACAO_PILOTO = {
    **CONFIGURACAO_TESTE,
    "CARGA_IAM_DECISAO_REMOTA_ATIVA": True,
    "IAM_URL_CARGA": "http://127.0.0.1:8000/interno/iam/v1/decisoes/",
}


def _sessao(usuario, aplicacao="CARGA_ORG_LOT", *, expirada=False, revogada=False):
    chave = f"iam-teste-{usuario.pk}-{aplicacao}-{AccountsSession.objects.count()}"
    return AccountsSession.objects.create(
        user=usuario,
        session_key=chave,
        session_cookie_name=f"gpp_session_{aplicacao}",
        app_context=aplicacao,
        expires_at=timezone.now() + timedelta(hours=-1 if expirada else 1),
        revoked=revogada,
    )


def _consultar(*sessoes, acao=PERMISSAO):
    return Client().post(
        CAMINHO,
        data={
            "acao": acao,
            "credenciais_usuario": [
                {"nome_cookie": sessao.session_cookie_name, "valor": sessao.session_key}
                for sessao in sessoes
            ],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {TOKEN_TESTE}",
    )


def _postar_iam_local(url, **opcoes):
    """Exercita o contrato HTTP sem abrir rede nem trocar de banco."""
    assert url == CONFIGURACAO_PILOTO["IAM_URL_CARGA"]
    resposta = Client().post(
        CAMINHO,
        data=opcoes["json"],
        content_type="application/json",
        HTTP_AUTHORIZATION=opcoes["headers"]["Authorization"],
        HTTP_X_CORRELATION_ID=opcoes["headers"]["X-Correlation-ID"],
    )
    return SimpleNamespace(status_code=resposta.status_code, json=resposta.json)


def _guardar_carga(usuario, sessao):
    requisicao = APIRequestFactory().get(
        "/api/carga-org-lot/dashboard/", HTTP_X_CORRELATION_ID="integracao-iam-1"
    )
    requisicao.COOKIES[sessao.session_cookie_name] = sessao.session_key
    requisicao.user = usuario
    visao = SimpleNamespace(required_permission=PERMISSAO, permission_context=None)
    with patch(
        "apps.carga_org_lot.services.cliente_iam.requests.post",
        side_effect=_postar_iam_local,
    ):
        return CanPermissionCarga().has_permission(requisicao, visao)


@override_settings(**CONFIGURACAO_TESTE)
def test_sessao_carga_com_role_real_e_autorizada(gestor_carga):
    sessao = _sessao(gestor_carga)
    resposta = _consultar(sessao)
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "AUTORIZADO"
    assert resposta.json()["usuario_id"] == gestor_carga.pk
    assert resposta.json()["usuario_nome"] == (
        gestor_carga.get_full_name().strip() or gestor_carga.get_username()
    )
    assert resposta.json()["expira_em"] == sessao.expires_at.isoformat()


@override_settings(**{
    **CONFIGURACAO_PILOTO,
    "CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA": True,
    "CARGA_IAM_DECISAO_REMOTA_ATIVA": False,
})
def test_view_http_usa_sessao_real_so_no_iam_e_preserva_auditoria(gestor_carga):
    """A decisão IAM consulta o banco; a cadeia HTTP da app não o consulta."""
    from apps.accounts.middleware import AppContextMiddleware
    from apps.core.middleware.application_context import ApplicationContextMiddleware
    from apps.core.middleware.role_context import RoleContextMiddleware
    from apps.carga_org_lot.views.dashboard import DashboardCargaOrgLotView

    sessao = _sessao(gestor_carga)
    cliente = Client()
    cliente.cookies[sessao.session_cookie_name] = sessao.session_key

    def responder(_view, request):
        return Response({
            "usuario_id": request.user.pk,
            "usuario_nome": request.user.get_full_name(),
        })

    with (
        patch("apps.carga_org_lot.services.cliente_iam.requests.post", side_effect=_postar_iam_local),
        patch.object(AppContextMiddleware, "_authenticate_specific_cookie", side_effect=AssertionError("sessão local")),
        patch.object(ApplicationContextMiddleware, "_resolve_application", side_effect=AssertionError("app local")),
        patch.object(RoleContextMiddleware, "_load_roles", side_effect=AssertionError("roles locais")),
        patch.object(DashboardCargaOrgLotView, "get", responder),
    ):
        resposta = cliente.get("/api/carga-org-lot/dashboard/")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "usuario_id": gestor_carga.pk,
        "usuario_nome": gestor_carga.get_full_name().strip() or gestor_carga.get_username(),
    }


@override_settings(**CONFIGURACAO_TESTE)
def test_sessao_valida_sem_role_e_negada(usuario_sem_role):
    resposta = _consultar(_sessao(usuario_sem_role))
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "NEGADO"


@override_settings(**CONFIGURACAO_TESTE)
def test_cookie_portal_admin_nao_autoriza_carga(portal_admin):
    resposta = _consultar(_sessao(portal_admin, "PORTAL"))
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "SESSAO_INVALIDA"


@override_settings(**CONFIGURACAO_TESTE)
def test_cookie_portal_de_usuario_nao_admin_e_sessao_invalida(gestor_carga):
    resposta = _consultar(_sessao(gestor_carga, "PORTAL"))
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "SESSAO_INVALIDA"


@override_settings(**CONFIGURACAO_TESTE)
def test_cookie_dedicado_invalido_nao_usa_cookie_portal(portal_admin, gestor_carga):
    dedicado = _sessao(gestor_carga, revogada=True)
    portal = _sessao(portal_admin, "PORTAL")
    resposta = _consultar(dedicado, portal)
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "SESSAO_INVALIDA"


@override_settings(**CONFIGURACAO_TESTE)
@pytest.mark.parametrize("estado", ["expirada", "revogada", "inativa"])
def test_sessao_expirada_revogada_ou_usuario_inativo_falha(gestor_carga, estado):
    sessao = _sessao(
        gestor_carga,
        expirada=estado == "expirada",
        revogada=estado == "revogada",
    )
    if estado == "inativa":
        gestor_carga.is_active = False
        gestor_carga.save(update_fields=["is_active"])
    resposta = _consultar(sessao)
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "SESSAO_INVALIDA"


@override_settings(**CONFIGURACAO_TESTE)
def test_cookies_de_outras_apps_nao_autorizam_carga(portal_admin, usuario_sem_role):
    portal = _sessao(portal_admin, "PORTAL")
    outra = _sessao(usuario_sem_role, "ACOES_PNGI")
    AccountsSession.objects.filter(pk=portal.pk).update(
        created_at=timezone.now() - timedelta(minutes=2)
    )
    AccountsSession.objects.filter(pk=outra.pk).update(created_at=timezone.now())
    resposta = _consultar(portal, outra)
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "SESSAO_INVALIDA"


@override_settings(**CONFIGURACAO_TESTE)
def test_retirada_de_role_invalida_decisao_em_chamada_seguinte(gestor_carga):
    sessao = _sessao(gestor_carga)
    assert _consultar(sessao).json()["resultado"] == "AUTORIZADO"
    UserRole.objects.filter(user=gestor_carga, role__codigoperfil="GESTOR_CARGA").delete()
    resposta = _consultar(sessao)
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "NEGADO"


@override_settings(**CONFIGURACAO_TESTE)
def test_decisao_interna_nao_aceita_permissao_revogada_em_cache(gestor_carga):
    """Mesmo se a invalidação falhar, o IAM não reutiliza autorização antiga."""
    aplicacao = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
    autorizacao_local = AuthorizationService(gestor_carga, aplicacao)
    chave_cache = autorizacao_local._permissions_cache_key()  # pylint: disable=protected-access
    cache.delete(chave_cache)
    assert autorizacao_local.can(PERMISSAO) is True
    assert PERMISSAO in cache.get(chave_cache)

    # Simula alteração fora dos sinais de invalidação: o cache fica obsoleto.
    gestor_carga.user_permissions.through.objects.filter(
        user_id=gestor_carga.pk,
        permission__codename=PERMISSAO,
    ).delete()
    assert PERMISSAO in cache.get(chave_cache)
    try:
        resposta = _consultar(_sessao(gestor_carga))
        assert resposta.status_code == 200
        assert resposta.json()["resultado"] == "NEGADO"
    finally:
        cache.delete(chave_cache)


@override_settings(**CONFIGURACAO_PILOTO)
def test_piloto_http_integrado_autoriza_sessao_e_role_reais(gestor_carga):
    assert _guardar_carga(gestor_carga, _sessao(gestor_carga)) is True


@override_settings(**CONFIGURACAO_PILOTO)
def test_piloto_http_integrado_nega_apos_retirada_da_role(gestor_carga):
    sessao = _sessao(gestor_carga)
    assert _guardar_carga(gestor_carga, sessao) is True
    UserRole.objects.filter(user=gestor_carga, role__codigoperfil="GESTOR_CARGA").delete()
    with pytest.raises(PermissaoCargaNegada):
        _guardar_carga(gestor_carga, sessao)


@override_settings(**CONFIGURACAO_PILOTO)
def test_piloto_http_integrado_rejeita_sessao_revogada(gestor_carga):
    sessao = _sessao(gestor_carga, revogada=True)
    with pytest.raises(SessaoCargaInvalida):
        _guardar_carga(gestor_carga, sessao)


@override_settings(**CONFIGURACAO_PILOTO)
def test_piloto_http_integrado_rejeita_identidade_divergente(
    gestor_carga, usuario_sem_role
):
    sessao = _sessao(gestor_carga)
    with pytest.raises(ServicoIAMIndisponivel):
        _guardar_carga(usuario_sem_role, sessao)
