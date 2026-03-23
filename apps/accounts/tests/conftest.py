# apps/accounts/tests/conftest.py
"""
Conftest central da app accounts.

ESTRATEGIA:
  - Completamente autossuficiente: nao depende de fixtures JSON no pytest.ini.
  - Cria todos os dados de lookup (StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, Aplicacao, Group, Role) via get_or_create.
  - Login real via POST /api/accounts/login/ -- sem force_authenticate, mock.
  - Seguro com --reuse-db: todos os objetos sao get_or_create, nunca create.
  - THROTTLE: override de settings desativa rate limit globalmente nos testes
    para evitar 429 em endpoints publicos (AplicacaoPublicaViewSet).
  - Para evitar problemas, após inserir os dados base, é feito o reset sequence 
    das tabelas Aplicação e Roles ao final do bootstrap:

PERFIS disponiveis:
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
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient
from django.db import connection

from apps.accounts.models import (
    Aplicacao,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
)

LOGIN_URL = "/api/accounts/login/"
DEFAULT_PASSWORD = "TestPass@2026"


# --- Override de throttle para todos os testes desta app ---------------------
#
# O DRF aplica AnonRateThrottle globalmente. Em testes que disparam multiplas
# requisicoes anonimas em rapida sucessao (ex: test_auth_aplicacoes.py), o
# contador de throttle acumula e retorna 429. Zeramos os limites aqui para que
# os testes nao dependam de timing nem de cache de throttle entre runs.

@pytest.fixture(autouse=True)
def _disable_throttling(settings):
    """
    Sobrescreve DEFAULT_THROTTLE_RATES e DEFAULT_THROTTLE_CLASSES para vazio
    durante toda a suite de testes desta app. Isso garante que nenhum endpoint
    retorne 429 por acumulacao de rate limit entre testes consecutivos.
    """
    drf = settings.REST_FRAMEWORK.copy()
    drf["DEFAULT_THROTTLE_CLASSES"] = []
    drf["DEFAULT_THROTTLE_RATES"] = {}
    settings.REST_FRAMEWORK = drf



def _reset_pk_sequence(table: str, pk_col: str):
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', '{pk_col}'),
                COALESCE((SELECT MAX({pk_col}) FROM "{table}"), 0) + 1,
                false
            )
        """)


# --- Bootstrap de dados base -------------------------------------------------
#
# Toda a hierarquia de dados necessaria para os testes e criada aqui via
# get_or_create. Os pks sao fixos para garantir compatibilidade com os
# testes que referenciam objetos por pk (ex: Role.objects.get(pk=1)).
# Isso tambem funciona quando initial_data.json JA foi carregado no banco:
# get_or_create simplesmente encontra os registros existentes.

def _bootstrap_lookup_tables():
    """Cria StatusUsuario, TipoUsuario e ClassificacaoUsuario base."""
    StatusUsuario.objects.get_or_create(
        pk=1,
        defaults={"strdescricao": "Ativo"},
    )
    TipoUsuario.objects.get_or_create(
        pk=1,
        defaults={"strdescricao": "Interno"},
    )
    ClassificacaoUsuario.objects.get_or_create(
        pk=1,
        defaults={
            "strdescricao": "Usuario Padrao",
            "pode_criar_usuario": False,
            "pode_editar_usuario": False,
        },
    )
    ClassificacaoUsuario.objects.get_or_create(
        pk=2,
        defaults={
            "strdescricao": "Gestor",
            "pode_criar_usuario": True,
            "pode_editar_usuario": True,
        },
    )
    ClassificacaoUsuario.objects.get_or_create( 
        pk=3,
        defaults={
            "strdescricao": "Coordenador",
            "pode_criar_usuario": True,
            "pode_editar_usuario": True,
        },
    )


def _bootstrap_aplicacoes():
    """
    Cria as Aplicacoes base com os pks fixos do initial_data.json.
    APP_BLOQUEADA e APP_NAO_PRONTA sao criadas apenas se ausentes
    (os testes de TestAplicacoesPortalAdmin esperam ve-las).
    """
    Aplicacao.objects.get_or_create(
        pk=1,
        defaults={
            "codigointerno": "PORTAL",
            "nomeaplicacao": "Portal GPP",
            "isappbloqueada": False,
            "isappproductionready": True,
        },
    )
    Aplicacao.objects.get_or_create(
        pk=2,
        defaults={
            "codigointerno": "ACOES_PNGI",
            "nomeaplicacao": "Acoes PNGI",
            "isappbloqueada": False,
            "isappproductionready": True,
        },
    )
    Aplicacao.objects.get_or_create(
        pk=3,
        defaults={
            "codigointerno": "CARGA_ORG_LOT",
            "nomeaplicacao": "Carga Org Lot",
            "isappbloqueada": False,
            "isappproductionready": True,
        },
    )
    
    # 2) Resetar a sequence AQUI, antes de qualquer insert sem pk
    _reset_pk_sequence('tblaplicacao', 'idaplicacao')

    # Apps extras usadas nos testes de visibilidade
    Aplicacao.objects.get_or_create(
        codigointerno="APP_BLOQUEADA",
        defaults={
            "nomeaplicacao": "App Bloqueada",
            "isappbloqueada": True,
            "isappproductionready": True,
        },
    )
    Aplicacao.objects.get_or_create(
        codigointerno="APP_NAO_PRONTA",
        defaults={
            "nomeaplicacao": "App Nao Pronta",
            "isappbloqueada": False,
            "isappproductionready": False,
        },
    )


def _bootstrap_roles():
    """
    Cria os Groups e Roles base com pks fixos.
    O Group e criado antes da Role para que role.group seja populado.
    """
    app_portal = Aplicacao.objects.get(pk=1)
    app_pngi   = Aplicacao.objects.get(pk=2)
    app_carga  = Aplicacao.objects.get(pk=3)

    _role_data = [
        # (pk, codigoperfil, nomeperfil, aplicacao, group_name)
        (1, "PORTAL_ADMIN",    "Portal Admin",      app_portal, "portal_admin_group"),
        (2, "GESTOR_PNGI",     "Gestor PNGI",       app_pngi,   "gestor_pngi_group"),
        (3, "COORDENADOR_PNGI","Coordenador PNGI",  app_pngi,   "coordenador_pngi_group"),
        (4, "OPERADOR_ACAO",   "Operador de Acao",  app_pngi,   "operador_acao_group"),
        (6, "GESTOR_CARGA",    "Gestor Carga",      app_carga,  "gestor_carga_group"),
    ]

    for pk, codigo, nome, app, group_name in _role_data:
        group, _ = Group.objects.get_or_create(name=group_name)
        Role.objects.get_or_create(
            pk=pk,
            defaults={
                "codigoperfil": codigo,
                "nomeperfil": nome,
                "aplicacao": app,
                "group": group,
            },
        )


def _bootstrap_all():
    """Ponto de entrada unico para popular todos os dados base."""
    _bootstrap_lookup_tables()
    _bootstrap_aplicacoes()
    _bootstrap_roles()
    
    # Garante que a sequence do PostgreSQL está além dos IDs inseridos com pk explícita
    _reset_pk_sequence('tblaplicacao', 'idaplicacao')
    _reset_pk_sequence('accounts_role', 'id')


# --- Fixture autouse: garante dados base antes de qualquer teste -------------

@pytest.fixture(autouse=True)
def _ensure_base_data(db):
    """
    Executada antes de cada teste que use db/django_db.
    Garante que StatusUsuario, TipoUsuario, ClassificacaoUsuario,
    Aplicacao e Role base existam, sem depender de fixtures JSON.
    """
    _bootstrap_all()


# --- Helpers internos --------------------------------------------------------

def _get_status_usuario():
    return StatusUsuario.objects.get(pk=1)


def _get_tipo_usuario():
    return TipoUsuario.objects.get(pk=1)


def _get_classificacao_usuario():
    return ClassificacaoUsuario.objects.get(pk=1)

# DEPOIS
def _make_user(username, password=DEFAULT_PASSWORD,
               is_superuser=False, classificacao_pk=1):
    """
    Cria (ou recupera) auth.User + UserProfile.
    Seguro com --reuse-db: usa get_or_create e atualiza senha sempre.
    classificacao_pk permite sobrescrever a ClassificacaoUsuario por fixture.
    """
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"is_superuser": is_superuser, "is_active": True},
    )
    user.set_password(password)
    user.is_superuser = is_superuser
    user.is_active = True
    user.save(update_fields=["password", "is_superuser", "is_active"])

    classificacao = ClassificacaoUsuario.objects.get(pk=classificacao_pk)
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "name": username,
            "status_usuario": _get_status_usuario(),
            "tipo_usuario": _get_tipo_usuario(),
            "classificacao_usuario": classificacao,
        },
    )
    if profile.classificacao_usuario_id != classificacao_pk:
        profile.classificacao_usuario = classificacao
        profile.save(update_fields=["classificacao_usuario"])
    return user

# DEPOIS
def _assign_role(user, role_pk):
    """
    Atribui uma Role ao usuario via UserRole (idempotente).
    O lookup e por (user, aplicacao) que e a constraint de unicidade.
    Seguro com --reuse-db: atualiza a role se o registro ja existia com outra.
    """
    role = Role.objects.get(pk=role_pk)
    user_role, created = UserRole.objects.get_or_create(
        user=user,
        aplicacao=role.aplicacao,
        defaults={"role": role},
    )
    if not created and user_role.role_id != role.pk:
        user_role.role = role
        user_role.save(update_fields=["role"])
    if role.group:
        user.groups.add(role.group)
    return role



def _do_login(client, username, app_context, password=DEFAULT_PASSWORD):
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
    client = APIClient()
    resp = _do_login(client, username, app_context, password)
    return client, resp


# --- Fixtures de usuarios por perfil -----------------------------------------
# DEPOIS
@pytest.fixture
def gestor_pngi(db):
    """
    Usuario com perfil GESTOR_PNGI (Role pk=2, ACOES_PNGI).
    ClassificacaoUsuario pk=2 -> pode_criar_usuario=True, pode_editar_usuario=True.
    """
    user = _make_user("gestor_test", classificacao_pk=2)
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
    """Usuario sem role -- alvo generico para operacoes de assign/revoke/create."""
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
