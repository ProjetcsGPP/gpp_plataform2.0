"""
GPP Plataform 2.0 — Carga Org Lot Views
FASE 6: Scaffold de APIs com SecureQuerysetMixin obrigatório.

Roles obrigatórias: GESTOR_CARGA (todos os endpoints).
"""
from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import HasRolePermission

ROLES_CARGA = {"GESTOR_CARGA"}


def _check_carga_role(request):
    """
    Verifica se o usuário possui a role GESTOR_CARGA.
    Lança PermissionDenied (403) caso contrário.
    """
    if getattr(request, "is_portal_admin", False):
        return
    user_roles = {r.role.codigoperfil for r in getattr(request, "user_roles", [])}
    if not user_roles.intersection(ROLES_CARGA):
        raise PermissionDenied(
            "Acesso negado. Role necessária: GESTOR_CARGA"
        )


class CargaOrgLotViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    ViewSet scaffold para Carga Organizacional / Lotação.
    Models e serializers serão implementados na fase de domínio.

    SecureQuerysetMixin garante filtro por orgao (proteção IDOR).
    AuditableMixin preenche created_by / updated_by automaticamente.
    Todos os endpoints exigem role GESTOR_CARGA.
    """
    permission_classes = [IsAuthenticated, HasRolePermission]
    scope_field = "orgao"
    scope_source = "orgao"

    # ── Substituir nas implementações finais ──────────────────────────────
    queryset = None  # definir quando o model CargaOrgLot estiver disponível
    serializer_class = None  # definir quando o serializer estiver disponível
    # ─────────────────────────────────────────────────────────────────────

    def get_queryset(self):
        """
        Retorna queryset vazio até o model ser implementado.
        Quando o model estiver disponível, substituir por:
            from .models import CargaOrgLot
            self.queryset = CargaOrgLot.objects.all()
            return super().get_queryset()
        """
        return _EmptyQueryset()

    def list(self, request, *args, **kwargs):
        _check_carga_role(request)
        return Response([])

    def retrieve(self, request, *args, **kwargs):
        _check_carga_role(request)
        return Response({})

    def create(self, request, *args, **kwargs):
        _check_carga_role(request)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def update(self, request, *args, **kwargs):
        _check_carga_role(request)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def partial_update(self, request, *args, **kwargs):
        _check_carga_role(request)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def destroy(self, request, *args, **kwargs):
        _check_carga_role(request)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class _EmptyQueryset:
    """Placeholder para evitar erros enquanto o model não existe."""
    def none(self):
        return self

    def filter(self, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0
