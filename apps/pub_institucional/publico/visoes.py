"""Views sem sessão da projeção pública versionada."""

import hashlib
import json
import logging

from django.db import DatabaseError
from django.utils.http import http_date, parse_etags
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pub_institucional.models import Publicacao, SituacaoPublicacao

from .projecoes import (projetar_publicacao, projetar_resumo_publicacao,
                        projetar_series_publicacao)
from .serializadores import (SerializadorErroPublico,
                             SerializadorHistoricoPublico,
                             SerializadorPublicacaoPublica,
                             SerializadorSeriesPublicacaoPublica)
from .throttling import TaxaPublicacoesPublicas

logger = logging.getLogger(__name__)

SITUACOES_HISTORICO_PUBLICO = (
    SituacaoPublicacao.PUBLICADA,
    SituacaoPublicacao.SUBSTITUIDA,
)
SITUACOES_TERMINAIS_PUBLICAS = (
    *SITUACOES_HISTORICO_PUBLICO,
    SituacaoPublicacao.REVOGADA,
)


def _erro(codigo, detalhe, status_http, *, retry_after=None):
    resposta = Response(
        {"codigo": codigo, "detalhe": detalhe},
        status=status_http,
    )
    resposta["Cache-Control"] = "no-store"
    if retry_after is not None:
        resposta["Retry-After"] = str(max(1, int(retry_after)))
    return resposta


def _consulta_publica():
    return Publicacao.objects.prefetch_related("secoes").filter(
        situacao__in=SITUACOES_TERMINAIS_PUBLICAS,
        publicada_em__isnull=False,
    )


def _publicacao_vigente():
    candidata = _consulta_publica().order_by(
        "-ano_referencia",
        "-mes_referencia",
        "-publicada_em",
        "-versao",
    ).first()
    if candidata is None or candidata.situacao != SituacaoPublicacao.PUBLICADA:
        return None
    return candidata


def _etag(publicacao, sufixo=""):
    valor = f"{publicacao.hash_conteudo}:{sufixo}" if sufixo else publicacao.hash_conteudo
    return f'"{valor}"'


def _etag_conteudo(conteudo):
    bruto = json.dumps(
        conteudo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f'"{hashlib.sha256(bruto).hexdigest()}"'


def _nao_modificado(request, etag):
    return etag in parse_etags(request.headers.get("If-None-Match", ""))


def _resposta_cacheada(request, conteudo, publicacao, *, sufixo=""):
    etag = _etag(publicacao, sufixo)
    if _nao_modificado(request, etag):
        resposta = Response(status=status.HTTP_304_NOT_MODIFIED)
    else:
        resposta = Response(conteudo)
    resposta["ETag"] = etag
    resposta["Last-Modified"] = http_date(publicacao.publicada_em.timestamp())
    resposta["Cache-Control"] = "public, max-age=60, must-revalidate"
    return resposta


class VisaoPublicaBase(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [TaxaPublicacoesPublicas]

    def throttled(self, request, wait):
        raise LimitePublicoExcedido(wait)

    def handle_exception(self, exc):
        if isinstance(exc, LimitePublicoExcedido):
            return _erro(
                "LIMITE_PUBLICO_EXCEDIDO",
                "Limite temporário de consultas públicas excedido.",
                status.HTTP_429_TOO_MANY_REQUESTS,
                retry_after=exc.wait,
            )
        return super().handle_exception(exc)


class LimitePublicoExcedido(Exception):
    def __init__(self, wait):
        super().__init__("Limite público excedido.")
        self.wait = wait or 1


class VisaoPublicacaoVigente(VisaoPublicaBase):
    @extend_schema(
        operation_id="publicacoes_institucionais_publica_vigente",
        tags=["Publicações Institucionais - Público"],
        responses={
            200: SerializadorPublicacaoPublica,
            304: OpenApiResponse(description="Representação não modificada."),
            404: SerializadorErroPublico,
            429: SerializadorErroPublico,
            503: SerializadorErroPublico,
        },
    )
    def get(self, request):
        try:
            publicacao = _publicacao_vigente()
        except DatabaseError:
            logger.exception("Falha ao consultar a publicação pública vigente")
            return _erro(
                "PUBLICACAO_TEMPORARIAMENTE_INDISPONIVEL",
                "A publicação está temporariamente indisponível.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if publicacao is None:
            return _erro(
                "PUBLICACAO_NAO_DISPONIVEL",
                "Não existe publicação vigente disponível.",
                status.HTTP_404_NOT_FOUND,
            )
        resposta = _resposta_cacheada(
            request,
            projetar_publicacao(publicacao),
            publicacao,
            sufixo="vigente",
        )
        resposta["Cache-Control"] = "public, no-cache, max-age=0, must-revalidate"
        return resposta


class VisaoHistoricoPublico(VisaoPublicaBase):
    @extend_schema(
        operation_id="publicacoes_institucionais_publica_historico",
        tags=["Publicações Institucionais - Público"],
        responses={
            200: SerializadorHistoricoPublico,
            304: OpenApiResponse(description="Representação não modificada."),
            429: SerializadorErroPublico,
            503: SerializadorErroPublico,
        },
    )
    def get(self, request):
        try:
            publicacoes = list(
                _consulta_publica()
                .filter(situacao__in=SITUACOES_HISTORICO_PUBLICO)
                .order_by("-ano_referencia", "-mes_referencia", "-publicada_em")
            )
        except DatabaseError:
            logger.exception("Falha ao consultar o histórico público")
            return _erro(
                "PUBLICACAO_TEMPORARIAMENTE_INDISPONIVEL",
                "O histórico está temporariamente indisponível.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        conteudo = {
            "schema_version": "1.0",
            "quantidade": len(publicacoes),
            "resultados": [
                projetar_resumo_publicacao(publicacao)
                for publicacao in publicacoes
            ],
        }
        etag = _etag_conteudo(conteudo)
        if _nao_modificado(request, etag):
            resposta = Response(status=status.HTTP_304_NOT_MODIFIED)
        else:
            resposta = Response(conteudo)
        resposta["ETag"] = etag
        if publicacoes:
            publicada_em_mais_recente = max(
                publicacao.publicada_em for publicacao in publicacoes
            )
            resposta["Last-Modified"] = http_date(
                publicada_em_mais_recente.timestamp()
            )
        resposta["Cache-Control"] = "public, max-age=60, must-revalidate"
        return resposta


class VisaoDetalhePublicacaoPublica(VisaoPublicaBase):
    @extend_schema(
        operation_id="publicacoes_institucionais_publica_detalhe",
        tags=["Publicações Institucionais - Público"],
        responses={
            200: SerializadorPublicacaoPublica,
            304: OpenApiResponse(description="Representação não modificada."),
            404: SerializadorErroPublico,
            410: SerializadorErroPublico,
            429: SerializadorErroPublico,
            503: SerializadorErroPublico,
        },
    )
    def get(self, request, publicacao_id):
        try:
            publicacao = _consulta_publica().filter(pk=publicacao_id).first()
        except DatabaseError:
            logger.exception("Falha ao consultar uma publicação pública")
            return _erro(
                "PUBLICACAO_TEMPORARIAMENTE_INDISPONIVEL",
                "A publicação está temporariamente indisponível.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if publicacao is None:
            return _erro(
                "PUBLICACAO_NAO_ENCONTRADA",
                "A publicação informada não foi encontrada.",
                status.HTTP_404_NOT_FOUND,
            )
        if publicacao.situacao == SituacaoPublicacao.REVOGADA:
            return _erro(
                "PUBLICACAO_REVOGADA",
                "A publicação informada foi revogada.",
                status.HTTP_410_GONE,
            )
        return _resposta_cacheada(
            request,
            projetar_publicacao(publicacao),
            publicacao,
        )


class VisaoSeriesPublicacaoPublica(VisaoPublicaBase):
    @extend_schema(
        operation_id="publicacoes_institucionais_publica_series",
        tags=["Publicações Institucionais - Público"],
        responses={
            200: SerializadorSeriesPublicacaoPublica,
            304: OpenApiResponse(description="Representação não modificada."),
            404: SerializadorErroPublico,
            410: SerializadorErroPublico,
            429: SerializadorErroPublico,
            503: SerializadorErroPublico,
        },
    )
    def get(self, request, publicacao_id):
        try:
            publicacao = _consulta_publica().filter(pk=publicacao_id).first()
        except DatabaseError:
            logger.exception("Falha ao consultar séries públicas")
            return _erro(
                "PUBLICACAO_TEMPORARIAMENTE_INDISPONIVEL",
                "As séries estão temporariamente indisponíveis.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if publicacao is None:
            return _erro(
                "PUBLICACAO_NAO_ENCONTRADA",
                "A publicação informada não foi encontrada.",
                status.HTTP_404_NOT_FOUND,
            )
        if publicacao.situacao == SituacaoPublicacao.REVOGADA:
            return _erro(
                "PUBLICACAO_REVOGADA",
                "A publicação informada foi revogada.",
                status.HTTP_410_GONE,
            )
        return _resposta_cacheada(
            request,
            projetar_series_publicacao(publicacao),
            publicacao,
            sufixo="series",
        )
