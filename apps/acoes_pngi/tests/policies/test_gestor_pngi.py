"""
Policy tests: GESTOR_PNGI tem acesso total (READ + WRITE + DELETE).
"""
import pytest

from apps.acoes_pngi.tests.conftest import ACOES_URL, VIGENCIAS_URL


class TestGestorPNGI:
    """GESTOR_PNGI tem acesso completo a todos os endpoints de acoes_pngi."""

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_acoes(self, client_gestor):
        assert client_gestor.get(ACOES_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_criar_acao(self, client_gestor, payload_acao):
        resp = client_gestor.post(ACOES_URL, payload_acao, format="json")
        assert resp.status_code == 201

    @pytest.mark.django_db(transaction=True)
    def test_pode_recuperar_acao(self, client_gestor, acao):
        resp = client_gestor.get(f"{ACOES_URL}{acao.pk}/")
        assert resp.status_code == 200
        assert resp.json()["idacao"] == acao.pk

    @pytest.mark.django_db(transaction=True)
    def test_pode_atualizar_acao(self, client_gestor, acao):
        resp = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/",
            {"strdescricaoentrega": "Atualizado pelo gestor"},
            format="json",
        )
        assert resp.status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_deletar_acao(self, client_gestor, acao):
        resp = client_gestor.delete(f"{ACOES_URL}{acao.pk}/")
        assert resp.status_code == 204

    @pytest.mark.django_db(transaction=True)
    def test_pode_criar_vigencia(self, client_gestor):
        payload = {"strdescricao": "PNGI Gestor", "datiniciovigencia": "2027-01-01"}
        resp = client_gestor.post(VIGENCIAS_URL, payload, format="json")
        assert resp.status_code == 201

    @pytest.mark.django_db(transaction=True)
    def test_pode_deletar_vigencia(self, client_gestor, vigencia):
        resp = client_gestor.delete(f"{VIGENCIAS_URL}{vigencia.pk}/")
        assert resp.status_code == 204

    @pytest.mark.django_db(transaction=True)
    def test_created_by_id_preenchido(self, client_gestor, payload_acao, gestor_pngi):
        resp = client_gestor.post(ACOES_URL, payload_acao, format="json")
        assert resp.status_code == 201
        assert resp.json()["created_by_id"] == gestor_pngi.pk
