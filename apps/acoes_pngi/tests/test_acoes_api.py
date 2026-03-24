"""
Testes de CRUD completo da API de Acoes PNGI.
Cobre: list, retrieve, create, update, partial_update, destroy.
"""
import pytest

from .conftest import ACOES_URL


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_list_acoes_sem_autenticacao(client_anonimo):
    """Requisicao sem sessao deve retornar 401."""
    resp = client_anonimo.get(ACOES_URL)
    assert resp.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_list_acoes_sem_role_retorna_403(db, usuario_sem_role):
    """Usuario autenticado mas sem role em ACOES_PNGI deve receber 403."""
    from rest_framework.test import APIClient
    from .conftest import _login
    client, resp = _login("sem_role_pngi_u")
    assert resp.status_code == 200  # login ok
    resp = client.get(ACOES_URL)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_list_acoes_gestor_retorna_200(client_gestor):
    """GESTOR_PNGI pode listar acoes."""
    resp = client_gestor.get(ACOES_URL)
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_list_acoes_consultor_retorna_200(client_consultor):
    """CONSULTOR_PNGI pode listar acoes."""
    resp = client_consultor.get(ACOES_URL)
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_list_acoes_retorna_lista(client_gestor, acao):
    """List deve retornar lista com a acao criada."""
    resp = client_gestor.get(ACOES_URL)
    assert resp.status_code == 200
    data = resp.json()
    # Suporte a paginacao ou lista direta
    items = data.get("results", data) if isinstance(data, dict) else data
    assert any(a["idacao"] == acao.pk for a in items)


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_retrieve_acao_gestor(client_gestor, acao):
    """GESTOR_PNGI pode recuperar acao por pk."""
    resp = client_gestor.get(f"{ACOES_URL}{acao.pk}/")
    assert resp.status_code == 200
    assert resp.json()["idacao"] == acao.pk


@pytest.mark.django_db(transaction=True)
def test_retrieve_acao_consultor(client_consultor, acao):
    """CONSULTOR_PNGI pode recuperar acao (read-only)."""
    resp = client_consultor.get(f"{ACOES_URL}{acao.pk}/")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_create_acao_gestor_retorna_201(client_gestor, payload_acao):
    """GESTOR_PNGI pode criar Acao — resposta 201."""
    resp = client_gestor.post(ACOES_URL, payload_acao, format="json")
    assert resp.status_code == 201
    assert resp.json()["strapelido"] == payload_acao["strapelido"]


@pytest.mark.django_db(transaction=True)
def test_create_acao_coordenador_retorna_201(client_coordenador, payload_acao):
    """COORDENADOR_PNGI pode criar Acao."""
    payload_acao["strapelido"] = "ACAO-COORD-001"
    resp = client_coordenador.post(ACOES_URL, payload_acao, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_create_acao_operador_retorna_201(client_operador, payload_acao):
    """OPERADOR_ACAO pode criar Acao."""
    payload_acao["strapelido"] = "ACAO-OPER-001"
    resp = client_operador.post(ACOES_URL, payload_acao, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_create_acao_consultor_retorna_403(client_consultor, payload_acao):
    """CONSULTOR_PNGI NAO pode criar Acao — 403."""
    resp = client_consultor.post(ACOES_URL, payload_acao, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_create_acao_sem_auth_retorna_401(client_anonimo, payload_acao):
    """Anonimo NAO pode criar Acao — 401."""
    resp = client_anonimo.post(ACOES_URL, payload_acao, format="json")
    assert resp.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_create_acao_preenche_created_by(client_gestor, payload_acao, gestor_pngi):
    """created_by_id deve ser preenchido automaticamente pelo AuditableMixin."""
    resp = client_gestor.post(ACOES_URL, payload_acao, format="json")
    assert resp.status_code == 201
    data = resp.json()
    assert data["created_by_id"] == gestor_pngi.pk
    assert data["created_by_name"] != ""


@pytest.mark.django_db(transaction=True)
def test_create_acao_nao_aceita_campo_orgao(client_gestor, payload_acao):
    """Payload com orgao deve ser ignorado (campo nao existe no model)."""
    payload_acao["orgao"] = "ES"
    resp = client_gestor.post(ACOES_URL, payload_acao, format="json")
    # 201 ou 400, mas nunca orgao no response
    if resp.status_code == 201:
        assert "orgao" not in resp.json()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_update_acao_gestor_retorna_200(client_gestor, acao):
    """GESTOR_PNGI pode atualizar Acao via PUT."""
    payload = {
        "strapelido": "ACAO-UPDATED",
        "strdescricaoacao": "Atualizada",
        "strdescricaoentrega": "Entrega atualizada",
        "idvigenciapngi_id": acao.idvigenciapngi_id,
    }
    resp = client_gestor.put(f"{ACOES_URL}{acao.pk}/", payload, format="json")
    assert resp.status_code == 200
    assert resp.json()["strapelido"] == "ACAO-UPDATED"


@pytest.mark.django_db(transaction=True)
def test_partial_update_acao_operador_retorna_200(client_operador, acao):
    """OPERADOR_ACAO pode usar PATCH."""
    resp = client_operador.patch(
        f"{ACOES_URL}{acao.pk}/",
        {"strdescricaoentrega": "Entrega patch"},
        format="json",
    )
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_update_acao_consultor_retorna_403(client_consultor, acao):
    """CONSULTOR_PNGI NAO pode atualizar Acao — 403."""
    resp = client_consultor.patch(
        f"{ACOES_URL}{acao.pk}/",
        {"strdescricaoentrega": "tentativa"},
        format="json",
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_delete_acao_gestor_retorna_204(client_gestor, acao):
    """GESTOR_PNGI pode deletar Acao — 204."""
    resp = client_gestor.delete(f"{ACOES_URL}{acao.pk}/")
    assert resp.status_code == 204


@pytest.mark.django_db(transaction=True)
def test_delete_acao_operador_retorna_403(client_operador, acao):
    """OPERADOR_ACAO NAO pode deletar Acao — 403."""
    resp = client_operador.delete(f"{ACOES_URL}{acao.pk}/")
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_delete_acao_coordenador_retorna_403(client_coordenador, acao):
    """COORDENADOR_PNGI NAO pode deletar Acao — 403."""
    resp = client_coordenador.delete(f"{ACOES_URL}{acao.pk}/")
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_delete_acao_consultor_retorna_403(client_consultor, acao):
    """CONSULTOR_PNGI NAO pode deletar Acao — 403."""
    resp = client_consultor.delete(f"{ACOES_URL}{acao.pk}/")
    assert resp.status_code == 403
