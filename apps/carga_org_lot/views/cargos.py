"""Views de cargos da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from rest_framework import serializers, viewsets

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..models import (
    CargoReferenciaGlobal,
    MapeamentoCargoPatriarca,
    OcorrenciaCargoImportacao,
    VariacaoCargoGlobal,
)
from ..serializers import (
    CargoReferenciaGlobalSerializer,
    MapeamentoCargoPatriarcaSerializer,
    OcorrenciaCargoImportacaoSerializer,
    VariacaoCargoGlobalSerializer,
)
from .base import (
    DeterministicOrderingFilter,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
)


class CargoCatalogPermissionMixin:
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "create": "add_importacaoplanilha",
        "update": "change_importacaoplanilha",
        "partial_update": "change_importacaoplanilha",
        "destroy": "delete_importacaoplanilha",
    }


@tag_all_actions("4 - Carga Org/Lot")
class CargoReferenciaGlobalViewSet(
    CargoCatalogPermissionMixin,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = CargoReferenciaGlobal.objects.all()
    serializer_class = CargoReferenciaGlobalSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["strnome", "strstatus", "created_at", "idcargoreferencia"]
    ordering = ["strnome", "idcargoreferencia"]
    ordering_tie_breaker = "idcargoreferencia"

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(strstatus=status_value)
        active = self.request.query_params.get("ativo")
        if active is not None:
            if active.lower() not in {"true", "false"}:
                raise serializers.ValidationError({"ativo": "Informe true ou false."})
            queryset = queryset.filter(flgativo=active.lower() == "true")
        search = self.request.query_params.get("q", "").strip()
        if search:
            queryset = queryset.filter(strnome__icontains=search)
        return queryset


@tag_all_actions("4 - Carga Org/Lot")
class VariacaoCargoGlobalViewSet(
    CargoCatalogPermissionMixin,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = VariacaoCargoGlobal.objects.select_related("idcargoreferencia").all()
    serializer_class = VariacaoCargoGlobalSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strdescricao",
        "strstatus",
        "inttotalocorrencias",
        "datultimaocorrencia",
        "idvariacaocargo",
    ]
    ordering = ["-inttotalocorrencias", "idvariacaocargo"]
    ordering_tie_breaker = "idvariacaocargo"

    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in {
            "status": "strstatus",
            "cargo_referencia": "idcargoreferencia_id",
        }.items():
            value = self.request.query_params.get(parameter)
            if value:
                if parameter == "cargo_referencia" and not value.isdecimal():
                    raise serializers.ValidationError(
                        {parameter: "Informe um identificador numérico válido."}
                    )
                queryset = queryset.filter(**{field: value})
        search = self.request.query_params.get("q", "").strip()
        if search:
            queryset = queryset.filter(strdescricao__icontains=search)
        return queryset


@tag_all_actions("4 - Carga Org/Lot")
class OcorrenciaCargoImportacaoViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = OcorrenciaCargoImportacao.objects.select_related(
        "idvariacaocargo__idcargoreferencia",
        "idimportacaoplanilha",
        "idpatriarca",
    ).all()
    serializer_class = OcorrenciaCargoImportacaoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["created_at", "intquantidade", "idocorrenciacargo"]
    ordering = ["-created_at", "-idocorrenciacargo"]
    ordering_tie_breaker = "idocorrenciacargo"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in {
            "importacao": "idimportacaoplanilha_id",
            "patriarca": "idpatriarca_id",
            "variacao": "idvariacaocargo_id",
        }.items():
            value = self.request.query_params.get(parameter)
            if value is not None:
                if not value.isdecimal():
                    raise serializers.ValidationError(
                        {parameter: "Informe um identificador numérico válido."}
                    )
                queryset = queryset.filter(**{field: int(value)})
        return queryset


@tag_all_actions("4 - Carga Org/Lot")
class MapeamentoCargoPatriarcaViewSet(
    CargoCatalogPermissionMixin,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = MapeamentoCargoPatriarca.objects.select_related(
        "idpatriarca",
        "idvariacaocargo",
        "idcargoreferencia",
    ).all()
    serializer_class = MapeamentoCargoPatriarcaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["created_at", "idmapeamentocargo"]
    ordering = ["-created_at", "-idmapeamentocargo"]
    ordering_tie_breaker = "idmapeamentocargo"

    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in {
            "patriarca": "idpatriarca_id",
            "variacao": "idvariacaocargo_id",
            "cargo_referencia": "idcargoreferencia_id",
        }.items():
            value = self.request.query_params.get(parameter)
            if value is not None:
                if not value.isdecimal():
                    raise serializers.ValidationError(
                        {parameter: "Informe um identificador numérico válido."}
                    )
                queryset = queryset.filter(**{field: int(value)})
        return queryset
