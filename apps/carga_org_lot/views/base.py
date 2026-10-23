"""Views de base da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from rest_framework import serializers
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import CanPermission

from ..models import ImportacaoPlanilha


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
