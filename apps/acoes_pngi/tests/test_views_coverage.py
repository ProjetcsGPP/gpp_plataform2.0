"""
apps/acoes_pngi/tests/test_views_coverage.py

Testes de cobertura para apps/acoes_pngi/views.py.

Objetivo:


Cobrir a implementação atual dos ViewSets de Ações PNGI,
baseada exclusivamente em permissions efetivas.


A autorização funcional por perfil é validada em:


apps/acoes_pngi/tests/test_permissions.py


Este arquivo concentra-se em:


- PermissionedViewSetMixin.get_permissions()
- permission_map de cada ViewSet
- operações dos ViewSets principais
- operações dos ViewSets nested
- get_queryset() dos ViewSets nested


Não são testados aqui:


- _check_roles
- matrizes de roles
- CONSULTOR_PNGI
- auth_user_groups como fonte de autorização
- regras ABAC


Esses elementos não fazem parte da implementação atual de views.py.
"""

import pytest
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated

from apps.acoes_pngi.models import AcaoAnotacaoAlinhamento, AcaoDestaque, AcaoPrazo
from apps.acoes_pngi.views import (
    AcaoAnotacaoViewSet,
    AcaoDestaqueViewSet,
    AcaoPrazoViewSet,
    AcaoViewSet,
    EixoViewSet,
    PermissionedViewSetMixin,
    SituacaoAcaoViewSet,
    VigenciaPNGIViewSet,
)

# ---------------------------------------------------------------------------

# URLs

# ---------------------------------------------------------------------------

ACOES_URL = "/api/acoes-pngi/acoes/"
VIGENCIAS_URL = "/api/acoes-pngi/vigencias/"
EIXOS_URL = "/api/acoes-pngi/eixos/"
SITUACOES_URL = "/api/acoes-pngi/situacoes/"

# ---------------------------------------------------------------------------

# PermissionedViewSetMixin

# ---------------------------------------------------------------------------


class TestPermissionedViewSetMixin:
    """
    Verifica o comportamento genérico do PermissionedViewSetMixin.


    A lógica efetiva de autorização é exercida por CanPermission e
    AuthorizationService nos testes funcionais. Aqui verificamos apenas
    se a operação DRF seleciona a permission correta.
    """

    @pytest.mark.parametrize(
        ("viewset_class", "expected_map"),
        [
            (
                EixoViewSet,
                {
                    "list": "view_eixo",
                    "retrieve": "view_eixo",
                },
            ),
            (
                SituacaoAcaoViewSet,
                {
                    "list": "view_situacaoacao",
                    "retrieve": "view_situacaoacao",
                },
            ),
            (
                VigenciaPNGIViewSet,
                {
                    "list": "view_vigenciapngi",
                    "retrieve": "view_vigenciapngi",
                    "create": "add_vigenciapngi",
                    "update": "change_vigenciapngi",
                    "partial_update": "change_vigenciapngi",
                    "destroy": "delete_vigenciapngi",
                },
            ),
            (
                AcaoViewSet,
                {
                    "list": "view_acoes",
                    "retrieve": "view_acoes",
                    "create": "add_acoes",
                    "update": "change_acoes",
                    "partial_update": "change_acoes",
                    "destroy": "delete_acoes",
                },
            ),
            (
                AcaoPrazoViewSet,
                {
                    "list": "view_acaoprazo",
                    "retrieve": "view_acaoprazo",
                    "create": "add_acaoprazo",
                    "update": "change_acaoprazo",
                    "partial_update": "change_acaoprazo",
                    "destroy": "delete_acaoprazo",
                },
            ),
            (
                AcaoDestaqueViewSet,
                {
                    "list": "view_acaodestaque",
                    "retrieve": "view_acaodestaque",
                    "create": "add_acaodestaque",
                    "update": "change_acaodestaque",
                    "partial_update": "change_acaodestaque",
                    "destroy": "delete_acaodestaque",
                },
            ),
            (
                AcaoAnotacaoViewSet,
                {
                    "list": "view_acaoanotacaoalinhamento",
                    "retrieve": "view_acaoanotacaoalinhamento",
                    "create": "add_acaoanotacaoalinhamento",
                    "update": "change_acaoanotacaoalinhamento",
                    "partial_update": "change_acaoanotacaoalinhamento",
                    "destroy": "delete_acaoanotacaoalinhamento",
                },
            ),
        ],
    )
    def test_permission_map(self, viewset_class, expected_map):
        assert viewset_class.permission_map == expected_map

    @pytest.mark.parametrize(
        ("viewset_class", "action", "expected_permission"),
        [
            (EixoViewSet, "list", "view_eixo"),
            (EixoViewSet, "retrieve", "view_eixo"),
            (SituacaoAcaoViewSet, "list", "view_situacaoacao"),
            (SituacaoAcaoViewSet, "retrieve", "view_situacaoacao"),
            (VigenciaPNGIViewSet, "list", "view_vigenciapngi"),
            (VigenciaPNGIViewSet, "retrieve", "view_vigenciapngi"),
            (VigenciaPNGIViewSet, "create", "add_vigenciapngi"),
            (VigenciaPNGIViewSet, "update", "change_vigenciapngi"),
            (VigenciaPNGIViewSet, "partial_update", "change_vigenciapngi"),
            (VigenciaPNGIViewSet, "destroy", "delete_vigenciapngi"),
            (AcaoViewSet, "list", "view_acoes"),
            (AcaoViewSet, "retrieve", "view_acoes"),
            (AcaoViewSet, "create", "add_acoes"),
            (AcaoViewSet, "update", "change_acoes"),
            (AcaoViewSet, "partial_update", "change_acoes"),
            (AcaoViewSet, "destroy", "delete_acoes"),
            (AcaoPrazoViewSet, "list", "view_acaoprazo"),
            (AcaoPrazoViewSet, "retrieve", "view_acaoprazo"),
            (AcaoPrazoViewSet, "create", "add_acaoprazo"),
            (AcaoPrazoViewSet, "update", "change_acaoprazo"),
            (AcaoPrazoViewSet, "partial_update", "change_acaoprazo"),
            (AcaoPrazoViewSet, "destroy", "delete_acaoprazo"),
            (AcaoDestaqueViewSet, "list", "view_acaodestaque"),
            (AcaoDestaqueViewSet, "retrieve", "view_acaodestaque"),
            (AcaoDestaqueViewSet, "create", "add_acaodestaque"),
            (AcaoDestaqueViewSet, "update", "change_acaodestaque"),
            (AcaoDestaqueViewSet, "partial_update", "change_acaodestaque"),
            (AcaoDestaqueViewSet, "destroy", "delete_acaodestaque"),
            (
                AcaoAnotacaoViewSet,
                "list",
                "view_acaoanotacaoalinhamento",
            ),
            (
                AcaoAnotacaoViewSet,
                "retrieve",
                "view_acaoanotacaoalinhamento",
            ),
            (
                AcaoAnotacaoViewSet,
                "create",
                "add_acaoanotacaoalinhamento",
            ),
            (
                AcaoAnotacaoViewSet,
                "update",
                "change_acaoanotacaoalinhamento",
            ),
            (
                AcaoAnotacaoViewSet,
                "partial_update",
                "change_acaoanotacaoalinhamento",
            ),
            (
                AcaoAnotacaoViewSet,
                "destroy",
                "delete_acaoanotacaoalinhamento",
            ),
        ],
    )
    def test_get_permissions_define_required_permission(
        self,
        viewset_class,
        action,
        expected_permission,
    ):
        view = viewset_class()
        view.action = action

        permissions = view.get_permissions()

        assert view.required_permission == expected_permission
        assert len(permissions) == 2
        assert isinstance(permissions[0], IsAuthenticated)

    def test_mixin_get_permissions_usa_none_para_acao_nao_mapeada(self):
        view = PermissionedViewSetMixin()
        view.action = "acao_nao_mapeada"

        permissions = view.get_permissions()

        assert view.required_permission is None
        assert len(permissions) == 2
        assert isinstance(permissions[0], IsAuthenticated)


# ---------------------------------------------------------------------------

# EixoViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEixoViewSet:

    def test_list(self, client_gestor, eixo):
        response = client_gestor.get(EIXOS_URL)

        assert response.status_code == 200

    def test_retrieve(self, client_gestor, eixo):
        response = client_gestor.get(f"{EIXOS_URL}{eixo.pk}/")

        assert response.status_code == 200


# ---------------------------------------------------------------------------

# SituacaoAcaoViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSituacaoAcaoViewSet:

    def test_list(self, client_gestor, situacao):
        response = client_gestor.get(SITUACOES_URL)

        assert response.status_code == 200

    def test_retrieve(self, client_gestor, situacao):
        response = client_gestor.get(f"{SITUACOES_URL}{situacao.pk}/")

        assert response.status_code == 200


# ---------------------------------------------------------------------------

# VigenciaPNGIViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVigenciaPNGIViewSet:

    def test_list(self, client_gestor):
        response = client_gestor.get(VIGENCIAS_URL)

        assert response.status_code == 200

    def test_retrieve(self, client_gestor, vigencia):
        response = client_gestor.get(f"{VIGENCIAS_URL}{vigencia.pk}/")

        assert response.status_code == 200

    def test_create(self, client_gestor):
        response = client_gestor.post(
            VIGENCIAS_URL,
            {
                "strdescricao": "Vigência cobertura",
                "datiniciovigencia": timezone.localdate().isoformat(),
            },
            format="json",
        )

        assert response.status_code == 201

    def test_update(self, client_gestor, vigencia):
        response = client_gestor.put(
            f"{VIGENCIAS_URL}{vigencia.pk}/",
            {
                "strdescricao": "Vigência atualizada",
                "datiniciovigencia": timezone.localdate().isoformat(),
            },
            format="json",
        )

        assert response.status_code == 200

    def test_partial_update(self, client_gestor, vigencia):
        response = client_gestor.patch(
            f"{VIGENCIAS_URL}{vigencia.pk}/",
            {"strdescricao": "Vigência parcial"},
            format="json",
        )

        assert response.status_code == 200

    def test_destroy(self, client_gestor, vigencia):
        response = client_gestor.delete(f"{VIGENCIAS_URL}{vigencia.pk}/")

        assert response.status_code == 204


# ---------------------------------------------------------------------------

# AcaoViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcaoViewSet:

    def test_list(self, client_gestor):
        response = client_gestor.get(ACOES_URL)

        assert response.status_code == 200

    def test_retrieve(self, client_gestor, acao):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/")

        assert response.status_code == 200

    def test_create(self, client_gestor, vigencia):
        response = client_gestor.post(
            ACOES_URL,
            {
                "strapelido": "ACAO-COVERAGE-CREATE",
                "strdescricaoacao": "Ação criada no teste de cobertura",
                "strdescricaoentrega": "Entrega da ação",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )

        assert response.status_code == 201

    def test_update(self, client_gestor, acao, vigencia):
        response = client_gestor.put(
            f"{ACOES_URL}{acao.pk}/",
            {
                "strapelido": "ACAO-COVERAGE-UPDATE",
                "strdescricaoacao": "Ação atualizada",
                "strdescricaoentrega": "Entrega atualizada",
                "idvigenciapngi_id": vigencia.pk,
            },
            format="json",
        )

        assert response.status_code == 200

    def test_partial_update(self, client_gestor, acao):
        response = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/",
            {"strdescricaoacao": "Ação parcialmente atualizada"},
            format="json",
        )

        assert response.status_code == 200

    def test_destroy(self, client_gestor, acao):
        response = client_gestor.delete(f"{ACOES_URL}{acao.pk}/")

        assert response.status_code == 204


# ---------------------------------------------------------------------------

# AcaoPrazoViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcaoPrazoViewSet:

    def test_list(self, client_gestor, acao, prazo):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/prazos/")

        assert response.status_code == 200
        assert response.data

    def test_retrieve(self, client_gestor, acao, prazo):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/")

        assert response.status_code == 200

    def test_create(self, client_gestor, acao):
        response = client_gestor.post(
            f"{ACOES_URL}{acao.pk}/prazos/",
            {
                "idacao_id": acao.pk,
                "strprazo": "Prazo criado no teste",
            },
            format="json",
        )

        assert response.status_code == 201

    def test_update(self, client_gestor, acao, prazo):
        response = client_gestor.put(
            f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/",
            {
                "idacao_id": acao.pk,
                "strprazo": "Prazo atualizado integralmente",
            },
            format="json",
        )

        assert response.status_code == 200

    def test_partial_update(self, client_gestor, acao, prazo):
        response = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/",
            {"strprazo": "Prazo atualizado"},
            format="json",
        )

        assert response.status_code == 200

    def test_destroy(self, client_gestor, acao, prazo):
        response = client_gestor.delete(f"{ACOES_URL}{acao.pk}/prazos/{prazo.pk}/")

        assert response.status_code == 204

    def test_get_queryset_filtra_por_acao(self, acao, prazo):
        view = AcaoPrazoViewSet()
        view.kwargs = {"acao_pk": acao.pk}

        queryset = view.get_queryset()

        assert list(queryset.values_list("pk", flat=True)) == [prazo.pk]
        assert isinstance(queryset.first(), AcaoPrazo)


# ---------------------------------------------------------------------------

# AcaoDestaqueViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcaoDestaqueViewSet:

    def test_list(self, client_gestor, acao, destaque):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/destaques/")

        assert response.status_code == 200
        assert response.data

    def test_retrieve(self, client_gestor, acao, destaque):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/destaques/{destaque.pk}/")

        assert response.status_code == 200

    def test_create(self, client_gestor, acao):
        response = client_gestor.post(
            f"{ACOES_URL}{acao.pk}/destaques/",
            {
                "idacao_id": acao.pk,
                "datdatadestaque": timezone.now().isoformat(),
            },
            format="json",
        )

        assert response.status_code == 201

    def test_update(self, client_gestor, acao, destaque):
        response = client_gestor.put(
            f"{ACOES_URL}{acao.pk}/destaques/{destaque.pk}/",
            {
                "idacao_id": acao.pk,
                "datdatadestaque": timezone.now().isoformat(),
            },
            format="json",
        )

        assert response.status_code == 200

    def test_partial_update(self, client_gestor, acao, destaque):
        response = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/destaques/{destaque.pk}/",
            {"datdatadestaque": timezone.now().isoformat()},
            format="json",
        )

        assert response.status_code == 200

    def test_destroy(self, client_gestor, acao, destaque):
        response = client_gestor.delete(
            f"{ACOES_URL}{acao.pk}/destaques/{destaque.pk}/"
        )

        assert response.status_code == 204

    def test_get_queryset_filtra_por_acao(self, acao, destaque):
        view = AcaoDestaqueViewSet()
        view.kwargs = {"acao_pk": acao.pk}

        queryset = view.get_queryset()

        assert list(queryset.values_list("pk", flat=True)) == [destaque.pk]
        assert isinstance(queryset.first(), AcaoDestaque)


# ---------------------------------------------------------------------------

# AcaoAnotacaoViewSet

# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcaoAnotacaoViewSet:

    def test_list(self, client_gestor, acao, anotacao):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/anotacoes/")

        assert response.status_code == 200
        assert response.data

    def test_retrieve(self, client_gestor, acao, anotacao):
        response = client_gestor.get(f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/")

        assert response.status_code == 200

    def test_create(self, client_gestor, acao, tipo_anotacao):
        response = client_gestor.post(
            f"{ACOES_URL}{acao.pk}/anotacoes/",
            {
                "idacao_id": acao.pk,
                "idtipoanotacaoalinhamento_id": tipo_anotacao.pk,
                "strdescricao": "Anotação criada no teste",
            },
            format="json",
        )

        assert response.status_code == 201

    def test_update(self, client_gestor, acao, anotacao, tipo_anotacao):
        response = client_gestor.put(
            f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/",
            {
                "idacao_id": acao.pk,
                "idtipoanotacaoalinhamento_id": tipo_anotacao.pk,
                "strdescricao": "Anotação atualizada integralmente",
            },
            format="json",
        )

        assert response.status_code == 200

    def test_partial_update(self, client_gestor, acao, anotacao):
        response = client_gestor.patch(
            f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/",
            {"strdescricao": "Anotação atualizada"},
            format="json",
        )

        assert response.status_code == 200

    def test_destroy(self, client_gestor, acao, anotacao):
        response = client_gestor.delete(
            f"{ACOES_URL}{acao.pk}/anotacoes/{anotacao.pk}/"
        )

        assert response.status_code == 204

    def test_get_queryset_filtra_por_acao(self, acao, anotacao):
        view = AcaoAnotacaoViewSet()
        view.kwargs = {"acao_pk": acao.pk}

        queryset = view.get_queryset()

        assert list(queryset.values_list("pk", flat=True)) == [anotacao.pk]
        assert isinstance(queryset.first(), AcaoAnotacaoAlinhamento)
