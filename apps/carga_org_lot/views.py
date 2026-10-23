"""API da aplicação de carga de organograma e lotação."""

from __future__ import annotations

from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import (
    Count,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core.permissions import CanPermission
from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from .exceptions import (
    SpreadsheetImportValidationError,
    SubtreeDeletionConfirmationRequired,
)
from .models import (
    AlternativaResolucaoValidacao,
    CargoReferenciaGlobal,
    CasoValidacaoImportacao,
    ConjuntoLotacao,
    DetalheStatusCarga,
    EnvioOrganogramaProdest,
    EventoIntegracaoProdest,
    ImportacaoPlanilha,
    ItemLotacao,
    ItemLotacaoImportado,
    ItemOrganograma,
    MapeamentoCargoPatriarca,
    OcorrenciaCargoImportacao,
    Patriarca,
    ProcessoCargaInicial,
    RelatorioValidacaoImportacao,
    ResolucaoValidacao,
    StatusCarga,
    StatusImportacaoLocal,
    StatusItemLotacaoImportado,
    SituacaoConjuntoLotacao,
    StatusProgresso,
    TipoCarga,
    TokenEnvioCarga,
    VariacaoCargoGlobal,
)
from .serializers import (
    AlternativaResolucaoValidacaoSerializer,
    AcaoConjuntoLotacaoSerializer,
    CasoValidacaoImportacaoSerializer,
    CargoReferenciaGlobalSerializer,
    ConjuntoLotacaoSerializer,
    ConsultarCargasIniciaisProdestSerializer,
    CriarOrganogramaInicialSerializer,
    DetalheStatusCargaSerializer,
    EnvioOrganogramaProdestSerializer,
    EventoIntegracaoProdestSerializer,
    ImportacaoPlanilhaListSerializer,
    ImportacaoPlanilhaSerializer,
    HistoricoConjuntoLotacaoSerializer,
    ItemLotacaoSerializer,
    ItemLotacaoDescartadoSerializer,
    ItemLotacaoImportadoSerializer,
    ItemOrganogramaSerializer,
    MapeamentoCargoPatriarcaSerializer,
    OcorrenciaCargoImportacaoSerializer,
    PatriarcaSerializer,
    ProcessoCargaInicialSerializer,
    RelatorioValidacaoImportacaoSerializer,
    ResolverCasoValidacaoSerializer,
    ResolucaoValidacaoSerializer,
    SolicitarEnvioOrganogramaSerializer,
    StatusCargaSerializer,
    StatusProgressoSerializer,
    TipoCargaSerializer,
    TokenEnvioCargaSerializer,
    VariacaoCargoGlobalSerializer,
)
from .services.organograma import ORGANOGRAMA_TYPE_ID
from .services.lotacao_review import incorporate_lotation, resolve_validation_case
from .services.lotacao_pending_report import build_pending_lotation_report_xlsx
from .services.lotacao_sets import (
    activate_lotation_set,
    build_consolidated_lotation_xlsx,
    cancel_lotation_set,
    create_lotation_set,
    homologate_lotation_set,
)
from .services.validation_cases import (
    SUBJECT_LABELS,
    validation_case_subject,
    validation_subject_query,
)
from .services.organograma_editing import (
    build_initial_organogram_xlsx,
    build_updated_organogram_xlsx,
    deletion_impact,
    get_subtree_descendants,
)
from .services.cargarh import (
    CargaRHClient,
    CargaRHConfigurationError,
    CargaRHRequestError,
    configuration_status,
)
from .services.organogram_submission import (
    OrganogramSubmissionError,
    refresh_submission_report,
    refresh_submission_status,
    prepare_organogram_submission,
)
from .tasks import processar_envio_organograma
from .services.workflow import AuditActor, register_organogram_item_change


class DashboardCargaOrgLotView(APIView):
    permission_classes = [IsAuthenticated, CanPermission]
    required_permission = "view_importacaoplanilha"

    @extend_schema(responses={200: dict})
    def get(self, request):
        active = EnvioOrganogramaProdest.objects.select_related(
            "idimportacaoplanilha__idpatriarca",
            "idprocessocargainicial",
        ).filter(strstatus__in=["SOLICITANDO", "PROCESSANDO"])
        all_submissions = EnvioOrganogramaProdest.objects.all()
        today = timezone.localdate()
        return Response(
            {
                "gerado_em": timezone.now(),
                "resumo": {
                    "patriarcas": Patriarca.objects.count(),
                    "processos_em_andamento": active.count(),
                    "processos_com_erro": all_submissions.filter(
                        strstatus="ERRO"
                    ).count(),
                    "processos_concluidos_hoje": all_submissions.filter(
                        datfinalizacao__date=today,
                        strstatus__in=["CONCLUIDO", "CONCLUIDO_DESATUALIZADO"],
                    ).count(),
                },
                "processos_em_andamento": EnvioOrganogramaProdestSerializer(
                    active, many=True
                ).data,
            }
        )


class DashboardPublicoCargaOrgLotView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):
        active = EnvioOrganogramaProdest.objects.select_related(
            "idimportacaoplanilha__idpatriarca"
        ).filter(strstatus__in=["SOLICITANDO", "PROCESSANDO"])
        return Response(
            {
                "gerado_em": timezone.now(),
                "processos_em_andamento": [
                    {
                        "patriarca_nome": item.idimportacaoplanilha.idpatriarca.strnome,
                        "tipo_carga": "ORGANOGRAMA",
                        "modo": "SIMULACAO" if item.flgdryrun else "DEFINITIVO",
                        "fase_atual": item.strfaseatual,
                        "fase_atual_nome": item.get_strfaseatual_display(),
                        "status_atual": item.strstatusoperacional,
                        "datultimaatividade": item.datultimaatividade,
                    }
                    for item in active
                ],
            }
        )


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


@tag_all_actions("4 - Carga Org/Lot")
class PatriarcaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = Patriarca.objects.select_related("idstatusprogresso").all()
    serializer_class = PatriarcaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strsiglapatriarca",
        "strnome",
        "datcriacao",
        "datalteracao",
        "idpatriarca",
    ]
    ordering = ["strsiglapatriarca", "idpatriarca"]
    ordering_tie_breaker = "idpatriarca"
    permission_map = {
        "list": "view_patriarca",
        "retrieve": "view_patriarca",
        "create": "add_patriarca",
        "update": "change_patriarca",
        "partial_update": "change_patriarca",
        "destroy": "delete_patriarca",
        "download_organograma": "view_importacaoplanilha",
    }

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        },
        description=(
            "Baixa a planilha da importação de organograma mais recente "
            "do patriarca."
        ),
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="organograma/download",
    )
    def download_organograma(self, request, *args, **kwargs):
        patriarca = self.get_object()
        importacao = (
            patriarca.importacoes.filter(idtipocarga_id=ORGANOGRAMA_TYPE_ID)
            .exclude(strstatusimportacao=StatusImportacaoLocal.REJEITADA)
            .order_by("-datimportacao", "-idimportacaoplanilha")
            .first()
        )
        if importacao is None:
            raise NotFound(
                "O patriarca ainda não possui uma planilha de organograma importada."
            )
        return spreadsheet_download_response(importacao)


class BaseCatalogViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    viewsets.ModelViewSet,
):
    pagination_class = None


@tag_all_actions("4 - Carga Org/Lot")
class StatusCargaViewSet(BaseCatalogViewSet):
    queryset = StatusCarga.objects.order_by("idstatuscarga")
    serializer_class = StatusCargaSerializer
    permission_map = {
        "list": "view_statuscarga",
        "retrieve": "view_statuscarga",
        "create": "add_statuscarga",
        "update": "change_statuscarga",
        "partial_update": "change_statuscarga",
        "destroy": "delete_statuscarga",
    }


@tag_all_actions("4 - Carga Org/Lot")
class StatusProgressoViewSet(BaseCatalogViewSet):
    queryset = StatusProgresso.objects.order_by("idstatusprogresso")
    serializer_class = StatusProgressoSerializer
    permission_map = {
        "list": "view_statusprogresso",
        "retrieve": "view_statusprogresso",
        "create": "add_statusprogresso",
        "update": "change_statusprogresso",
        "partial_update": "change_statusprogresso",
        "destroy": "delete_statusprogresso",
    }


@tag_all_actions("4 - Carga Org/Lot")
class TipoCargaViewSet(BaseCatalogViewSet):
    queryset = TipoCarga.objects.order_by("idtipocarga")
    serializer_class = TipoCargaSerializer
    permission_map = {
        "list": "view_tipocarga",
        "retrieve": "view_tipocarga",
        "create": "add_tipocarga",
        "update": "change_tipocarga",
        "partial_update": "change_tipocarga",
        "destroy": "delete_tipocarga",
    }


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


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "patriarca",
                int,
                description="Filtra pelo ID interno do patriarca.",
            ),
            OpenApiParameter(
                "ativo",
                bool,
                description="Filtra processos ativos ou encerrados.",
            ),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ProcessoCargaInicialViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ProcessoCargaInicial.objects.select_related(
        "idpatriarca"
    ).prefetch_related("historico")
    serializer_class = ProcessoCargaInicialSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["databertura", "idprocessocargainicial"]
    ordering = ["-databertura", "-idprocessocargainicial"]
    ordering_tie_breaker = "idprocessocargainicial"
    permission_map = {
        "list": "view_patriarca",
        "retrieve": "view_patriarca",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        patriarca = self.request.query_params.get("patriarca")
        if patriarca is not None:
            if not patriarca.isdecimal():
                raise serializers.ValidationError(
                    {"patriarca": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(idpatriarca_id=int(patriarca))
        ativo = self.request.query_params.get("ativo")
        if ativo is not None:
            normalized = ativo.lower()
            if normalized not in {"true", "false"}:
                raise serializers.ValidationError(
                    {"ativo": "Informe true ou false."}
                )
            queryset = queryset.filter(flgativo=normalized == "true")
        return queryset


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "patriarca",
                int,
                description="Filtra pelo ID interno do patriarca.",
            ),
            OpenApiParameter(
                "tipo_carga",
                int,
                description="Filtra pelo ID do tipo de carga.",
            ),
            OpenApiParameter(
                "status",
                int,
                description="Filtra pelo ID do status de progresso.",
            ),
            OpenApiParameter(
                "status_importacao",
                str,
                description="Filtra pelo status local da importação.",
            ),
            OpenApiParameter(
                "organograma",
                int,
                description="Filtra pela importação de organograma de referência.",
            ),
            OpenApiParameter(
                "conjunto_lotacao",
                int,
                description="Filtra pelo conjunto histórico de lotação.",
            ),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ImportacaoPlanilhaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    _organogram_item_count = (
        ItemOrganograma.objects.filter(idimportacaoplanilha_id=OuterRef("pk"))
        .order_by()
        .values("idimportacaoplanilha_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    _lotation_item_count = (
        ItemLotacao.objects.filter(idimportacaoplanilha_id=OuterRef("pk"))
        .order_by()
        .values("idimportacaoplanilha_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    _staged_lotation_item_count = (
        ItemLotacaoImportado.objects.filter(
            idimportacaoplanilha_id=OuterRef("pk")
        )
        .order_by()
        .values("idimportacaoplanilha_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    _pending_case_count = (
        CasoValidacaoImportacao.objects.filter(
            idrelatoriovalidacao__idimportacaoplanilha_id=OuterRef("pk"),
            strstatus="PENDENTE",
        )
        .order_by()
        .values("idrelatoriovalidacao__idimportacaoplanilha_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    queryset = ImportacaoPlanilha.objects.select_related(
        "idpatriarca",
        "idpatriarca__idstatusprogresso",
        "idtipocarga",
        "idstatusprogresso",
        "idimportacaoorganograma",
        "idprocessocargainicial",
        "relatorio_validacao",
    ).annotate(
        total_itens_organograma=Coalesce(
            Subquery(_organogram_item_count, output_field=IntegerField()),
            Value(0),
        ),
        total_itens_lotacao=Coalesce(
            Subquery(_lotation_item_count, output_field=IntegerField()),
            Value(0),
        ),
        total_itens_lotacao_importados=Coalesce(
            Subquery(
                _staged_lotation_item_count,
                output_field=IntegerField(),
            ),
            Value(0),
        ),
        total_casos_pendentes=Coalesce(
            Subquery(_pending_case_count, output_field=IntegerField()),
            Value(0),
        ),
    )
    serializer_class = ImportacaoPlanilhaSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "datimportacao",
        "strnomearquivo",
        "inttamanhoarquivo",
        "idimportacaoplanilha",
    ]
    ordering = ["-datimportacao", "-idimportacaoplanilha"]
    ordering_tie_breaker = "idimportacaoplanilha"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "create": "add_importacaoplanilha",
        "upload": "add_importacaoplanilha",
        "criar_organograma_inicial": "add_importacaoplanilha",
        "download": "view_importacaoplanilha",
        "download_pendencias": "view_importacaoplanilha",
        "download_organograma_atualizado": "view_importacaoplanilha",
        "relatorio": "view_importacaoplanilha",
        "update": "change_importacaoplanilha",
        "partial_update": "change_importacaoplanilha",
        "destroy": "delete_importacaoplanilha",
        "incorporar_lotacao": "change_importacaoplanilha",
    }

    def get_serializer_class(self):
        if self.action == "list":
            return ImportacaoPlanilhaListSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in {"retrieve", "relatorio", "incorporar_lotacao"}:
            cases = CasoValidacaoImportacao.objects.prefetch_related(
                "alternativas",
                "resolucoes",
                "itens",
                "ocorrencias",
            )
            queryset = queryset.prefetch_related(
                "idprocessocargainicial__historico",
                "relatorio_validacao__ocorrencias",
                Prefetch("relatorio_validacao__casos", queryset=cases),
            )
        filters = {
            "patriarca": "idpatriarca_id",
            "tipo_carga": "idtipocarga_id",
            "status": "idstatusprogresso_id",
            "organograma": "idimportacaoorganograma_id",
            "conjunto_lotacao": "idconjuntolotacao_id",
        }
        for parameter, model_field in filters.items():
            value = self.request.query_params.get(parameter)
            if value is None:
                continue
            if not value.isdecimal():
                raise serializers.ValidationError(
                    {parameter: "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(**{model_field: int(value)})
        status_importacao = self.request.query_params.get("status_importacao")
        if status_importacao is not None:
            valid_statuses = {choice for choice, _ in StatusImportacaoLocal.choices}
            if status_importacao not in valid_statuses:
                raise serializers.ValidationError(
                    {"status_importacao": "Informe um status de importação válido."}
                )
            queryset = queryset.filter(strstatusimportacao=status_importacao)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        instance = serializer.instance
        if instance.strstatusimportacao == StatusImportacaoLocal.REJEITADA:
            report = dict(instance.relatorio_validacao.jsonresumo)
            report["idimportacaoplanilha"] = instance.pk
            raise SpreadsheetImportValidationError(report)

    @transaction.atomic
    def perform_destroy(self, instance):
        """Exclui fisicamente a importação, seu arquivo e os itens em cascata."""
        if instance.idconjuntolotacao_id is not None:
            raise serializers.ValidationError(
                "Importações vinculadas a um conjunto são históricas e não podem "
                "ser excluídas. Cancele o conjunto quando necessário."
            )
        super().perform_destroy(instance)

    @extend_schema(
        request=ImportacaoPlanilhaSerializer,
        responses={status.HTTP_201_CREATED: ImportacaoPlanilhaSerializer},
    )
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @extend_schema(
        request=CriarOrganogramaInicialSerializer,
        responses={status.HTTP_201_CREATED: ImportacaoPlanilhaSerializer},
        description=(
            "Gera um XLSX inicial com o patriarca, GAB, SEFAZ, SESA e SEMED, "
            "incluindo uma unidade espelho para cada órgão, e o importa pelo "
            "mesmo fluxo de validação das planilhas enviadas."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="criar-organograma-inicial",
    )
    def criar_organograma_inicial(self, request, *args, **kwargs):
        request_serializer = CriarOrganogramaInicialSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        patriarca = request_serializer.validated_data["idpatriarca"]
        content = build_initial_organogram_xlsx(
            patriarch_name=patriarca.strnome,
            patriarch_acronym=patriarca.strsiglapatriarca,
        )
        safe_acronym = get_valid_filename(patriarca.strsiglapatriarca)
        filename = f"organograma_inicial_{safe_acronym}.xlsx"
        spreadsheet = SimpleUploadedFile(
            filename,
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        serializer = self.get_serializer(
            data={
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": ORGANOGRAMA_TYPE_ID,
                "strreferencia": request_serializer.validated_data[
                    "strreferencia"
                ],
                "arquivo": spreadsheet,
            }
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        }
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, *args, **kwargs):
        importacao = self.get_object()
        return spreadsheet_download_response(importacao)

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        },
        description=(
            "Gera uma planilha objetiva com todas as ocorrências dos casos de "
            "validação que ainda estão pendentes na importação de lotação."
        ),
    )
    @action(detail=True, methods=["get"], url_path="pendencias/download")
    def download_pendencias(self, request, *args, **kwargs):
        importacao = self.get_object()
        if importacao.idtipocarga_id not in {4, 5}:
            raise NotFound("A importação informada não é uma lotação.")
        try:
            content, summary = build_pending_lotation_report_xlsx(importacao)
        except RelatorioValidacaoImportacao.DoesNotExist as exc:
            raise NotFound(
                "A importação ainda não possui relatório de validação."
            ) from exc
        if summary["total"] == 0:
            raise serializers.ValidationError(
                {"pendencias": "A importação não possui pendências em aberto."}
            )

        filename = get_valid_filename(
            "pendencias_"
            f"{importacao.idpatriarca.strsiglapatriarca}_"
            f"{importacao.pk}.xlsx"
        )
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = content_disposition_header(True, filename)
        response["Content-Length"] = len(content)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        },
        description=(
            "Gera o organograma atualizado a partir dos itens persistidos. "
            "Disponível após edição manual ou geração automática de unidades."
        ),
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="organograma-atualizado/download",
    )
    def download_organograma_atualizado(self, request, *args, **kwargs):
        importacao = self.get_object()
        if importacao.idtipocarga_id != ORGANOGRAMA_TYPE_ID:
            raise NotFound("A importação informada não é um organograma.")
        if not importacao.flgpossuialteracoes:
            raise NotFound("O organograma ainda não possui alterações.")

        content = build_updated_organogram_xlsx(importacao)
        filename = (
            f"organograma_atualizado_{importacao.idpatriarca.strsiglapatriarca}.xlsx"
        )
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = content_disposition_header(True, filename)
        response["Content-Length"] = len(content)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(
        responses={status.HTTP_200_OK: RelatorioValidacaoImportacaoSerializer}
    )
    @action(detail=True, methods=["get"], url_path="relatorio")
    def relatorio(self, request, *args, **kwargs):
        importacao = self.get_object()
        try:
            report = importacao.relatorio_validacao
        except RelatorioValidacaoImportacao.DoesNotExist as exc:
            raise NotFound(
                "A importação ainda não possui relatório de validação."
            ) from exc
        serializer = RelatorioValidacaoImportacaoSerializer(
            report,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @extend_schema(
        request=None,
        responses={status.HTTP_200_OK: ImportacaoPlanilhaSerializer},
        description=(
            "Incorpora os itens de lotação aceitos após todos os casos de "
            "erro e aviso terem sido resolvidos."
        ),
    )
    @action(detail=True, methods=["post"], url_path="incorporar-lotacao")
    def incorporar_lotacao(self, request, *args, **kwargs):
        importacao = self.get_object()
        actor = AuditActor(
            user_id=request.user.pk,
            user_name=AuditableMixin._resolve_user_name(request.user),
        )
        incorporate_lotation(importacao, actor)
        importacao = self.get_queryset().get(pk=importacao.pk)
        return Response(self.get_serializer(importacao).data)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("patriarca", int),
            OpenApiParameter("organograma", int),
            OpenApiParameter("situacao", str),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ConjuntoLotacaoViewSet(
    PermissionedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ConjuntoLotacao.objects.select_related(
        "idpatriarca",
        "idimportacaoorganograma",
        "idconjuntoanterior",
    ).prefetch_related(
        "importacoes__itens_lotacao",
        "importacoes__itens_lotacao_importados",
        "importacoes__relatorio_validacao__casos",
        "conjuntos_substitutos",
    )
    serializer_class = ConjuntoLotacaoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strreferencia",
        "strsituacao",
        "created_at",
        "updated_at",
        "idconjuntolotacao",
    ]
    ordering = ["-created_at", "-idconjuntolotacao"]
    ordering_tie_breaker = "idconjuntolotacao"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "create": "add_importacaoplanilha",
        "adicionar_importacao": "add_importacaoplanilha",
        "homologar": "change_importacaoplanilha",
        "ativar": "change_importacaoplanilha",
        "cancelar": "change_importacaoplanilha",
        "download_consolidado": "view_importacaoplanilha",
        "historico": "view_importacaoplanilha",
        "resumo": "view_importacaoplanilha",
        "resumo_organograma": "view_importacaoplanilha",
    }

    @staticmethod
    def _actor(request) -> AuditActor:
        return AuditActor(
            user_id=request.user.pk,
            user_name=AuditableMixin._resolve_user_name(request.user),
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        integer_filters = {
            "patriarca": "idpatriarca_id",
            "organograma": "idimportacaoorganograma_id",
        }
        for parameter, field in integer_filters.items():
            value = self.request.query_params.get(parameter)
            if value is not None:
                if not value.isdecimal():
                    raise serializers.ValidationError(
                        {parameter: "Informe um identificador numérico válido."}
                    )
                queryset = queryset.filter(**{field: int(value)})
        situation = self.request.query_params.get("situacao")
        if situation:
            valid = {value for value, _ in SituacaoConjuntoLotacao.choices}
            if situation not in valid:
                raise serializers.ValidationError(
                    {"situacao": "Informe uma situação de conjunto válida."}
                )
            queryset = queryset.filter(strsituacao=situation)
        reference = self.request.query_params.get("referencia", "").strip()
        if reference:
            queryset = queryset.filter(strreferencia__icontains=reference)
        for parameter, lookup in {
            "data_inicio": "created_at__date__gte",
            "data_fim": "created_at__date__lte",
        }.items():
            value = self.request.query_params.get(parameter)
            if not value:
                continue
            parsed = parse_date(value)
            if parsed is None:
                raise serializers.ValidationError(
                    {parameter: "Informe uma data válida no formato AAAA-MM-DD."}
                )
            queryset = queryset.filter(**{lookup: parsed})
        return queryset

    def create(self, request, *args, **kwargs):
        request_serializer = self.get_serializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data
        conjunto = create_lotation_set(
            patriarca=data["idpatriarca"],
            organograma=data["idimportacaoorganograma"],
            reference=data.get("strreferencia", ""),
            actor=self._actor(request),
        )
        response_serializer = self.get_serializer(conjunto)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=ImportacaoPlanilhaSerializer,
        responses={status.HTTP_201_CREATED: ImportacaoPlanilhaSerializer},
        description="Adiciona uma nova planilha imutável ao conjunto.",
    )
    @action(detail=True, methods=["post"], url_path="importacoes")
    def adicionar_importacao(self, request, *args, **kwargs):
        conjunto = self.get_object()
        data = request.data.copy()
        data["idpatriarca_id"] = conjunto.idpatriarca_id
        data["idimportacaoorganograma_id"] = conjunto.idimportacaoorganograma_id
        data["idconjuntolotacao_id"] = conjunto.pk
        if not data.get("idtipocarga_id"):
            data["idtipocarga_id"] = 4
        serializer = ImportacaoPlanilhaSerializer(
            data=data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        actor = self._actor(request)
        instance = serializer.save(
            created_by_id=actor.user_id,
            created_by_name=actor.user_name,
            updated_by_id=actor.user_id,
            updated_by_name=actor.user_name,
        )
        if instance.strstatusimportacao == StatusImportacaoLocal.REJEITADA:
            report = dict(instance.relatorio_validacao.jsonresumo)
            report["idimportacaoplanilha"] = instance.pk
            raise SpreadsheetImportValidationError(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _execute_transition(self, request, transition):
        request_serializer = AcaoConjuntoLotacaoSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        conjunto = transition(
            self.get_object(),
            justification=request_serializer.validated_data["justificativa"],
            actor=self._actor(request),
        )
        return Response(self.get_serializer(conjunto).data)

    @extend_schema(
        request=AcaoConjuntoLotacaoSerializer,
        responses={status.HTTP_200_OK: ConjuntoLotacaoSerializer},
    )
    @action(detail=True, methods=["post"])
    def homologar(self, request, *args, **kwargs):
        return self._execute_transition(request, homologate_lotation_set)

    @extend_schema(
        request=AcaoConjuntoLotacaoSerializer,
        responses={status.HTTP_200_OK: ConjuntoLotacaoSerializer},
    )
    @action(detail=True, methods=["post"])
    def ativar(self, request, *args, **kwargs):
        return self._execute_transition(request, activate_lotation_set)

    @extend_schema(
        request=AcaoConjuntoLotacaoSerializer,
        responses={status.HTTP_200_OK: ConjuntoLotacaoSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancelar(self, request, *args, **kwargs):
        return self._execute_transition(request, cancel_lotation_set)

    @extend_schema(
        responses={
            (status.HTTP_200_OK, "application/octet-stream"): OpenApiTypes.BINARY
        }
    )
    @action(detail=True, methods=["get"], url_path="download-consolidado")
    def download_consolidado(self, request, *args, **kwargs):
        conjunto = self.get_object()
        content = build_consolidated_lotation_xlsx(conjunto)
        filename = f"lotacoes_consolidadas_{conjunto.pk}.xlsx"
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = content_disposition_header(
            True,
            filename,
        )
        return response

    @extend_schema(responses={status.HTTP_200_OK: HistoricoConjuntoLotacaoSerializer})
    @action(detail=True, methods=["get"])
    def historico(self, request, *args, **kwargs):
        conjunto = self.get_object()
        queryset = conjunto.historico.all()
        page = self.paginate_queryset(queryset)
        serializer = HistoricoConjuntoLotacaoSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(responses={status.HTTP_200_OK: dict})
    @action(detail=False, methods=["get"])
    def resumo(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        counts = {
            entry["strsituacao"]: entry["total"]
            for entry in queryset.values("strsituacao").annotate(total=Count("pk"))
        }
        return Response(
            {
                "total_conjuntos": sum(counts.values()),
                "por_situacao": [
                    {
                        "situacao": value,
                        "nome": label,
                        "total": counts.get(value, 0),
                    }
                    for value, label in SituacaoConjuntoLotacao.choices
                ],
            }
        )

    @extend_schema(responses={status.HTTP_200_OK: dict})
    @action(detail=False, methods=["get"], url_path="resumo-organograma")
    def resumo_organograma(self, request, *args, **kwargs):
        organograma = request.query_params.get("organograma")
        if not organograma or not organograma.isdecimal():
            raise serializers.ValidationError(
                {"organograma": "Informe um identificador numérico válido."}
            )
        queryset = self.get_queryset().filter(
            idimportacaoorganograma_id=int(organograma)
        )
        active = queryset.filter(strsituacao=SituacaoConjuntoLotacao.ATIVO).first()
        situation_counts = {
            entry["strsituacao"]: entry["total"]
            for entry in queryset.values("strsituacao").annotate(total=Count("pk"))
        }
        return Response(
            {
                "idimportacaoorganograma": int(organograma),
                "total_conjuntos": queryset.count(),
                "total_importacoes": ImportacaoPlanilha.objects.filter(
                    idconjuntolotacao__in=queryset
                ).count(),
                "conjuntos_em_validacao": queryset.filter(
                    strsituacao=SituacaoConjuntoLotacao.EM_VALIDACAO
                ).count(),
                "conjuntos_com_pendencias": queryset.filter(
                    strsituacao=SituacaoConjuntoLotacao.COM_PENDENCIAS
                ).count(),
                "por_situacao": [
                    {
                        "situacao": value,
                        "nome": label,
                        "total": situation_counts.get(value, 0),
                    }
                    for value, label in SituacaoConjuntoLotacao.choices
                ],
                "conjunto_ativo": (
                    self.get_serializer(active).data if active is not None else None
                ),
            }
        )


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "importacao",
                int,
                description="Filtra pela versão importada do organograma.",
            ),
            OpenApiParameter(
                "pai",
                int,
                description="Filtra pelo item pai; use 'raiz' para a raiz.",
            ),
        ]
    )
)
@tag_all_actions("4 - Carga Org/Lot")
class ItemOrganogramaViewSet(
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
    AuditableMixin,
    viewsets.ModelViewSet,
):
    queryset = ItemOrganograma.objects.select_related(
        "idimportacaoplanilha",
        "idimportacaoplanilha__idpatriarca",
        "idpai",
    ).all()
    serializer_class = ItemOrganogramaSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strnumero",
        "strsigla",
        "strnome",
        "intlinhaorigem",
        "iditemorganograma",
    ]
    ordering = ["strnumero", "intlinhaorigem", "iditemorganograma"]
    ordering_tie_breaker = "iditemorganograma"
    permission_map = {
        "list": "view_itemorganograma",
        "retrieve": "view_itemorganograma",
        "create": "add_itemorganograma",
        "update": "change_itemorganograma",
        "partial_update": "change_itemorganograma",
        "destroy": "delete_itemorganograma",
        "impacto_exclusao": "view_itemorganograma",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        importacao = self.request.query_params.get("importacao")
        if importacao is not None:
            if not importacao.isdecimal():
                raise serializers.ValidationError(
                    {"importacao": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(idimportacaoplanilha_id=int(importacao))

        pai = self.request.query_params.get("pai")
        if pai == "raiz":
            queryset = queryset.filter(idpai__isnull=True)
        elif pai is not None:
            if not pai.isdecimal():
                raise serializers.ValidationError(
                    {"pai": "Informe um identificador numérico ou 'raiz'."}
                )
            queryset = queryset.filter(idpai_id=int(pai))
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        item = serializer.instance
        register_organogram_item_change(
            item.idimportacaoplanilha,
            actor=self._audit_actor(),
            action="ITEM_ORGANOGRAMA_INCLUIDO",
            message=f"Unidade {item.strsigla} incluída manualmente no organograma.",
            details={"item": self._item_snapshot(item)},
        )

    def perform_update(self, serializer):
        before = self._item_snapshot(serializer.instance)
        super().perform_update(serializer)
        item = serializer.instance
        register_organogram_item_change(
            item.idimportacaoplanilha,
            actor=self._audit_actor(),
            action="ITEM_ORGANOGRAMA_ALTERADO",
            message=f"Unidade {item.strsigla} alterada no organograma.",
            details={"antes": before, "depois": self._item_snapshot(item)},
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "confirmar_subarvore",
                bool,
                description=(
                    "Obrigatório como true quando a unidade possui descendentes."
                ),
            )
        ]
    )
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        item = self.get_object()
        descendants = get_subtree_descendants(item)
        impact = deletion_impact(item, descendants)
        confirmed = request.query_params.get("confirmar_subarvore", "").lower()
        if descendants and confirmed != "true":
            raise SubtreeDeletionConfirmationRequired(impact)

        register_organogram_item_change(
            item.idimportacaoplanilha,
            actor=self._audit_actor(),
            action=(
                "SUBARVORE_ORGANOGRAMA_EXCLUIDA"
                if descendants
                else "ITEM_ORGANOGRAMA_EXCLUIDO"
            ),
            message=(
                f"Unidade {item.strsigla} e {len(descendants)} unidade(s) "
                "subordinada(s) excluídas do organograma."
            ),
            details={"impacto": impact},
        )
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(description="Calcula as unidades afetadas pela exclusão.")
    @action(detail=True, methods=["get"], url_path="impacto-exclusao")
    def impacto_exclusao(self, request, *args, **kwargs):
        item = self.get_object()
        return Response(deletion_impact(item))

    def _audit_actor(self) -> AuditActor:
        return AuditActor(
            user_id=self.request.user.pk,
            user_name=self._resolve_user_name(self.request.user),
        )

    @staticmethod
    def _item_snapshot(item: ItemOrganograma) -> dict:
        return {
            "iditemorganograma": item.pk,
            "idpai_id": item.idpai_id,
            "strnumero": item.strnumero,
            "strnome": item.strnome,
            "strsigla": item.strsigla,
            "strresponsavel": item.strresponsavel,
            "strcargo": item.strcargo,
        }


@tag_all_actions("4 - Carga Org/Lot")
class ItemLotacaoViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ItemLotacao.objects.select_related(
        "idimportacaoplanilha",
        "idimportacaoplanilha__idpatriarca",
        "idimportacaoplanilha__idimportacaoorganograma",
        "idimportacaoplanilha__idconjuntolotacao",
        "idorgaoorganograma",
        "idunidadeorganograma",
        "idcargoreferencia",
    ).all()
    serializer_class = ItemLotacaoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strabaorigem",
        "intlinhaorigem",
        "strsiglaorgao",
        "strsiglaunidade",
        "strnomeservidor",
        "strcpf",
        "strcargonormalizado",
        "iditemlotacao",
    ]
    ordering = ["strabaorigem", "intlinhaorigem", "iditemlotacao"]
    ordering_tie_breaker = "iditemlotacao"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        integer_filters = {
            "importacao": "idimportacaoplanilha_id",
            "orgao": "idorgaoorganograma_id",
            "unidade": "idunidadeorganograma_id",
            "conjunto_lotacao": "idimportacaoplanilha__idconjuntolotacao_id",
            "patriarca": "idimportacaoplanilha__idpatriarca_id",
            "organograma": "idimportacaoplanilha__idimportacaoorganograma_id",
            "cargo_referencia": "idcargoreferencia_id",
        }
        for parameter, field_name in integer_filters.items():
            value = self.request.query_params.get(parameter)
            if value is None:
                continue
            if not value.isdecimal():
                raise serializers.ValidationError(
                    {parameter: "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(**{field_name: int(value)})
        text_filters = {
            "cpf": "strcpf",
            "aba": "strabaorigem",
        }
        for parameter, field_name in text_filters.items():
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{field_name: value.strip()})
        person_name = self.request.query_params.get("nome", "").strip()
        if person_name:
            queryset = queryset.filter(strnomeservidor__icontains=person_name)
        position = self.request.query_params.get("cargo", "").strip()
        if position:
            queryset = queryset.filter(
                Q(strcargooriginal__icontains=position)
                | Q(strcargonormalizado__icontains=position)
                | Q(idcargoreferencia__strnome__icontains=position)
            )
        search = self.request.query_params.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(strnomeservidor__icontains=search)
                | Q(strcpf__icontains=search)
            )
        vigente = self.request.query_params.get("vigente")
        if vigente is not None:
            if vigente.lower() not in {"true", "false"}:
                raise serializers.ValidationError(
                    {"vigente": "Informe true ou false."}
                )
            active_filter = {
                "idimportacaoplanilha__idconjuntolotacao__strsituacao": (
                    SituacaoConjuntoLotacao.ATIVO
                )
            }
            if vigente.lower() == "true":
                queryset = queryset.filter(**active_filter)
            else:
                queryset = queryset.exclude(**active_filter)
        return queryset


@tag_all_actions("4 - Carga Org/Lot")
class ItemLotacaoImportadoViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ItemLotacaoImportado.objects.select_related(
        "idimportacaoplanilha",
        "idimportacaoplanilha__idpatriarca",
        "idimportacaoplanilha__idimportacaoorganograma",
        "idimportacaoplanilha__idconjuntolotacao",
        "idorgaoorganograma",
        "idunidadeorganograma",
        "idcargoreferencia",
    ).prefetch_related(
        "casos_validacao__resolucoes",
    )
    serializer_class = ItemLotacaoImportadoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strabaorigem",
        "intlinhaorigem",
        "strsituacao",
        "strnomeservidor",
        "strcpf",
        "iditemlotacaoimportado",
    ]
    ordering = ["strabaorigem", "intlinhaorigem", "iditemlotacaoimportado"]
    ordering_tie_breaker = "iditemlotacaoimportado"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "descartados": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in {
            "importacao": "idimportacaoplanilha_id",
            "conjunto": "idimportacaoplanilha__idconjuntolotacao_id",
            "patriarca": "idimportacaoplanilha__idpatriarca_id",
            "organograma": "idimportacaoplanilha__idimportacaoorganograma_id",
        }.items():
            value = self.request.query_params.get(parameter)
            if value is None:
                continue
            if not value.isdecimal():
                raise serializers.ValidationError(
                    {parameter: "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(**{field: int(value)})
        situacao = self.request.query_params.get("situacao")
        if situacao:
            queryset = queryset.filter(strsituacao=situacao)
        code = self.request.query_params.get("codigo", "").strip()
        if code:
            queryset = queryset.filter(casos_validacao__strcodigo=code)
        discarded_by = self.request.query_params.get("descartado_por")
        if discarded_by is not None:
            if not discarded_by.isdecimal():
                raise serializers.ValidationError(
                    {"descartado_por": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(
                casos_validacao__resolucoes__stracao="DESCARTAR_LINHAS",
                casos_validacao__resolucoes__created_by_id=int(discarded_by),
            )
        for parameter, lookup in {
            "data_inicio": "casos_validacao__resolucoes__datresolucao__date__gte",
            "data_fim": "casos_validacao__resolucoes__datresolucao__date__lte",
        }.items():
            value = self.request.query_params.get(parameter)
            if not value:
                continue
            parsed = parse_date(value)
            if parsed is None:
                raise serializers.ValidationError(
                    {parameter: "Informe uma data válida no formato AAAA-MM-DD."}
                )
            queryset = queryset.filter(**{lookup: parsed})
        return queryset.distinct()

    @extend_schema(
        responses={
            status.HTTP_200_OK: ItemLotacaoDescartadoSerializer(many=True),
        }
    )
    @action(detail=False, methods=["get"])
    def descartados(self, request, *args, **kwargs):
        queryset = self.filter_queryset(
            self.get_queryset().filter(
                strsituacao=StatusItemLotacaoImportado.DESCARTADO,
                casos_validacao__resolucoes__stracao="DESCARTAR_LINHAS",
            )
        ).distinct()
        page = self.paginate_queryset(queryset)
        serializer = ItemLotacaoDescartadoSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


@tag_all_actions("4 - Carga Org/Lot")
class CasoValidacaoImportacaoViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = CasoValidacaoImportacao.objects.select_related(
        "idrelatoriovalidacao__idimportacaoplanilha",
        "idrelatoriovalidacao__idimportacaoplanilha__idpatriarca",
        "idrelatoriovalidacao__idimportacaoplanilha__idimportacaoorganograma",
        "idrelatoriovalidacao__idimportacaoplanilha__idconjuntolotacao",
    ).prefetch_related("itens", "ocorrencias", "alternativas", "resolucoes")
    serializer_class = CasoValidacaoImportacaoSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "strseveridade",
        "strstatus",
        "idcasovalidacao",
    ]
    ordering = ["strseveridade", "idcasovalidacao"]
    ordering_tie_breaker = "idcasovalidacao"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "resumo": "view_importacaoplanilha",
        "resolver": "change_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in {
            "importacao": "idrelatoriovalidacao__idimportacaoplanilha_id",
            "patriarca": (
                "idrelatoriovalidacao__idimportacaoplanilha__idpatriarca_id"
            ),
            "organograma": (
                "idrelatoriovalidacao__idimportacaoplanilha__"
                "idimportacaoorganograma_id"
            ),
            "conjunto": (
                "idrelatoriovalidacao__idimportacaoplanilha__idconjuntolotacao_id"
            ),
        }.items():
            value = self.request.query_params.get(parameter)
            if value is None:
                continue
            if not value.isdecimal():
                raise serializers.ValidationError(
                    {parameter: "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(**{field: int(value)})
        for parameter, field in {
            "status": "strstatus",
            "severidade": "strseveridade",
            "codigo": "strcodigo",
        }.items():
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{field: value})
        subject = self.request.query_params.get("assunto")
        if subject:
            try:
                queryset = queryset.filter(validation_subject_query(subject))
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"assunto": f"{exc} Opções: {', '.join(SUBJECT_LABELS)}."}
                ) from exc
        resolved_by = self.request.query_params.get("resolvido_por")
        if resolved_by is not None:
            if not resolved_by.isdecimal():
                raise serializers.ValidationError(
                    {"resolvido_por": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(resolucoes__created_by_id=int(resolved_by))
        for parameter, lookup in {
            "data_inicio": "created_at__date__gte",
            "data_fim": "created_at__date__lte",
        }.items():
            value = self.request.query_params.get(parameter)
            if not value:
                continue
            parsed = parse_date(value)
            if parsed is None:
                raise serializers.ValidationError(
                    {parameter: "Informe uma data válida no formato AAAA-MM-DD."}
                )
            queryset = queryset.filter(**{lookup: parsed})
        search = self.request.query_params.get("q", "").strip()
        if search:
            importation_prefix = "idrelatoriovalidacao__idimportacaoplanilha__"
            queryset = queryset.filter(
                Q(strtitulo__icontains=search)
                | Q(strmensagem__icontains=search)
                | Q(**{f"{importation_prefix}strreferencia__icontains": search})
                | Q(**{f"{importation_prefix}strnomearquivo__icontains": search})
                | Q(
                    **{
                        f"{importation_prefix}idpatriarca__strnome__icontains": (
                            search
                        )
                    }
                )
            )
        return queryset.distinct()

    @extend_schema(responses={status.HTTP_200_OK: dict})
    @action(detail=False, methods=["get"])
    def resumo(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        code_counts = queryset.values("strcodigo").annotate(total=Count("pk"))
        subject_counts = {key: 0 for key in SUBJECT_LABELS}
        for entry in code_counts:
            subject_counts[validation_case_subject(entry["strcodigo"])] += entry[
                "total"
            ]

        importation = "idrelatoriovalidacao__idimportacaoplanilha"
        return Response(
            {
                "total": queryset.count(),
                "por_assunto": [
                    {
                        "assunto": key,
                        "nome": label,
                        "total": subject_counts[key],
                    }
                    for key, label in SUBJECT_LABELS.items()
                ],
                "por_severidade": list(
                    queryset.values(severidade=F("strseveridade")).annotate(
                        total=Count("pk")
                    )
                ),
                "por_status": list(
                    queryset.values(status=F("strstatus")).annotate(
                        total=Count("pk")
                    )
                ),
                "por_patriarca": list(
                    queryset.values(
                        idpatriarca=F(f"{importation}__idpatriarca_id"),
                        nome=F(f"{importation}__idpatriarca__strnome"),
                    ).annotate(total=Count("pk"))
                ),
                "por_organograma": list(
                    queryset.values(
                        idimportacaoorganograma=F(
                            f"{importation}__idimportacaoorganograma_id"
                        ),
                        referencia=F(
                            f"{importation}__idimportacaoorganograma__strreferencia"
                        ),
                    ).annotate(total=Count("pk"))
                ),
                "por_conjunto": list(
                    queryset.values(
                        idconjuntolotacao=F(
                            f"{importation}__idconjuntolotacao_id"
                        ),
                        referencia=F(
                            f"{importation}__idconjuntolotacao__strreferencia"
                        ),
                    ).annotate(total=Count("pk"))
                ),
            }
        )

    @extend_schema(
        request=ResolverCasoValidacaoSerializer,
        responses={status.HTTP_200_OK: CasoValidacaoImportacaoSerializer},
    )
    @action(detail=True, methods=["post"], url_path="resolver")
    def resolver(self, request, *args, **kwargs):
        case = self.get_object()
        request_serializer = ResolverCasoValidacaoSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        actor = AuditActor(
            user_id=request.user.pk,
            user_name=AuditableMixin._resolve_user_name(request.user),
        )
        case = resolve_validation_case(
            case,
            action=request_serializer.validated_data["acao"],
            actor=actor,
            justification=request_serializer.validated_data["justificativa"],
            alternative=request_serializer.validated_data.get("alternativa"),
            changes=request_serializer.validated_data["alteracoes"],
            position_scope=request_serializer.validated_data["escopo_cargo"],
            remember_position=request_serializer.validated_data["memorizar_cargo"],
        )
        return Response(self.get_serializer(case).data)


@tag_all_actions("4 - Carga Org/Lot")
class AlternativaResolucaoValidacaoViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = AlternativaResolucaoValidacao.objects.select_related(
        "idcasovalidacao",
    ).all()
    serializer_class = AlternativaResolucaoValidacaoSerializer
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        case = self.request.query_params.get("caso")
        if case is not None:
            if not case.isdecimal():
                raise serializers.ValidationError(
                    {"caso": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(idcasovalidacao_id=int(case))
        return queryset


@tag_all_actions("4 - Carga Org/Lot")
class ResolucaoValidacaoViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ResolucaoValidacao.objects.select_related(
        "idcasovalidacao",
        "idalternativaresolucao",
    ).all()
    serializer_class = ResolucaoValidacaoSerializer
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        case = self.request.query_params.get("caso")
        if case is not None:
            if not case.isdecimal():
                raise serializers.ValidationError(
                    {"caso": "Informe um identificador numérico válido."}
                )
            queryset = queryset.filter(idcasovalidacao_id=int(case))
        return queryset


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


@tag_all_actions("4 - Carga Org/Lot - Envio de organograma")
class EnvioOrganogramaProdestViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = EnvioOrganogramaProdest.objects.select_related(
        "idimportacaoplanilha__idpatriarca",
        "idprocessocargainicial",
    )
    serializer_class = EnvioOrganogramaProdestSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = [
        "datsolicitacao",
        "datultimaconsulta",
        "datfinalizacao",
        "idenvioorganograma",
    ]
    ordering = ["-datsolicitacao", "-idenvioorganograma"]
    ordering_tie_breaker = "idenvioorganograma"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
        "create": "change_importacaoplanilha",
        "configuracao": "view_importacaoplanilha",
        "ultimas_prodest": "view_importacaoplanilha",
        "testar_conexao": "change_importacaoplanilha",
        "consultar_status": "change_importacaoplanilha",
        "consultar_relatorio": "change_importacaoplanilha",
        "acompanhamento": "view_importacaoplanilha",
        "eventos": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if importacao := self.request.query_params.get("importacao"):
            queryset = queryset.filter(idimportacaoplanilha_id=importacao)
        if patriarca := self.request.query_params.get("patriarca"):
            queryset = queryset.filter(
                idimportacaoplanilha__idpatriarca_id=patriarca
            )
        if remote_status := self.request.query_params.get("status"):
            queryset = queryset.filter(strstatus=remote_status)
        dry_run = self.request.query_params.get("dry_run")
        if dry_run is not None:
            normalized = dry_run.strip().lower()
            if normalized in {"true", "1"}:
                queryset = queryset.filter(flgdryrun=True)
            elif normalized in {"false", "0"}:
                queryset = queryset.filter(flgdryrun=False)
        return queryset

    @extend_schema(
        request=SolicitarEnvioOrganogramaSerializer,
        responses={201: EnvioOrganogramaProdestSerializer},
        description=(
            "Envia uma importação de organograma para a PRODEST. Use "
            "dry_run=true para simulação e dry_run=false para envio definitivo."
        ),
    )
    def create(self, request, *args, **kwargs):
        input_serializer = SolicitarEnvioOrganogramaSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        actor = self._actor()
        try:
            envio = prepare_organogram_submission(
                input_serializer.validated_data["idimportacaoplanilha"],
                dry_run=input_serializer.validated_data["dry_run"],
                actor=actor,
            )
        except OrganogramSubmissionError as exc:
            return self._error_response(exc)
        except IntegrityError:
            return Response(
                {
                    "success": False,
                    "errors": {
                        "code": "envio_organograma_em_processamento",
                        "message": (
                            "Já existe uma carga inicial em processamento "
                            "para este patriarca."
                        ),
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        transaction.on_commit(
            lambda: processar_envio_organograma.delay(envio.pk)
        )
        output = self.get_serializer(envio)
        return Response(output.data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["get"], url_path="acompanhamento")
    def acompanhamento(self, request, *args, **kwargs):
        patriarca = request.query_params.get("patriarca")
        if not patriarca or not patriarca.isdigit():
            raise serializers.ValidationError(
                {"patriarca": "Informe um identificador numérico válido."}
            )
        queryset = self.get_queryset().filter(
            idimportacaoplanilha__idpatriarca_id=int(patriarca)
        )
        active = queryset.filter(
            strstatus__in=["SOLICITANDO", "PROCESSANDO"]
        ).first()
        latest = queryset.first()
        target = active or latest
        return Response(
            {
                "patriarca_id": int(patriarca),
                "tentativa_ativa": (
                    self.get_serializer(active).data if active else None
                ),
                "ultimo_resultado": (
                    self.get_serializer(latest).data
                    if latest and latest != active
                    else None
                ),
                "bloqueio_novo_envio": active is not None,
                "motivo_bloqueio": (
                    "Existe uma carga inicial em processamento."
                    if active else ""
                ),
                "eventos_recentes": (
                    EventoIntegracaoProdestSerializer(
                        target.eventos_integracao_prodest.filter(
                            strvisibilidade="OPERACIONAL"
                        )[:20],
                        many=True,
                    ).data
                    if target else []
                ),
            }
        )

    @action(detail=True, methods=["get"], url_path="eventos")
    def eventos(self, request, *args, **kwargs):
        envio = self.get_object()
        try:
            after_id = int(request.query_params.get("after_id", 0))
            limit = min(int(request.query_params.get("limit", 100)), 100)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError(
                {"after_id": "Informe valores numéricos válidos."}
            ) from exc
        events = list(
            envio.eventos_integracao_prodest.filter(
                strvisibilidade=request.query_params.get(
                    "visibilidade", "OPERACIONAL"
                ),
                pk__gt=after_id,
            ).order_by("pk")[: limit + 1]
        )
        page = events[:limit]
        return Response(
            {
                "idenvioorganograma": envio.pk,
                "ultimo_evento_id": page[-1].pk if page else after_id,
                "possui_mais": len(events) > limit,
                "eventos": EventoIntegracaoProdestSerializer(
                    page, many=True
                ).data,
            }
        )

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"], url_path="configuracao")
    def configuracao(self, request, *args, **kwargs):
        return Response(configuration_status())

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="patriarca",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="limit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Quantidade entre 1 e 10; padrão 10.",
            ),
        ],
        responses={200: dict},
        description=(
            "Consulta na PRODEST as cargas iniciais mais recentes do "
            "patriarca e informa quando há uma tentativa local correspondente."
        ),
    )
    @action(detail=False, methods=["get"], url_path="ultimas-prodest")
    def ultimas_prodest(self, request, *args, **kwargs):
        input_serializer = ConsultarCargasIniciaisProdestSerializer(
            data=request.query_params
        )
        input_serializer.is_valid(raise_exception=True)
        patriarca = input_serializer.validated_data["patriarca"]
        limit = input_serializer.validated_data["limit"]
        try:
            remote_loads = CargaRHClient(
                patriarch_id=patriarca.pk,
                actor=self._actor(),
            ).list_initial_imports(
                patriarca.idexternopatriarca,
                limit=limit,
            )
        except CargaRHConfigurationError as exc:
            return self._error_response(
                OrganogramSubmissionError(str(exc), kind="configuration")
            )
        except CargaRHRequestError as exc:
            return self._error_response(
                OrganogramSubmissionError(
                    str(exc),
                    details=exc.details,
                    kind="upstream",
                )
            )

        local_by_external_id = {
            str(external_id).lower(): local_id
            for external_id, local_id in EnvioOrganogramaProdest.objects.filter(
                idimportacaoplanilha__idpatriarca=patriarca,
                idexternocarga__isnull=False,
            ).values_list("idexternocarga", "idenvioorganograma")
        }
        loads = []
        for remote_load in remote_loads:
            item = dict(remote_load)
            external_id = item.get("guid") or item.get("cargaId")
            item["idenvioorganograma_local"] = local_by_external_id.get(
                str(external_id).lower()
            )
            loads.append(item)
        return Response(
            {
                "patriarca_id": patriarca.pk,
                "patriarca_externo_id": patriarca.idexternopatriarca,
                "limite": limit,
                "cargas": loads,
            }
        )

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="testar-conexao")
    def testar_conexao(self, request, *args, **kwargs):
        try:
            authenticated = CargaRHClient(actor=self._actor()).test_connection()
        except CargaRHConfigurationError as exc:
            return self._error_response(
                OrganogramSubmissionError(str(exc), kind="configuration")
            )
        except CargaRHRequestError as exc:
            return self._error_response(
                OrganogramSubmissionError(
                    str(exc),
                    details=exc.details,
                    kind="upstream",
                )
            )
        return Response(
            {
                "conectado": authenticated,
                "ambiente": configuration_status()["ambiente"],
                "token_armazenado": "cache",
                "token_exposto": False,
            }
        )

    @extend_schema(
        request=None,
        responses={200: EnvioOrganogramaProdestSerializer},
    )
    @action(detail=True, methods=["post"], url_path="consultar-status")
    def consultar_status(self, request, *args, **kwargs):
        envio = self.get_object()
        try:
            envio = refresh_submission_status(envio, actor=self._actor())
        except OrganogramSubmissionError as exc:
            return self._error_response(exc)
        return Response(self.get_serializer(envio).data)

    @extend_schema(
        request=None,
        responses={200: EnvioOrganogramaProdestSerializer},
    )
    @action(detail=True, methods=["post"], url_path="consultar-relatorio")
    def consultar_relatorio(self, request, *args, **kwargs):
        envio = self.get_object()
        try:
            envio = refresh_submission_report(envio, actor=self._actor())
        except OrganogramSubmissionError as exc:
            return self._error_response(exc)
        return Response(self.get_serializer(envio).data)

    def _actor(self):
        return AuditActor(
            user_id=self.request.user.pk,
            user_name=self._resolve_user_name(self.request.user),
        )

    @staticmethod
    def _resolve_user_name(user):
        full_name = user.get_full_name().strip()
        return full_name or user.username

    @staticmethod
    def _error_response(exc):
        status_code = {
            "validation": status.HTTP_400_BAD_REQUEST,
            "configuration": status.HTTP_503_SERVICE_UNAVAILABLE,
            "upstream": status.HTTP_502_BAD_GATEWAY,
        }.get(exc.kind, status.HTTP_502_BAD_GATEWAY)
        errors = {
            "code": f"envio_organograma_{exc.kind}",
            "message": str(exc),
        }
        if exc.envio is not None:
            errors["idenvioorganograma"] = exc.envio.pk
        if exc.details:
            errors["prodest"] = exc.details
        return Response(
            {"success": False, "errors": errors},
            status=status_code,
        )


@tag_all_actions("4 - Carga Org/Lot - Comunicação com a PRODEST")
class EventoIntegracaoProdestViewSet(
    PermissionedViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = EventoIntegracaoProdest.objects.select_related(
        "idpatriarca",
        "idprocessocargainicial",
        "idenvioorganograma",
    )
    serializer_class = EventoIntegracaoProdestSerializer
    filter_backends = [DeterministicOrderingFilter]
    ordering_fields = ["datocorrencia", "ideventointegracao"]
    ordering = ["-datocorrencia", "-ideventointegracao"]
    ordering_tie_breaker = "ideventointegracao"
    permission_map = {
        "list": "view_importacaoplanilha",
        "retrieve": "view_importacaoplanilha",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        integer_filters = {
            "patriarca": "idpatriarca_id",
            "processo": "idprocessocargainicial_id",
            "envio": "idenvioorganograma_id",
        }
        for parameter, field_name in integer_filters.items():
            value = self.request.query_params.get(parameter)
            if value is None:
                continue
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {parameter: "Informe um identificador numérico válido."}
                ) from exc
            queryset = queryset.filter(**{field_name: value})
        if operation := self.request.query_params.get("operacao"):
            queryset = queryset.filter(stroperacao=operation)
        if result := self.request.query_params.get("resultado"):
            queryset = queryset.filter(strresultado=result)
        if visibility := self.request.query_params.get("visibilidade"):
            queryset = queryset.filter(strvisibilidade=visibility)
        if load_type := self.request.query_params.get("tipo_carga"):
            queryset = queryset.filter(strtipocarga=load_type)
        if phase := self.request.query_params.get("fase"):
            queryset = queryset.filter(strfase=phase)
        if submission := self.request.query_params.get("idenvioorganograma"):
            try:
                submission = int(submission)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"idenvioorganograma": "Informe um identificador válido."}
                ) from exc
            queryset = queryset.filter(idenvioorganograma_id=submission)
        if correlation := self.request.query_params.get("correlacao"):
            try:
                correlation = UUID(correlation)
            except (TypeError, ValueError, AttributeError) as exc:
                raise serializers.ValidationError(
                    {"correlacao": "Informe um identificador UUID válido."}
                ) from exc
            queryset = queryset.filter(idcorrelacao=correlation)
        return queryset


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
