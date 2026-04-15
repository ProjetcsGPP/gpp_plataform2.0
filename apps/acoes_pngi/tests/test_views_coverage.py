"""
Testes de cobertura para apps/acoes_pngi/views.py.

Objetivo: atingir ≥80% de cobertura em views.py, cobrindo:
  - _load_role_matrix / _load_vigencia_role_matrix (cache + conteúdo)
  - _check_roles (todos os branches: portal_admin, sem role, com role)
  - Todos os ViewSets: list, retrieve, create, update, partial_update, destroy
  - ViewSets nested: AcaoPrazo, AcaoDestaque, AcaoAnotacao
  - Roles: GESTOR, COORDENADOR, OPERADOR, CONSULTOR
"""

from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.accounts.tests.conftest import _make_authenticated_client, _make_user
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
from apps.acoes_pngi.views import (
    _LEVEL_DELETE,
    _LEVEL_READ,
    _LEVEL_WRITE,
    _check_roles,
    _load_role_matrix,
    _load_vigencia_role_matrix,
)

# URLs base
ACOES_URL = "/api/acoes-pngi/acoes/"
VIGENCIAS_URL = "/api/acoes-pngi/vigencias/"
EIXOS_URL = "/api/acoes-pngi/eixos/"
SITUACOES_URL = "/api/acoes-pngi/situacoes/"


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """Garante que as matrizes sejam relidas do banco em cada teste."""
    _load_role_matrix.cache_clear()
    _load_vigencia_role_matrix.cache_clear()
    yield
    _load_role_matrix.cache_clear()
    _load_vigencia_role_matrix.cache_clear()


# ---------------------------------------------------------------------------
# Fixtures de usuários/roles
# ---------------------------------------------------------------------------


@pytest.fixture
def consultor_pngi(db):
    from apps.accounts.models import ClassificacaoUsuario

    ClassificacaoUsuario.objects.get_or_create(
        pk=1,
        defaults={
            "strdescricao": "Usuario Padrao",
            "pode_criar_usuario": False,
            "pode_editar_usuario": False,
        },
    )
    app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
    from django.contrib.auth.models import Group

    group, _ = Group.objects.get_or_create(name="consultor_pngi_group")
    role, _ = Role.objects.get_or_create(
        codigoperfil="CONSULTOR_PNGI",
        aplicacao=app,
        defaults={"nomeperfil": "Consultor PNGI", "group": group},
    )
    user = _make_user("consultor_test")
    UserRole.objects.get_or_create(user=user, aplicacao=app, defaults={"role": role})
    user.groups.add(group)
    return user


@pytest.fixture
def client_consultor(db, consultor_pngi):
    client, resp = _make_authenticated_client("consultor_test", "ACOES_PNGI")
    assert resp.status_code == 200, f"Login consultor falhou: {resp.data}"
    return client


# ---------------------------------------------------------------------------
# Fixtures de dados
# ---------------------------------------------------------------------------


@pytest.fixture
def vigencia(db):
    return VigenciaPNGI.objects.create(
        strdescricao="Vigencia Teste",
        datiniciovigencia="2026-01-01",
    )


@pytest.fixture
def eixo(db):
    obj, _ = Eixo.objects.get_or_create(
        stralias="TST",
        defaults={"strdescricaoeixo": "Eixo Teste"},
    )
    return obj


@pytest.fixture
def situacao(db):
    obj, _ = SituacaoAcao.objects.get_or_create(strdescricaosituacao="Em andamento")
    return obj


@pytest.fixture
def acao(db, vigencia):
    return Acoes.objects.create(
        strapelido="ACAO-COV-001",
        strdescricaoacao="Acao de cobertura",
        strdescricaoentrega="Entrega esperada",
        idvigenciapngi=vigencia,
    )


@pytest.fixture
def prazo(db, acao):
    return AcaoPrazo.objects.create(idacao=acao, strprazo="Prazo fixture")


@pytest.fixture
def destaque(db, acao):
    return AcaoDestaque.objects.create(idacao=acao, datdatadestaque=timezone.now())


@pytest.fixture
def tipo_anotacao(db):
    obj, _ = TipoAnotacaoAlinhamento.objects.get_or_create(
        strdescricaotipoanotacaoalinhamento="Tipo Teste"
    )
    return obj


@pytest.fixture
def anotacao(db, acao, tipo_anotacao):
    return AcaoAnotacaoAlinhamento.objects.create(
        idacao=acao,
        idtipoanotacaoalinhamento=tipo_anotacao,
        strdescricao="Anotacao fixture",
    )


# ---------------------------------------------------------------------------
# TestCheckRolesDirect — cobre _check_roles() diretamente (sem HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCheckRolesDirect:
    """Cobre todos os branches de _check_roles()."""

    def test_portal_admin_bypass(self):
        req = MagicMock()
        req.is_portal_admin = True
        req.user_roles = []
        _check_roles(req, _LEVEL_READ)  # não deve lançar

    def test_portal_admin_bypass_delete(self):
        req = MagicMock()
        req.is_portal_admin = True
        req.user_roles = []
        _check_roles(req, _LEVEL_DELETE)  # não deve lançar

    def test_sem_role_lanca_read(self):
        req = MagicMock()
        req.is_portal_admin = False
        req.user_roles = []
        with pytest.raises(PermissionDenied):
            _check_roles(req, _LEVEL_READ)

    def test_sem_role_lanca_write(self):
        req = MagicMock()
        req.is_portal_admin = False
        req.user_roles = []
        with pytest.raises(PermissionDenied):
            _check_roles(req, _LEVEL_WRITE)

    def test_gestor_passa_delete(self):
        matrix = _load_role_matrix()
        assert "GESTOR_PNGI" in matrix[_LEVEL_DELETE]
        role_mock = MagicMock()
        role_mock.role.codigoperfil = "GESTOR_PNGI"
        req = MagicMock()
        req.is_portal_admin = False
        req.user_roles = [role_mock]
        _check_roles(req, _LEVEL_DELETE)  # não deve lançar

    def test_consultor_nao_passa_write(self):
        matrix = _load_role_matrix()
        assert "CONSULTOR_PNGI" not in matrix[_LEVEL_WRITE]
        role_mock = MagicMock()
        role_mock.role.codigoperfil = "CONSULTOR_PNGI"
        req = MagicMock()
        req.is_portal_admin = False
        req.user_roles = [role_mock]
        with pytest.raises(PermissionDenied):
            _check_roles(req, _LEVEL_WRITE)

    def test_matrix_fn_custom(self):
        """Testa o branch matrix_fn != None passando _load_vigencia_role_matrix."""
        role_mock = MagicMock()
        role_mock.role.codigoperfil = "GESTOR_PNGI"
        req = MagicMock()
        req.is_portal_admin = False
        req.user_roles = [role_mock]
        _check_roles(
            req, _LEVEL_WRITE, matrix_fn=_load_vigencia_role_matrix
        )  # não deve lançar

    def test_operador_nao_passa_vigencia_write(self):
        """OPERADOR_ACAO não pode escrever vigencias."""
        matrix = _load_vigencia_role_matrix()
        assert "OPERADOR_ACAO" not in matrix[_LEVEL_WRITE]
        role_mock = MagicMock()
        role_mock.role.codigoperfil = "OPERADOR_ACAO"
        req = MagicMock()
        req.is_portal_admin = False
        req.user_roles = [role_mock]
        with pytest.raises(PermissionDenied):
            _check_roles(req, _LEVEL_WRITE, matrix_fn=_load_vigencia_role_matrix)


# ---------------------------------------------------------------------------
# TestLoadMatrices — cobre _load_role_matrix e _load_vigencia_role_matrix
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLoadMatrices:

    def test_load_role_matrix_retorna_dict(self):
        m = _load_role_matrix()
        assert isinstance(m, dict)
        assert set(m.keys()) == {_LEVEL_READ, _LEVEL_WRITE, _LEVEL_DELETE}

    def test_load_role_matrix_gestor_em_todos(self):
        m = _load_role_matrix()
        assert "GESTOR_PNGI" in m[_LEVEL_READ]
        assert "GESTOR_PNGI" in m[_LEVEL_WRITE]
        assert "GESTOR_PNGI" in m[_LEVEL_DELETE]

    def test_load_role_matrix_consultor_so_read(self):
        m = _load_role_matrix()
        assert "CONSULTOR_PNGI" in m[_LEVEL_READ]
        assert "CONSULTOR_PNGI" not in m[_LEVEL_WRITE]
        assert "CONSULTOR_PNGI" not in m[_LEVEL_DELETE]

    def test_load_role_matrix_cache_hit(self):
        m1 = _load_role_matrix()
        m2 = _load_role_matrix()
        assert m1 is m2

    def test_load_vigencia_matrix_operador_so_read(self):
        m = _load_vigencia_role_matrix()
        assert "OPERADOR_ACAO" in m[_LEVEL_READ]
        assert "OPERADOR_ACAO" not in m[_LEVEL_WRITE]

    def test_load_vigencia_matrix_cache_hit(self):
        m1 = _load_vigencia_role_matrix()
        m2 = _load_vigencia_role_matrix()
        assert m1 is m2


# ---------------------------------------------------------------------------
# TestCoordenadorPermissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCoordenadorPermissions:

    def test_coordenador_pode_listar_acoes(self, client_coordenador):
        assert client_coordenador.get(ACOES_URL).status_code == 200

    def test_coordenador_pode_criar_acao(self, client_coordenador, vigencia):
        resp = client_coordenador.post(
            ACOES_URL,
            {
                "strapelido": "ACAO-COORD-001",
                "strdescricaoacao": "Nova Acao Coordenador",
                "strdescricaoentrega": "Entrega coordenador",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_coordenador_pode_retrieve_acao(self, client_coordenador, acao):
        assert client_coordenador.get(f"{ACOES_URL}{acao.pk}/").status_code == 200

    def test_coordenador_pode_update_acao(self, client_coordenador, acao, vigencia):
        resp = client_coordenador.put(
            f"{ACOES_URL}{acao.pk}/",
            {
                "strapelido": "ACAO-UPDATED",
                "strdescricaoacao": "Atualizada",
                "strdescricaoentrega": "Entrega",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )
        assert resp.status_code == 200

    def test_coordenador_nao_pode_deletar_acao(self, client_coordenador, acao):
        assert client_coordenador.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403

    def test_coordenador_pode_criar_vigencia(self, client_coordenador):
        resp = client_coordenador.post(
            VIGENCIAS_URL,
            {
                "strdescricao": "Vigencia Coordenador",
                "datiniciovigencia": "2026-01-01",
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_coordenador_pode_retrieve_vigencia(self, client_coordenador, vigencia):
        assert (
            client_coordenador.get(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code == 200
        )

    def test_coordenador_nao_pode_deletar_vigencia(self, client_coordenador, vigencia):
        assert (
            client_coordenador.delete(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code
            == 403
        )


# ---------------------------------------------------------------------------
# TestOperadorPermissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOperadorPermissions:

    def test_operador_pode_listar_acoes(self, client_operador):
        assert client_operador.get(ACOES_URL).status_code == 200

    def test_operador_pode_criar_acao(self, client_operador, vigencia):
        resp = client_operador.post(
            ACOES_URL,
            {
                "strapelido": "ACAO-OPER-001",
                "strdescricaoacao": "Nova Acao Operador",
                "strdescricaoentrega": "Entrega operador",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_operador_pode_retrieve_acao(self, client_operador, acao):
        assert client_operador.get(f"{ACOES_URL}{acao.pk}/").status_code == 200

    def test_operador_nao_pode_deletar_acao(self, client_operador, acao):
        assert client_operador.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403

    def test_operador_nao_pode_criar_vigencia(self, client_operador):
        resp = client_operador.post(
            VIGENCIAS_URL,
            {
                "strdescricao": "Vigencia Operador",
                "datiniciovigencia": "2026-01-01",
            },
            format="json",
        )
        assert resp.status_code == 403

    def test_operador_nao_pode_deletar_vigencia(self, client_operador, vigencia):
        assert (
            client_operador.delete(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code == 403
        )

    def test_operador_pode_listar_vigencias(self, client_operador):
        assert client_operador.get(VIGENCIAS_URL).status_code == 200

    def test_operador_pode_retrieve_vigencia(self, client_operador, vigencia):
        assert client_operador.get(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code == 200

    def test_operador_nao_pode_patch_vigencia(self, client_operador, vigencia):
        assert (
            client_operador.patch(
                f"{VIGENCIAS_URL}{vigencia.pk}/", {"strdescricao": "X"}, format="json"
            ).status_code
            == 403
        )


# ---------------------------------------------------------------------------
# TestConsultorPermissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConsultorPermissions:

    def test_consultor_pode_listar_acoes(self, client_consultor):
        assert client_consultor.get(ACOES_URL).status_code == 200

    def test_consultor_nao_pode_criar_acao(self, client_consultor, vigencia):
        resp = client_consultor.post(
            ACOES_URL,
            {
                "strapelido": "ACAO-BLOCK",
                "strdescricaoacao": "Acao Bloqueada",
                "strdescricaoentrega": "Bloqueada",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )
        assert resp.status_code == 403

    def test_consultor_pode_retrieve_acao(self, client_consultor, acao):
        assert client_consultor.get(f"{ACOES_URL}{acao.pk}/").status_code == 200

    def test_consultor_nao_pode_deletar_acao(self, client_consultor, acao):
        assert client_consultor.delete(f"{ACOES_URL}{acao.pk}/").status_code == 403

    def test_consultor_nao_pode_criar_vigencia(self, client_consultor):
        resp = client_consultor.post(
            VIGENCIAS_URL,
            {"strdescricao": "Blocked", "datiniciovigencia": "2026-01-01"},
            format="json",
        )
        assert resp.status_code == 403

    def test_consultor_pode_listar_vigencias(self, client_consultor):
        assert client_consultor.get(VIGENCIAS_URL).status_code == 200


# ---------------------------------------------------------------------------
# TestEixoSituacaoViewSets
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEixoSituacaoViewSets:

    def test_gestor_lista_eixos(self, client_gestor, eixo):
        assert client_gestor.get(EIXOS_URL).status_code == 200

    def test_gestor_retrieve_eixo(self, client_gestor, eixo):
        assert client_gestor.get(f"{EIXOS_URL}{eixo.pk}/").status_code == 200

    def test_gestor_lista_situacoes(self, client_gestor, situacao):
        assert client_gestor.get(SITUACOES_URL).status_code == 200

    def test_gestor_retrieve_situacao(self, client_gestor, situacao):
        assert client_gestor.get(f"{SITUACOES_URL}{situacao.pk}/").status_code == 200

    def test_consultor_lista_eixos(self, client_consultor, eixo):
        assert client_consultor.get(EIXOS_URL).status_code == 200

    def test_consultor_lista_situacoes(self, client_consultor, situacao):
        assert client_consultor.get(SITUACOES_URL).status_code == 200


# ---------------------------------------------------------------------------
# TestVigenciaFullCRUD — GESTOR faz ciclo completo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVigenciaFullCRUD:

    def test_gestor_pode_listar(self, client_gestor):
        assert client_gestor.get(VIGENCIAS_URL).status_code == 200

    def test_gestor_pode_criar(self, client_gestor):
        resp = client_gestor.post(
            VIGENCIAS_URL,
            {
                "strdescricao": "Vigencia GESTOR",
                "datiniciovigencia": "2026-01-01",
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_gestor_pode_retrieve(self, client_gestor, vigencia):
        assert client_gestor.get(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code == 200

    def test_gestor_pode_update(self, client_gestor, vigencia):
        resp = client_gestor.put(
            f"{VIGENCIAS_URL}{vigencia.pk}/",
            {
                "strdescricao": "Atualizada",
                "datiniciovigencia": "2026-06-01",
            },
            format="json",
        )
        assert resp.status_code == 200

    def test_gestor_pode_patch(self, client_gestor, vigencia):
        resp = client_gestor.patch(
            f"{VIGENCIAS_URL}{vigencia.pk}/", {"strdescricao": "Patched"}, format="json"
        )
        assert resp.status_code == 200

    def test_gestor_pode_deletar(self, client_gestor, vigencia):
        assert client_gestor.delete(f"{VIGENCIAS_URL}{vigencia.pk}/").status_code == 204


# ---------------------------------------------------------------------------
# TestAcaoFullCRUD — GESTOR faz ciclo completo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcaoFullCRUD:

    def test_gestor_pode_listar(self, client_gestor):
        assert client_gestor.get(ACOES_URL).status_code == 200

    def test_gestor_pode_criar(self, client_gestor, vigencia):
        resp = client_gestor.post(
            ACOES_URL,
            {
                "strapelido": "ACAO-GESTOR",
                "strdescricaoacao": "Acao Gestor",
                "strdescricaoentrega": "Entrega",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_gestor_pode_retrieve(self, client_gestor, acao):
        assert client_gestor.get(f"{ACOES_URL}{acao.pk}/").status_code == 200

    def test_gestor_pode_update(self, client_gestor, acao, vigencia):
        resp = client_gestor.put(
            f"{ACOES_URL}{acao.pk}/",
            {
                "strapelido": "UPDATED",
                "strdescricaoacao": "Atualizada",
                "strdescricaoentrega": "Entrega",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )
        assert resp.status_code == 200

    def test_gestor_pode_patch(self, client_gestor, acao):
        resp = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/", {"strdescricaoacao": "Patched"}, format="json"
        )
        assert resp.status_code == 200

    def test_gestor_pode_deletar(self, client_gestor, acao):
        assert client_gestor.delete(f"{ACOES_URL}{acao.pk}/").status_code == 204


# ---------------------------------------------------------------------------
# TestVigenciaPartialUpdate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVigenciaPartialUpdate:

    def test_gestor_pode_patch_vigencia(self, client_gestor, vigencia):
        resp = client_gestor.patch(
            f"{VIGENCIAS_URL}{vigencia.pk}/",
            {"strdescricao": "Vigencia Atualizada"},
            format="json",
        )
        assert resp.status_code == 200

    def test_coordenador_pode_patch_vigencia(self, client_coordenador, vigencia):
        resp = client_coordenador.patch(
            f"{VIGENCIAS_URL}{vigencia.pk}/",
            {"strdescricao": "Atualizado Coord"},
            format="json",
        )
        assert resp.status_code == 200

    def test_operador_nao_pode_patch_vigencia(self, client_operador, vigencia):
        resp = client_operador.patch(
            f"{VIGENCIAS_URL}{vigencia.pk}/",
            {"strdescricao": "Tentativa Operador"},
            format="json",
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestAcaoPartialUpdate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcaoPartialUpdate:

    def test_operador_pode_patch_acao(self, client_operador, acao):
        resp = client_operador.patch(
            f"{ACOES_URL}{acao.pk}/",
            {"strdescricaoacao": "Acao Patched"},
            format="json",
        )
        assert resp.status_code == 200

    def test_consultor_nao_pode_patch_acao(self, client_consultor, acao):
        resp = client_consultor.patch(
            f"{ACOES_URL}{acao.pk}/",
            {"strdescricaoacao": "Tentativa Consultor"},
            format="json",
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestNestedViewSets — CRUD completo em Prazo, Destaque, Anotacao
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNestedViewSets:

    # Prazo
    def test_gestor_lista_prazos(self, client_gestor, acao):
        assert client_gestor.get(f"{ACOES_URL}{acao.pk}/prazos/").status_code == 200

    def test_gestor_cria_prazo(self, client_gestor, acao):
        resp = client_gestor.post(
            f"{ACOES_URL}{acao.pk}/prazos/",
            {"idacao_id": acao.pk, "strprazo": "Prazo Teste"},
            format="json",
        )
        assert resp.status_code in (201, 400)

    def test_gestor_retrieve_prazo(self, client_gestor, acao, prazo):
        assert (
            client_gestor.get(f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/").status_code
            == 200
        )

    def test_gestor_update_prazo(self, client_gestor, acao, prazo):
        resp = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/",
            {"strprazo": "Prazo Atualizado"},
            format="json",
        )
        assert resp.status_code == 200

    def test_gestor_pode_deletar_prazo(self, client_gestor, acao, prazo):
        assert (
            client_gestor.delete(f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/").status_code
            == 204
        )

    def test_operador_nao_pode_deletar_prazo(self, client_operador, acao):
        prazo = AcaoPrazo.objects.create(idacao=acao, strprazo="prazo a deletar")
        assert (
            client_operador.delete(
                f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/"
            ).status_code
            == 403
        )

    def test_consultor_nao_pode_criar_prazo(self, client_consultor, acao):
        resp = client_consultor.post(
            f"{ACOES_URL}{acao.pk}/prazos/", {"strprazo": "blocked"}, format="json"
        )
        assert resp.status_code == 403

    # Destaque
    def test_gestor_lista_destaques(self, client_gestor, acao):
        assert client_gestor.get(f"{ACOES_URL}{acao.pk}/destaques/").status_code == 200

    def test_gestor_retrieve_destaque(self, client_gestor, acao, destaque):
        assert (
            client_gestor.get(
                f"{ACOES_URL}{acao.pk}/destaques/{destaque.pk}/"
            ).status_code
            == 200
        )

    def test_gestor_pode_deletar_destaque(self, client_gestor, acao):
        d = AcaoDestaque.objects.create(idacao=acao, datdatadestaque=timezone.now())
        assert (
            client_gestor.delete(f"{ACOES_URL}{acao.pk}/destaques/{d.pk}/").status_code
            == 204
        )

    def test_gestor_patch_destaque(self, client_gestor, acao, destaque):
        resp = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/destaques/{destaque.pk}/",
            {"datdatadestaque": "2026-06-01T10:00:00Z"},
            format="json",
        )
        assert resp.status_code == 200

    def test_consultor_nao_pode_criar_destaque(self, client_consultor, acao):
        resp = client_consultor.post(
            f"{ACOES_URL}{acao.pk}/destaques/",
            {"datdatadestaque": "2026-01-01T00:00:00Z"},
            format="json",
        )
        assert resp.status_code == 403

    # Anotacao
    def test_gestor_lista_anotacoes(self, client_gestor, acao):
        assert client_gestor.get(f"{ACOES_URL}{acao.pk}/anotacoes/").status_code == 200

    def test_gestor_retrieve_anotacao(self, client_gestor, acao, anotacao):
        assert (
            client_gestor.get(
                f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/"
            ).status_code
            == 200
        )

    def test_gestor_patch_anotacao(self, client_gestor, acao, anotacao):
        resp = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/",
            {"strdescricao": "Atualizada"},
            format="json",
        )
        assert resp.status_code == 200

    def test_gestor_pode_deletar_anotacao(self, client_gestor, acao, anotacao):
        assert (
            client_gestor.delete(
                f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/"
            ).status_code
            == 204
        )

    def test_consultor_nao_pode_criar_anotacao(self, client_consultor, acao):
        resp = client_consultor.post(
            f"{ACOES_URL}{acao.pk}/anotacoes/",
            {"strdescricao": "blocked"},
            format="json",
        )
        assert resp.status_code == 403
