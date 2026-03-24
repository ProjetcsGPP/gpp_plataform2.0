"""
Policy tests: COORDENADOR_PNGI tem READ + WRITE, sem DELETE.
"""
import pytest

from apps.acoes_pngi.tests.conftest import ACOES_URL, VIGENCIAS_URL


class TestCoordenadorPNGI:
    """COORDENADOR_PNGI pode ler e escrever, mas nao pode deletar."""

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_acoes(self, client_coordenador):
        assert client_coordenador.get(ACOES_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_criar_acao(self, client_coordenador, payload_acao):
        payload_acao["strapelido"] = "ACAO-COORD-POL"
        resp = client_coordenador.post(ACOES_URL, payload_acao, format="json")
        assert resp.status_code == 201

    @pytest.mark.django_db(transaction=True)
    def test_pode_atualizar_acao(self, client_coordenador, acao):
        resp = client_coordenador.patch(
            f"{ACOES_URL}{acao.pk}/",
            {"strdescricaoentrega": "Atualizado pelo coordenador"},
            format="json",
        )
        assert resp.status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_deletar_acao(self, client_coordenador, acao):
        assert client_coordenador.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_deletar_vigencia(self, client_coordenador, vigencia):
        assert client_coordenador.delete(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_pode_criar_vigencia(self, client_coordenador):
        payload = {"strdescricao": "PNGI Coord", "datiniciovigencia": "2028-01-01"}
        resp = client_coordenador.post(VIGENCIAS_URL, payload, format="json")
        assert resp.status_code == 201
