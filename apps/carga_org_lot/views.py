"""API da aplicação de carga de organograma e lotação."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core.permissions import CanPermission
from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from .models import (
    DetalheStatusCarga,
    ImportacaoPlanilha,
    ItemOrganograma,
    Patriarca,
    StatusCarga,
    StatusProgresso,
    TipoCarga,
    TokenEnvioCarga,
)
from .serializers import (
    DetalheStatusCargaSerializer,
    ImportacaoPlanilhaSerializer,
    ItemOrganogramaSerializer,
    PatriarcaSerializer,
    StatusCargaSerializer,
    StatusProgressoSerializer,
    TipoCargaSerializer,
    TokenEnvioCargaSerializer,
)
from .services.organograma import ORGANOGRAMA_TYPE_ID


def spreadsheet_download_response(importacao: ImportacaoPlanilha) -> HttpResponse:
    """Cria uma resposta segura para download da planilha armazenada."""
    response = HttpResponse(
        bytes(importacao.binconteudo),
        content_type=importacao.strtipomime or "application/octet-stream",
    )
    response["Content-Disposition"] = content_disposition_header(
        True,
        importacao.strnomearquivo,
    )
    response["Content-Length"] = importacao.inttamanhoarquivo
    response["X-Content-Type-Options"] = "nosniff"
    return response


class PermissionedViewSetMixin:
    """Aplica a permissão Django correspondente a cada operação DRF."""

    permission_classes = [IsAuthenticated, CanPermission]
    permission_map: dict[str, str] = {}

    def get_permissions(self):
        self.required_permission = self.permission_map.get(self.action)
        return [permission() for permission in self.permission_classes]


class ProtectedDestroyMixin:
    """Converte violações de PROTECT em erro de validação compreensível."""

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise serializers.ValidationError(
                "O registro não pode ser excluído porque está em uso."
            ) from exc


class DeterministicOrderingFilter(OrderingFilter):
    """Acrescenta a chave primária como desempate da paginação."""

    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or [])
        tie_breaker = view.ordering_tie_breaker
        if not any(field.lstrip("-") == tie_breaker for field in ordering):
            ordering.append(tie_breaker)
        return ordering


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
                "tipo_carga",
                int,
                description="Filtra pelo ID do tipo de carga.",
            ),
            OpenApiParameter(
                "status",
                int,
                description="Filtra pelo ID do status de progresso.",
            ),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ImportacaoPlanilhaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = ImportacaoPlanilha.objects.select_related(
        "idpatriarca",
        "idpatriarca__idstatusprogresso",
        "idtipocarga",
        "idstatusprogresso",
        "idimportacaoorganograma",
    ).annotate(total_itens_organograma=Count("itens_organograma"))
    serializer_class = ImportacaoPlanilhaSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "datimportacao",
        "strnomearquivo",
        "inttamanhoarquivo",
        "idimportacaoplanilha",
    ]
    ordering = ["-datimportacao", "-idimportacaoplanilha"]
    ordering_tie_breaker = "idimportacaoplanilha"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "create": "add_importacaoplanilha",
        "upload": "add_importacaoplanilha",
        "download": "view_importacaoplanilha",
        "update": "change_importacaoplanilha",
        "partial_update": "change_importacaoplanilha",
        "destroy": "delete_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        filters = {
            "patriarca": "idpatriarca_id",
            "tipo_carga": "idtipocarga_id",
            "status": "idstatusprogresso_id",
        }
        for parameter, model_field in filters.items():
            value = self.request.query_params.get(parameter)
            if value is None:
                continue
            if not value.isdecimal():
                raise serializers.ValidationError(
                    {parameter: "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(**{model_field: int(value)})
        return queryset

    @transaction.atomic
    def perform_destroy(self, instance):
        """Exclui fisicamente a importação, seu arquivo e os itens em cascata."""
        super().perform_destroy(instance)

    @extend_schema(
        request=ImportacaoPlanilhaSerializer,
        responses={status.HTTP_201_CREATED: ImportacaoPlanilhaSerializer},
    )
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        }
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, *args, **kwargs):
        importacao = self.get_object()
        return spreadsheet_download_response(importacao)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "importacao",
                int,
                description="Filtra pela versão importada do organograma.",
            ),
            OpenApiParameter(
                "pai",
                int,
                description="Filtra pelo item pai; use 'raiz' para a raiz.",
            ),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ItemOrganogramaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = ItemOrganograma.objects.select_related(
        "idimportacaoplanilha",
        "idimportacaoplanilha__idpatriarca",
        "idpai",
    ).all()
    serializer_class = ItemOrganogramaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strnumero",
        "strsigla",
        "strnome",
        "intlinhaorigem",
        "iditemorganograma",
    ]
    ordering = ["strnumero", "intlinhaorigem", "iditemorganograma"]
    ordering_tie_breaker = "iditemorganograma"
    permission_map = {
        "list": "view_itemorganograma",
        "retrieve": "view_itemorganograma",
        "create": "add_itemorganograma",
        "update": "change_itemorganograma",
        "partial_update": "change_itemorganograma",
        "destroy": "delete_itemorganograma",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        importacao = self.request.query_params.get("importacao")
        if importacao is not None:
            if not importacao.isdecimal():
                raise serializers.ValidationError(
                    {"importacao": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(idimportacaoplanilha_id=int(importacao))

        pai = self.request.query_params.get("pai")
        if pai == "raiz":
            queryset = queryset.filter(idpai__isnull=True)
        elif pai is not None:
            if not pai.isdecimal():
                raise serializers.ValidationError(
                    {"pai": "Informe um identificador numérico ou 'raiz'."}
                )
            queryset = queryset.filter(idpai_id=int(pai))
        return queryset


@tag_all_actions("4 - Carga Org/Lot")
class CargaOrgLotViewSet(
    PermissionedViewSetMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = TokenEnvioCarga.objects.select_related(
        "idtipocarga", "idstatusprogresso"
    ).prefetch_related("detalhes__idstatuscarga")
    serializer_class = TokenEnvioCargaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["created_at", "updated_at", "idtokenenviocarga"]
    ordering = ["-created_at", "-idtokenenviocarga"]
    ordering_tie_breaker = "idtokenenviocarga"
    permission_map = {
        "list": "view_tokenenviocarga",
        "retrieve": "view_tokenenviocarga",
        "create": "add_tokenenviocarga",
        "update": "change_tokenenviocarga",
        "partial_update": "change_tokenenviocarga",
        "destroy": "delete_tokenenviocarga",
    }


@tag_all_actions("4 - Carga Org/Lot")
class HistoricoCargaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = DetalheStatusCarga.objects.select_related(
        "idtokenenviocarga", "idstatuscarga"
    ).all()
    serializer_class = DetalheStatusCargaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["created_at", "iddetalhestatuscarga"]
    ordering = ["-created_at", "-iddetalhestatuscarga"]
    ordering_tie_breaker = "iddetalhestatuscarga"
    permission_map = {
        "list": "view_detalhestatuscarga",
        "retrieve": "view_detalhestatuscarga",
        "create": "add_detalhestatuscarga",
        "update": "change_detalhestatuscarga",
        "partial_update": "change_detalhestatuscarga",
        "destroy": "delete_detalhestatuscarga",
    }
