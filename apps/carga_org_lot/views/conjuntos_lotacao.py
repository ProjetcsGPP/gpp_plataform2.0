"""Views de conjuntos lotacao da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from django.db.models import Count
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (OpenApiParameter, extend_schema,
                                   extend_schema_view)
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..exceptions import SpreadsheetImportValidationError
from ..models import (ConjuntoLotacao, ImportacaoPlanilha,
                      SituacaoConjuntoLotacao, StatusImportacaoLocal)
from ..serializers import (AcaoConjuntoLotacaoSerializer,
                           ConjuntoLotacaoSerializer,
                           HistoricoConjuntoLotacaoSerializer,
                           ImportacaoPlanilhaSerializer)
from ..services.lotacao_sets import (activate_lotation_set,
                                     build_consolidated_lotation_xlsx,
                                     cancel_lotation_set, create_lotation_set,
                                     homologate_lotation_set)
from ..services.workflow import AuditActor
from .base import DeterministicOrderingFilter, PermissionedViewSetMixin


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
