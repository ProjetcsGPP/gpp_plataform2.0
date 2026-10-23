"""Views de lotacao da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from django.db.models import Count, F, Q
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..models import (
    AlternativaResolucaoValidacao,
    CasoValidacaoImportacao,
    ItemLotacao,
    ItemLotacaoImportado,
    ResolucaoValidacao,
    SituacaoConjuntoLotacao,
    StatusItemLotacaoImportado,
)
from ..serializers import (
    AlternativaResolucaoValidacaoSerializer,
    CasoValidacaoImportacaoSerializer,
    ItemLotacaoDescartadoSerializer,
    ItemLotacaoImportadoSerializer,
    ItemLotacaoSerializer,
    ResolucaoValidacaoSerializer,
    ResolverCasoValidacaoSerializer,
)
from ..services.lotacao_review import resolve_validation_case
from ..services.validation_cases import (
    SUBJECT_LABELS,
    validation_case_subject,
    validation_subject_query,
)
from ..services.workflow import AuditActor
from .base import DeterministicOrderingFilter, PermissionedViewSetMixin


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
                Q(strnomeservidor__icontains=search) | Q(strcpf__icontains=search)
            )
        vigente = self.request.query_params.get("vigente")
        if vigente is not None:
            if vigente.lower() not in {"true", "false"}:
                raise serializers.ValidationError({"vigente": "Informe true ou false."})
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
            "patriarca": ("idrelatoriovalidacao__idimportacaoplanilha__idpatriarca_id"),
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
                    **{f"{importation_prefix}idpatriarca__strnome__icontains": (search)}
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
                    queryset.values(status=F("strstatus")).annotate(total=Count("pk"))
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
                        idconjuntolotacao=F(f"{importation}__idconjuntolotacao_id"),
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
