"""
apps/acoes_pngi/tests/test_permissions.py

Testes de autorizacao das views de acoes_pngi.

A autorizacao e baseada nas permissions efetivas avaliadas por
AuthorizationService/CanPermission.

Nao existem mais testes de matriz READ/WRITE/DELETE por role.

Regras atuais:

GESTOR_PNGI
  - acesso total

COORDENADOR_PNGI
  - pode visualizar Acoes
  - pode criar Acoes
  - pode alterar Acoes
  - nao pode excluir Acoes

OPERADOR_ACAO
  - pode visualizar Acoes
  - nao pode criar Acoes
  - pode alterar Acoes somente quando o escopo ABAC permitir
  - nao pode excluir Acoes

CONSULTOR_PNGI
  - nao existe mais
"""

import pytest

from .conftest import ACOES_URL

# ---------------------------------------------------------------------------
# GESTOR_PNGI
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_gestor_pode_listar(client_gestor):
    response = client_gestor.get(ACOES_URL)

    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_gestor_pode_criar(client_gestor, payload_acao):
    response = client_gestor.post(
        ACOES_URL,
        payload_acao,
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_gestor_pode_atualizar(
    client_gestor,
    acao,
):
    response = client_gestor.patch(
        f"{ACOES_URL}{acao.pk}/",
        {
            "strdescricaoentrega": "Entrega atualizada pelo gestor",
        },
        format="json",
    )

    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_gestor_pode_deletar(
    client_gestor,
    acao,
):
    response = client_gestor.delete(
        f"{ACOES_URL}{acao.pk}/",
    )

    assert response.status_code == 204


# ---------------------------------------------------------------------------
# COORDENADOR_PNGI
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_coordenador_pode_listar(client_coordenador):
    response = client_coordenador.get(ACOES_URL)

    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_coordenador_pode_criar(
    client_coordenador,
    payload_acao,
):
    payload_acao["strapelido"] = "ACAO-COORD-PERM"

    response = client_coordenador.post(
        ACOES_URL,
        payload_acao,
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_coordenador_pode_atualizar(
    client_coordenador,
    acao,
):
    response = client_coordenador.patch(
        f"{ACOES_URL}{acao.pk}/",
        {
            "strdescricaoentrega": "Entrega atualizada pelo coordenador",
        },
        format="json",
    )

    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_coordenador_nao_pode_deletar(
    client_coordenador,
    acao,
):
    response = client_coordenador.delete(
        f"{ACOES_URL}{acao.pk}/",
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# OPERADOR_ACAO
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_operador_pode_listar(client_operador):
    response = client_operador.get(ACOES_URL)

    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_operador_nao_pode_criar(
    client_operador,
    payload_acao,
):
    payload_acao["strapelido"] = "ACAO-OPER-PERM"

    response = client_operador.post(
        ACOES_URL,
        payload_acao,
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_operador_nao_pode_deletar(
    client_operador,
    acao,
):
    response = client_operador.delete(
        f"{ACOES_URL}{acao.pk}/",
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# SEM ROLE
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sem_role_nao_pode_listar(
    db,
    usuario_sem_role,
):
    from .conftest import _login

    client, login_resp = _login(
        "sem_role_pngi_u",
    )

    assert login_resp.status_code != 200

    response = client.get(ACOES_URL)

    assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_sem_role_nao_pode_criar(
    db,
    usuario_sem_role,
    payload_acao,
):
    from .conftest import _login

    client, login_resp = _login(
        "sem_role_pngi_u",
    )

    assert login_resp.status_code != 200

    response = client.post(
        ACOES_URL,
        payload_acao,
        format="json",
    )

    assert response.status_code == 401
