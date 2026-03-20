# apps/accounts/tests/test_roles.py
"""
Testes do RoleViewSet.

Endpoints cobertos:
  GET /api/accounts/roles/
  GET /api/accounts/roles/?aplicacao_id={id}

Regras validadas:
  PORTAL_ADMIN:
    - Lista todas as roles (sem filtro)
    - Filtra por aplicacao_id corretamente
    - aplicacao_id invalido (string) retorna lista vazia, nao 500
    - aplicacao_id inexistente retorna lista vazia

  Qualquer usuario nao-admin:
    - GET retorna 403

  Nao autenticado:
    - GET retorna 401/403

Dados base: initial_data.json
  Role pk=1  -> PORTAL_ADMIN   / Aplicacao pk=1
  Role pk=2  -> GESTOR_PNGI    / Aplicacao pk=2
  Role pk=3  -> COORDENADOR_PNGI / Aplicacao pk=2
  Role pk=4  -> OPERADOR_ACAO  / Aplicacao pk=2
  Role pk=6  -> GESTOR_CARGA   / Aplicacao pk=3
"""
import pytest

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/accounts/roles/"


# --- PORTAL_ADMIN ------------------------------------------------------------

class TestRolesPortalAdmin:

    def test_lista_retorna_200(self, client_portal_admin):
        resp = client_portal_admin.get(URL)
        assert resp.status_code == 200

    def test_lista_tem_pelo_menos_4_roles(self, client_portal_admin):
        """initial_data.json tem ao menos 4 roles cadastradas."""
        resp = client_portal_admin.get(URL)
        assert len(resp.data) >= 4

    def test_filtra_por_aplicacao_id_acoes_pngi(self, client_portal_admin):
        """Aplicacao pk=2 (ACOES_PNGI) tem 3 roles no initial_data."""
        resp = client_portal_admin.get(f"{URL}?aplicacao_id=2")
        assert resp.status_code == 200
        assert len(resp.data) >= 3
        for role in resp.data:
            assert role["aplicacao"] == 2

    def test_filtra_por_aplicacao_id_portal(self, client_portal_admin):
        """Aplicacao pk=1 (PORTAL) tem 1 role no initial_data."""
        resp = client_portal_admin.get(f"{URL}?aplicacao_id=1")
        assert resp.status_code == 200
        for role in resp.data:
            assert role["aplicacao"] == 1

    def test_aplicacao_id_string_invalido_retorna_lista_vazia(self, client_portal_admin):
        """Nao deve gerar 500 — deve retornar lista vazia."""
        resp = client_portal_admin.get(f"{URL}?aplicacao_id=abc")
        assert resp.status_code == 200
        assert resp.data == []

    def test_aplicacao_id_inexistente_retorna_lista_vazia(self, client_portal_admin):
        resp = client_portal_admin.get(f"{URL}?aplicacao_id=9999")
        assert resp.status_code == 200
        assert resp.data == []

    def test_roles_pngi_contem_codigosperfil_corretos(self, client_portal_admin):
        resp = client_portal_admin.get(f"{URL}?aplicacao_id=2")
        codigos = {r["codigoperfil"] for r in resp.data}
        assert {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}.issubset(codigos)


# --- Acesso negado para usuarios comuns --------------------------------------

class TestRolesAcessoNegado:

    def test_gestor_pngi_retorna_403(self, client_gestor):
        resp = client_gestor.get(URL)
        assert resp.status_code == 403

    def test_coordenador_pngi_retorna_403(self, client_coordenador):
        resp = client_coordenador.get(URL)
        assert resp.status_code == 403

    def test_operador_acao_retorna_403(self, client_operador):
        resp = client_operador.get(URL)
        assert resp.status_code == 403

    def test_anonimo_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(URL)
        assert resp.status_code in (401, 403)
