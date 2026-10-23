"""Views de organograma da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.mixins import AuditableMixin
from common.schema import tag_all_actions

from ..exceptions import SubtreeDeletionConfirmationRequired
from ..models import EnvioOrganogramaProdest, EventoIntegracaoProdest, ItemOrganograma
from ..serializers import (
    ConsultarCargasIniciaisProdestSerializer,
    EnvioOrganogramaProdestSerializer,
    EventoIntegracaoProdestSerializer,
    ItemOrganogramaSerializer,
    SolicitarEnvioOrganogramaSerializer,
)
from ..services.cargarh import (
    CargaRHClient,
    CargaRHConfigurationError,
    CargaRHRequestError,
    configuration_status,
)
from ..services.organogram_submission import (
    OrganogramSubmissionError,
    prepare_organogram_submission,
    refresh_submission_report,
    refresh_submission_status,
)
from ..services.organograma_editing import deletion_impact, get_subtree_descendants
from ..services.workflow import AuditActor, register_organogram_item_change
from ..tasks import processar_envio_organograma
from .base import (
    DeterministicOrderingFilter,
    PermissionedViewSetMixin,
    ProtectedDestroyMixin,
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
            queryset = queryset.filter(idimportacaoplanilha__idpatriarca_id=patriarca)
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
        transaction.on_commit(lambda: processar_envio_organograma.delay(envio.pk))
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
        active = queryset.filter(strstatus__in=["SOLICITANDO", "PROCESSANDO"]).first()
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
                    "Existe uma carga inicial em processamento." if active else ""
                ),
                "eventos_recentes": (
                    EventoIntegracaoProdestSerializer(
                        target.eventos_integracao_prodest.filter(
                            strvisibilidade="OPERACIONAL"
                        )[:20],
                        many=True,
                    ).data
                    if target
                    else []
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
                strvisibilidade=request.query_params.get("visibilidade", "OPERACIONAL"),
                pk__gt=after_id,
            ).order_by("pk")[: limit + 1]
        )
        page = events[:limit]
        return Response(
            {
                "idenvioorganograma": envio.pk,
                "ultimo_evento_id": page[-1].pk if page else after_id,
                "possui_mais": len(events) > limit,
                "eventos": EventoIntegracaoProdestSerializer(page, many=True).data,
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
