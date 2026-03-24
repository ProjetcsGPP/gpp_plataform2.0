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

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from common.mixins import AuditableMixin
from common.permissions import HasRolePermission

from .models import (
    Acoes,
    AcaoAnotacaoAlinhamento,
    AcaoDestaque,
    AcaoPrazo,
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

# Identificador da aplicação no banco (accounts.Aplicacao.codigointerno)
# ATENÇÃO: deve ser MAIÚSCULO — idêntico ao valor gravado em Aplicacao.codigointerno
_APP_CODE = "ACOES_PNGI"

_LEVEL_READ = "READ"
_LEVEL_WRITE = "WRITE"
_LEVEL_DELETE = "DELETE"


@lru_cache(maxsize=1)
def _load_role_matrix() -> dict[str, frozenset[str]]:
    """
    Consulta o banco e monta a matriz de permissões para acoes_pngi.

    Retorna:
        {
          "READ":   frozenset({"GESTOR_PNGI", "COORDENADOR_PNGI", ...}),
          "WRITE":  frozenset({"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}),
          "DELETE": frozenset({"GESTOR_PNGI"}),
        }

    lru_cache(maxsize=1) → query ao banco feita apenas uma vez por worker.
    Para recarregar: _load_role_matrix.cache_clear()
    """
    from apps.accounts.models import Role

    roles_qs = Role.objects.filter(
        aplicacao__codigointerno=_APP_CODE
    ).values_list("codigoperfil", flat=True)

    all_roles: frozenset[str] = frozenset(roles_qs)

    read_codes   = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO", "CONSULTOR_PNGI"}
    write_codes  = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}
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
    Portal admin bypass via request.is_portal_admin.
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


# ---------------------------------------------------------------------------
# ViewSets de referência (somente leitura)
# ---------------------------------------------------------------------------

class EixoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Eixos temáticos do programa PNGI.
    Somente leitura para todos os usuários autenticados.
    """
    queryset = Eixo.objects.all()
    serializer_class = EixoSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)


class SituacaoAcaoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Situações possíveis de uma Ação PNGI.
    Somente leitura para todos os usuários autenticados.
    """
    queryset = SituacaoAcao.objects.all()
    serializer_class = SituacaoAcaoSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# VigenciaPNGIViewSet (CRUD completo — apenas GESTOR_PNGI pode escrever)
# ---------------------------------------------------------------------------

class VigenciaPNGIViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Vigências do programa PNGI.
    CRUD completo restrito a GESTOR_PNGI para escrita.
    Leitura: todos os roles READ.
    """
    queryset = VigenciaPNGI.objects.all()
    serializer_class = VigenciaPNGISerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return super().destroy(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# AcaoViewSet (CRUD completo com matrix de roles)
# ---------------------------------------------------------------------------

class AcaoViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Ações PNGI — entidade principal.

    Acoes são independentes de orgão (iniciativas do programa PNGI).
    NÃO herda SecureQuerysetMixin.
    Controle de acesso exclusivamente por roles via _load_role_matrix().
    AuditableMixin preenche created_by_id/name e updated_by_id/name.
    """
    queryset = Acoes.objects.select_related(
        "idvigenciapngi",
        "idtipoentravealerta",
        "idsituacaoacao",
        "ideixo",
    )
    serializer_class = AcoesSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return super().destroy(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# ViewSets nested em Acao
# ---------------------------------------------------------------------------

class AcaoPrazoViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Prazos de uma Ação PNGI.
    Filtrado pelo idacao passado na URL.
    """
    serializer_class = AcaoPrazoSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def get_queryset(self):
        return AcaoPrazo.objects.filter(
            idacao_id=self.kwargs["acao_pk"]
        )

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return super().destroy(request, *args, **kwargs)


class AcaoDestaqueViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Destaques de uma Ação PNGI.
    Filtrado pelo idacao passado na URL.
    """
    serializer_class = AcaoDestaqueSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def get_queryset(self):
        return AcaoDestaque.objects.filter(
            idacao_id=self.kwargs["acao_pk"]
        )

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return super().destroy(request, *args, **kwargs)


class AcaoAnotacaoViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Anotações de alinhamento de uma Ação PNGI.
    Filtrado pelo idacao passado na URL.
    """
    serializer_class = AcaoAnotacaoAlinhamentoSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def get_queryset(self):
        return AcaoAnotacaoAlinhamento.objects.filter(
            idacao_id=self.kwargs["acao_pk"]
        )

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return super().destroy(request, *args, **kwargs)
