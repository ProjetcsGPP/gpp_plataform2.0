"""Views de cargas da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from rest_framework import viewsets

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..models import DetalheStatusCarga, TokenEnvioCarga
from ..serializers import DetalheStatusCargaSerializer, TokenEnvioCargaSerializer
from .base import (
    DeterministicOrderingFilter,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
)


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
