"""
Policy tests: OPERADOR_ACAO tem READ + WRITE, sem DELETE.
"""
import pytest

from apps.acoes_pngi.tests.conftest import ACOES_URL


class TestOperadorAcao:
    """OPERADOR_ACAO pode ler e escrever, mas nao pode deletar."""

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_acoes(self, client_operador):
        assert client_operador.get(ACOES_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_criar_acao(self, client_operador, payload_acao):
        payload_acao["strapelido"] = "ACAO-OPER-POL"
        resp = client_operador.post(ACOES_URL, payload_acao, format="json")
        assert resp.status_code == 201

    @pytest.mark.django_db(transaction=True)
    def test_pode_atualizar_acao(self, client_operador, acao):
        resp = client_operador.patch(
            f"{ACOES_URL}{acao.pk}/",
            {"strdescricaoentrega": "Atualizado pelo operador"},
            format="json",
        )
        assert resp.status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_deletar_acao(self, client_operador, acao):
        assert client_operador.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_criar_vigencia(self, client_operador):
        """OPERADOR_ACAO nao tem permissao WRITE para VigenciaPNGI — 403."""
        from apps.acoes_pngi.tests.conftest import VIGENCIAS_URL
        payload = {"strdescricao": "PNGI Oper", "datiniciovigencia": "2031-01-01"}
        resp = client_operador.post(VIGENCIAS_URL, payload, format="json")
        assert resp.status_code == 403
