# apps/acoes_pngi/tests/conftest.py
"""
Conftest da suite de testes de acoes_pngi.

ESTRATEGIA:
  - Autossuficiente para os dados necessários aos testes de acoes_pngi.
  - Cria os dados base de lookup (StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, Aplicacao e Roles) via get_or_create.
  - Cria e configura os Groups usados pelos Roles.
  - Popula auth_group_permissions com a matriz de permissões efetivas
    definida para os perfis de ACOES_PNGI.
  - Login real via POST /api/accounts/login/ — sem force_authenticate.
  - Todos os testes usam @pytest.mark.django_db(transaction=True).
  - THROTTLE: desabilitado globalmente pelo conftest raiz.

AUTORIZACAO:
  - Os testes nao usam mais matriz de roles diretamente.
  - As views de acoes_pngi usam CanPermission.
  - A autorizacao e baseada nas permissions efetivas materializadas
    em auth_user_user_permissions pelo fluxo de accounts.
  - auth_user_groups nao e usado como fonte runtime de autorizacao.
  - Os Groups funcionam como templates de permissao dos Roles.

PERFIS:
  - GESTOR_PNGI
  - COORDENADOR_PNGI
  - OPERADOR_ACAO

URLs dos endpoints acoes_pngi:
  GET/POST   /api/acoes-pngi/acoes/
  GET/PATCH/PUT/DELETE /api/acoes-pngi/acoes/{pk}/
  GET/POST   /api/acoes-pngi/acoes/{pk}/prazos/
  GET/POST   /api/acoes-pngi/acoes/{pk}/destaques/
  GET/POST   /api/acoes-pngi/acoes/{pk}/anotacoes/
  GET        /api/acoes-pngi/eixos/
  GET        /api/acoes-pngi/situacoes/
  GET/POST/PUT/PATCH/DELETE /api/acoes-pngi/vigencias/
"""

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import (
    Aplicacao,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
)
from apps.acoes_pngi.models import (
    AcaoAnotacaoAlinhamento,
    AcaoDestaque,
    AcaoPrazo,
    Acoes,
    Eixo,
    SituacaoAcao,
    TipoAnotacaoAlinhamento,
    VigenciaPNGI,
)

LOGIN_URL = "/api/accounts/login/"
ACOES_URL = "/api/acoes-pngi/acoes/"
VIGENCIAS_URL = "/api/acoes-pngi/vigencias/"
EIXOS_URL = "/api/acoes-pngi/eixos/"
SITUACOES_URL = "/api/acoes-pngi/situacoes/"

DEFAULT_PASSWORD = "gpp@2026"


# ---------------------------------------------------------------------------
# Bootstrap de dados base
# ---------------------------------------------------------------------------


def _bootstrap_base_data():
    """
    Garante tabelas lookup, aplicacao, roles, groups e permissions base.

    IMPORTANTE:
    Os Groups sao templates de permissao dos Roles.
    A autorizacao em runtime nao consulta auth_user_groups.
    As permissoes sao materializadas em auth_user_user_permissions
    pelo permission_sync.
    """

    # -----------------------------------------------------------------------
    # Lookups
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Aplicacao
    # -----------------------------------------------------------------------

    app_pngi, _ = Aplicacao.objects.get_or_create(
        pk=2,
        defaults={
            "codigointerno": "ACOES_PNGI",
            "nomeaplicacao": "Acoes PNGI",
            "isappbloqueada": False,
            "isappproductionready": True,
        },
    )

    # -----------------------------------------------------------------------
    # Roles e Groups
    # -----------------------------------------------------------------------

    roles_data = [
        (
            2,
            "GESTOR_PNGI",
            "Gestor PNGI",
            "gestor_pngi_group",
        ),
        (
            3,
            "COORDENADOR_PNGI",
            "Coordenador PNGI",
            "coordenador_pngi_group",
        ),
        (
            4,
            "OPERADOR_ACAO",
            "Operador de Acao",
            "operador_acao_group",
        ),
    ]

    for pk, codigo, nome, group_name in roles_data:
        group, _ = Group.objects.get_or_create(name=group_name)

        role, created = Role.objects.get_or_create(
            pk=pk,
            defaults={
                "codigoperfil": codigo,
                "nomeperfil": nome,
                "aplicacao": app_pngi,
                "group": group,
            },
        )

        # Com --reuse-db, o Role pode ja existir.
        # Nesse caso, garantimos que seus dados continuem coerentes
        # com o bootstrap da suite.
        fields_to_update = []

        if role.codigoperfil != codigo:
            role.codigoperfil = codigo
            fields_to_update.append("codigoperfil")

        if role.nomeperfil != nome:
            role.nomeperfil = nome
            fields_to_update.append("nomeperfil")

        if role.aplicacao_id != app_pngi.pk:
            role.aplicacao = app_pngi
            fields_to_update.append("aplicacao")

        if role.group_id != group.pk:
            role.group = group
            fields_to_update.append("group")

        if fields_to_update:
            role.save(update_fields=fields_to_update)

    # -----------------------------------------------------------------------
    # Permissoes por Group
    #
    # Estas permissoes sao o template institucional de cada Role.
    #
    # Depois da atribuicao do UserRole, sync_user_permissions() calcula:
    #
    #     inherited + grants - revokes
    #
    # e materializa o resultado em auth_user_user_permissions.
    # -----------------------------------------------------------------------

    _group_permissions = {
        # -------------------------------------------------------------------
        # GESTOR_PNGI
        #
        # Acesso completo aos recursos de ACOES_PNGI.
        # -------------------------------------------------------------------
        "gestor_pngi_group": [
            # Acoes
            "add_acoes",
            "change_acoes",
            "delete_acoes",
            "view_acoes",
            # Eixos
            "add_eixo",
            "change_eixo",
            "delete_eixo",
            "view_eixo",
            # Situacoes
            "add_situacaoacao",
            "change_situacaoacao",
            "delete_situacaoacao",
            "view_situacaoacao",
            # Tipos de Entrave/Alerta
            "add_tipoentravealerta",
            "change_tipoentravealerta",
            "delete_tipoentravealerta",
            "view_tipoentravealerta",
            # Tipos de Anotacao/Alinhamento
            "add_tipoanotacaoalinhamento",
            "change_tipoanotacaoalinhamento",
            "delete_tipoanotacaoalinhamento",
            "view_tipoanotacaoalinhamento",
            # Vigencias
            "add_vigenciapngi",
            "change_vigenciapngi",
            "delete_vigenciapngi",
            "view_vigenciapngi",
            # Prazo
            "add_acaoprazo",
            "change_acaoprazo",
            "delete_acaoprazo",
            "view_acaoprazo",
            # Destaque
            "add_acaodestaque",
            "change_acaodestaque",
            "delete_acaodestaque",
            "view_acaodestaque",
            # Anotacao/Alinhamento
            "add_acaoanotacaoalinhamento",
            "change_acaoanotacaoalinhamento",
            "delete_acaoanotacaoalinhamento",
            "view_acaoanotacaoalinhamento",
            # Responsaveis
            "add_relacaoacaousuarioresponsavel",
            "change_relacaoacaousuarioresponsavel",
            "delete_relacaoacaousuarioresponsavel",
            "view_relacaoacaousuarioresponsavel",
        ],
        # -------------------------------------------------------------------
        # COORDENADOR_PNGI
        #
        # Regras atualmente definidas:
        #   - Acoes: view/add/change, sem delete
        #   - Prazo: CRUD
        #   - Destaque: CRUD
        #   - Responsaveis: CRUD
        #   - Anotacao/Alinhamento: view
        #   - Tipo Anotacao/Alinhamento: CRUD
        #   - Tipo Entrave/Alerta: view
        #   - Eixo: view
        #   - Situacao: view
        #   - Vigencia: view
        # -------------------------------------------------------------------
        "coordenador_pngi_group": [
            # Acoes
            "add_acoes",
            "change_acoes",
            "view_acoes",
            # Eixos
            "view_eixo",
            # Situacoes
            "view_situacaoacao",
            # Tipos de Entrave/Alerta
            "view_tipoentravealerta",
            # Tipos de Anotacao/Alinhamento
            "add_tipoanotacaoalinhamento",
            "change_tipoanotacaoalinhamento",
            "delete_tipoanotacaoalinhamento",
            "view_tipoanotacaoalinhamento",
            # Vigencias
            "view_vigenciapngi",
            # Prazo
            "add_acaoprazo",
            "change_acaoprazo",
            "delete_acaoprazo",
            "view_acaoprazo",
            # Destaque
            "add_acaodestaque",
            "change_acaodestaque",
            "delete_acaodestaque",
            "view_acaodestaque",
            # Anotacao/Alinhamento
            "view_acaoanotacaoalinhamento",
            # Responsaveis
            "add_relacaoacaousuarioresponsavel",
            "change_relacaoacaousuarioresponsavel",
            "delete_relacaoacaousuarioresponsavel",
            "view_relacaoacaousuarioresponsavel",
        ],
        # -------------------------------------------------------------------
        # OPERADOR_ACAO
        #
        # Regras atualmente definidas:
        #   - Acoes: view/change
        #   - sem add/delete Acoes
        #   - Destaque: CRUD
        #   - Anotacao/Alinhamento: change/view
        #   - recursos de configuracao: somente view
        #
        # A restricao ABAC de atuar somente nas Acoes das quais participa
        # sera tratada posteriormente no AuthorizationService/contexto.
        # -------------------------------------------------------------------
        "operador_acao_group": [
            # Acoes
            "change_acoes",
            "view_acoes",
            # Eixos
            "view_eixo",
            # Situacoes
            "view_situacaoacao",
            # Tipos de Entrave/Alerta
            "view_tipoentravealerta",
            # Tipos de Anotacao/Alinhamento
            "view_tipoanotacaoalinhamento",
            # Vigencias
            "view_vigenciapngi",
            # Prazo
            "view_acaoprazo",
            # Destaque
            "add_acaodestaque",
            "change_acaodestaque",
            "delete_acaodestaque",
            "view_acaodestaque",
            # Anotacao/Alinhamento
            "change_acaoanotacaoalinhamento",
            "view_acaoanotacaoalinhamento",
            # Responsaveis
            "view_relacaoacaousuarioresponsavel",
        ],
    }

    # -----------------------------------------------------------------------
    # Materializa as permissoes nos Groups.
    #
    # O .set() e idempotente e garante que permissoes antigas eventualmente
    # existentes no banco de testes nao contaminem a suite.
    # -----------------------------------------------------------------------

    for group_name, codenames in _group_permissions.items():
        group = Group.objects.get(name=group_name)

        perms = Permission.objects.filter(
            codename__in=codenames,
        )

        group.permissions.set(perms)


@pytest.fixture(autouse=True)
def _ensure_base_data(db):
    """
    Executada antes de cada teste que use db/django_db.

    Garante que StatusUsuario, TipoUsuario, ClassificacaoUsuario,
    Aplicacao, Roles, Groups e permissions base existam.
    """
    _bootstrap_base_data()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    username,
    password=DEFAULT_PASSWORD,
    classificacao_pk=1,
):
    """
    Cria ou recupera auth.User + UserProfile.

    Seguro com --reuse-db: usa get_or_create e atualiza a senha sempre.
    """
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"is_active": True},
    )

    user.set_password(password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])

    classificacao = ClassificacaoUsuario.objects.get(pk=classificacao_pk)

    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "name": username,
            "orgao": "ES",
            "status_usuario": StatusUsuario.objects.get(pk=1),
            "tipo_usuario": TipoUsuario.objects.get(pk=1),
            "classificacao_usuario": classificacao,
        },
    )

    return user


def _make_user_rj(
    username,
    password=DEFAULT_PASSWORD,
):
    """
    Cria usuario com orgao=RJ para testes futuros de ABAC/IDOR.
    """
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"is_active": True},
    )

    user.set_password(password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])

    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "name": username,
            "orgao": "RJ",
            "status_usuario": StatusUsuario.objects.get(pk=1),
            "tipo_usuario": TipoUsuario.objects.get(pk=1),
            "classificacao_usuario": ClassificacaoUsuario.objects.get(pk=1),
        },
    )

    return user


def _assign_role(user, role_pk):
    """
    Associa o usuario a uma UserRole.

    A suite nao adiciona o usuario diretamente a auth_user_groups.

    A materializacao das permissions efetivas ocorre pelo fluxo normal
    de accounts:
        Role -> Group -> permissions
        -> sync_user_permissions()
        -> auth_user_user_permissions
    """

    from apps.accounts.services.permission_sync import sync_user_permissions

    role = Role.objects.get(pk=role_pk)

    user_role, created = UserRole.objects.get_or_create(
        user=user,
        aplicacao=role.aplicacao,
        defaults={"role": role},
    )

    if not created and user_role.role_id != role.pk:
        user_role.role = role
        user_role.save(update_fields=["role"])

    # Garante a materializacao das permissoes efetivas.
    sync_user_permissions(user)

    return role


def _login(
    username,
    app_context=None,
    password=DEFAULT_PASSWORD,
):
    """
    Retorna (client, response) com sessao autenticada.

    Envia X-Application-Code: ACOES_PNGI para que o
    ApplicationContextMiddleware resolva request.application
    corretamente.
    """

    client = APIClient()

    client.credentials(
        HTTP_X_APPLICATION_CODE="ACOES_PNGI",
    )

    resp = client.post(
        LOGIN_URL,
        {
            "username": username,
            "password": password,
            "app_context": app_context or "ACOES_PNGI",
        },
        format="json",
    )

    return client, resp


# ---------------------------------------------------------------------------
# Fixtures de usuarios por role
# ---------------------------------------------------------------------------


@pytest.fixture
def gestor_pngi(db):
    user = _make_user(
        "gestor_pngi_u",
        classificacao_pk=2,
    )

    _assign_role(user, role_pk=2)

    return user


@pytest.fixture
def coordenador_pngi(db):
    user = _make_user(
        "coordenador_pngi_u",
    )

    _assign_role(user, role_pk=3)

    return user


@pytest.fixture
def operador_acao(db):
    user = _make_user(
        "operador_acao_u",
    )

    _assign_role(user, role_pk=4)

    return user


@pytest.fixture
def usuario_sem_role(db):
    return _make_user(
        "sem_role_pngi_u",
    )


# ---------------------------------------------------------------------------
# Fixtures de clients autenticados
# ---------------------------------------------------------------------------


@pytest.fixture
def client_gestor(db, gestor_pngi):
    client, resp = _login("gestor_pngi_u")

    assert resp.status_code == 200, f"Login GESTOR_PNGI falhou: {resp.data}"

    return client


@pytest.fixture
def client_coordenador(db, coordenador_pngi):
    client, resp = _login("coordenador_pngi_u")

    assert resp.status_code == 200, f"Login COORDENADOR_PNGI falhou: {resp.data}"

    return client


@pytest.fixture
def client_operador(db, operador_acao):
    client, resp = _login("operador_acao_u")

    assert resp.status_code == 200, f"Login OPERADOR_ACAO falhou: {resp.data}"

    return client


@pytest.fixture
def client_anonimo():
    return APIClient()


# ---------------------------------------------------------------------------
# Fixtures de dados de dominio
# ---------------------------------------------------------------------------


@pytest.fixture
def vigencia(db):
    """
    Cria uma VigenciaPNGI isolada para o teste corrente.

    Usa create() porque strdescricao nao e unique.
    """

    return VigenciaPNGI.objects.create(
        strdescricao="PNGI 2025-2028",
        datiniciovigencia="2025-01-01",
    )


@pytest.fixture
def vigencia_livre(db):
    """
    VigenciaPNGI sem nenhuma Acoes vinculada.

    Usar nos testes de DELETE de vigencia.
    """

    return VigenciaPNGI.objects.create(
        strdescricao="PNGI Vigencia Livre - Delete Test",
        datiniciovigencia="2099-01-01",
    )


@pytest.fixture
def eixo(db):
    obj, _ = Eixo.objects.get_or_create(
        stralias="INF",
        defaults={
            "strdescricaoeixo": "Infraestrutura",
        },
    )

    return obj


@pytest.fixture
def situacao(db):
    obj, _ = SituacaoAcao.objects.get_or_create(
        strdescricaosituacao="Em andamento",
    )

    return obj


@pytest.fixture
def acao(db, vigencia):
    """Acao base para testes de retrieve/update/delete."""

    return Acoes.objects.create(
        strapelido="ACAO-TEST-001",
        strdescricaoacao="Descricao da acao de teste",
        strdescricaoentrega="Entrega esperada",
        idvigenciapngi=vigencia,
    )


@pytest.fixture
def payload_acao(vigencia):
    """Payload minimo valido para criar uma Acao via API."""

    return {
        "strapelido": "ACAO-API-001",
        "strdescricaoacao": "Acao criada via API",
        "strdescricaoentrega": "Entrega via API",
        "idvigenciapngi_id": vigencia.pk,
    }


@pytest.fixture
def prazo(db, acao):
    return AcaoPrazo.objects.create(
        idacao=acao,
        strprazo="Prazo de teste",
    )


@pytest.fixture
def destaque(db, acao):
    return AcaoDestaque.objects.create(
        idacao=acao,
        datdatadestaque=timezone.now(),
    )


@pytest.fixture
def tipo_anotacao(db):
    return TipoAnotacaoAlinhamento.objects.create(
        strdescricaotipoanotacaoalinhamento="Alinhamento de teste",
    )


@pytest.fixture
def anotacao(db, acao, tipo_anotacao):
    return AcaoAnotacaoAlinhamento.objects.create(
        idacao=acao,
        idtipoanotacaoalinhamento=tipo_anotacao,
        strdescricao="Anotacao de teste",
    )
