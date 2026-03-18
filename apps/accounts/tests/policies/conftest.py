"""
Helpers e fixtures reutilizáveis para testes de policies.

Estratégia:
  - Zero banco de dados
  - MagicMock para user, aplicacao, role e user_role
  - patch via parâmetro nos próprios testes quando necessário
"""
from unittest.mock import MagicMock
import pytest


# ── Factories de objetos mock ─────────────────────────────────────────────────

def make_user(user_id=1, is_superuser=False):
    """Retorna um user MagicMock com id e is_superuser configurados."""
    user = MagicMock()
    user.id = user_id
    user.is_superuser = is_superuser
    return user


def make_aplicacao(
    codigointerno="APP_TEST",
    isappbloqueada=False,
    isappproductionready=True,
):
    """Retorna uma aplicacao MagicMock com os campos de flag configurados."""
    app = MagicMock()
    app.codigointerno = codigointerno
    app.isappbloqueada = isappbloqueada
    app.isappproductionready = isappproductionready
    return app


def make_user_role():
    """Retorna um UserRole MagicMock simples."""
    return MagicMock()


def make_role(codigoperfil="VIEWER", aplicacao=None):
    """Retorna uma Role MagicMock com codigoperfil e aplicacao configurados."""
    role = MagicMock()
    role.pk = 1
    role.codigoperfil = codigoperfil
    role.aplicacao = aplicacao if aplicacao is not None else make_aplicacao()
    return role


# ── Fixtures pytest ───────────────────────────────────────────────────────────

@pytest.fixture
def app_ready():
    """Aplicação desbloqueada e em produção."""
    return make_aplicacao(codigointerno="APP_READY", isappbloqueada=False, isappproductionready=True)


@pytest.fixture
def app_blocked():
    """Aplicação bloqueada."""
    return make_aplicacao(codigointerno="APP_BLOCKED", isappbloqueada=True, isappproductionready=True)


@pytest.fixture
def app_not_ready():
    """Aplicação desbloqueada mas não em produção."""
    return make_aplicacao(codigointerno="APP_NOT_READY", isappbloqueada=False, isappproductionready=False)


@pytest.fixture
def regular_role(app_ready):
    """Role comum (VIEWER) vinculada a app_ready."""
    return make_role(codigoperfil="VIEWER", aplicacao=app_ready)


@pytest.fixture
def admin_role(app_ready):
    """Role raiz PORTAL_ADMIN vinculada a app_ready."""
    return make_role(codigoperfil="PORTAL_ADMIN", aplicacao=app_ready)


@pytest.fixture
def superuser():
    """Usuário superuser."""
    return make_user(user_id=10, is_superuser=True)


@pytest.fixture
def regular_user():
    """Usuário sem privilégios."""
    return make_user(user_id=20, is_superuser=False)


@pytest.fixture
def other_user():
    """Usuário alvo (distinto do ator) para testes de assign/revoke."""
    return make_user(user_id=30, is_superuser=False)
