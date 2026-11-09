"""API administrativa do catálogo de patriarcas E-Docs."""

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.services.authorization_service import AuthorizationService
from apps.core.permissions import CanPermission
from apps.pub_institucional.models import (
    ColetaPatriarcasEdocs,
    DivergenciaPatriarcaEdocs,
    EventoAuditoriaPatriarcaEdocs,
    PatriarcaEdocs,
    SituacaoColetaPatriarcas,
    SituacaoDivergenciaPatriarca,
    TipoComparacaoPatriarca,
    TipoEventoAuditoriaPatriarca,
)
from apps.pub_institucional.serializadores import (
    SerializadorColetaPatriarcasEdocs,
    SerializadorDecisaoDivergencia,
    SerializadorDivergenciaPatriarcaEdocs,
    SerializadorEventoAuditoriaPatriarcaEdocs,
    SerializadorPatriarcaEdocs,
    SerializadorSelecaoColeta,
)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs,
    ErroDecisaoPatriarcaEdocs,
    aplicar_decisao_divergencia_patriarca,
    definir_selecao_coleta_patriarca,
    sincronizar_patriarcas_edocs,
)


class ConflitoCatalogoEdocs(APIException):
    """Indica que o estado canônico mudou ou impede a decisão solicitada."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflito_catalogo_edocs"
    default_detail = "A operação conflita com o estado atual do catálogo."

    def __init__(self, detalhe=None):
        super().__init__(
            {
                "codigo": self.default_code,
                "detalhe": detalhe or self.default_detail,
            },
            code=self.default_code,
        )


class MixinPermissaoPorAcao:
    """Seleciona a permissão técnica declarada para cada operação DRF."""

    permission_classes = [IsAuthenticated, CanPermission]
    mapa_permissoes: dict[str, str] = {}

    def get_permissions(self):
        self.required_permission = self.mapa_permissoes.get(self.action)
        return [classe() for classe in self.permission_classes]


def _ator_do_usuario(usuario):
    nome = usuario.get_full_name().strip() or usuario.get_username()
    return AtorAuditoriaEdocs(usuario_id=usuario.pk, nome=nome)


def _parametro_booleano(request, nome):
    valor = request.query_params.get(nome)
    if valor is None:
        return None
    normalizado = valor.strip().lower()
    if normalizado in {"true", "1"}:
        return True
    if normalizado in {"false", "0"}:
        return False
    raise ValidationError({nome: "Use true, false, 1 ou 0."})


def _parametro_escolha(request, nome, permitidos):
    valor = request.query_params.get(nome)
    if valor is None:
        return None
    if valor not in permitidos:
        raise ValidationError({nome: "Valor não reconhecido."})
    return valor


def _parametro_uuid(request, nome):
    valor = request.query_params.get(nome)
    if valor is None:
        return None
    try:
        return UUID(valor)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({nome: "Informe um UUID válido."}) from exc


def _parametro_inteiro(request, nome):
    valor = request.query_params.get(nome)
    if valor is None:
        return None
    try:
        convertido = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValidationError({nome: "Informe um número inteiro válido."}) from exc
    if convertido <= 0:
        raise ValidationError({nome: "Informe um número inteiro positivo."})
    return convertido


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoPatriarcaEdocs(MixinPermissaoPorAcao, viewsets.ReadOnlyModelViewSet):
    """Consulta o catálogo definitivo e altera somente sua seleção de coleta."""

    queryset = PatriarcaEdocs.objects.all()
    serializer_class = SerializadorPatriarcaEdocs
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["sigla", "nome", "id_externo"]
    ordering_fields = ["nome", "sigla", "ativo", "coletar_detalhes", "atualizado_em"]
    ordering = ["nome", "id"]
    mapa_permissoes = {
        "list": "view_patriarcaedocs",
        "retrieve": "view_patriarcaedocs",
        "selecao_coleta": "selecionar_patriarcas_coleta",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        ativo = _parametro_booleano(self.request, "ativo")
        coletar = _parametro_booleano(self.request, "coletar_detalhes")
        if ativo is not None:
            consulta = consulta.filter(ativo=ativo)
        if coletar is not None:
            consulta = consulta.filter(coletar_detalhes=coletar)
        return consulta

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        autorizacao = AuthorizationService(
            self.request.user,
            getattr(self.request, "application", None),
        )
        contexto["pode_selecionar"] = autorizacao.can(
            "selecionar_patriarcas_coleta"
        )
        return contexto

    @extend_schema(
        request=SerializadorSelecaoColeta,
        responses=SerializadorPatriarcaEdocs,
    )
    @action(detail=True, methods=["patch"], url_path="selecao-coleta")
    def selecao_coleta(self, request, pk=None):
        patriarca = self.get_object()
        entrada = SerializadorSelecaoColeta(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            patriarca = definir_selecao_coleta_patriarca(
                patriarca.pk,
                ator=_ator_do_usuario(request.user),
                **entrada.validated_data,
            )
        except ErroDecisaoPatriarcaEdocs as exc:
            raise ConflitoCatalogoEdocs(str(exc)) from exc
        return Response(self.get_serializer(patriarca).data)


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoColetaPatriarcasEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Lista execuções e permite solicitar uma nova comparação remota."""

    queryset = ColetaPatriarcasEdocs.objects.all()
    serializer_class = SerializadorColetaPatriarcasEdocs
    filter_backends = [OrderingFilter]
    ordering_fields = ["iniciada_em", "concluida_em", "situacao"]
    ordering = ["-iniciada_em"]
    mapa_permissoes = {
        "list": "view_coletapatriarcasedocs",
        "retrieve": "view_coletapatriarcasedocs",
        "create": "solicitar_coleta_patriarcas_edocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        situacao = _parametro_escolha(
            self.request,
            "situacao",
            SituacaoColetaPatriarcas.values,
        )
        return consulta.filter(situacao=situacao) if situacao else consulta

    @extend_schema(
        request=None,
        responses={status.HTTP_201_CREATED: SerializadorColetaPatriarcasEdocs},
    )
    def create(self, request, *args, **kwargs):
        coleta = sincronizar_patriarcas_edocs(ator=_ator_do_usuario(request.user))
        return Response(
            self.get_serializer(coleta).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoDivergenciaPatriarcaEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Consulta divergências e recebe uma decisão humana explícita."""

    queryset = DivergenciaPatriarcaEdocs.objects.select_related(
        "coleta", "patriarca"
    )
    serializer_class = SerializadorDivergenciaPatriarcaEdocs
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "situacao", "comparacao"]
    ordering = ["-criado_em", "-id"]
    mapa_permissoes = {
        "list": "view_divergenciapatriarcaedocs",
        "retrieve": "view_divergenciapatriarcaedocs",
        "decidir": "revisar_patriarcas_edocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        filtros = {
            "situacao": _parametro_escolha(
                self.request,
                "situacao",
                SituacaoDivergenciaPatriarca.values,
            ),
            "comparacao": _parametro_escolha(
                self.request,
                "comparacao",
                TipoComparacaoPatriarca.values,
            ),
            "coleta_id": _parametro_uuid(self.request, "coleta_id"),
            "patriarca_id": _parametro_inteiro(self.request, "patriarca_id"),
        }
        for campo, valor in filtros.items():
            if valor is not None:
                consulta = consulta.filter(**{campo: valor})
        return consulta

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        autorizacao = AuthorizationService(
            self.request.user,
            getattr(self.request, "application", None),
        )
        contexto["pode_revisar"] = autorizacao.can("revisar_patriarcas_edocs")
        return contexto

    @extend_schema(
        request=SerializadorDecisaoDivergencia,
        responses=SerializadorDivergenciaPatriarcaEdocs,
    )
    @action(detail=True, methods=["post"])
    def decidir(self, request, pk=None):
        divergencia = self.get_object()
        entrada = SerializadorDecisaoDivergencia(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            divergencia = aplicar_decisao_divergencia_patriarca(
                divergencia.pk,
                ator=_ator_do_usuario(request.user),
                **entrada.validated_data,
            )
        except ErroDecisaoPatriarcaEdocs as exc:
            raise ConflitoCatalogoEdocs(str(exc)) from exc
        return Response(self.get_serializer(divergencia).data)


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoEventoAuditoriaPatriarcaEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Expõe, sem mutação, os fatos e decisões do catálogo."""

    queryset = EventoAuditoriaPatriarcaEdocs.objects.select_related(
        "coleta", "patriarca", "divergencia"
    )
    serializer_class = SerializadorEventoAuditoriaPatriarcaEdocs
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "tipo_evento"]
    ordering = ["-criado_em", "-id"]
    mapa_permissoes = {
        "list": "view_eventoauditoriapatriarcaedocs",
        "retrieve": "view_eventoauditoriapatriarcaedocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        filtros = {
            "tipo_evento": _parametro_escolha(
                self.request,
                "tipo_evento",
                TipoEventoAuditoriaPatriarca.values,
            ),
            "coleta_id": _parametro_uuid(self.request, "coleta_id"),
            "patriarca_id": _parametro_inteiro(self.request, "patriarca_id"),
            "divergencia_id": _parametro_inteiro(
                self.request,
                "divergencia_id",
            ),
        }
        for campo, valor in filtros.items():
            if valor is not None:
                consulta = consulta.filter(**{campo: valor})
        return consulta
