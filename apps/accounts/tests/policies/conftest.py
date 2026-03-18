"""
Helpers e fixtures reutilizáveis para testes de policies.

ESTRATÉGIA POR CAMADA:
  Testes unitários de policy isolada → MagicMock (sem DB)
  Testes cross-policy (integração de domínio) → fixtures com DB real

As factories mock originais são mantidas para compatibilidade com os
testes unitários existentes (Prompts 1-6).
As fixtures com DB são prefixadas com nomes do cenário cross-policy
definido no Prompt 7.
"""
from unittest.mock import MagicMock
import pytest

from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import (
    Aplicacao,
    AccountsSession,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
)


# ── Factories de objetos mock (mantidos para testes unitários) ────────────────

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


# ── Fixtures pytest unitárias (sem DB) ───────────────────────────────────────

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


# ── Helpers para fixtures com DB real ─────────────────────────────────────────

def _ensure_lookup_tables(db):
    """
    Garante que as tabelas de lookup obrigatórias (StatusUsuario, TipoUsuario,
    ClassificacaoUsuario) existam com pk=1 para satisfazer os defaults do model.
    ClassificacaoUsuario pk=1 → pode_editar_usuario=False  (padrão)
    ClassificacaoUsuario pk=2 → pode_editar_usuario=True   (gestor)
    """
    StatusUsuario.objects.get_or_create(
        idstatususuario=1,
        defaults={"strdescricao": "Ativo"},
    )
    TipoUsuario.objects.get_or_create(
        idtipousuario=1,
        defaults={"strdescricao": "Padrão"},
    )
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1,
        defaults={
            "strdescricao": "Padrão",
            "pode_criar_usuario": False,
            "pode_editar_usuario": False,
        },
    )
    ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=2,
        defaults={
            "strdescricao": "Gestor",
            "pode_criar_usuario": False,
            "pode_editar_usuario": True,
        },
    )


def _make_db_user(username, is_superuser=False):
    """Cria um User + UserProfile no banco. Retorna o User."""
    user = User.objects.create_user(
        username=username,
        password="TestPass123!",
        is_superuser=is_superuser,
    )
    classificacao = ClassificacaoUsuario.objects.get(pk=1)
    UserProfile.objects.create(
        user=user,
        name=username,
        status_usuario=StatusUsuario.objects.get(pk=1),
        tipo_usuario=TipoUsuario.objects.get(pk=1),
        classificacao_usuario=classificacao,
    )
    return user


# ── Fixtures cross-policy (com DB) ────────────────────────────────────────────
# Todas marcadas com @pytest.mark.django_db no nível do fixture via
# scope="function" padrão; os testes que as usam devem declarar
# @pytest.mark.django_db explicitamente.

@pytest.fixture
def db_app_ready(db):
    """Aplicacao real: desbloqueada + pronta para produção."""
    return Aplicacao.objects.create(
        codigointerno="CROSS_READY",
        nomeaplicacao="App Ready",
        isappbloqueada=False,
        isappproductionready=True,
    )


@pytest.fixture
def db_app_blocked(db):
    """Aplicacao real: bloqueada."""
    return Aplicacao.objects.create(
        codigointerno="CROSS_BLOCKED",
        nomeaplicacao="App Blocked",
        isappbloqueada=True,
        isappproductionready=True,
    )


@pytest.fixture
def db_app_staging(db):
    """Aplicacao real: não pronta para produção (staging)."""
    return Aplicacao.objects.create(
        codigointerno="CROSS_STAGING",
        nomeaplicacao="App Staging",
        isappbloqueada=False,
        isappproductionready=False,
    )


@pytest.fixture
def db_app_other(db):
    """Aplicacao real: totalmente independente, sem interseção com cenário principal."""
    return Aplicacao.objects.create(
        codigointerno="CROSS_OTHER",
        nomeaplicacao="App Other",
        isappbloqueada=False,
        isappproductionready=True,
    )


@pytest.fixture
def db_role_viewer(db, db_app_ready):
    """Role VIEWER vinculada a db_app_ready."""
    return Role.objects.create(
        codigoperfil="VIEWER",
        nomeperfil="Viewer",
        aplicacao=db_app_ready,
    )


@pytest.fixture
def db_role_admin(db):
    """Role PORTAL_ADMIN sem aplicação (role global raiz)."""
    return Role.objects.create(
        codigoperfil="PORTAL_ADMIN",
        nomeperfil="Portal Admin",
        aplicacao=None,
    )


@pytest.fixture
def db_role_other(db, db_app_other):
    """Role VIEWER vinculada a db_app_other."""
    return Role.objects.create(
        codigoperfil="VIEWER",
        nomeperfil="Viewer Other",
        aplicacao=db_app_other,
    )


@pytest.fixture
def db_superuser(db):
    """SuperUser com UserProfile no banco."""
    _ensure_lookup_tables(db)
    return _make_db_user("cross_superuser", is_superuser=True)


@pytest.fixture
def db_portal_admin(db, db_role_admin):
    """Usuário com UserRole PORTAL_ADMIN."""
    _ensure_lookup_tables(db)
    user = _make_db_user("cross_portal_admin")
    UserRole.objects.create(user=user, role=db_role_admin, aplicacao=None)
    return user


@pytest.fixture
def db_gestor(db, db_app_ready, db_role_viewer):
    """
    Usuário gestor:
      - ClassificacaoUsuario.pode_editar_usuario=True
      - UserRole(role=VIEWER, aplicacao=db_app_ready)
    """
    _ensure_lookup_tables(db)
    user = _make_db_user("cross_gestor")
    classificacao_gestor = ClassificacaoUsuario.objects.get(pk=2)
    profile = user.profile
    profile.classificacao_usuario = classificacao_gestor
    profile.save()
    UserRole.objects.create(user=user, role=db_role_viewer, aplicacao=db_app_ready)
    return user


@pytest.fixture
def db_regular_user(db, db_app_ready, db_role_viewer):
    """Usuário comum com UserRole(VIEWER, db_app_ready)."""
    _ensure_lookup_tables(db)
    user = _make_db_user("cross_regular")
    UserRole.objects.create(user=user, role=db_role_viewer, aplicacao=db_app_ready)
    return user


@pytest.fixture
def db_isolated_user(db, db_app_other, db_role_other):
    """Usuário isolado com UserRole em db_app_other (sem interseção com cenário principal)."""
    _ensure_lookup_tables(db)
    user = _make_db_user("cross_isolated")
    UserRole.objects.create(user=user, role=db_role_other, aplicacao=db_app_other)
    return user
