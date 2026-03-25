# apps/carga_org_lot/tests/conftest.py
"""
Conftest local para a app carga_org_lot.

Reutiliza os helpers do conftest de accounts e os
client_* fixtures já disponíveis naquele escopo.
O conftest raiz (accounts) é auto-importado pelo pytest
por estar em apps/accounts/tests/ — aqui apenas
criamos as fixtures específicas de carga.

Fixtures exportadas:
  client_gestor_carga  — GESTOR_CARGA autenticado em CARGA_ORG_LOT
  client_sem_role_carga — usuário sem role alguma

Nota: _ensure_base_data (autouse) do conftest de accounts
popula as Roles e Aplicacoes necessárias antes de cada teste.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.conftest import (
    DEFAULT_PASSWORD,
    _assign_role,
    _make_authenticated_client,
    _make_user,
)


@pytest.fixture
def gestor_carga_lot(db):
    """Usuário com perfil GESTOR_CARGA (Role pk=6, CARGA_ORG_LOT)."""
    user = _make_user("gestor_carga_lot_test")
    _assign_role(user, role_pk=6)
    return user


@pytest.fixture
def client_gestor_carga_lot(db, gestor_carga_lot):
    """APIClient autenticado como GESTOR_CARGA via sessão Django real."""
    client, resp = _make_authenticated_client("gestor_carga_lot_test", "CARGA_ORG_LOT")
    assert resp.status_code == 200, (
        f"Falha no login do GESTOR_CARGA: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def usuario_sem_role_carga(db):
    """Usuário sem nenhuma role — acesso negado em todos os endpoints."""
    return _make_user("sem_role_carga_test")


@pytest.fixture
def client_sem_role_carga(db, usuario_sem_role_carga):
    """APIClient autenticado sem role."""
    client, resp = _make_authenticated_client("sem_role_carga_test", "CARGA_ORG_LOT")
    # O login pode retornar 200 mesmo sem role na app — o 403 vem no endpoint
    return client


@pytest.fixture
def client_anonimo_carga():
    """APIClient sem autenticação."""
    return APIClient()
