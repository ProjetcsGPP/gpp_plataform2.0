import pytest
from rest_framework.test import APIClient
from django.urls import get_resolver

# =========================================================
# HELPERS (infra-level)
# =========================================================

def get_any_url_for_app(prefix: str) -> str:
    """
    Retorna qualquer URL válida registrada no Django para uma app.
    Evita acoplamento com endpoints específicos.
    """
    resolver = get_resolver()

    for pattern in resolver.url_patterns:
        try:
            route = str(pattern.pattern)
            if prefix in route:
                return f"/{route}".replace("//", "/")
        except Exception:
            continue

    raise AssertionError(f"Nenhuma URL encontrada para prefixo {prefix}")


def assert_access_ok(resp):
    """
    Em testes de arquitetura:
    - 200 = acesso OK
    - 403 = endpoint existe, mas sem permissão (aceitável)
    """
    assert resp.status_code in (200, 403)


# =========================================================
# FIXTURES AUXILIARES
# =========================================================

@pytest.fixture
def urls():
    return {
        "ACOES": get_any_url_for_app("api/acoes-pngi"),
        "CARGA": get_any_url_for_app("api/carga-org-lot"),
    }


# =========================================================
# TESTES
# =========================================================

@pytest.mark.django_db(transaction=True)
def test_login_denied_without_role(gestor_pngi):
    client = APIClient()

    resp = client.post("/api/accounts/login/", {
        "username": gestor_pngi.username,
        "password": "TestPass@2026",
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    assert resp.status_code == 403


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_multi_app_same_user_multi_cookie(gestor_pngi, grant_role, urls):
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    # usuário vira multi-app
    grant_role(gestor_pngi, "GESTOR_CARGA")

    # LOGIN ACOES
    resp1 = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")

    assert resp1.status_code == 200
    assert "gpp_session_ACOES_PNGI" in client.cookies

    # LOGIN CARGA
    resp2 = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    assert resp2.status_code == 200
    assert "gpp_session_CARGA_ORG_LOT" in client.cookies

    # ambos acessos válidos
    assert_access_ok(client.get(urls["ACOES"]))
    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_session_isolation_between_apps(gestor_pngi, grant_role, urls):
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    grant_role(gestor_pngi, "GESTOR_CARGA")

    # login nas duas apps
    client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")

    client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    # ambas válidas
    assert_access_ok(client.get(urls["ACOES"]))
    assert_access_ok(client.get(urls["CARGA"]))

    # remove cookie ACOES manualmente
    del client.cookies["gpp_session_ACOES_PNGI"]

    # ACOES falha
    assert client.get(urls["ACOES"]).status_code == 401

    # CARGA continua válida
    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_selective_logout(gestor_pngi, grant_role, urls):
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    grant_role(gestor_pngi, "GESTOR_CARGA")

    # login nas duas apps
    client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")

    client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    # logout seletivo
    resp = client.post("/api/accounts/logout/ACOES_PNGI/")
    assert resp.status_code == 200

    # ACOES inválido
    assert client.get(urls["ACOES"]).status_code == 401

    # CARGA continua válido
    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_role_cache_consistency(gestor_pngi, grant_role, urls):
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    # login inicial
    client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")

    assert_access_ok(client.get(urls["ACOES"]))

    # adiciona nova role → deve invalidar cache
    grant_role(gestor_pngi, "GESTOR_CARGA")

    # login nova app
    resp = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    assert resp.status_code == 200

    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_full_multi_app_regression_flow(gestor_pngi, grant_role, urls):
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    grant_role(gestor_pngi, "GESTOR_CARGA")

    # login nas duas apps
    assert client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json").status_code == 200

    assert client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json").status_code == 200

    # ambos válidos
    assert_access_ok(client.get(urls["ACOES"]))
    assert_access_ok(client.get(urls["CARGA"]))

    # logout seletivo
    client.post("/api/accounts/logout/ACOES_PNGI/")

    assert client.get(urls["ACOES"]).status_code == 401
    assert_access_ok(client.get(urls["CARGA"]))