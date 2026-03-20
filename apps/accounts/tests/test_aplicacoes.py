# apps/accounts/tests/test_aplicacoes.py
"""
Testes do AplicacaoViewSet.

Endpoint coberto:
  GET /api/accounts/aplicacoes/
  GET /api/accounts/aplicacoes/{id}/

Regras validadas:
  PORTAL_ADMIN / SuperUser:
    - Vê TODAS as aplicações (sem filtro de flags)
    - Vê apps bloqueadas (isappbloqueada=True)
    - Vê apps não prontas (isappproductionready=False)

  Usuário comum:
    - Vê apenas apps onde possui UserRole
    - Não vê apps bloqueadas
    - Não vê apps não prontas
    - Lista vazia se não tiver nenhuma UserRole ativa

  Qualquer perfil autenticado:
    - Deve encontrar ACOES_PNGI na lista (pk=2 do initial_data)
    - ViewSet é ReadOnly: POST/PUT/PATCH/DELETE → 405

  Não autenticado:
    - GET → 401/403

Dados base: initial_data.json + policy_expansion_flags.json
  APP_BLOQUEADA  → isappbloqueada=True
  APP_NAO_PRONTA → isappproductionready=False
"""
import pytest

pytestmark = pytest.mark.django_db(transaction=True)

APLICAC OES_URL = "/api/accounts/aplicacoes/"


# ─── PORTAL_ADMIN: visão irrestrita ──────────────────────────────────────────

class TestAplicacoesPortalAdmin:

    def test_portal_admin_recebe_200(self, client_portal_admin):
        resp = client_portal_admin.get(APLICACOES_URL)
        assert resp.status_code == 200

    def test_portal_admin_ve_pelo_menos_3_apps(self, client_portal_admin):
        """initial_data.json tem 3 apps (PORTAL, ACOES_PNGI, CARGA_ORG_LOT)."""
        resp = client_portal_admin.get(APLICACOES_URL)
        assert len(resp.data) >= 3

    def test_portal_admin_ve_todas_as_apps_do_initial_data(self, client_portal_admin):
        resp = client_portal_admin.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert {"PORTAL", "ACOES_PNGI", "CARGA_ORG_LOT"}.issubset(codigos)

    def test_portal_admin_ve_app_bloqueada(self, client_portal_admin):
        """APP_BLOQUEADA (policy_expansion_flags.json) deve aparecer para admin."""
        resp = client_portal_admin.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_BLOQUEADA" in codigos

    def test_portal_admin_ve_app_nao_pronta(self, client_portal_admin):
        resp = client_portal_admin.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_NAO_PRONTA" in codigos

    def test_superuser_tambem_ve_todas_as_apps(self, client_superuser):
        resp = client_superuser.get(APLICACOES_URL)
        assert resp.status_code == 200
        assert len(resp.data) >= 3


# ─── Usuário comum: escopo restrito ───────────────────────────────────────────

class TestAplicacoesUsuarioComum:

    def test_gestor_ve_acoes_pngi(self, client_gestor):
        resp = client_gestor.get(APLICACOES_URL)
        assert resp.status_code == 200
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" in codigos

    def test_gestor_nao_ve_portal(self, client_gestor):
        """Gestor não tem UserRole no PORTAL."""
        resp = client_gestor.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "PORTAL" not in codigos

    def test_gestor_nao_ve_carga_org_lot(self, client_gestor):
        resp = client_gestor.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "CARGA_ORG_LOT" not in codigos

    def test_gestor_nao_ve_app_bloqueada(self, client_gestor):
        resp = client_gestor.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_BLOQUEADA" not in codigos

    def test_gestor_nao_ve_app_nao_pronta(self, client_gestor):
        resp = client_gestor.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_NAO_PRONTA" not in codigos

    def test_coordenador_ve_acoes_pngi(self, client_coordenador):
        resp = client_coordenador.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" in codigos

    def test_operador_ve_acoes_pngi(self, client_operador):
        resp = client_operador.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" in codigos

    def test_gestor_carga_ve_carga_org_lot(self, client_gestor_carga):
        resp = client_gestor_carga.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "CARGA_ORG_LOT" in codigos

    def test_gestor_carga_nao_ve_acoes_pngi(self, client_gestor_carga):
        resp = client_gestor_carga.get(APLICACOES_URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "ACOES_PNGI" not in codigos


# ─── Acesso não autenticado ──────────────────────────────────────────────────

class TestAplicacoesNaoAutenticado:

    def test_get_sem_autenticacao_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(APLICACOES_URL)
        assert resp.status_code in (401, 403)


# ─── ReadOnly ────────────────────────────────────────────────────────────────

class TestAplicacoesReadOnly:

    def test_post_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.post(
            APLICACOES_URL,
            {"codigointerno": "NOVA_APP", "nomeaplicacao": "Nova"},
            format="json",
        )
        assert resp.status_code == 405

    def test_put_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.put(f"{APLICACOES_URL}1/", {}, format="json")
        assert resp.status_code == 405

    def test_delete_retorna_405(self, client_portal_admin):
        resp = client_portal_admin.delete(f"{APLICACOES_URL}1/")
        assert resp.status_code == 405
