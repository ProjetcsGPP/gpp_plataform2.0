"""
GPP Plataform 2.0 — Carga Org Lot Views
FASE 6: Scaffold de APIs com SecureQuerysetMixin obrigatório.

Todos os endpoints exigem que o usuário possua a role associada
à aplicação 'CARGA_ORG_LOT'. A role NÃO está hardcoded: ela é
lida do banco de dados via _load_carga_roles().
"""
from __future__ import annotations

from functools import lru_cache

from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import HasRolePermission
from common.schema import tag_all_actions

# Identificador da aplicação no banco (accounts.Aplicacao.codigointerno)
# DEVE ser maiúsculo para corresponder ao valor gravado no banco.
_APP_CODE = "CARGA_ORG_LOT"


@lru_cache(maxsize=1)
def _load_carga_roles() -> frozenset[str]:
    """
    Consulta o banco e retorna o conjunto de codigoperfil
    autorizados para a aplicação CARGA_ORG_LOT.

    O lru_cache(maxsize=1) garante que a query ao banco é feita
    apenas uma vez por processo (worker). Para forçar recarregamento:
        _load_carga_roles.cache_clear()
    """
    from apps.accounts.models import Role

    return frozenset(
        Role.objects.filter(
            aplicacao__codigointerno=_APP_CODE
        ).values_list("codigoperfil", flat=True)
    )


def _check_carga_role(request) -> None:
    """
    Verifica se o usuário possui alguma role autorizada para CARGA_ORG_LOT.
    Lança PermissionDenied (403) caso contrário.
    """
    if getattr(request, "is_portal_admin", False):
        return

    allowed = _load_carga_roles()
    user_roles = {r.role.codigoperfil for r in getattr(request, "user_roles", [])}

    if not user_roles.intersection(allowed):
        raise PermissionDenied(
            f"Acesso negado. Roles necessárias: {', '.join(sorted(allowed))}"
        )


@tag_all_actions("4 - Carga Org/Lot")
class CargaOrgLotViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    ViewSet scaffold para Carga Organizacional / Lotação.
    Models e serializers serão implementados na fase de domínio.

    SecureQuerysetMixin garante filtro por orgao (proteção IDOR).
    AuditableMixin preenche created_by / updated_by automaticamente.
    """
    permission_classes = [IsAuthenticated, HasRolePermission]
    scope_field = "orgao"
    scope_source = "orgao"

    # ── Substituir nas implementações finais ────────────────────────────────────
    queryset = None  # definir quando o model CargaOrgLot estiver disponível
    serializer_class = None  # definir quando o serializer estiver disponível
    # ───────────────────────────────────────────────────────────────────────────────────

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
    """Placeholder para evitar erros enquanto o model CargaOrgLot não existe."""

    def none(self):
        return self

    def filter(self, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0
