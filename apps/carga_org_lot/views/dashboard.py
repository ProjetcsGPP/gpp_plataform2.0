"""Views de dashboard da aplicação CARGA_ORG_LOT."""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carga_org_lot.permissoes_iam import CanPermissionCarga
from config.iam_boundary import carga_http_iam_remoto

from ..models import EnvioOrganogramaProdest, Patriarca
from ..serializers import EnvioOrganogramaProdestSerializer


class DashboardCargaOrgLotView(APIView):
    permission_classes = [IsAuthenticated, CanPermissionCarga]
    required_permission = "view_importacaoplanilha"

    def get_permissions(self):
        if carga_http_iam_remoto(self.request.path):
            return [CanPermissionCarga()]
        return super().get_permissions()

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
