"""
Conftest da suite de testes de acoes_pngi.

ESTRATEGIA:
  - Reutiliza os dados base ja criados pelo conftest de accounts
    (StatusUsuario, TipoUsuario, ClassificacaoUsuario, Aplicacao, Roles)
    via get_or_create — sem duplicar bootstrap.
  - Usuarios e roles especificos de acoes_pngi sao criados aqui.
  - Login real via POST /api/accounts/login/ — sem force_authenticate.
  - Todos os testes usam @pytest.mark.django_db(transaction=True).
  - THROTTLE: desabilitado globalmente pelo conftest raiz (session-scoped).
    Não há override local aqui nem cache.clear() — o controle está
    centralizado em conftest.py (raiz).

URLs dos endpoints acoes_pngi:
  GET/POST   /api/acoes-pngi/acoes/
  GET/PATCH/PUT/DELETE /api/acoes-pngi/acoes/{pk}/
  GET/POST   /api/acoes-pngi/acoes/{pk}/prazos/
  GET/POST   /api/acoes-pngi/acoes/{pk}/destaques/
  GET/POST   /api/acoes-pngi/acoes/{pk}/anotacoes/
  GET        /api/acoes-pngi/eixos/
  GET        /api/acoes-pngi/situacoes/
  GET/POST   /api/acoes-pngi/vigencias/
"""
import pytest
from django.contrib.auth.models import Group, User
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
from apps.acoes_pngi.models import Acoes, Eixo, SituacaoAcao, VigenciaPNGI

LOGIN_URL = "/api/accounts/login/"
ACOES_URL = "/api/acoes-pngi/acoes/"
VIGENCIAS_URL = "/api/acoes-pngi/vigencias/"
EIXOS_URL = "/api/acoes-pngi/eixos/"
SITUACOES_URL = "/api/acoes-pngi/situacoes/"
DEFAULT_PASSWORD = "gpp@2026"


# ---------------------------------------------------------------------------
# lru_cache bust — _load_role_matrix() deve reler o banco em cada teste
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_role_matrix_cache():
    """
    Limpa o lru_cache de _load_role_matrix() e _load_vigencia_role_matrix()
    antes e apos cada teste.

    Sem isso, se o cache for populado antes do _ensure_base_data criar
    as roles no banco de teste, _load_role_matrix() retorna frozenset
    vazio e todos os endpoints retornam 403 por falta de roles permitidas.

    IMPORTANTE: com transaction=True cada teste faz commits reais.
    O lru_cache sobrevive entre testes no mesmo processo — sem o bust,
    _load_vigencia_role_matrix() pode retornar uma matrix carregada em
    run anterior onde OPERADOR_ACAO tinha permissao WRITE (cache stale),
    fazendo test_nao_pode_criar_vigencia retornar 201 em vez de 403.
    """
    from apps.acoes_pngi.views import _load_role_matrix, _load_vigencia_role_matrix
    _load_role_matrix.cache_clear()
    _load_vigencia_role_matrix.cache_clear()
    yield
    _load_role_matrix.cache_clear()
    _load_vigencia_role_matrix.cache_clear()


# ---------------------------------------------------------------------------
# Bootstrap de dados base (idempotente — funciona com --reuse-db)
# ---------------------------------------------------------------------------

def _bootstrap_base_data():
    """Garante tabelas lookup e aplicacoes/roles base (get_or_create)."""
    StatusUsuario.objects.get_or_create(pk=1, defaults={"strdescricao": "Ativo"})
    TipoUsuario.objects.get_or_create(pk=1, defaults={"strdescricao": "Interno"})
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

    app_pngi, _ = Aplicacao.objects.get_or_create(
        pk=2,
        defaults={
            "codigointerno": "ACOES_PNGI",
            "nomeaplicacao": "Acoes PNGI",
            "isappbloqueada": False,
            "isappproductionready": True,
        },
    )

    roles_data = [
        (2, "GESTOR_PNGI",      "Gestor PNGI",       "gestor_pngi_group"),
        (3, "COORDENADOR_PNGI", "Coordenador PNGI",  "coordenador_pngi_group"),
        (4, "OPERADOR_ACAO",    "Operador de Acao",  "operador_acao_group"),
        (5, "CONSULTOR_PNGI",   "Consultor PNGI",    "consultor_pngi_group"),
    ]
    for pk, codigo, nome, group_name in roles_data:
        group, _ = Group.objects.get_or_create(name=group_name)
        Role.objects.get_or_create(
            pk=pk,
            defaults={
                "codigoperfil": codigo,
                "nomeperfil": nome,
                "aplicacao": app_pngi,
                "group": group,
            },
        )


@pytest.fixture(autouse=True)
def _ensure_base_data(db):
    _bootstrap_base_data()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username, password=DEFAULT_PASSWORD, classificacao_pk=1):
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


def _make_user_rj(username, password=DEFAULT_PASSWORD):
    """Cria usuario com orgao=RJ para testes de IDOR."""
    user, _ = User.objects.get_or_create(username=username, defaults={"is_active": True})
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


def _login(username, app_context=None, password=DEFAULT_PASSWORD):
    """
    Retorna (client, response) com sessao autenticada.

    Envia X-Application-Code: ACOES_PNGI para que o
    ApplicationContextMiddleware resolva request.application
    corretamente (sem cair no fallback "portal" ou APP_CONTEXT_NONE),
    garantindo que o RoleContextMiddleware carregue user_roles
    filtrados pela aplicacao correta apos o login.
    """
    client = APIClient()
    client.credentials(HTTP_X_APPLICATION_CODE="ACOES_PNGI")
    resp = client.post(
        LOGIN_URL,
        {"username": username, "password": password, "app_context": app_context or "ACOES_PNGI"},
        format="json",
    )
    return client, resp


# ---------------------------------------------------------------------------
# Fixtures de usuarios por role
# ---------------------------------------------------------------------------

@pytest.fixture
def gestor_pngi(db):
    user = _make_user("gestor_pngi_u", classificacao_pk=2)
    _assign_role(user, role_pk=2)
    return user


@pytest.fixture
def coordenador_pngi(db):
    user = _make_user("coordenador_pngi_u")
    _assign_role(user, role_pk=3)
    return user


@pytest.fixture
def operador_acao(db):
    user = _make_user("operador_acao_u")
    _assign_role(user, role_pk=4)
    return user


@pytest.fixture
def consultor_pngi(db):
    user = _make_user("consultor_pngi_u")
    _assign_role(user, role_pk=5)
    return user


@pytest.fixture
def usuario_sem_role(db):
    return _make_user("sem_role_pngi_u")


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
def client_consultor(db, consultor_pngi):
    client, resp = _login("consultor_pngi_u")
    assert resp.status_code == 200, f"Login CONSULTOR_PNGI falhou: {resp.data}"
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

    USA create() — nao get_or_create — porque strdescricao nao tem
    unique=True no model. Com get_or_create, execucoes anteriores da
    suite acumulavam registros com o mesmo strdescricao no banco de
    testes persistente, causando MultipleObjectsReturned no proximo run.
    O rollback de transaction=True cuida da limpeza apos cada teste.

    ATENCAO: NAO usar esta fixture em testes de DELETE de vigencia.
    Como transaction=True faz commits reais, Acoes criadas por testes
    anteriores (que usam a fixture acao) podem estar vinculadas a esta
    VigenciaPNGI via idvigenciapngi (on_delete=PROTECT), causando
    ProtectedError. Use vigencia_livre nesses casos.
    """
    return VigenciaPNGI.objects.create(
        strdescricao="PNGI 2025-2028",
        datiniciovigencia="2025-01-01",
    )


@pytest.fixture
def vigencia_livre(db):
    """
    VigenciaPNGI garantidamente sem nenhuma Acoes vinculada.

    Usar EXCLUSIVAMENTE em testes de DELETE de vigencia.

    Contexto: idvigenciapngi tem on_delete=PROTECT. Com transaction=True
    os testes fazem commits reais no banco — Acoes criadas por testes
    anteriores da mesma suite (ex: test_pode_criar_acao) podem estar
    apontando para a vigencia generica. Ao tentar deletar, Django lanca
    ProtectedError porque existem Acoes dependentes.

    Esta fixture cria uma VigenciaPNGI com datiniciovigencia futura e
    strdescricao unica para que nenhum outro teste a referencie,
    garantindo que o DELETE retorne 204 sem conflito de FK.
    """
    return VigenciaPNGI.objects.create(
        strdescricao="PNGI Vigencia Livre - Delete Test",
        datiniciovigencia="2099-01-01",
    )


@pytest.fixture
def eixo(db):
    obj, _ = Eixo.objects.get_or_create(
        stralias="INF",
        defaults={"strdescricaoeixo": "Infraestrutura"},
    )
    return obj


@pytest.fixture
def situacao(db):
    """
    Usa get_or_create para evitar UniqueViolation quando _ensure_base_data
    ou outro teste ja inseriu 'Em andamento' na mesma transacao.
    """
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
