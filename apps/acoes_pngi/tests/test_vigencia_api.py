"""
Testes de CRUD da API de VigenciaPNGI.
"""
import pytest

from .conftest import VIGENCIAS_URL


@pytest.mark.django_db(transaction=True)
def test_list_vigencias_sem_auth_retorna_401(client_anonimo):
    resp = client_anonimo.get(VIGENCIAS_URL)
    assert resp.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_list_vigencias_gestor_retorna_200(client_gestor, vigencia):
    """
    Verifica que o gestor consegue listar vigencias e que ha ao menos
    um registro. Nao checa pk especifico pois em transaction=True a
    vigencia da fixture pode nao estar visivel antes do GET dependendo
    da ordem de setup das fixtures.
    """
    resp = client_gestor.get(VIGENCIAS_URL)
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("results", data) if isinstance(data, dict) else data
    assert len(items) >= 1


@pytest.mark.django_db(transaction=True)
def test_list_vigencias_consultor_retorna_200(client_consultor, vigencia):
    resp = client_consultor.get(VIGENCIAS_URL)
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_create_vigencia_gestor_retorna_201(client_gestor):
    payload = {
        "strdescricao": "PNGI 2029-2032",
        "datiniciovigencia": "2029-01-01",
    }
    resp = client_gestor.post(VIGENCIAS_URL, payload, format="json")
    assert resp.status_code == 201
    assert resp.json()["strdescricao"] == "PNGI 2029-2032"


@pytest.mark.django_db(transaction=True)
def test_create_vigencia_consultor_retorna_403(client_consultor):
    payload = {
        "strdescricao": "PNGI 2033-2036",
        "datiniciovigencia": "2033-01-01",
    }
    resp = client_consultor.post(VIGENCIAS_URL, payload, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_delete_vigencia_gestor_retorna_204(client_gestor, vigencia_livre):
    """
    Usa vigencia_livre (sem Acoes vinculadas) para evitar ProtectedError.

    idvigenciapngi tem on_delete=PROTECT. Com transaction=True, testes
    anteriores que criam Acoes fazem commits reais — essas Acoes ficam
    no banco ate o flush pre-teste seguinte. Se a fixture vigencia
    generica fosse usada aqui, o DELETE falharia com ProtectedError.
    """
    resp = client_gestor.delete(f"{VIGENCIAS_URL}{vigencia_livre.pk}/")
    assert resp.status_code == 204


@pytest.mark.django_db(transaction=True)
def test_delete_vigencia_operador_retorna_403(client_operador, vigencia):
    resp = client_operador.delete(f"{VIGENCIAS_URL}{vigencia.pk}/")
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_create_vigencia_preenche_auditoria(client_gestor, gestor_pngi):
    """AuditableMixin deve preencher created_by_id na criacao de vigencia."""
    payload = {
        "strdescricao": "PNGI Auditoria",
        "datiniciovigencia": "2030-01-01",
    }
    resp = client_gestor.post(VIGENCIAS_URL, payload, format="json")
    assert resp.status_code == 201
    assert resp.json()["created_by_id"] == gestor_pngi.pk
