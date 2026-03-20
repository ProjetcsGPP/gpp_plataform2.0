# apps/accounts/tests/conftest.py
"""
Conftest central da app accounts.

ESTRATÉGIA:
  - Fixtures com escopo 'function' (padrão) garantem isolamento total entre testes.
  - Login real via POST /api/accounts/login/ — sem force_authenticate, sem mock.
  - Dados de lookup (StatusUsuario, TipoUsuario, ClassificacaoUsuario, Aplicacao,
    auth.Group, Role) carregados pelas fixtures JSON:
      initial_data.json          → dados base de toda a plataforma
      policy_expansion_flags.json → apps/roles extras para testes de flags
    NÃO usa fase6_initial_data.json.

FIXTURES JSON carregadas via pytest-django (django_db_setup / fixtures=[...]).
Cada teste ou fixture que precisar dos dados de lookup deve declarar:
    @pytest.fixture
    def minha_fixture(db):   # db já inclui as fixtures do conftest

PERFIS PNGI disponíveis via initial_data.json:
  Role pk=1  → PORTAL_ADMIN   / Aplicacao pk=1 (PORTAL)
  Role pk=2  → GESTOR_PNGI    / Aplicacao pk=2 (ACOES_PNGI)
  Role pk=3  → COORDENADOR_PNGI / Aplicacao pk=2
  Role pk=4  → OPERADOR_ACAO  / Aplicacao pk=2
  Role pk=6  → GESTOR_CARGA   / Aplicacao pk=3 (CARGA_ORG_LOT)

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

# ─── Fixtures JSON carregadas automaticamente ─────────────────────────────────
# Declaradas aqui para que todos os testes deste pacote as recebam via autouse.
# O pytest-django injeta os dados ANTES do primeiro teste de cada função.

@pytest.fixture(autouse=True)
def _load_fixtures(db, django_db_setup):
    """
    Garante que as fixtures JSON sejam carregadas no banco de cada teste.
    O django_db_setup com fixtures=['...'] já trata disso quando configurado
    no pytest.ini / conftest raiz. Esta fixture é um guard explícito.
    """
    pass


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _make_user(username, password=DEFAULT_PASSWORD, is_superuser=False):
    """
    Cria auth.User + UserProfile usando dados das fixtures carregadas.
    StatusUsuario pk=1 = Ativo
    TipoUsuario   pk=1 = Interno
    ClassificacaoUsuario pk=1 = Usuário (pode_criar_usuario=False)
    """
    user = User.objects.create_user(
        username=username,
        password=password,
        is_superuser=is_superuser,
    )
    UserProfile.objects.create(
        user=user,
        name=username,
        status_usuario=StatusUsuario.objects.get(pk=1),
        tipo_usuario=TipoUsuario.objects.get(pk=1),
        classificacao_usuario=ClassificacaoUsuario.objects.get(pk=1),
    )
    return user


def _assign_role(user, role_pk):
    """
    Atribui uma Role ao usuário via UserRole.
    Também adiciona o auth.Group correspondente ao usuário,
    replicando exatamente o que o UserRoleViewSet.create() faz.
    """
    role = Role.objects.get(pk=role_pk)
    UserRole.objects.create(
        user=user,
        role=role,
        aplicacao=role.aplicacao,
    )
    if role.group:
        user.groups.add(role.group)
    return role


def _do_login(client, username, app_context, password=DEFAULT_PASSWORD):
    """
    Executa login real via API — percorre LoginView, middleware, auditoria.
    Retorna o objeto Response para inspeção de status/dados.
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
    Cria um APIClient e realiza login real.
    Retorna (client, response) para que o chamador possa validar o login.
    """
    client = APIClient()
    resp = _do_login(client, username, app_context, password)
    return client, resp


# ─── Fixtures de usuários por perfil ──────────────────────────────────────────

@pytest.fixture
def gestor_pngi(db):
    """
    Usuário com perfil GESTOR_PNGI (Role pk=2, ACOES_PNGI).
    ClassificacaoUsuario pk=1 → pode_criar_usuario=False (padrão).
    """
    user = _make_user("gestor_test")
    _assign_role(user, role_pk=2)
    return user


@pytest.fixture
def coordenador_pngi(db):
    """Usuário com perfil COORDENADOR_PNGI (Role pk=3, ACOES_PNGI)."""
    user = _make_user("coordenador_test")
    _assign_role(user, role_pk=3)
    return user


@pytest.fixture
def operador_acao(db):
    """Usuário com perfil OPERADOR_ACAO (Role pk=4, ACOES_PNGI)."""
    user = _make_user("operador_test")
    _assign_role(user, role_pk=4)
    return user


@pytest.fixture
def gestor_carga(db):
    """Usuário com perfil GESTOR_CARGA (Role pk=6, CARGA_ORG_LOT)."""
    user = _make_user("gestor_carga_test")
    _assign_role(user, role_pk=6)
    return user


@pytest.fixture
def portal_admin(db):
    """
    Usuário com perfil PORTAL_ADMIN (Role pk=1, PORTAL).
    Tem acesso irrestrito ao PORTAL e gerencia usuários/roles.
    """
    user = _make_user("portal_admin_test")
    _assign_role(user, role_pk=1)
    return user


@pytest.fixture
def superuser(db):
    """SuperUser Django — bypassa todas as restrições de role."""
    return _make_user("superuser_test", is_superuser=True)


@pytest.fixture
def usuario_sem_role(db):
    """Usuário válido mas sem nenhuma UserRole atribuída."""
    return _make_user("sem_role_test")


@pytest.fixture
def usuario_alvo(db):
    """
    Usuário sem role — alvo genérico para operações de assign/revoke/create.
    """
    return _make_user("alvo_test")


# ─── Fixtures de clients autenticados (sessão real) ───────────────────────────

@pytest.fixture
def client_gestor(db, gestor_pngi):
    """APIClient autenticado como GESTOR_PNGI via sessão Django real."""
    client, resp = _make_authenticated_client("gestor_test", "ACOES_PNGI")
    assert resp.status_code == 200, (
        f"Falha no login do GESTOR_PNGI: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_coordenador(db, coordenador_pngi):
    """APIClient autenticado como COORDENADOR_PNGI via sessão Django real."""
    client, resp = _make_authenticated_client("coordenador_test", "ACOES_PNGI")
    assert resp.status_code == 200, (
        f"Falha no login do COORDENADOR_PNGI: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_operador(db, operador_acao):
    """APIClient autenticado como OPERADOR_ACAO via sessão Django real."""
    client, resp = _make_authenticated_client("operador_test", "ACOES_PNGI")
    assert resp.status_code == 200, (
        f"Falha no login do OPERADOR_ACAO: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_gestor_carga(db, gestor_carga):
    """APIClient autenticado como GESTOR_CARGA via sessão Django real."""
    client, resp = _make_authenticated_client("gestor_carga_test", "CARGA_ORG_LOT")
    assert resp.status_code == 200, (
        f"Falha no login do GESTOR_CARGA: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_portal_admin(db, portal_admin):
    """APIClient autenticado como PORTAL_ADMIN via sessão Django real."""
    client, resp = _make_authenticated_client("portal_admin_test", "PORTAL")
    assert resp.status_code == 200, (
        f"Falha no login do PORTAL_ADMIN: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_superuser(db, superuser):
    """APIClient autenticado como SuperUser via sessão Django real."""
    client, resp = _make_authenticated_client("superuser_test", "PORTAL")
    assert resp.status_code == 200, (
        f"Falha no login do SUPERUSER: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_anonimo():
    """APIClient sem nenhuma autenticação."""
    return APIClient()
