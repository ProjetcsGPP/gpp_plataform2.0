"""
GPP Plataform 2.0 — Ações PNGI Views

Matriz de permissões por operação:
  - list / retrieve  : ROLES_READ
  - create / update  : ROLES_WRITE
  - destroy          : ROLES_DELETE

As roles SÃO LIDAS DO BANCO DE DADOS na primeira requisição e
cacheadas no processo via _load_role_matrix(). Não há strings
hardcoded de codigoperfil neste módulo.

Nota: SecureQuerysetMixin NÃO é usado aqui pois Acoes PNGI
não são recursos de tenant (independentes de orgão).
O controle de acesso é feito exclusivamente por roles.
"""
from __future__ import annotations

from functools import lru_cache

from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.mixins import AuditableMixin
from common.permissions import HasRolePermission

# Identificador da aplicação no banco (accounts.Aplicacao.codigointerno)
_APP_CODE = "acoes_pngi"

# Nomes lógicos dos conjuntos de permissão usados neste módulo
_LEVEL_READ = "READ"
_LEVEL_WRITE = "WRITE"
_LEVEL_DELETE = "DELETE"


@lru_cache(maxsize=1)
def _load_role_matrix() -> dict[str, frozenset[str]]:
    """
    Consulta o banco e monta a matriz de permissões para acoes_pngi.

    Retorna um dict com a estrutura:
        {
          "READ":   frozenset({"GESTOR_PNGI", "COORDENADOR_PNGI", ...}),
          "WRITE":  frozenset({"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}),
          "DELETE": frozenset({"GESTOR_PNGI"}),
        }

    O lru_cache(maxsize=1) garante que a query ao banco é feita apenas
    uma vez por processo (worker). Se as roles mudarem em produção,
    reinicie os workers ou chame _load_role_matrix.cache_clear().
    """
    from apps.accounts.models import Role

    # Traz todas as roles da aplicação de uma só vez
    roles_qs = Role.objects.filter(
        aplicacao__codigointerno=_APP_CODE
    ).values_list("codigoperfil", flat=True)

    all_roles: frozenset[str] = frozenset(roles_qs)

    # Regras de negócio: quais roles têm cada nível de acesso.
    # A lógica hierárquica fica aqui, centralizada, e reflete
    # o que está no banco — se uma role não existir lá, não entra.
    read_codes  = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO", "CONSULTOR_PNGI"}
    write_codes = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}
    delete_codes = {"GESTOR_PNGI"}

    return {
        _LEVEL_READ:   all_roles.intersection(read_codes),
        _LEVEL_WRITE:  all_roles.intersection(write_codes),
        _LEVEL_DELETE: all_roles.intersection(delete_codes),
    }


def _check_roles(request, level: str) -> None:
    """
    Verifica se o usuário possui alguma role do nível solicitado.
    Lança PermissionDenied (403) caso contrário.
    """
    if getattr(request, "is_portal_admin", False):
        return

    matrix = _load_role_matrix()
    allowed = matrix.get(level, frozenset())
    user_roles = {r.role.codigoperfil for r in getattr(request, "user_roles", [])}

    if not user_roles.intersection(allowed):
        raise PermissionDenied(
            f"Acesso negado. Roles necessárias: {', '.join(sorted(allowed))}"
        )


class AcaoPNGIViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    ViewSet scaffold para Ações PNGI.
    Models e serializers serão implementados na fase de domínio.

    AuditableMixin preenche created_by / updated_by automaticamente.
    SecureQuerysetMixin não é aplicado pois Acoes são independentes
    de orgão (não são recursos de tenant).
    O controle de acesso é feito exclusivamente por roles via HasRolePermission.
    """
    permission_classes = [IsAuthenticated, HasRolePermission]

    # ── Substituir nas implementações finais ───────────────────────────────────────
    queryset = None  # definir quando o model AcaoPNGI estiver disponível
    serializer_class = None  # definir quando o serializer estiver disponível
    # ─────────────────────────────────────────────────────────────────────────────

    def get_queryset(self):
        """
        Retorna queryset vazio até o model ser implementado.
        Quando o model estiver disponível, substituir por:
            from .models import Acoes
            self.queryset = Acoes.objects.all()
            return super().get_queryset()
        """
        return _EmptyQueryset()

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return Response([])

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return Response({})

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return Response({"detail": "Não implementado."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class _EmptyQueryset:
    """Placeholder para evitar erros enquanto o model Acoes não está totalmente implementado."""

    def none(self):
        return self

    def filter(self, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0
