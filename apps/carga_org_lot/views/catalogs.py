"""Views de catalogs da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..models import (
    Patriarca,
    ProcessoCargaInicial,
    StatusCarga,
    StatusImportacaoLocal,
    StatusProgresso,
    TipoCarga,
)
from ..serializers import (
    PatriarcaSerializer,
    ProcessoCargaInicialSerializer,
    StatusCargaSerializer,
    StatusProgressoSerializer,
    TipoCargaSerializer,
)
from ..services.organograma import ORGANOGRAMA_TYPE_ID
from .base import (
    DeterministicOrderingFilter,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    spreadsheet_download_response,
)


@tag_all_actions("4 - Carga Org/Lot")
class PatriarcaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = Patriarca.objects.select_related("idstatusprogresso").all()
    serializer_class = PatriarcaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strsiglapatriarca",
        "strnome",
        "datcriacao",
        "datalteracao",
        "idpatriarca",
    ]
    ordering = ["strsiglapatriarca", "idpatriarca"]
    ordering_tie_breaker = "idpatriarca"
    permission_map = {
        "list": "view_patriarca",
        "retrieve": "view_patriarca",
        "create": "add_patriarca",
        "update": "change_patriarca",
        "partial_update": "change_patriarca",
        "destroy": "delete_patriarca",
        "download_organograma": "view_importacaoplanilha",
    }

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        },
        description=(
            "Baixa a planilha da importação de organograma mais recente "
            "do patriarca."
        ),
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="organograma/download",
    )
    def download_organograma(self, request, *args, **kwargs):
        patriarca = self.get_object()
        importacao = (
            patriarca.importacoes.filter(idtipocarga_id=ORGANOGRAMA_TYPE_ID)
            .exclude(strstatusimportacao=StatusImportacaoLocal.REJEITADA)
            .order_by("-datimportacao", "-idimportacaoplanilha")
            .first()
        )
        if importacao is None:
            raise NotFound(
                "O patriarca ainda não possui uma planilha de organograma importada."
            )
        return spreadsheet_download_response(importacao)


class BaseCatalogViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    viewsets.ModelViewSet,
):
    pagination_class = None


@tag_all_actions("4 - Carga Org/Lot")
class StatusCargaViewSet(BaseCatalogViewSet):
    queryset = StatusCarga.objects.order_by("idstatuscarga")
    serializer_class = StatusCargaSerializer
    permission_map = {
        "list": "view_statuscarga",
        "retrieve": "view_statuscarga",
        "create": "add_statuscarga",
        "update": "change_statuscarga",
        "partial_update": "change_statuscarga",
        "destroy": "delete_statuscarga",
    }


@tag_all_actions("4 - Carga Org/Lot")
class StatusProgressoViewSet(BaseCatalogViewSet):
    queryset = StatusProgresso.objects.order_by("idstatusprogresso")
    serializer_class = StatusProgressoSerializer
    permission_map = {
        "list": "view_statusprogresso",
        "retrieve": "view_statusprogresso",
        "create": "add_statusprogresso",
        "update": "change_statusprogresso",
        "partial_update": "change_statusprogresso",
        "destroy": "delete_statusprogresso",
    }


@tag_all_actions("4 - Carga Org/Lot")
class TipoCargaViewSet(BaseCatalogViewSet):
    queryset = TipoCarga.objects.order_by("idtipocarga")
    serializer_class = TipoCargaSerializer
    permission_map = {
        "list": "view_tipocarga",
        "retrieve": "view_tipocarga",
        "create": "add_tipocarga",
        "update": "change_tipocarga",
        "partial_update": "change_tipocarga",
        "destroy": "delete_tipocarga",
    }


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "patriarca",
                int,
                description="Filtra pelo ID interno do patriarca.",
            ),
            OpenApiParameter(
                "ativo",
                bool,
                description="Filtra processos ativos ou encerrados.",
            ),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ProcessoCargaInicialViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ProcessoCargaInicial.objects.select_related(
        "idpatriarca"
    ).prefetch_related("historico")
    serializer_class = ProcessoCargaInicialSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["databertura", "idprocessocargainicial"]
    ordering = ["-databertura", "-idprocessocargainicial"]
    ordering_tie_breaker = "idprocessocargainicial"
    permission_map = {
        "list": "view_patriarca",
        "retrieve": "view_patriarca",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        patriarca = self.request.query_params.get("patriarca")
        if patriarca is not None:
            if not patriarca.isdecimal():
                raise serializers.ValidationError(
                    {"patriarca": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(idpatriarca_id=int(patriarca))
        ativo = self.request.query_params.get("ativo")
        if ativo is not None:
            normalized = ativo.lower()
            if normalized not in {"true", "false"}:
                raise serializers.ValidationError({"ativo": "Informe true ou false."})
            queryset = queryset.filter(flgativo=normalized == "true")
        return queryset
