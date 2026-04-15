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

Matriz de permissões por ViewSet:

  Acoes (AcaoViewSet):
    READ   = GESTOR_PNGI, COORDENADOR_PNGI, OPERADOR_ACAO, CONSULTOR_PNGI
    WRITE  = GESTOR_PNGI, COORDENADOR_PNGI, OPERADOR_ACAO
    DELETE = GESTOR_PNGI

  Vigencias (VigenciaPNGIViewSet):
    READ   = GESTOR_PNGI, COORDENADOR_PNGI, OPERADOR_ACAO, CONSULTOR_PNGI
    WRITE  = GESTOR_PNGI, COORDENADOR_PNGI   ← OPERADOR_ACAO nao pode escrever vigencias
    DELETE = GESTOR_PNGI
"""

from __future__ import annotations

from functools import lru_cache

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from common.mixins import AuditableMixin
from common.permissions import HasRolePermission
from common.schema import tag_all_actions

from .models import (
    AcaoAnotacaoAlinhamento,
    AcaoDestaque,
    AcaoPrazo,
    Acoes,
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

# Parâmetro reutilizável para os 3 nested ViewSets
_ACAO_PK_PARAM = OpenApiParameter(
    name="acao_pk",
    type=int,
    location=OpenApiParameter.PATH,
    description="ID (idacao) da Ação PNGI pai",
)


@lru_cache(maxsize=1)
def _load_role_matrix() -> dict[str, frozenset[str]]:
    """
    Matriz de permissões para os recursos principais de acoes_pngi
    (Acoes, Eixo, SituacaoAcao, Prazo, Destaque, Anotacao).

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

    roles_qs = Role.objects.filter(aplicacao__codigointerno=_APP_CODE).values_list(
        "codigoperfil", flat=True
    )

    all_roles: frozenset[str] = frozenset(roles_qs)

    read_codes = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO", "CONSULTOR_PNGI"}
    write_codes = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO"}
    delete_codes = {"GESTOR_PNGI"}

    return {
        _LEVEL_READ: all_roles.intersection(read_codes),
        _LEVEL_WRITE: all_roles.intersection(write_codes),
        _LEVEL_DELETE: all_roles.intersection(delete_codes),
    }


@lru_cache(maxsize=1)
def _load_vigencia_role_matrix() -> dict[str, frozenset[str]]:
    """
    Matriz de permissões exclusiva para VigenciaPNGI.

    Vigências representam os ciclos do programa PNGI — domínio do Gestor
    e do Coordenador. OPERADOR_ACAO pode apenas consultar, não escrever.

    Retorna:
        {
          "READ":   frozenset({"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO", "CONSULTOR_PNGI"}),
          "WRITE":  frozenset({"GESTOR_PNGI", "COORDENADOR_PNGI"}),
          "DELETE": frozenset({"GESTOR_PNGI"}),
        }
    """
    from apps.accounts.models import Role

    roles_qs = Role.objects.filter(aplicacao__codigointerno=_APP_CODE).values_list(
        "codigoperfil", flat=True
    )

    all_roles: frozenset[str] = frozenset(roles_qs)

    read_codes = {"GESTOR_PNGI", "COORDENADOR_PNGI", "OPERADOR_ACAO", "CONSULTOR_PNGI"}
    write_codes = {
        "GESTOR_PNGI",
        "COORDENADOR_PNGI",
    }  # OPERADOR_ACAO nao pode criar/editar vigencias
    delete_codes = {"GESTOR_PNGI"}

    return {
        _LEVEL_READ: all_roles.intersection(read_codes),
        _LEVEL_WRITE: all_roles.intersection(write_codes),
        _LEVEL_DELETE: all_roles.intersection(delete_codes),
    }


def _check_roles(request, level: str, matrix_fn=None) -> None:
    """
    Verifica se o usuário possui alguma role do nível solicitado.
    Lança PermissionDenied (403) caso contrário.
    Portal admin bypass via request.is_portal_admin.

    matrix_fn: função que retorna a matriz de permissões.
               Padrão: _load_role_matrix (usado por Acoes e recursos nested).
               Passar _load_vigencia_role_matrix para VigenciaPNGIViewSet.
    """
    if getattr(request, "is_portal_admin", False):
        return

    if matrix_fn is None:
        matrix_fn = _load_role_matrix

    matrix = matrix_fn()
    allowed = matrix.get(level, frozenset())
    user_roles = {r.role.codigoperfil for r in getattr(request, "user_roles", [])}

    if not user_roles.intersection(allowed):
        raise PermissionDenied(
            f"Acesso negado. Roles necessárias: {', '.join(sorted(allowed))}"
        )


# ---------------------------------------------------------------------------
# ViewSets de referência (somente leitura)
# ---------------------------------------------------------------------------


@tag_all_actions("3 - Ações PNGI")
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


@tag_all_actions("3 - Ações PNGI")
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
# VigenciaPNGIViewSet (CRUD completo — apenas GESTOR/COORDENADOR escrevem)
# ---------------------------------------------------------------------------


@tag_all_actions("3 - Ações PNGI")
class VigenciaPNGIViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Vigências do programa PNGI.

    Escrita restrita a GESTOR_PNGI e COORDENADOR_PNGI.
    OPERADOR_ACAO e CONSULTOR_PNGI somente leitura.
    Deleção exclusiva do GESTOR_PNGI.

    Usa _load_vigencia_role_matrix() — matriz separada de _load_role_matrix()
    para garantir que OPERADOR_ACAO nao herde permissao de escrita de Acoes.
    """

    queryset = VigenciaPNGI.objects.all()
    serializer_class = VigenciaPNGISerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ, matrix_fn=_load_vigencia_role_matrix)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ, matrix_fn=_load_vigencia_role_matrix)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE, matrix_fn=_load_vigencia_role_matrix)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE, matrix_fn=_load_vigencia_role_matrix)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE, matrix_fn=_load_vigencia_role_matrix)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE, matrix_fn=_load_vigencia_role_matrix)
        return super().destroy(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# AcaoViewSet (CRUD completo com matrix de roles)
# ---------------------------------------------------------------------------


@tag_all_actions("3 - Ações PNGI")
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
@extend_schema_view(
    list=extend_schema(parameters=[_ACAO_PK_PARAM]),
    create=extend_schema(parameters=[_ACAO_PK_PARAM]),
    retrieve=extend_schema(parameters=[_ACAO_PK_PARAM]),
    update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    partial_update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    destroy=extend_schema(parameters=[_ACAO_PK_PARAM]),
)
@tag_all_actions("3 - Ações PNGI")
class AcaoPrazoViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Prazos de uma Ação PNGI.
    Filtrado pelo idacao passado na URL.
    """

    serializer_class = AcaoPrazoSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]
    queryset = (
        AcaoPrazo.objects.all()
    )  # ← usado apenas pelo drf-spectacular para introspecção

    def get_queryset(self):
        return AcaoPrazo.objects.filter(idacao_id=self.kwargs["acao_pk"])

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


@extend_schema_view(
    list=extend_schema(parameters=[_ACAO_PK_PARAM]),
    create=extend_schema(parameters=[_ACAO_PK_PARAM]),
    retrieve=extend_schema(parameters=[_ACAO_PK_PARAM]),
    update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    partial_update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    destroy=extend_schema(parameters=[_ACAO_PK_PARAM]),
)
@tag_all_actions("3 - Ações PNGI")
class AcaoDestaqueViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Destaques de uma Ação PNGI.
    Filtrado pelo idacao passado na URL.
    """

    serializer_class = AcaoDestaqueSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]
    queryset = AcaoDestaque.objects.all()  # ← adicionar

    def get_queryset(self):
        return AcaoDestaque.objects.filter(idacao_id=self.kwargs["acao_pk"])

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


@extend_schema_view(
    list=extend_schema(parameters=[_ACAO_PK_PARAM]),
    create=extend_schema(parameters=[_ACAO_PK_PARAM]),
    retrieve=extend_schema(parameters=[_ACAO_PK_PARAM]),
    update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    partial_update=extend_schema(parameters=[_ACAO_PK_PARAM]),
    destroy=extend_schema(parameters=[_ACAO_PK_PARAM]),
)
@tag_all_actions("3 - Ações PNGI")
class AcaoAnotacaoViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Anotações de alinhamento de uma Ação PNGI.
    Filtrado pelo idacao passado na URL.
    """

    serializer_class = AcaoAnotacaoAlinhamentoSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]
    queryset = AcaoAnotacaoAlinhamento.objects.all()

    def get_queryset(self):
        return AcaoAnotacaoAlinhamento.objects.filter(idacao_id=self.kwargs["acao_pk"])

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
