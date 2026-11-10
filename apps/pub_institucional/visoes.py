"""API administrativa do catálogo de patriarcas E-Docs."""

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.services.authorization_service import AuthorizationService
from apps.core.permissions import CanPermission
from apps.pub_institucional.models import (ColetaEflow, ColetaMensalEdocs,
                                           ColetaPatriarcasEdocs,
                                           DefinicaoFluxoEflow,
                                           DivergenciaPatriarcaEdocs,
                                           EventoAuditoriaColetaMensalEdocs,
                                           EventoAuditoriaEflow,
                                           EventoAuditoriaPatriarcaEdocs,
                                           EventoAuditoriaPreferenciaEflow,
                                           FonteBrutaColetaMensalEdocs,
                                           PatriarcaEdocs, PerfilCalculoEflow,
                                           PublicoAlvoEflow,
                                           ResultadoCalculoEflow,
                                           ResultadoMensalOrganizacaoEdocs,
                                           ResultadoMensalPatriarcaEdocs,
                                           SituacaoColetaEflow,
                                           SituacaoColetaMensalEdocs,
                                           SituacaoColetaPatriarcas,
                                           SituacaoDivergenciaPatriarca,
                                           TipoComparacaoPatriarca,
                                           TipoEventoAuditoriaEflow,
                                           TipoEventoAuditoriaPatriarca)
from apps.pub_institucional.serializadores import (
    SerializadorAlteracaoPreferenciaEflow, SerializadorArquivoEflow,
    SerializadorColetaEflow, SerializadorColetaMensalEdocs,
    SerializadorColetaPatriarcasEdocs, SerializadorDecisaoDivergencia,
    SerializadorDefinicaoFluxoEflow, SerializadorDivergenciaPatriarcaEdocs,
    SerializadorEventoAuditoriaColetaMensalEdocs,
    SerializadorEventoAuditoriaEflow,
    SerializadorEventoAuditoriaPatriarcaEdocs,
    SerializadorEventoAuditoriaPreferenciaEflow,
    SerializadorFonteBrutaColetaMensalEdocs,
    SerializadorIndicadoresMunicipaisEdocs,
    SerializadorIndicadorMunicipioSemEdocs, SerializadorPatriarcaEdocs,
    SerializadorPreferenciaExibicaoEflow, SerializadorResultadoCalculoEflow,
    SerializadorResultadoMensalOrganizacaoEdocs,
    SerializadorResultadoMensalPatriarcaEdocs, SerializadorSelecaoColeta,
    SerializadorSolicitacaoColetaMensalEdocs)
from apps.pub_institucional.services.edocs_mensal import (
    ErroColetaMensalEdocs, solicitar_coleta_mensal_edocs)
from apps.pub_institucional.services.eflow import (
    AtorAuditoriaEflow, ErroValidacaoEflow, alterar_preferencia_exibicao_eflow,
    importar_csv_eflow, obter_preferencia_exibicao_eflow)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, ErroDecisaoPatriarcaEdocs,
    aplicar_decisao_divergencia_patriarca,
    definir_indicador_municipio_sem_edocs,
    definir_indicadores_municipais_patriarca, definir_selecao_coleta_patriarca,
    sincronizar_patriarcas_edocs)


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


def _ator_eflow_do_usuario(usuario):
    nome = usuario.get_full_name().strip() or usuario.get_username()
    return AtorAuditoriaEflow(usuario_id=usuario.pk, nome=nome)


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
    """Consulta o catálogo e executa suas alterações manuais auditadas."""

    queryset = PatriarcaEdocs.objects.all()
    serializer_class = SerializadorPatriarcaEdocs
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["sigla", "nome", "id_externo", "codigo_municipio"]
    ordering_fields = [
        "nome",
        "sigla",
        "ativo",
        "coletar_detalhes",
        "codigo_municipio",
        "municipio_implantado",
        "municipio_em_implantacao",
        "municipio_manifestou_interesse",
        "municipio_implantado_sem_uso_edocs",
        "atualizado_em",
    ]
    ordering = ["nome", "id"]
    mapa_permissoes = {
        "list": "view_patriarcaedocs",
        "retrieve": "view_patriarcaedocs",
        "selecao_coleta": "selecionar_patriarcas_coleta",
        "indicador_municipio_sem_edocs": (
            "alterar_indicador_municipio_sem_edocs"
        ),
        "indicadores_municipais": "alterar_indicadores_municipais_edocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        ativo = _parametro_booleano(self.request, "ativo")
        coletar = _parametro_booleano(self.request, "coletar_detalhes")
        sem_uso_edocs = _parametro_booleano(
            self.request,
            "municipio_implantado_sem_uso_edocs",
        )
        implantado = _parametro_booleano(self.request, "municipio_implantado")
        em_implantacao = _parametro_booleano(
            self.request,
            "municipio_em_implantacao",
        )
        manifestou_interesse = _parametro_booleano(
            self.request,
            "municipio_manifestou_interesse",
        )
        if ativo is not None:
            consulta = consulta.filter(ativo=ativo)
        if coletar is not None:
            consulta = consulta.filter(coletar_detalhes=coletar)
        if sem_uso_edocs is not None:
            consulta = consulta.filter(
                municipio_implantado_sem_uso_edocs=sem_uso_edocs
            )
        if implantado is not None:
            consulta = consulta.filter(municipio_implantado=implantado)
        if em_implantacao is not None:
            consulta = consulta.filter(
                municipio_em_implantacao=em_implantacao
            )
        if manifestou_interesse is not None:
            consulta = consulta.filter(
                municipio_manifestou_interesse=manifestou_interesse
            )
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
        contexto["pode_alterar_indicador"] = autorizacao.can(
            "alterar_indicador_municipio_sem_edocs"
        )
        contexto["pode_alterar_indicadores_municipais"] = autorizacao.can(
            "alterar_indicadores_municipais_edocs"
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

    @extend_schema(
        request=SerializadorIndicadorMunicipioSemEdocs,
        responses=SerializadorPatriarcaEdocs,
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="indicador-municipio-sem-edocs",
    )
    def indicador_municipio_sem_edocs(self, request, pk=None):
        patriarca = self.get_object()
        entrada = SerializadorIndicadorMunicipioSemEdocs(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            patriarca = definir_indicador_municipio_sem_edocs(
                patriarca.pk,
                ator=_ator_do_usuario(request.user),
                **entrada.validated_data,
            )
        except ErroDecisaoPatriarcaEdocs as exc:
            raise ConflitoCatalogoEdocs(str(exc)) from exc
        return Response(self.get_serializer(patriarca).data)

    @extend_schema(
        request=SerializadorIndicadoresMunicipaisEdocs,
        responses=SerializadorPatriarcaEdocs,
    )
    @action(detail=True, methods=["patch"], url_path="indicadores-municipais")
    def indicadores_municipais(self, request, pk=None):
        patriarca = self.get_object()
        entrada = SerializadorIndicadoresMunicipaisEdocs(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = dict(entrada.validated_data)
        justificativa = dados.pop("justificativa")
        try:
            patriarca = definir_indicadores_municipais_patriarca(
                patriarca.pk,
                ator=_ator_do_usuario(request.user),
                justificativa=justificativa,
                **dados,
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


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoColetaMensalEdocs(MixinPermissaoPorAcao, viewsets.ReadOnlyModelViewSet):
    """Solicita e acompanha revisões mensais dos relatórios E-Docs."""

    queryset = ColetaMensalEdocs.objects.select_related("competencia")
    serializer_class = SerializadorColetaMensalEdocs
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "iniciada_em", "concluida_em", "revisao"]
    ordering = ["-criado_em"]
    mapa_permissoes = {
        "list": "view_coletamensaledocs",
        "retrieve": "view_coletamensaledocs",
        "create": "solicitar_coleta_mensal_edocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        ano = _parametro_inteiro(self.request, "ano")
        mes = _parametro_inteiro(self.request, "mes")
        situacao = _parametro_escolha(
            self.request,
            "situacao",
            SituacaoColetaMensalEdocs.values,
        )
        if ano is not None:
            consulta = consulta.filter(competencia__ano=ano)
        if mes is not None:
            if mes > 12:
                raise ValidationError({"mes": "Informe um mês entre 1 e 12."})
            consulta = consulta.filter(competencia__mes=mes)
        if situacao is not None:
            consulta = consulta.filter(situacao=situacao)
        return consulta

    @extend_schema(
        request=SerializadorSolicitacaoColetaMensalEdocs,
        responses={status.HTTP_202_ACCEPTED: SerializadorColetaMensalEdocs},
    )
    def create(self, request, *args, **kwargs):
        entrada = SerializadorSolicitacaoColetaMensalEdocs(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            coleta = solicitar_coleta_mensal_edocs(
                ator=_ator_do_usuario(request.user),
                **entrada.validated_data,
            )
        except ErroColetaMensalEdocs as exc:
            raise ConflitoCatalogoEdocs(str(exc)) from exc
        return Response(
            self.get_serializer(coleta).data,
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoResultadoMensalPatriarcaEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ResultadoMensalPatriarcaEdocs.objects.select_related(
        "coleta", "patriarca"
    )
    serializer_class = SerializadorResultadoMensalPatriarcaEdocs
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["sigla_patriarca", "nome_patriarca"]
    ordering_fields = ["nome_patriarca", "total_processos", "total_documentos"]
    ordering = ["nome_patriarca", "id"]
    mapa_permissoes = {
        "list": "view_resultadomensalpatriarcaedocs",
        "retrieve": "view_resultadomensalpatriarcaedocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        coleta_id = _parametro_uuid(self.request, "coleta_id")
        patriarca_id = _parametro_inteiro(self.request, "patriarca_id")
        if coleta_id is not None:
            consulta = consulta.filter(coleta_id=coleta_id)
        if patriarca_id is not None:
            consulta = consulta.filter(patriarca_id=patriarca_id)
        return consulta


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoResultadoMensalOrganizacaoEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = ResultadoMensalOrganizacaoEdocs.objects.select_related(
        "coleta", "patriarca"
    )
    serializer_class = SerializadorResultadoMensalOrganizacaoEdocs
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["nome_patriarca", "nome_organizacao"]
    ordering_fields = ["nome_organizacao", "total_processos", "total_documentos"]
    ordering = ["nome_patriarca", "nome_organizacao", "id"]
    mapa_permissoes = {
        "list": "view_resultadomensalorganizacaoedocs",
        "retrieve": "view_resultadomensalorganizacaoedocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        coleta_id = _parametro_uuid(self.request, "coleta_id")
        patriarca_id = _parametro_inteiro(self.request, "patriarca_id")
        if coleta_id is not None:
            consulta = consulta.filter(coleta_id=coleta_id)
        if patriarca_id is not None:
            consulta = consulta.filter(patriarca_id=patriarca_id)
        return consulta


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoFonteBrutaColetaMensalEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = FonteBrutaColetaMensalEdocs.objects.select_related(
        "coleta", "patriarca"
    )
    serializer_class = SerializadorFonteBrutaColetaMensalEdocs
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "codigo_fonte"]
    ordering = ["codigo_fonte", "id_patriarca_externo"]
    mapa_permissoes = {
        "list": "view_fontebrutacoletamensaledocs",
        "retrieve": "view_fontebrutacoletamensaledocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        coleta_id = _parametro_uuid(self.request, "coleta_id")
        return consulta.filter(coleta_id=coleta_id) if coleta_id else consulta


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoEventoAuditoriaColetaMensalEdocs(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = EventoAuditoriaColetaMensalEdocs.objects.select_related("coleta")
    serializer_class = SerializadorEventoAuditoriaColetaMensalEdocs
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "tipo_evento"]
    ordering = ["-criado_em", "-id"]
    mapa_permissoes = {
        "list": "view_eventoauditoriacoletamensaledocs",
        "retrieve": "view_eventoauditoriacoletamensaledocs",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        coleta_id = _parametro_uuid(self.request, "coleta_id")
        return consulta.filter(coleta_id=coleta_id) if coleta_id else consulta


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoColetaEflow(MixinPermissaoPorAcao, viewsets.ReadOnlyModelViewSet):
    """Importa e consulta snapshots das definições disponíveis do E-Flow."""

    queryset = ColetaEflow.objects.prefetch_related("resultados_calculo")
    serializer_class = SerializadorColetaEflow
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [OrderingFilter]
    ordering_fields = ["iniciada_em", "concluida_em", "situacao"]
    ordering = ["-iniciada_em"]
    mapa_permissoes = {
        "list": "view_coletaeflow",
        "retrieve": "view_coletaeflow",
        "create": "importar_coleta_eflow",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        situacao = _parametro_escolha(
            self.request,
            "situacao",
            SituacaoColetaEflow.values,
        )
        return consulta.filter(situacao=situacao) if situacao else consulta

    @extend_schema(
        request=SerializadorArquivoEflow,
        responses={status.HTTP_201_CREATED: SerializadorColetaEflow},
    )
    def create(self, request, *args, **kwargs):
        entrada = SerializadorArquivoEflow(data=request.data)
        entrada.is_valid(raise_exception=True)
        arquivo = entrada.validated_data["arquivo"]
        try:
            coleta = importar_csv_eflow(
                nome_arquivo=arquivo.name,
                conteudo=arquivo.read(),
                ator=_ator_eflow_do_usuario(request.user),
            )
        except ErroValidacaoEflow as exc:
            raise ValidationError(
                {"arquivo": {"codigo": exc.codigo, "detalhe": str(exc)}}
            ) from exc
        return Response(
            self.get_serializer(coleta).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoDefinicaoFluxoEflow(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Consulta as linhas normalizadas de um snapshot E-Flow."""

    queryset = DefinicaoFluxoEflow.objects.select_related("coleta", "patriarca")
    serializer_class = SerializadorDefinicaoFluxoEflow
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["nome", "orgao", "setor", "patriarca__sigla"]
    ordering_fields = ["nome", "orgao", "setor", "publico_alvo"]
    ordering = ["nome", "id"]
    mapa_permissoes = {
        "list": "view_definicaofluxoeflow",
        "retrieve": "view_definicaofluxoeflow",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        filtros = {
            "coleta_id": _parametro_uuid(self.request, "coleta_id"),
            "patriarca_id": _parametro_inteiro(self.request, "patriarca_id"),
            "publico_alvo": _parametro_escolha(
                self.request,
                "publico_alvo",
                PublicoAlvoEflow.values,
            ),
        }
        for campo, valor in filtros.items():
            if valor is not None:
                consulta = consulta.filter(**{campo: valor})
        return consulta


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoResultadoCalculoEflow(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Consulta os dois resultados calculados de cada snapshot."""

    queryset = ResultadoCalculoEflow.objects.select_related("coleta")
    serializer_class = SerializadorResultadoCalculoEflow
    filter_backends = [OrderingFilter]
    ordering_fields = ["calculado_em", "perfil"]
    ordering = ["perfil"]
    mapa_permissoes = {
        "list": "view_resultadocalculoeflow",
        "retrieve": "view_resultadocalculoeflow",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        filtros = {
            "coleta_id": _parametro_uuid(self.request, "coleta_id"),
            "perfil": _parametro_escolha(
                self.request,
                "perfil",
                PerfilCalculoEflow.values,
            ),
        }
        for campo, valor in filtros.items():
            if valor is not None:
                consulta = consulta.filter(**{campo: valor})
        return consulta


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoPreferenciaExibicaoEflow(MixinPermissaoPorAcao, viewsets.ViewSet):
    """Consulta e altera apenas a preferência do usuário autenticado."""

    required_permission = None

    def get_permissions(self):
        self.required_permission = (
            "alterar_preferencia_exibicao_eflow"
            if self.request.method == "PATCH"
            else "view_preferenciaexibicaoeflow"
        )
        return [classe() for classe in self.permission_classes]

    def _contexto_serializador(self, request):
        autorizacao = AuthorizationService(
            request.user,
            getattr(request, "application", None),
        )
        return {
            "request": request,
            "pode_alterar": autorizacao.can(
                "alterar_preferencia_exibicao_eflow"
            ),
        }

    @extend_schema(
        methods=["GET"],
        responses=SerializadorPreferenciaExibicaoEflow,
    )
    @extend_schema(
        methods=["PATCH"],
        request=SerializadorAlteracaoPreferenciaEflow,
        responses=SerializadorPreferenciaExibicaoEflow,
    )
    @action(detail=False, methods=["get", "patch"], url_path="minha")
    def minha(self, request):
        ator = _ator_eflow_do_usuario(request.user)
        if request.method == "PATCH":
            entrada = SerializadorAlteracaoPreferenciaEflow(data=request.data)
            entrada.is_valid(raise_exception=True)
            preferencia = alterar_preferencia_exibicao_eflow(
                request.user,
                ator=ator,
                **entrada.validated_data,
            )
        else:
            preferencia = obter_preferencia_exibicao_eflow(
                request.user,
                ator=ator,
            )
        saida = SerializadorPreferenciaExibicaoEflow(
            preferencia,
            context=self._contexto_serializador(request),
        )
        return Response(saida.data)


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoEventoAuditoriaPreferenciaEflow(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Consulta a auditoria da preferência do próprio usuário."""

    queryset = EventoAuditoriaPreferenciaEflow.objects.none()
    serializer_class = SerializadorEventoAuditoriaPreferenciaEflow
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "tipo_evento"]
    ordering = ["-criado_em", "-id"]
    mapa_permissoes = {
        "list": "view_eventoauditoriapreferenciaeflow",
        "retrieve": "view_eventoauditoriapreferenciaeflow",
    }

    def get_queryset(self):
        return EventoAuditoriaPreferenciaEflow.objects.filter(
            preferencia__usuario=self.request.user
        ).select_related("preferencia")


@extend_schema(tags=["7 - Publicações Institucionais"])
class VisaoEventoAuditoriaEflow(
    MixinPermissaoPorAcao,
    viewsets.ReadOnlyModelViewSet,
):
    """Consulta os eventos imutáveis das importações E-Flow."""

    queryset = EventoAuditoriaEflow.objects.select_related("coleta")
    serializer_class = SerializadorEventoAuditoriaEflow
    filter_backends = [OrderingFilter]
    ordering_fields = ["criado_em", "tipo_evento"]
    ordering = ["-criado_em", "-id"]
    mapa_permissoes = {
        "list": "view_eventoauditoriaeflow",
        "retrieve": "view_eventoauditoriaeflow",
    }

    def get_queryset(self):
        consulta = super().get_queryset()
        filtros = {
            "coleta_id": _parametro_uuid(self.request, "coleta_id"),
            "tipo_evento": _parametro_escolha(
                self.request,
                "tipo_evento",
                TipoEventoAuditoriaEflow.values,
            ),
        }
        for campo, valor in filtros.items():
            if valor is not None:
                consulta = consulta.filter(**{campo: valor})
        return consulta
