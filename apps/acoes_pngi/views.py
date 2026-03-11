"""
GPP Plataform 2.0 — Ações PNGI Views
FASE 6: Scaffold de APIs com SecureQuerysetMixin obrigatório.

Convenção de roles por ação (enforced via get_permissions):
  - list / retrieve : GESTOR_PNGI | COORDENADOR_PNGI | OPERADOR_ACAO | CONSULTOR_PNGI
  - create / update : GESTOR_PNGI | COORDENADOR_PNGI | OPERADOR_ACAO
  - destroy         : GESTOR_PNGI
"""
from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import HasRolePermission

# Roles permitidas por nível de acesso
ROLES_READ = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO", "CONSULTOR_PNGI"}
ROLES_WRITE = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}
ROLES_DELETE = {"GESTOR_PNGI"}


def _check_roles(request, allowed_roles: set):
    """
    Verifica se alguma das roles do request está no conjunto permitido.
    Lança PermissionDenied (403) caso contrário.
    """
    if getattr(request, "is_portal_admin", False):
        return
    user_roles = {r.role.codigoperfil for r in getattr(request, "user_roles", [])}
    if not user_roles.intersection(allowed_roles):
        raise PermissionDenied(
            f"Acesso negado. Roles necessárias: {', '.join(sorted(allowed_roles))}"
        )


class AcaoPNGIViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    ViewSet scaffold para Ações PNGI.
    Models e serializers serão implementados na fase de domínio.

    SecureQuerysetMixin garante filtro por orgao (proteção IDOR).
    AuditableMixin preenche created_by / updated_by automaticamente.
    """
    permission_classes = [IsAuthenticated, HasRolePermission]
    scope_field = "orgao"
    scope_source = "orgao"

    # ── Substituir nas implementações finais ──────────────────────────────
    queryset = None  # definir quando o model AcaoPNGI estiver disponível
    serializer_class = None  # definir quando o serializer estiver disponível
    # ─────────────────────────────────────────────────────────────────────

    def get_queryset(self):
        """
        Retorna queryset vazio até o model ser implementado.
        Quando o model estiver disponível, substituir por:
            from .models import AcaoPNGI
            self.queryset = AcaoPNGI.objects.all()
            return super().get_queryset()
        """
        from django.db.models import QuerySet
        # Scaffold: retorna queryset vazio até o model estar disponível
        return UserRolesPlaceholder()

    def list(self, request, *args, **kwargs):
        _check_roles(request, ROLES_READ)
        return Response([])

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, ROLES_READ)
        return Response({})

    def create(self, request, *args, **kwargs):
        _check_roles(request, ROLES_WRITE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def update(self, request, *args, **kwargs):
        _check_roles(request, ROLES_WRITE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, ROLES_WRITE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, ROLES_DELETE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class UserRolesPlaceholder:
    """
    Placeholder para evitar erros enquanto o model AcaoPNGI não existe.
    Retorna queryset-like vazio em operações essenciais.
    """
    def none(self):
        return self

    def filter(self, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0
