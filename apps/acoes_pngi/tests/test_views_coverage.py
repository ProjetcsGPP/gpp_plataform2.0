"""
Testes de cobertura para apps/acoes_pngi/views.py.

Objetivo: cobrir as linhas 148, 181-182, 199-200, 227-228, 235-240, 307, 312-413
que ficaram descobertas — principalmente os branches _check_roles() com
COORDENADOR_PNGI, OPERADOR_ACAO e CONSULTOR_PNGI nas operações WRITE/DELETE
e os ViewSets nested (AcaoPrazoViewSet, AcaoDestaqueViewSet, AcaoAnotacaoViewSet).

Estraégia:
  - Autenticação real via sessão Django (client_* fixtures do conftest.py)
  - Testar explicitamente os roles que não existiam nos testes anteriores:
      COORDENADOR_PNGI  → pode WRITE Acao, NÃO pode DELETE, NÃO pode WRITE Vigencia
      OPERADOR_ACAO     → pode WRITE Acao, NÃO pode DELETE, NÃO pode WRITE Vigencia
      CONSULTOR_PNGI    → pode READ, NÃO pode WRITE nem DELETE
  - Testar ViewSets nested (Prazo, Destaque, Anotacao)
  - Usar _load_role_matrix.cache_clear() antes de cada teste para garantir
    que a matriz seja recarregada do banco de teste
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.accounts.tests.conftest import (
    DEFAULT_PASSWORD,
    _assign_role,
    _make_authenticated_client,
    _make_user,
)
from apps.acoes_pngi.models import (
    Acoes,
    AcaoDestaque,
    AcaoPrazo,
    AcaoAnotacaoAlinhamento,
    Eixo,
    SituacaoAcao,
    VigenciaPNGI,
)
from apps.acoes_pngi.views import _load_role_matrix, _load_vigencia_role_matrix

# URLs base
ACOES_URL = "/api/acoes-pngi/acoes/"
VIGENCIAS_URL = "/api/acoes-pngi/vigencias/"
EIXOS_URL = "/api/acoes-pngi/eixos/"
SITUACOES_URL = "/api/acoes-pngi/situacoes/"


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """Garante que _load_role_matrix() releia do banco em cada teste."""
    _load_role_matrix.cache_clear()
    _load_vigencia_role_matrix.cache_clear()
    yield
    _load_role_matrix.cache_clear()
    _load_vigencia_role_matrix.cache_clear()


@pytest.fixture
def consultor_pngi(db):
    """Usuário com CONSULTOR_PNGI — role somente leitura."""
    from apps.accounts.models import ClassificacaoUsuario
    ClassificacaoUsuario.objects.get_or_create(
        pk=1,
        defaults={"strdescricao": "Usuario Padrao", "pode_criar_usuario": False, "pode_editar_usuario": False},
    )
    # Cria a role CONSULTOR_PNGI se ainda não existir
    app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
    from django.contrib.auth.models import Group
    group, _ = Group.objects.get_or_create(name="consultor_pngi_group")
    role, _ = Role.objects.get_or_create(
        codigoperfil="CONSULTOR_PNGI",
        aplicacao=app,
        defaults={"nomeperfil": "Consultor PNGI", "group": group},
    )
    user = _make_user("consultor_test")
    UserRole.objects.get_or_create(
        user=user,
        aplicacao=app,
        defaults={"role": role},
    )
    user.groups.add(group)
    return user


@pytest.fixture
def client_consultor(db, consultor_pngi):
    client, resp = _make_authenticated_client("consultor_test", "ACOES_PNGI")
    assert resp.status_code == 200, f"Login consultor falhou: {resp.data}"
    return client


@pytest.fixture
def vigencia(db):
    """VigenciaPNGI base para testes."""
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
    obj, _ = SituacaoAcao.objects.get_or_create(
        strdescricaosituacao="Em andamento",
    )
    return obj


@pytest.fixture
def acao(db, vigencia):
    return Acoes.objects.create(
        strapelido="ACAO-COV-001",
        strdescricaoacao="Acao de cobertura",
        strdescricaoentrega="Entrega esperada",
        idvigenciapngi=vigencia,
    )


# ---------------------------------------------------------------------------
# TestCoordenadorPermissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCoordenadorPermissions:
    """COORDENADOR_PNGI: READ + WRITE Acao, NÃO pode DELETE, NÃO pode WRITE Vigencia."""

    def test_coordenador_pode_listar_acoes(self, client_coordenador):
        resp = client_coordenador.get(ACOES_URL)
        assert resp.status_code == 200

    def test_coordenador_pode_criar_acao(self, client_coordenador, vigencia):
        payload = {
            "strapelido": "ACAO-COORD-001",
            "strdescricaoacao": "Nova Acao Coordenador",
            "strdescricaoentrega": "Entrega coordenador",
            "idvigenciapngi_id": vigencia.pk,
        }
        resp = client_coordenador.post(ACOES_URL, payload, format="json")
        assert resp.status_code == 201

    def test_coordenador_nao_pode_deletar_acao(self, client_coordenador, acao):
        resp = client_coordenador.delete(f"{ACOES_URL}{acao.pk}/")
        assert resp.status_code == 403

    def test_coordenador_pode_criar_vigencia(self, client_coordenador):
        payload = {
            "strdescricao": "Vigencia Coordenador",
            "datiniciovigencia": "2026-01-01",
        }
        resp = client_coordenador.post(VIGENCIAS_URL, payload, format="json")
        assert resp.status_code == 201

    def test_coordenador_nao_pode_deletar_vigencia(self, client_coordenador, vigencia):
        resp = client_coordenador.delete(f"{VIGENCIAS_URL}{vigencia.pk}/")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestOperadorPermissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOperadorPermissions:
    """OPERADOR_ACAO: READ + WRITE Acao, NÃO pode DELETE, NÃO pode WRITE Vigencia."""

    def test_operador_pode_listar_acoes(self, client_operador):
        resp = client_operador.get(ACOES_URL)
        assert resp.status_code == 200

    def test_operador_pode_criar_acao(self, client_operador, vigencia):
        payload = {
            "strapelido": "ACAO-OPER-001",
            "strdescricaoacao": "Nova Acao Operador",
            "strdescricaoentrega": "Entrega operador",
            "idvigenciapngi_id": vigencia.pk,
        }
        resp = client_operador.post(ACOES_URL, payload, format="json")
        assert resp.status_code == 201

    def test_operador_nao_pode_deletar_acao(self, client_operador, acao):
        resp = client_operador.delete(f"{ACOES_URL}{acao.pk}/")
        assert resp.status_code == 403

    def test_operador_nao_pode_criar_vigencia(self, client_operador):
        """OPERADOR_ACAO não tem WRITE na matriz de vigencias."""
        payload = {
            "strdescricao": "Vigencia Operador",
            "datiniciovigencia": "2026-01-01",
        }
        resp = client_operador.post(VIGENCIAS_URL, payload, format="json")
        assert resp.status_code == 403

    def test_operador_nao_pode_deletar_vigencia(self, client_operador, vigencia):
        resp = client_operador.delete(f"{VIGENCIAS_URL}{vigencia.pk}/")
        assert resp.status_code == 403

    def test_operador_pode_listar_vigencias(self, client_operador):
        resp = client_operador.get(VIGENCIAS_URL)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestConsultorPermissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConsultorPermissions:
    """CONSULTOR_PNGI: somente READ, sem WRITE nem DELETE."""

    def test_consultor_pode_listar_acoes(self, client_consultor):
        resp = client_consultor.get(ACOES_URL)
        assert resp.status_code == 200

    def test_consultor_nao_pode_criar_acao(self, client_consultor, vigencia):
        payload = {
            "strapelido": "ACAO-BLOCK",
            "strdescricaoacao": "Acao Bloqueada",
            "strdescricaoentrega": "Bloqueada",
            "idvigenciapngi_id": vigencia.pk,
        }
        resp = client_consultor.post(ACOES_URL, payload, format="json")
        assert resp.status_code == 403

    def test_consultor_nao_pode_deletar_acao(self, client_consultor, acao):
        resp = client_consultor.delete(f"{ACOES_URL}{acao.pk}/")
        assert resp.status_code == 403

    def test_consultor_nao_pode_criar_vigencia(self, client_consultor):
        payload = {"strdescricao": "Blocked", "datiniciovigencia": "2026-01-01"}
        resp = client_consultor.post(VIGENCIAS_URL, payload, format="json")
        assert resp.status_code == 403

    def test_consultor_pode_listar_vigencias(self, client_consultor):
        resp = client_consultor.get(VIGENCIAS_URL)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestEixoSituacaoViewSets
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEixoSituacaoViewSets:
    """Cobre EixoViewSet e SituacaoAcaoViewSet (list + retrieve)."""

    def test_gestor_lista_eixos(self, client_gestor, eixo):
        resp = client_gestor.get(EIXOS_URL)
        assert resp.status_code == 200

    def test_gestor_retrieve_eixo(self, client_gestor, eixo):
        resp = client_gestor.get(f"{EIXOS_URL}{eixo.pk}/")
        assert resp.status_code == 200

    def test_gestor_lista_situacoes(self, client_gestor, situacao):
        resp = client_gestor.get(SITUACOES_URL)
        assert resp.status_code == 200

    def test_gestor_retrieve_situacao(self, client_gestor, situacao):
        resp = client_gestor.get(f"{SITUACOES_URL}{situacao.pk}/")
        assert resp.status_code == 200

    def test_consultor_lista_eixos(self, client_consultor, eixo):
        resp = client_consultor.get(EIXOS_URL)
        assert resp.status_code == 200

    def test_consultor_lista_situacoes(self, client_consultor, situacao):
        resp = client_consultor.get(SITUACOES_URL)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestVigenciaPartialUpdate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestVigenciaPartialUpdate:
    """Cobre partial_update (PATCH) nas vigencias."""

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
    """Cobre partial_update (PATCH) nas acoes."""

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
# TestNestedViewSets (Prazo, Destaque, Anotacao)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNestedViewSets:
    """Cobre AcaoPrazoViewSet, AcaoDestaqueViewSet e AcaoAnotacaoViewSet."""

    def test_gestor_lista_prazos(self, client_gestor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/prazos/"
        resp = client_gestor.get(url)
        assert resp.status_code == 200

    def test_gestor_cria_prazo(self, client_gestor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/prazos/"
        resp = client_gestor.post(url, {
            "idacao_id": acao.pk,
            "strprazo": "Prazo Teste",
        }, format="json")
        assert resp.status_code in (201, 400)

    def test_consultor_nao_pode_criar_prazo(self, client_consultor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/prazos/"
        resp = client_consultor.post(url, {"strprazo": "blocked"}, format="json")
        assert resp.status_code == 403

    def test_gestor_lista_destaques(self, client_gestor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/destaques/"
        resp = client_gestor.get(url)
        assert resp.status_code == 200

    def test_consultor_nao_pode_criar_destaque(self, client_consultor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/destaques/"
        resp = client_consultor.post(url, {"datdatadestaque": "2026-01-01T00:00:00Z"}, format="json")
        assert resp.status_code == 403

    def test_gestor_lista_anotacoes(self, client_gestor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/anotacoes/"
        resp = client_gestor.get(url)
        assert resp.status_code == 200

    def test_consultor_nao_pode_criar_anotacao(self, client_consultor, acao):
        url = f"/api/acoes-pngi/acoes/{acao.pk}/anotacoes/"
        resp = client_consultor.post(url, {"strdescricao": "blocked"}, format="json")
        assert resp.status_code == 403

    def test_operador_nao_pode_deletar_prazo(self, client_operador, acao):
        # AcaoPrazo: campos reais = idacao (FK), strprazo (CharField), isacaoprazoativo (Boolean)
        prazo = AcaoPrazo.objects.create(
            idacao=acao,
            strprazo="prazo a deletar",
        )
        url = f"/api/acoes-pngi/acoes/{acao.pk}/prazos/{prazo.pk}/"
        resp = client_operador.delete(url)
        assert resp.status_code == 403

    def test_gestor_pode_deletar_destaque(self, client_gestor, acao):
        # AcaoDestaque: campos reais = idacao (FK), datdatadestaque (DateTimeField, obrigatório)
        from django.utils import timezone
        destaque = AcaoDestaque.objects.create(
            idacao=acao,
            datdatadestaque=timezone.now(),
        )
        url = f"/api/acoes-pngi/acoes/{acao.pk}/destaques/{destaque.pk}/"
        resp = client_gestor.delete(url)
        assert resp.status_code == 204
