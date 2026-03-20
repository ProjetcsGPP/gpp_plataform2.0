# apps/accounts/tests/test_auth_aplicacoes.py
"""
Testes do AplicacaoPublicaViewSet — endpoint PÚBLICO.

Endpoint coberto: GET /api/accounts/auth/aplicacoes/

Regras:
  - AllowAny: anônimo recebe 200.
  - Retorna APENAS apps ativas: isappbloqueada=False AND isappproductionready=True.
  - Apps bloqueadas ou não prontas NAO aparecem.
  - Campos expostos: apenas codigointerno e nomeaplicacao (sem flags internos).
  - ReadOnly: POST/PUT/DELETE retornam 405.
  - Detalhe por codigointerno: GET /api/accounts/auth/aplicacoes/{codigointerno}/
"""
import pytest

pytestmark = pytest.mark.django_db

URL = "/api/accounts/auth/aplicacoes/"


# --- Acesso público ----------------------------------------------------------

class TestAuthAplicacoesPublico:

    def test_anonimo_recebe_200(self, client_anonimo):
        """Endpoint público — não requer autenticação."""
        resp = client_anonimo.get(URL)
        assert resp.status_code == 200

    def test_retorna_lista(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert isinstance(resp.data, list)

    def test_retorna_pelo_menos_3_apps(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert len(resp.data) >= 3

    def test_apps_principais_estao_presentes(self, client_anonimo):
        resp = client_anonimo.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert {"PORTAL", "ACOES_PNGI", "CARGA_ORG_LOT"}.issubset(codigos)


# --- Filtragem de apps inativas ----------------------------------------------

class TestAuthAplicacoesFiltragem:

    def test_app_bloqueada_nao_aparece(self, client_anonimo):
        resp = client_anonimo.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_BLOQUEADA" not in codigos

    def test_app_nao_pronta_nao_aparece(self, client_anonimo):
        resp = client_anonimo.get(URL)
        codigos = {a["codigointerno"] for a in resp.data}
        assert "APP_NAO_PRONTA" not in codigos


# --- Campos expostos (sem vazamento de flags internos) ----------------------

class TestAuthAplicacoesCampos:

    def test_campo_codigointerno_presente(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert "codigointerno" in resp.data[0]

    def test_campo_nomeaplicacao_presente(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert "nomeaplicacao" in resp.data[0]

    def test_flag_isappbloqueada_nao_exposto(self, client_anonimo):
        """Endpoint público não vaza flags internos de controle."""
        resp = client_anonimo.get(URL)
        assert "isappbloqueada" not in resp.data[0]

    def test_flag_isappproductionready_nao_exposto(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert "isappproductionready" not in resp.data[0]

    def test_idaplicacao_nao_exposto(self, client_anonimo):
        """PK interna não deve ser exposta publicamente."""
        resp = client_anonimo.get(URL)
        assert "idaplicacao" not in resp.data[0]


# --- Detalhe por codigointerno -----------------------------------------------

class TestAuthAplicacoesDetalhe:

    def test_detalhe_portal_retorna_200(self, client_anonimo):
        resp = client_anonimo.get(f"{URL}PORTAL/")
        assert resp.status_code == 200

    def test_detalhe_portal_campos_corretos(self, client_anonimo):
        resp = client_anonimo.get(f"{URL}PORTAL/")
        assert resp.data["codigointerno"] == "PORTAL"
        assert "nomeaplicacao" in resp.data

    def test_detalhe_app_bloqueada_retorna_404(self, client_anonimo):
        """App bloqueada está fora do queryset público — deve retornar 404."""
        resp = client_anonimo.get(f"{URL}APP_BLOQUEADA/")
        assert resp.status_code == 404

    def test_detalhe_app_inexistente_retorna_404(self, client_anonimo):
        resp = client_anonimo.get(f"{URL}NAO_EXISTE/")
        assert resp.status_code == 404


# --- ReadOnly ----------------------------------------------------------------

class TestAuthAplicacoesReadOnly:

    def test_post_retorna_405(self, client_anonimo):
        resp = client_anonimo.post(
            URL,
            {"codigointerno": "NOVA", "nomeaplicacao": "Nova"},
            format="json",
        )
        assert resp.status_code == 405

    def test_put_retorna_405(self, client_anonimo):
        resp = client_anonimo.put(f"{URL}PORTAL/", {}, format="json")
        assert resp.status_code == 405

    def test_delete_retorna_405(self, client_anonimo):
        resp = client_anonimo.delete(f"{URL}PORTAL/")
        assert resp.status_code == 405
