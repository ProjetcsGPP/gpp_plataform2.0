import pytest
from rest_framework.test import APIClient
from apps.accounts.models import AccountsSession

@pytest.mark.django_db(transaction=True)
def test_multi_cookie_login_logout(client: APIClient, gestor_acoes, app_acoes):
    # Login ACOES_PNGI
    login_resp = client.post("/api/accounts/login/", {
        "username": gestor_acoes.username,
        "password": "gpp@2026",
        "app_context": "ACOES_PNGI"
    }, format="json")
    assert login_resp.status_code == 200
    assert "gpp_session_ACOES_PNGI" in login_resp.cookies
    
    # Verificar cookie correto enviado
    acoes_resp = client.get("/api/acoes-pngi/acoes/")
    assert acoes_resp.status_code == 200  # Tem role
    
    # Logout específico ACOES_PNGI
    logout_resp = client.post("/api/acoes-pngi/auth/logout/")
    assert logout_resp.status_code == 200
    
    # Tentar acessar novamente → 401
    acoes_resp2 = client.get("/api/acoes-pngi/acoes/")
    assert acoes_resp2.status_code == 401

@pytest.mark.django_db(transaction=True) 
def test_multi_app_parallel(client: APIClient, gestor_acoes, gestor_carga, app_acoes, app_carga):
    # Login ACOES_PNGI em client1
    client1 = APIClient()
    client1.post("/api/accounts/login/", {
        "username": gestor_acoes.username,
        "password": "gpp@2026", 
        "app_context": "ACOES_PNGI"
    })
    
    # Login CARGA_ORG_LOT em client2 (simula outra tab)
    client2 = APIClient()
    client2.post("/api/accounts/login/", {
        "username": gestor_carga.username,
        "password": "gpp@2026",
        "app_context": "CARGA_ORG_LOT"
    })
    
    # AMBAS funcionam simultaneamente
    assert client1.get("/api/acoes-pngi/acoes/").status_code == 200
    assert client2.get("/api/carga-org-lot/orgaos/").status_code == 200  # assumindo endpoint