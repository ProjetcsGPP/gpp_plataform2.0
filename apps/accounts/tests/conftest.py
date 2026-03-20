# apps/accounts/tests/conftest.py
"""
Conftest central da app accounts.

ESTRATEGIA:
  - Fixtures com escopo 'function' (padrao) garantem isolamento total entre testes.
  - Login real via POST /api/accounts/login/ -- sem force_authenticate, sem mock.
  - Dados de lookup (StatusUsuario, TipoUsuario, ClassificacaoUsuario, Aplicacao,
    auth.Group, Role) carregados pelas fixtures JSON via pytest.ini:
      initial_data.json
      policy_expansion_flags.json
    Acesso a esses dados feito com get_or_create para robustez independente
    de como o banco foi populado (reuse-db, transaction, savepoint).

COMPATIBILIDADE COM --reuse-db:
  Com --reuse-db, o banco de teste e preservado entre sessoes do pytest.
  Todos os objetos User, UserProfile e UserRole sao criados com
  get_or_create para evitar UniqueViolation em rodadas repetidas.

PERFIS PNGI disponiveis via initial_data.json:
  Role pk=1  -> PORTAL_ADMIN    / Aplicacao pk=1 (PORTAL)
  Role pk=2  -> GESTOR_PNGI     / Aplicacao pk=2 (ACOES_PNGI)
  Role pk=3  -> COORDENADOR_PNGI / Aplicacao pk=2
  Role pk=4  -> OPERADOR_ACAO   / Aplicacao pk=2
  Role pk=6  -> GESTOR_CARGA    / Aplicacao pk=3 (CARGA_ORG_LOT)

URLs dos endpoints accounts:
  POST /api/accounts/login/
  POST /api/accounts/logout/
  POST /api/accounts/switch-app/
  GET  /api/accounts/me/
  GET  /api/accounts/aplicacoes/
  GET  /api/accounts/profiles/
  GET  /api/accounts/roles/
  GET  /api/accounts/user-roles/
  POST /api/accounts/users/
  POST /api/accounts/users/create-with-role/
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import (
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
)

LOGIN_URL = "/api/accounts/login/"
DEFAULT_PASSWORD = "TestPass@2026"


# --- Helpers de lookup (robustos com ou sem fixtures pre-carregadas) ----------

def _get_status_usuario():
    """
    Retorna StatusUsuario pk=1.
    Usa get_or_create para funcionar tanto com banco populado pelas fixtures
    JSON quanto com banco vazio (transaction=True).
    """
    obj, _ = StatusUsuario.objects.get_or_create(
        pk=1,
        defaults={"strdescricao": "Ativo"},
    )
    return obj


def _get_tipo_usuario():
    obj, _ = TipoUsuario.objects.get_or_create(
        pk=1,
        defaults={"strdescricao": "Interno"},
    )
    return obj


def _get_classificacao_usuario():
    """
    Retorna ClassificacaoUsuario pk=1.
    pode_criar_usuario=False e pode_editar_usuario=False sao os defaults
    corretos para usuarios comuns.
    """
    obj, _ = ClassificacaoUsuario.objects.get_or_create(
        pk=1,
        defaults={
            "strdescricao": "Usuario Padrao",
            "pode_criar_usuario": False,
            "pode_editar_usuario": False,
        },
    )
    return obj


# --- _make_user: seguro com --reuse-db ---------------------------------------

def _make_user(username, password=DEFAULT_PASSWORD, is_superuser=False):
    """
    Cria (ou recupera) auth.User + UserProfile.

    Usa get_or_create no User E no UserProfile para ser seguro com --reuse-db,
    onde o banco de teste e preservado entre sessoes do pytest e objetos criados
    em rodadas anteriores ja existem quando o proximo pytest e iniciado.

    Comportamento:
      - Primeira rodada: cria tudo do zero.
      - Rodadas seguintes com --reuse-db: recupera o User existente e
        garante que a senha esta atualizada (set_password) para que o
        login real via API continue funcionando.
      - Sempre garante que UserProfile existe (get_or_create).
    """
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "is_superuser": is_superuser,
            "is_active": True,
        },
    )
    if created:
        user.set_password(password)
        user.save()
    else:
        # Garante senha correta em rodadas com --reuse-db
        user.set_password(password)
        user.is_superuser = is_superuser
        user.is_active = True
        user.save(update_fields=["password", "is_superuser", "is_active"])

    # Garante que UserProfile existe (pode ter sido deletado ou nunca criado)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "name": username,
            "status_usuario": _get_status_usuario(),
            "tipo_usuario": _get_tipo_usuario(),
            "classificacao_usuario": _get_classificacao_usuario(),
        },
    )
    return user


def _assign_role(user, role_pk):
    """
    Atribui uma Role ao usuario via UserRole.
    Usa get_or_create para ser idempotente com --reuse-db:
    se a UserRole ja existe (rodada anterior), nao tenta criar de novo.
    Tambem sincroniza o auth.Group correspondente.
    """
    role = Role.objects.get(pk=role_pk)
    UserRole.objects.get_or_create(
        user=user,
        aplicacao=role.aplicacao,
        defaults={"role": role},
    )
    if role.group:
        user.groups.add(role.group)
    return role


def _do_login(client, username, app_context, password=DEFAULT_PASSWORD):
    """
    Executa login real via API -- percorre LoginView, middleware, auditoria.
    """
    return client.post(
        LOGIN_URL,
        {
            "username": username,
            "password": password,
            "app_context": app_context,
        },
        format="json",
    )


def _make_authenticated_client(username, app_context, password=DEFAULT_PASSWORD):
    """
    Cria APIClient e realiza login real.
    Retorna (client, response).
    """
    client = APIClient()
    resp = _do_login(client, username, app_context, password)
    return client, resp


# --- Fixtures de usuarios por perfil -----------------------------------------

@pytest.fixture
def gestor_pngi(db):
    """
    Usuario com perfil GESTOR_PNGI (Role pk=2, ACOES_PNGI).
    ClassificacaoUsuario pk=1 -> pode_criar_usuario=False (padrao).
    """
    user = _make_user("gestor_test")
    _assign_role(user, role_pk=2)
    return user


@pytest.fixture
def coordenador_pngi(db):
    """Usuario com perfil COORDENADOR_PNGI (Role pk=3, ACOES_PNGI)."""
    user = _make_user("coordenador_test")
    _assign_role(user, role_pk=3)
    return user


@pytest.fixture
def operador_acao(db):
    """Usuario com perfil OPERADOR_ACAO (Role pk=4, ACOES_PNGI)."""
    user = _make_user("operador_test")
    _assign_role(user, role_pk=4)
    return user


@pytest.fixture
def gestor_carga(db):
    """Usuario com perfil GESTOR_CARGA (Role pk=6, CARGA_ORG_LOT)."""
    user = _make_user("gestor_carga_test")
    _assign_role(user, role_pk=6)
    return user


@pytest.fixture
def portal_admin(db):
    """
    Usuario com perfil PORTAL_ADMIN (Role pk=1, PORTAL).
    Tem acesso irrestrito ao PORTAL e gerencia usuarios/roles.
    """
    user = _make_user("portal_admin_test")
    _assign_role(user, role_pk=1)
    return user


@pytest.fixture
def superuser(db):
    """SuperUser Django -- bypassa todas as restricoes de role."""
    return _make_user("superuser_test", is_superuser=True)


@pytest.fixture
def usuario_sem_role(db):
    """Usuario valido mas sem nenhuma UserRole atribuida."""
    return _make_user("sem_role_test")


@pytest.fixture
def usuario_alvo(db):
    """
    Usuario sem role -- alvo generico para operacoes de assign/revoke/create.
    """
    return _make_user("alvo_test")


# --- Fixtures de clients autenticados (sessao real) ---------------------------

@pytest.fixture
def client_gestor(db, gestor_pngi):
    """APIClient autenticado como GESTOR_PNGI via sessao Django real."""
    client, resp = _make_authenticated_client("gestor_test", "ACOES_PNGI")
    assert resp.status_code == 200, (
        f"Falha no login do GESTOR_PNGI: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_coordenador(db, coordenador_pngi):
    """APIClient autenticado como COORDENADOR_PNGI via sessao Django real."""
    client, resp = _make_authenticated_client("coordenador_test", "ACOES_PNGI")
    assert resp.status_code == 200, (
        f"Falha no login do COORDENADOR_PNGI: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_operador(db, operador_acao):
    """APIClient autenticado como OPERADOR_ACAO via sessao Django real."""
    client, resp = _make_authenticated_client("operador_test", "ACOES_PNGI")
    assert resp.status_code == 200, (
        f"Falha no login do OPERADOR_ACAO: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_gestor_carga(db, gestor_carga):
    """APIClient autenticado como GESTOR_CARGA via sessao Django real."""
    client, resp = _make_authenticated_client("gestor_carga_test", "CARGA_ORG_LOT")
    assert resp.status_code == 200, (
        f"Falha no login do GESTOR_CARGA: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_portal_admin(db, portal_admin):
    """APIClient autenticado como PORTAL_ADMIN via sessao Django real."""
    client, resp = _make_authenticated_client("portal_admin_test", "PORTAL")
    assert resp.status_code == 200, (
        f"Falha no login do PORTAL_ADMIN: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_superuser(db, superuser):
    """APIClient autenticado como SuperUser via sessao Django real."""
    client, resp = _make_authenticated_client("superuser_test", "PORTAL")
    assert resp.status_code == 200, (
        f"Falha no login do SUPERUSER: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_anonimo():
    """APIClient sem nenhuma autenticacao."""
    return APIClient()
