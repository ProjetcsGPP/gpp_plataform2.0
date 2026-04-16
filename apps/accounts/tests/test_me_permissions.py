"""
Testes automatizados: GET /api/accounts/me/permissions/

Cobre os mesmos cenários do script manual test_me_permissions.ps1.

Cenários:
  TC-01  GESTOR_PNGI autenticado em ACOES_PNGI    → 200, role + granted
  TC-02  COORDENADOR_PNGI autenticado em ACOES_PNGI → 200, role + granted
  TC-03  OPERADOR_ACAO autenticado em ACOES_PNGI  → 200, role + granted
  TC-04  GESTOR_CARGA autenticado em CARGA_ORG_LOT → 200, role + granted
  TC-05  PORTAL_ADMIN autenticado em PORTAL        → 200, role + granted
  TC-06  SuperUser autenticado em PORTAL           → 200, role ou 404 (superuser sem UserRole)
  TC-07  Sem autenticação                          → 401
  TC-08  Usuário sem role na app (ACOES_PNGI)      → 401 (middleware bloqueia) ou 404 (sem UserRole)
  TC-09  app_context ausente na request            → 400
  TC-10  App bloqueada no contexto                 → 404
  TC-11  PORTAL_ADMIN tenta acessar app de outra   → comportamento via fallback do middleware

NOTA: A autenticação é feita via login real (POST /api/accounts/login/)
      tal como o conftest desta app define nos helpers _do_login e
      _make_authenticated_client. O middleware AppContextMiddleware
      preenche request.app_context a partir do cookie gpp_session_{APP}.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.conftest import _make_authenticated_client

ME_PERMISSIONS_URL = "/api/accounts/me/permissions/"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _assert_permissions_200(resp, expected_role_code: str):
    """Verifica que a resposta é 200 com a estrutura correta."""
    assert (
        resp.status_code == 200
    ), f"Esperado 200, recebido {resp.status_code}. Body: {resp.data}"
    data = resp.data
    assert "role" in data, f"Chave 'role' ausente: {data}"
    assert "granted" in data, f"Chave 'granted' ausente: {data}"
    assert (
        data["role"] == expected_role_code
    ), f"Role esperada '{expected_role_code}', recebida '{data['role']}'"
    assert isinstance(
        data["granted"], list
    ), f"'granted' deve ser lista, recebido: {type(data['granted'])}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-01 — GESTOR_PNGI em ACOES_PNGI → 200
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_gestor_pngi(gestor_pngi):
    """
    TC-01: GESTOR_PNGI autenticado em ACOES_PNGI deve retornar 200
    com role=GESTOR_PNGI e lista de granted.
    """
    client, login_resp = _make_authenticated_client("gestor_test", "ACOES_PNGI")
    assert (
        login_resp.status_code == 200
    ), f"Login falhou: {login_resp.status_code} {login_resp.data}"

    resp = client.get(ME_PERMISSIONS_URL)
    _assert_permissions_200(resp, "GESTOR_PNGI")


# ─────────────────────────────────────────────────────────────────────────────
# TC-02 — COORDENADOR_PNGI em ACOES_PNGI → 200
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_coordenador_pngi(coordenador_pngi):
    """
    TC-02: COORDENADOR_PNGI autenticado em ACOES_PNGI deve retornar 200
    com role=COORDENADOR_PNGI.
    """
    client, login_resp = _make_authenticated_client("coordenador_test", "ACOES_PNGI")
    assert (
        login_resp.status_code == 200
    ), f"Login falhou: {login_resp.status_code} {login_resp.data}"

    resp = client.get(ME_PERMISSIONS_URL)
    _assert_permissions_200(resp, "COORDENADOR_PNGI")


# ─────────────────────────────────────────────────────────────────────────────
# TC-03 — OPERADOR_ACAO em ACOES_PNGI → 200
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_operador_acao(operador_acao):
    """
    TC-03: OPERADOR_ACAO autenticado em ACOES_PNGI deve retornar 200
    com role=OPERADOR_ACAO.
    """
    client, login_resp = _make_authenticated_client("operador_test", "ACOES_PNGI")
    assert (
        login_resp.status_code == 200
    ), f"Login falhou: {login_resp.status_code} {login_resp.data}"

    resp = client.get(ME_PERMISSIONS_URL)
    _assert_permissions_200(resp, "OPERADOR_ACAO")


# ─────────────────────────────────────────────────────────────────────────────
# TC-04 — GESTOR_CARGA em CARGA_ORG_LOT → 200
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_gestor_carga(gestor_carga):
    """
    TC-04: GESTOR_CARGA autenticado em CARGA_ORG_LOT deve retornar 200
    com role=GESTOR_CARGA.
    """
    client, login_resp = _make_authenticated_client(
        "gestor_carga_test", "CARGA_ORG_LOT"
    )
    assert (
        login_resp.status_code == 200
    ), f"Login falhou: {login_resp.status_code} {login_resp.data}"

    resp = client.get(ME_PERMISSIONS_URL)
    _assert_permissions_200(resp, "GESTOR_CARGA")


# ─────────────────────────────────────────────────────────────────────────────
# TC-05 — PORTAL_ADMIN em PORTAL → 200
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_portal_admin(portal_admin):
    """
    TC-05: PORTAL_ADMIN autenticado em PORTAL deve retornar 200
    com role=PORTAL_ADMIN.
    """
    client, login_resp = _make_authenticated_client("portal_admin_test", "PORTAL")
    assert (
        login_resp.status_code == 200
    ), f"Login falhou: {login_resp.status_code} {login_resp.data}"

    resp = client.get(ME_PERMISSIONS_URL)
    _assert_permissions_200(resp, "PORTAL_ADMIN")


# ─────────────────────────────────────────────────────────────────────────────
# TC-06 — SuperUser (sem UserRole) em PORTAL → 404 (no_role)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_superuser_sem_role(superuser):
    """
    TC-06: SuperUser sem UserRole atribuída em PORTAL.
    O login é bem-sucedido (superuser bypassa verificação de role no login),
    mas /me/permissions/ retorna 404 pois não há UserRole na tabela.
    """
    client, login_resp = _make_authenticated_client("superuser_test", "PORTAL")
    assert (
        login_resp.status_code == 200
    ), f"Login falhou: {login_resp.status_code} {login_resp.data}"

    resp = client.get(ME_PERMISSIONS_URL)
    # Superuser sem UserRole → 404 com code=no_role
    assert (
        resp.status_code == 404
    ), f"Esperado 404 para superuser sem UserRole, recebido {resp.status_code}. Body: {resp.data}"
    assert resp.data.get("code") == "no_role"


# ─────────────────────────────────────────────────────────────────────────────
# TC-07 — Sem autenticação → 401
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_sem_autenticacao():
    """
    TC-07: Request sem cookie algum deve retornar 401.
    O middleware deixa request.user=AnonymousUser e a permissão
    IsAuthenticated bloqueia com 401.
    """
    client = APIClient()
    resp = client.get(ME_PERMISSIONS_URL)
    assert (
        resp.status_code == 401
    ), f"Esperado 401 para request anônima, recebido {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-08 — Cookie forjado → 401
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_cookie_forjado():
    """
    TC-08: Cookie gpp_session_PORTAL com valor inválido.
    O middleware não encontra AccountsSession correspondente e
    retorna 401 (sessão inválida) antes mesmo de chegar na view.
    """
    client = APIClient()
    client.cookies["gpp_session_PORTAL"] = "sessao_invalida_forjada_12345"
    resp = client.get(ME_PERMISSIONS_URL)
    assert (
        resp.status_code == 401
    ), f"Esperado 401 para cookie forjado, recebido {resp.status_code}. Body: {resp.data}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-09 — app_context ausente na request → 400
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_sem_app_context(gestor_pngi):
    """
    TC-09: Usuário autenticado mas request.app_context ausente (None).
    Simula um cenário onde o middleware não consegue resolver o contexto
    (ex: sessão válida mas app_context não gravado no AccountsSession).
    Resposta esperada: 400 com code=no_app_context.
    """

    from django.contrib.auth.models import User
    from rest_framework.test import APIRequestFactory

    from apps.accounts.views import MePermissionView

    user = User.objects.get(username="gestor_test")
    factory = APIRequestFactory()
    request = factory.get(ME_PERMISSIONS_URL)
    request.user = user
    # Garante que app_context está ausente e session não tem o valor
    request.app_context = None
    request.session = {}

    view = MePermissionView.as_view()
    response = view(request)

    assert (
        response.status_code == 400
    ), f"Esperado 400 quando app_context ausente, recebido {response.status_code}"
    assert response.data.get("code") == "no_app_context"


# ─────────────────────────────────────────────────────────────────────────────
# TC-10 — App bloqueada → 404
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_app_bloqueada(gestor_pngi):
    """
    TC-10: app_context aponta para uma aplicação bloqueada.
    A view deve retornar 404 com code=app_not_found.
    """

    from django.contrib.auth.models import User
    from rest_framework.test import APIRequestFactory

    from apps.accounts.views import MePermissionView

    user = User.objects.get(username="gestor_test")
    factory = APIRequestFactory()
    request = factory.get(ME_PERMISSIONS_URL)
    request.user = user
    request.app_context = "APP_BLOQUEADA"
    request.session = {}

    view = MePermissionView.as_view()
    response = view(request)

    assert (
        response.status_code == 404
    ), f"Esperado 404 para app bloqueada, recebido {response.status_code}. Body: {response.data}"
    assert response.data.get("code") == "app_not_found"


# ─────────────────────────────────────────────────────────────────────────────
# TC-11 — Usuário sem role em app válida → 404
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_usuario_sem_role_na_app(gestor_pngi):
    """
    TC-11: Usuário autenticado, app_context válido,
    mas sem UserRole na aplicação informada.
    Resposta esperada: 404 com code=no_role.

    Usamos APIRequestFactory diretamente para definir app_context
    sem depender da camada de autenticação real.
    """
    from django.contrib.auth.models import User
    from rest_framework.test import APIRequestFactory

    from apps.accounts.views import MePermissionView

    # gestor_pngi tem role em ACOES_PNGI mas NÃO em CARGA_ORG_LOT
    user = User.objects.get(username="gestor_test")
    factory = APIRequestFactory()
    request = factory.get(ME_PERMISSIONS_URL)
    request.user = user
    request.app_context = "CARGA_ORG_LOT"  # app válida, sem role para este usuário
    request.session = {}

    view = MePermissionView.as_view()
    response = view(request)

    assert (
        response.status_code == 404
    ), f"Esperado 404 quando sem role na app, recebido {response.status_code}. Body: {response.data}"
    assert response.data.get("code") == "no_role"


# ─────────────────────────────────────────────────────────────────────────────
# TC-12 — Estrutura completa da resposta 200
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_me_permissions_estrutura_resposta(gestor_pngi):
    """
    TC-12: Verifica a estrutura completa da resposta 200:
    - Campos obrigatórios: role, granted
    - role deve ser string
    - granted deve ser lista de strings
    """
    client, login_resp = _make_authenticated_client("gestor_test", "ACOES_PNGI")
    assert login_resp.status_code == 200

    resp = client.get(ME_PERMISSIONS_URL)
    assert resp.status_code == 200

    data = resp.data
    assert isinstance(data.get("role"), str), "'role' deve ser string"
    assert isinstance(data.get("granted"), list), "'granted' deve ser lista"
    for item in data["granted"]:
        assert isinstance(
            item, str
        ), f"Cada item de 'granted' deve ser string, recebido: {type(item)}"
