# apps/carga_org_lot/tests/conftest.py
"""
Conftest local para a app carga_org_lot.

Reutiliza os helpers do conftest de accounts e os
client_* fixtures já disponíveis naquele escopo.

IMPORTANTE: O fixture autouse _ensure_base_data do conftest de accounts
NÃO se propaga automaticamente para apps irmãs — o pytest só carrega
conftest.py dos diretórios pai do arquivo de teste, nunca de apps irmãs.
Por isso declaramos _ensure_base_data_carga (autouse) aqui, que chama
_bootstrap_all() explicitamente antes de cada teste desta app.

Fixtures exportadas:
  gestor_carga_lot       — User com Role pk=6 (GESTOR_CARGA)
  client_gestor_carga_lot — APIClient autenticado como GESTOR_CARGA
  usuario_sem_role_carga  — User sem nenhuma role
  client_sem_role_carga   — APIClient autenticado sem role
  client_anonimo_carga    — APIClient sem autenticação
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.conftest import (
    _assign_role,
    _bootstrap_all,
    _make_authenticated_client,
    _make_user,
)


@pytest.fixture(autouse=True)
def _ensure_base_data_carga(db):
    """
    Garante que ClassificacaoUsuario, Aplicacao, Role e demais dados base
    existam no banco de teste antes de cada teste desta app.

    Necessário porque o _ensure_base_data (autouse) definido em
    apps/accounts/tests/conftest.py só é ativado automaticamente
    para testes dentro de apps/accounts/tests/ — não para apps irmãs.
    """
    _bootstrap_all()


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
    """APIClient autenticado sem role.

    O login retorna 200 mesmo sem role na app (autenticação passou),
    o 403 será retornado nos endpoints que exigem a role.
    """
    client, resp = _make_authenticated_client("sem_role_carga_test", "CARGA_ORG_LOT")
    return client


@pytest.fixture
def client_anonimo_carga():
    """APIClient sem autenticação."""
    return APIClient()
