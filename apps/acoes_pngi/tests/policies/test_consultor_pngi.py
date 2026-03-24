"""
Policy tests: CONSULTOR_PNGI tem apenas READ.
"""
import pytest

from apps.acoes_pngi.tests.conftest import ACOES_URL, VIGENCIAS_URL, EIXOS_URL, SITUACOES_URL


class TestConsultorPNGI:
    """CONSULTOR_PNGI: pode apenas listar e recuperar. Nenhuma escrita/delecao."""

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_acoes(self, client_consultor):
        assert client_consultor.get(ACOES_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_eixos(self, client_consultor):
        assert client_consultor.get(EIXOS_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_situacoes(self, client_consultor):
        assert client_consultor.get(SITUACOES_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar_vigencias(self, client_consultor):
        assert client_consultor.get(VIGENCIAS_URL).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_pode_recuperar_acao(self, client_consultor, acao):
        assert client_consultor.get(f"{ACOES_URL}{acao.pk}/").status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_criar_acao(self, client_consultor, payload_acao):
        assert client_consultor.post(ACOES_URL, payload_acao, format="json").status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_atualizar_acao(self, client_consultor, acao):
        assert client_consultor.patch(
            f"{ACOES_URL}{acao.pk}/", {"strapelido": "x"}, format="json"
        ).status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_deletar_acao(self, client_consultor, acao):
        assert client_consultor.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_nao_pode_criar_vigencia(self, client_consultor):
        payload = {"strdescricao": "PNGI Consultor", "datiniciovigencia": "2035-01-01"}
        assert client_consultor.post(VIGENCIAS_URL, payload, format="json").status_code == 403
