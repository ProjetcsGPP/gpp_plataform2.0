"""
GPP Plataform 2.0 — Ações PNGI Views

Autorização baseada exclusivamente em permissions efetivas.

As permissions são avaliadas pelo AuthorizationService através de
CanPermission. O mapeamento entre operação DRF e permission Django é:

  list / retrieve  → view_*
  create           → add_*
  update / PATCH   → change_*
  destroy          → delete_*

A atribuição das permissions aos usuários é materializada em
auth_user_user_permissions pelo permission_sync.py.

Nota: SecureQuerysetMixin NÃO é usado aqui pois Ações PNGI
não são recursos de tenant (independentes de órgão).

O controle de escopo ABAC das Ações, quando aplicável, é uma
camada posterior à autorização por permission.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import CanPermission
from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from .models import (
    AcaoAnotacaoAlinhamento,
    AcaoDestaque,
    AcaoPrazo,
    Acoes,
    Eixo,
    SituacaoAcao,
    VigenciaPNGI,
)
from .serializers import (
    AcaoAnotacaoAlinhamentoSerializer,
    AcaoDestaqueSerializer,
    AcaoPrazoSerializer,
    AcoesSerializer,
    EixoSerializer,
    SituacaoAcaoSerializer,
    VigenciaPNGISerializer,
)

# ---------------------------------------------------------------------------
# Mapeamento genérico de operação DRF → permission Django
# ---------------------------------------------------------------------------


class PermissionedViewSetMixin:
    """
    Seleciona a permission Django correspondente à operação DRF atual.

    O nome da permission é definido pela própria ViewSet em
    `permission_map`.

    Exemplo:

        permission_map = {
            "list": "view_acoes",
            "retrieve": "view_acoes",
            "create": "add_acoes",
            "update": "change_acoes",
            "partial_update": "change_acoes",
            "destroy": "delete_acoes",
        }

    A verificação efetiva é feita por CanPermission, que delega
    ao AuthorizationService.
    """

    permission_classes = [IsAuthenticated, CanPermission]
    permission_map: dict[str, str] = {}

    def get_permissions(self):
        self.required_permission = self.permission_map.get(self.action)
        return [permission() for permission in self.permission_classes]


# ---------------------------------------------------------------------------
# Parâmetro reutilizável para os 3 nested ViewSets
# ---------------------------------------------------------------------------


_ACAO_PK_PARAM = OpenApiParameter(
    name="acao_pk",
    type=int,
    location=OpenApiParameter.PATH,
    description="ID (idacao) da Ação PNGI pai",
)


# ---------------------------------------------------------------------------
# Ordenação segura e determinística
# ---------------------------------------------------------------------------


class DeterministicOrderingFilter(OrderingFilter):
    """Sanitiza a ordenação e acrescenta o desempate definido pela view."""

    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or [])
        tie_breaker = view.ordering_tie_breaker

        if not any(field.lstrip("-") == tie_breaker for field in ordering):
            ordering.append(tie_breaker)

        return ordering


# ---------------------------------------------------------------------------
# ViewSets de referência
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Ordenação composta por campos separados por vírgula. "
                    "Use o prefixo `-` para ordem decrescente. Campos permitidos: "
                    "`strdescricaoeixo`, `stralias`, `updated_by_name`, "
                    "`updated_at` e `ideixo`. O campo `ideixo` é acrescentado "
                    "automaticamente como desempate quando omitido. Exemplos: "
                    "`stralias`, `-updated_at` e "
                    "`strdescricaoeixo,-updated_at,ideixo`."
                ),
            )
        ]
    )
)
@tag_all_actions("3 - Ações PNGI")
class EixoViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Eixos temáticos do programa PNGI.

    Disponibiliza CRUD completo, com autorização por permissão efetiva e
    preenchimento automático dos campos de auditoria nas escritas.
    """

    queryset = Eixo.objects.all()
    serializer_class = EixoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strdescricaoeixo",
        "stralias",
        "updated_by_name",
        "updated_at",
        "ideixo",
    ]
    ordering = ["stralias", "ideixo"]
    ordering_tie_breaker = "ideixo"

    permission_map = {
        "list": "view_eixo",
        "retrieve": "view_eixo",
        "create": "add_eixo",
        "update": "change_eixo",
        "partial_update": "change_eixo",
        "destroy": "delete_eixo",
    }


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Ordenação composta por campos separados por vírgula. "
                    "Use o prefixo `-` para ordem decrescente. Campos permitidos: "
                    "`strdescricaosituacao`, `updated_by_name`, `updated_at` e "
                    "`idsituacaoacao`. O campo `idsituacaoacao` é acrescentado "
                    "automaticamente como desempate quando omitido. Exemplos: "
                    "`strdescricaosituacao`, `-updated_at` e "
                    "`strdescricaosituacao,-updated_at,idsituacaoacao`."
                ),
            )
        ]
    )
)
@tag_all_actions("3 - Ações PNGI")
class SituacaoAcaoViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Situações possíveis de uma Ação PNGI.

    Disponibiliza CRUD completo, com autorização por permissão efetiva,
    auditoria automática e ordenação segura.
    """

    queryset = SituacaoAcao.objects.all()
    serializer_class = SituacaoAcaoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strdescricaosituacao",
        "updated_by_name",
        "updated_at",
        "idsituacaoacao",
    ]
    ordering = ["strdescricaosituacao", "idsituacaoacao"]
    ordering_tie_breaker = "idsituacaoacao"

    permission_map = {
        "list": "view_situacaoacao",
        "retrieve": "view_situacaoacao",
        "create": "add_situacaoacao",
        "update": "change_situacaoacao",
        "partial_update": "change_situacaoacao",
        "destroy": "delete_situacaoacao",
    }


# ---------------------------------------------------------------------------
# VigenciaPNGIViewSet
# ---------------------------------------------------------------------------


@tag_all_actions("3 - Ações PNGI")
class VigenciaPNGIViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Vigências do programa PNGI.

    A autorização de cada operação é determinada pela permission
    efetiva correspondente:
        view_vigenciapngi
        add_vigenciapngi
        change_vigenciapngi
        delete_vigenciapngi
    """

    queryset = VigenciaPNGI.objects.all()
    serializer_class = VigenciaPNGISerializer

    permission_map = {
        "list": "view_vigenciapngi",
        "retrieve": "view_vigenciapngi",
        "create": "add_vigenciapngi",
        "update": "change_vigenciapngi",
        "partial_update": "change_vigenciapngi",
        "destroy": "delete_vigenciapngi",
    }


# ---------------------------------------------------------------------------
# AcaoViewSet
# ---------------------------------------------------------------------------


@tag_all_actions("3 - Ações PNGI")
class AcaoViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Ações PNGI — entidade principal.

    Ações são independentes de órgão (iniciativas do programa PNGI).
    NÃO herda SecureQuerysetMixin.

    A autorização de cada operação é determinada pela permission
    efetiva correspondente:

        view_acoes
        add_acoes
        change_acoes
        delete_acoes

    O eventual controle ABAC sobre quais Ações um usuário pode
    consultar ou alterar é uma camada adicional e não é tratado
    neste mapeamento de permissions.
    """

    queryset = Acoes.objects.select_related(
        "idvigenciapngi",
        "idtipoentravealerta",
        "idsituacaoacao",
        "ideixo",
    )
    serializer_class = AcoesSerializer

    permission_map = {
        "list": "view_acoes",
        "retrieve": "view_acoes",
        "create": "add_acoes",
        "update": "change_acoes",
        "partial_update": "change_acoes",
        "destroy": "delete_acoes",
    }


# ---------------------------------------------------------------------------
# ViewSets nested em Ação
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(parameters=[_ACAO_PK_PARAM]),
    create=extend_schema(parameters=[_ACAO_PK_PARAM]),
    retrieve=extend_schema(parameters=[_ACAO_PK_PARAM]),
    update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    partial_update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    destroy=extend_schema(parameters=[_ACAO_PK_PARAM]),
)
@tag_all_actions("3 - Ações PNGI")
class AcaoPrazoViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Prazos de uma Ação PNGI.

    Filtrado pelo idacao passado na URL.
    """

    serializer_class = AcaoPrazoSerializer

    # Usado pelo drf-spectacular para introspecção.
    queryset = AcaoPrazo.objects.all()

    permission_map = {
        "list": "view_acaoprazo",
        "retrieve": "view_acaoprazo",
        "create": "add_acaoprazo",
        "update": "change_acaoprazo",
        "partial_update": "change_acaoprazo",
        "destroy": "delete_acaoprazo",
    }

    def get_queryset(self):
        return AcaoPrazo.objects.filter(idacao_id=self.kwargs["acao_pk"])


@extend_schema_view(
    list=extend_schema(parameters=[_ACAO_PK_PARAM]),
    create=extend_schema(parameters=[_ACAO_PK_PARAM]),
    retrieve=extend_schema(parameters=[_ACAO_PK_PARAM]),
    update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    partial_update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    destroy=extend_schema(parameters=[_ACAO_PK_PARAM]),
)
@tag_all_actions("3 - Ações PNGI")
class AcaoDestaqueViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Destaques de uma Ação PNGI.

    Filtrado pelo idacao passado na URL.
    """

    serializer_class = AcaoDestaqueSerializer

    # Usado pelo drf-spectacular para introspecção.
    queryset = AcaoDestaque.objects.all()

    permission_map = {
        "list": "view_acaodestaque",
        "retrieve": "view_acaodestaque",
        "create": "add_acaodestaque",
        "update": "change_acaodestaque",
        "partial_update": "change_acaodestaque",
        "destroy": "delete_acaodestaque",
    }

    def get_queryset(self):
        return AcaoDestaque.objects.filter(idacao_id=self.kwargs["acao_pk"])


@extend_schema_view(
    list=extend_schema(parameters=[_ACAO_PK_PARAM]),
    create=extend_schema(parameters=[_ACAO_PK_PARAM]),
    retrieve=extend_schema(parameters=[_ACAO_PK_PARAM]),
    update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    partial_update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    destroy=extend_schema(parameters=[_ACAO_PK_PARAM]),
)
@tag_all_actions("3 - Ações PNGI")
class AcaoAnotacaoViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    """
    Anotações de alinhamento de uma Ação PNGI.

    Filtrado pelo idacao passado na URL.
    """

    serializer_class = AcaoAnotacaoAlinhamentoSerializer

    # Usado pelo drf-spectacular para introspecção.
    queryset = AcaoAnotacaoAlinhamento.objects.all()

    permission_map = {
        "list": "view_acaoanotacaoalinhamento",
        "retrieve": "view_acaoanotacaoalinhamento",
        "create": "add_acaoanotacaoalinhamento",
        "update": "change_acaoanotacaoalinhamento",
        "partial_update": "change_acaoanotacaoalinhamento",
        "destroy": "delete_acaoanotacaoalinhamento",
    }

    def get_queryset(self):
        return AcaoAnotacaoAlinhamento.objects.filter(idacao_id=self.kwargs["acao_pk"])
