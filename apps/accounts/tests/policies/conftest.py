"""
Fixtures compartilhadas para testes de ApplicationPolicy.
"""
import pytest
from model_bakery import baker


# ── Usuários ───────────────────────────────────────────────────────────────

@pytest.fixture
def portal_admin_user(db):
    """Usuário com UserRole codigoperfil='PORTAL_ADMIN'."""
    user = baker.make("accounts.User", is_superuser=False, is_active=True)
    role = baker.make("accounts.Role", codigoperfil="PORTAL_ADMIN")
    baker.make("accounts.UserRole", user=user, role=role)
    return user


@pytest.fixture
def superuser(db):
    """Usuário Django com is_superuser=True (sem UserRole explícito)."""
    return baker.make("accounts.User", is_superuser=True, is_active=True)


@pytest.fixture
def regular_user(db, app_ready):
    """Usuário comum com UserRole em app_ready."""
    user = baker.make("accounts.User", is_superuser=False, is_active=True)
    role = baker.make("accounts.Role", codigoperfil="BASIC_USER")
    baker.make("accounts.UserRole", user=user, role=role, aplicacao=app_ready)
    return user


# ── Aplicações ─────────────────────────────────────────────────────────────

@pytest.fixture
def app_ready(db):
    """App pronta para produção e não bloqueada."""
    return baker.make(
        "accounts.Aplicacao",
        isappbloqueada=False,
        isappproductionready=True,
    )


@pytest.fixture
def app_blocked(db):
    """App bloqueada mas production-ready."""
    return baker.make(
        "accounts.Aplicacao",
        isappbloqueada=True,
        isappproductionready=True,
    )


@pytest.fixture
def app_not_ready(db):
    """App não bloqueada mas ainda não production-ready (homologação)."""
    return baker.make(
        "accounts.Aplicacao",
        isappbloqueada=False,
        isappproductionready=False,
    )


@pytest.fixture
def app_portal(db):
    """App do portal (codigointerno='PORTAL'), pronta e não bloqueada."""
    return baker.make(
        "accounts.Aplicacao",
        codigointerno="PORTAL",
        isappbloqueada=False,
        isappproductionready=True,
    )
