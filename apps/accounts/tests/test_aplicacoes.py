# apps/accounts/tests/test_aplicacoes.py
"""
Testes do AplicacaoViewSet.

Endpoints cobertos:
  GET /api/accounts/aplicacoes/
  GET /api/accounts/aplicacoes/{id}/

Nao usa transaction=True: savepoints sao suficientes para testes HTTP
e evitam o problema de TRUNCATE bloqueado por FK de tblusuarioresponsavel.
"""
import pytest

pytestmark = pytest.mark.django_db

URL = "/api/accounts/aplicacoes/"


# --- PORTAL_ADMIN: visao irrestrita ------------------------------------------

class TestAplicacoesPortalAdmin:

    def test_portal_admin_recebe_200(self, client_portal_admin):
        resp = client_portal_admin.get(URL)
        assert resp.status_code == 200

    def test_portal_admin_ve_pelo_menos_3_apps(self, client_portal_admin):
        resp = client_portal_admin.get(URL)
        assert len(resp.data) >= 3

    def test_portal_admin_ve_todas_as_apps_do_initial_data(self, client_portal_admin):
        resp = client_portal_admin.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert {"PORTAL", "ACOES_PNGI", "CARGA_ORG_LOT"}.issubset(codigos)

    def test_portal_admin_ve_app_bloqueada(self, client_portal_admin):
        resp = client_portal_admin.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_BLOQUEADA" in codigos

    def test_portal_admin_ve_app_nao_pronta(self, client_portal_admin):
        resp = client_portal_admin.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_NAO_PRONTA" in codigos

    def test_superuser_tambem_ve_todas_as_apps(self, client_superuser):
        resp = client_superuser.get(URL)
        assert resp.status_code == 200
        assert len(resp.data) >= 3


# --- Usuario comum: escopo restrito ------------------------------------------

class TestAplicacoesUsuarioComum:

    def test_gestor_ve_acoes_pngi(self, client_gestor):
        resp = client_gestor.get(URL)
        assert resp.status_code == 200
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" in codigos

    def test_gestor_nao_ve_portal(self, client_gestor):
        resp = client_gestor.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "PORTAL" not in codigos

    def test_gestor_nao_ve_carga_org_lot(self, client_gestor):
        resp = client_gestor.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "CARGA_ORG_LOT" not in codigos

    def test_gestor_nao_ve_app_bloqueada(self, client_gestor):
        resp = client_gestor.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_BLOQUEADA" not in codigos

    def test_gestor_nao_ve_app_nao_pronta(self, client_gestor):
        resp = client_gestor.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_NAO_PRONTA" not in codigos

    def test_coordenador_ve_acoes_pngi(self, client_coordenador):
        resp = client_coordenador.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" in codigos

    def test_operador_ve_acoes_pngi(self, client_operador):
        resp = client_operador.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" in codigos

    def test_gestor_carga_ve_carga_org_lot(self, client_gestor_carga):
        resp = client_gestor_carga.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "CARGA_ORG_LOT" in codigos

    def test_gestor_carga_nao_ve_acoes_pngi(self, client_gestor_carga):
        resp = client_gestor_carga.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" not in codigos


# --- Acesso nao autenticado --------------------------------------------------

class TestAplicacoesNaoAutenticado:

    def test_get_sem_autenticacao_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert resp.status_code in (401, 403)


# --- ReadOnly ----------------------------------------------------------------

class TestAplicacoesReadOnly:

    def test_post_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.post(
            URL,
            {"codigointerno": "NOVA_APP", "nomeaplicacao": "Nova"},
            format="json",
        )
        assert resp.status_code == 405

    def test_put_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.put(f"{URL}1/", {}, format="json")
        assert resp.status_code == 405

    def test_delete_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.delete(f"{URL}1/")
        assert resp.status_code == 405
