"""
Testes da matriz de permissoes por role x operacao.

Matriz esperada:
  GESTOR_PNGI      → READ ✅  WRITE ✅  DELETE ✅
  COORDENADOR_PNGI → READ ✅  WRITE ✅  DELETE ❌
  OPERADOR_ACAO    → READ ✅  WRITE ✅  DELETE ❌
  CONSULTOR_PNGI   → READ ✅  WRITE ❌  DELETE ❌
  SEM_ROLE         → todas ❌ (login negado → 401 na API)
"""
import pytest

from apps.acoes_pngi.views import _load_role_matrix
from .conftest import ACOES_URL


# ---------------------------------------------------------------------------
# Testes de _load_role_matrix
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_role_matrix_carrega_gestor_pngi(db):
    """GESTOR_PNGI deve estar em READ, WRITE e DELETE."""
    _load_role_matrix.cache_clear()
    matrix = _load_role_matrix()
    assert "GESTOR_PNGI" in matrix["READ"]
    assert "GESTOR_PNGI" in matrix["WRITE"]
    assert "GESTOR_PNGI" in matrix["DELETE"]


@pytest.mark.django_db(transaction=True)
def test_role_matrix_coordenador_sem_delete(db):
    """COORDENADOR_PNGI deve ter READ e WRITE mas nao DELETE."""
    _load_role_matrix.cache_clear()
    matrix = _load_role_matrix()
    assert "COORDENADOR_PNGI" in matrix["READ"]
    assert "COORDENADOR_PNGI" in matrix["WRITE"]
    assert "COORDENADOR_PNGI" not in matrix["DELETE"]


@pytest.mark.django_db(transaction=True)
def test_role_matrix_operador_sem_delete(db):
    """OPERADOR_ACAO deve ter READ e WRITE mas nao DELETE."""
    _load_role_matrix.cache_clear()
    matrix = _load_role_matrix()
    assert "OPERADOR_ACAO" in matrix["READ"]
    assert "OPERADOR_ACAO" in matrix["WRITE"]
    assert "OPERADOR_ACAO" not in matrix["DELETE"]


@pytest.mark.django_db(transaction=True)
def test_role_matrix_consultor_so_read(db):
    """CONSULTOR_PNGI deve ter apenas READ."""
    _load_role_matrix.cache_clear()
    matrix = _load_role_matrix()
    assert "CONSULTOR_PNGI" in matrix["READ"]
    assert "CONSULTOR_PNGI" not in matrix["WRITE"]
    assert "CONSULTOR_PNGI" not in matrix["DELETE"]


# ---------------------------------------------------------------------------
# GESTOR_PNGI — acesso total
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_gestor_pode_listar(client_gestor):
    assert client_gestor.get(ACOES_URL).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_gestor_pode_criar(client_gestor, payload_acao):
    assert client_gestor.post(ACOES_URL, payload_acao, format="json").status_code == 201


@pytest.mark.django_db(transaction=True)
def test_gestor_pode_deletar(client_gestor, acao):
    assert client_gestor.delete(f"{ACOES_URL}{acao.pk}/").status_code == 204


# ---------------------------------------------------------------------------
# COORDENADOR_PNGI — sem delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_coordenador_pode_listar(client_coordenador):
    assert client_coordenador.get(ACOES_URL).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_coordenador_pode_criar(client_coordenador, payload_acao):
    payload_acao["strapelido"] = "ACAO-COORD-PERM"
    assert client_coordenador.post(ACOES_URL, payload_acao, format="json").status_code == 201


@pytest.mark.django_db(transaction=True)
def test_coordenador_nao_pode_deletar(client_coordenador, acao):
    assert client_coordenador.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403


# ---------------------------------------------------------------------------
# OPERADOR_ACAO — sem delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_operador_pode_listar(client_operador):
    assert client_operador.get(ACOES_URL).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_operador_pode_criar(client_operador, payload_acao):
    payload_acao["strapelido"] = "ACAO-OPER-PERM"
    assert client_operador.post(ACOES_URL, payload_acao, format="json").status_code == 201


@pytest.mark.django_db(transaction=True)
def test_operador_nao_pode_deletar(client_operador, acao):
    assert client_operador.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403


# ---------------------------------------------------------------------------
# CONSULTOR_PNGI — somente read
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_consultor_pode_listar(client_consultor):
    assert client_consultor.get(ACOES_URL).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_consultor_nao_pode_criar(client_consultor, payload_acao):
    assert client_consultor.post(ACOES_URL, payload_acao, format="json").status_code == 403


@pytest.mark.django_db(transaction=True)
def test_consultor_nao_pode_atualizar(client_consultor, acao):
    assert client_consultor.patch(
        f"{ACOES_URL}{acao.pk}/", {"strdescricaoentrega": "x"}, format="json"
    ).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_consultor_nao_pode_deletar(client_consultor, acao):
    assert client_consultor.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403


# ---------------------------------------------------------------------------
# SEM ROLE — login negado pelo LoginView (sem role na aplicacao)
# Usuario sem sessao valida → API retorna 401, nao 403
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_sem_role_nao_pode_listar(db, usuario_sem_role):
    from .conftest import _login
    client, login_resp = _login("sem_role_pngi_u")
    assert login_resp.status_code != 200  # login negado
    assert client.get(ACOES_URL).status_code == 401


@pytest.mark.django_db(transaction=True)
def test_sem_role_nao_pode_criar(db, usuario_sem_role, payload_acao):
    from .conftest import _login
    client, login_resp = _login("sem_role_pngi_u")
    assert login_resp.status_code != 200  # login negado
    assert client.post(ACOES_URL, payload_acao, format="json").status_code == 401
