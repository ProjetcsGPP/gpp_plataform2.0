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
  gestor_carga_lot        — User com Role pk=6 (GESTOR_CARGA)
  client_gestor_carga_lot — APIClient autenticado como GESTOR_CARGA
  usuario_sem_role_carga  — User sem nenhuma role
  client_sem_role_carga   — APIClient SEM autenticação (sem token/sessão),
                            pois o login é bloqueado (reason=no_role) →
                            a API retorna 401 em vez de 403.
  client_anonimo_carga    — APIClient sem autenticação (anônimo puro)
  client_portal_admin     — APIClient autenticado como PORTAL_ADMIN
                            (bypass completo de roles — is_portal_admin=True)
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
    """
    APIClient sem autenticação válida.

    O login de um usuário sem role em CARGA_ORG_LOT é bloqueado pelo
    middleware (reason=no_role), portanto a sessão nunca é criada e a
    API retorna 401 (não autenticado) — não 403 (autenticado, sem permissão).

    Os testes de TestSemRole devem verificar 401 | 403 para cobrir ambos
    os cenários (usuário sem role vs. usuário sem autenticação).
    """
    return APIClient()  # sem credenciais — garante 401 nos endpoints


@pytest.fixture
def client_anonimo_carga():
    """APIClient sem autenticação."""
    return APIClient()


@pytest.fixture
def client_portal_admin(db):
    """
    APIClient autenticado como PORTAL_ADMIN.

    PORTAL_ADMIN tem is_portal_admin=True no middleware, o que faz
    _check_carga_role() retornar imediatamente sem verificar roles.
    Usado em TestPortalAdminBypass para garantir que o bypass funciona.
    """
    user = _make_user("portal_admin_carga_test")
    # Role pk=1 é PORTAL_ADMIN conforme _bootstrap_all()
    _assign_role(user, role_pk=1)
    client, resp = _make_authenticated_client("portal_admin_carga_test", "PORTAL")
    assert resp.status_code == 200, (
        f"Falha no login do PORTAL_ADMIN: status={resp.status_code} data={resp.data}"
    )
    return client
