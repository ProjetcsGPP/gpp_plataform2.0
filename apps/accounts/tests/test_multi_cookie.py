import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, UserRole


# =========================================================
# HELPERS (infra-level)
# =========================================================

def _collect_all_routes(patterns, prefix=""):
    """
    Percorre recursivamente todos os URLpatterns (incluindo include())
    e retorna uma lista de rotas completas como strings.
    """
    from django.urls import URLResolver, URLPattern
    routes = []
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            routes.extend(_collect_all_routes(pattern.url_patterns, route))
        elif isinstance(pattern, URLPattern):
            routes.append(route)
    return routes


def get_any_url_for_app(prefix: str) -> str:
    """
    Retorna qualquer URL registrada no Django que contenha o prefixo.
    Percorre recursivamente URLResolvers aninhados (include()).
    """
    from django.urls import get_resolver
    all_routes = _collect_all_routes(get_resolver().url_patterns)
    for route in all_routes:
        if prefix in route:
            url = "/" + route.replace("//", "/")
            # Remove grupos de captura de regex e trailing slashes parciais
            import re
            url = re.sub(r"<[^>]+>", "1", url)   # <pk> -> 1
            url = re.sub(r"\([^)]+\)", "1", url)  # (?P<pk>...) -> 1
            url = url.rstrip("$")
            return url
    raise AssertionError(f"Nenhuma URL encontrada para prefixo '{prefix}'")


def assert_access_ok(resp):
    """
    Em testes de arquitetura:
    - 200 = acesso OK
    - 403 = endpoint existe, mas sem permissao (aceitavel)
    """
    assert resp.status_code in (200, 403), (
        f"Esperado 200 ou 403, recebido {resp.status_code}"
    )


# =========================================================
# FIXTURES AUXILIARES
# =========================================================

@pytest.fixture
def urls():
    """
    URLs fixas das apps dedicadas.
    Usar URLs hardcoded e mais robusto que descoberta dinamica via resolver,
    pois o resolver pode retornar rotas com parametros de captura.
    """
    return {
        "ACOES": "/api/acoes-pngi/",
        "CARGA": "/api/carga-org-lot/",
    }


@pytest.fixture
def grant_role(db):
    """
    Fixture factory: atribui uma Role extra a um usuario pelo codigoperfil.
    Usa get_or_create para ser idempotente (seguro com --reuse-db).

    Uso:
        grant_role(user, "GESTOR_CARGA")
    """
    def _grant(user, codigoperfil: str):
        role = Role.objects.get(codigoperfil=codigoperfil)
        user_role, created = UserRole.objects.get_or_create(
            user=user,
            aplicacao=role.aplicacao,
            defaults={"role": role},
        )
        if not created and user_role.role_id != role.pk:
            user_role.role = role
            user_role.save(update_fields=["role"])
        if role.group:
            user.groups.add(role.group)
        return role

    return _grant


# =========================================================
# TESTES
# =========================================================

@pytest.mark.django_db(transaction=True)
def test_login_denied_without_role(gestor_pngi):
    """
    Gestor PNGI nao tem role em CARGA_ORG_LOT.
    Login com app_context=CARGA_ORG_LOT deve retornar 403.
    """
    client = APIClient()

    resp = client.post("/api/accounts/login/", {
        "username": gestor_pngi.username,
        "password": "TestPass@2026",
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    assert resp.status_code == 403, (
        f"Esperado 403 (sem role em CARGA), recebido {resp.status_code}"
    )


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_multi_app_same_user_multi_cookie(gestor_pngi, grant_role, urls):
    """
    Mesmo usuario com roles em duas apps recebe cookies distintos
    e consegue acessar ambas as apps.
    """
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    grant_role(gestor_pngi, "GESTOR_CARGA")

    # LOGIN ACOES
    resp1 = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")

    assert resp1.status_code == 200, (
        f"Login ACOES_PNGI falhou: {resp1.status_code} {resp1.data}"
    )
    assert "gpp_session_ACOES_PNGI" in client.cookies, (
        "Cookie gpp_session_ACOES_PNGI ausente apos login"
    )

    # LOGIN CARGA
    resp2 = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    assert resp2.status_code == 200, (
        f"Login CARGA_ORG_LOT falhou: {resp2.status_code} {resp2.data}"
    )
    assert "gpp_session_CARGA_ORG_LOT" in client.cookies, (
        "Cookie gpp_session_CARGA_ORG_LOT ausente apos login"
    )

    # ambos acessos validos
    assert_access_ok(client.get(urls["ACOES"]))
    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_session_isolation_between_apps(gestor_pngi, grant_role, urls):
    """
    Remover o cookie de uma app nao afeta a sessao da outra.
    Sem cookie ACOES, o acesso ao endpoint de ACOES retorna 401.
    O cookie CARGA permanece valido.
    """
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

    # ambas validas
    assert_access_ok(client.get(urls["ACOES"]))
    assert_access_ok(client.get(urls["CARGA"]))

    # remove cookie ACOES manualmente
    del client.cookies["gpp_session_ACOES_PNGI"]

    # ACOES falha — sem cookie, middleware retorna AnonymousUser -> 401
    acoes_resp = client.get(urls["ACOES"])
    assert acoes_resp.status_code == 401, (
        f"Esperado 401 sem cookie ACOES, recebido {acoes_resp.status_code}"
    )

    # CARGA continua valida
    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_selective_logout(gestor_pngi, grant_role, urls):
    """
    Logout seletivo de ACOES_PNGI invalida apenas a sessao dessa app.
    A sessao de CARGA_ORG_LOT permanece ativa.
    """
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

    # logout seletivo da app ACOES_PNGI
    resp_logout = client.post("/api/accounts/logout/ACOES_PNGI/")
    assert resp_logout.status_code == 200, (
        f"Logout seletivo ACOES_PNGI falhou: {resp_logout.status_code}"
    )

    # ACOES invalido apos logout
    acoes_resp = client.get(urls["ACOES"])
    assert acoes_resp.status_code == 401, (
        f"Esperado 401 apos logout ACOES, recebido {acoes_resp.status_code}"
    )

    # CARGA continua valido
    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_role_cache_consistency(gestor_pngi, grant_role, urls):
    """
    Apos adicionar nova role ao usuario, o login na nova app deve funcionar.
    O cache de roles deve ser invalidado pelo sinal de mudanca de role.
    """
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    # login inicial em ACOES
    client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")

    assert_access_ok(client.get(urls["ACOES"]))

    # adiciona nova role -> deve invalidar cache
    grant_role(gestor_pngi, "GESTOR_CARGA")

    # login nova app
    resp = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")

    assert resp.status_code == 200, (
        f"Login CARGA apos grant_role falhou: {resp.status_code} {resp.data}"
    )

    assert_access_ok(client.get(urls["CARGA"]))


# ---------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_full_multi_app_regression_flow(gestor_pngi, grant_role, urls):
    """
    Fluxo completo de regressao:
    1. Login em duas apps -> ambas acessiveis
    2. Logout seletivo de ACOES -> ACOES retorna 401, CARGA continua OK
    """
    client = APIClient()

    username = gestor_pngi.username
    password = "TestPass@2026"

    grant_role(gestor_pngi, "GESTOR_CARGA")

    # login nas duas apps
    r1 = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "ACOES_PNGI"
    }, format="json")
    assert r1.status_code == 200, f"Login ACOES falhou: {r1.status_code}"

    r2 = client.post("/api/accounts/login/", {
        "username": username,
        "password": password,
        "app_context": "CARGA_ORG_LOT"
    }, format="json")
    assert r2.status_code == 200, f"Login CARGA falhou: {r2.status_code}"

    # ambos validos
    assert_access_ok(client.get(urls["ACOES"]))
    assert_access_ok(client.get(urls["CARGA"]))

    # logout seletivo de ACOES
    client.post("/api/accounts/logout/ACOES_PNGI/")

    # ACOES invalido
    assert client.get(urls["ACOES"]).status_code == 401, (
        "Esperado 401 para ACOES apos logout seletivo"
    )

    # CARGA continua valido
    assert_access_ok(client.get(urls["CARGA"]))
