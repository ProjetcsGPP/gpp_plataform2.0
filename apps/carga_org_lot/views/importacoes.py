"""Views de importacoes da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import (Count, IntegerField, OuterRef, Prefetch,
                              Subquery, Value)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (OpenApiParameter, extend_schema,
                                   extend_schema_view)
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..exceptions import SpreadsheetImportValidationError
from ..models import (CasoValidacaoImportacao, ImportacaoPlanilha, ItemLotacao,
                      ItemLotacaoImportado, ItemOrganograma,
                      RelatorioValidacaoImportacao, StatusImportacaoLocal)
from ..serializers import (CriarOrganogramaInicialSerializer,
                           ImportacaoPlanilhaListSerializer,
                           ImportacaoPlanilhaSerializer,
                           RelatorioValidacaoImportacaoSerializer)
from ..services.lotacao_pending_report import \
    build_pending_lotation_report_xlsx
from ..services.lotacao_review import incorporate_lotation
from ..services.organograma import ORGANOGRAMA_TYPE_ID
from ..services.organograma_editing import (build_initial_organogram_xlsx,
                                            build_updated_organogram_xlsx)
from ..services.workflow import AuditActor
from .base import (DeterministicOrderingFilter, PermissionedViewSetMixin,
                   ProtectedDestroyMixin, spreadsheet_download_response)


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
        ItemLotacaoImportado.objects.filter(idimportacaoplanilha_id=OuterRef("pk"))
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
                "strreferencia": request_serializer.validated_data["strreferencia"],
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
