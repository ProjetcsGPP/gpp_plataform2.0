"""Endpoint M2M de decisão IAM, desativado por padrão e fora do OpenAPI público."""

import json
import logging
import re
import secrets
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.services.decisao_interna import (
    decidir_acesso_carga,
    decidir_acesso_publicacoes,
    decidir_atividade_carga,
    decidir_atividade_publicacoes,
)

security_logger = logging.getLogger("gpp.security")
PADRAO_ACAO = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
PADRAO_CORRELACAO = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
TAMANHO_MAXIMO_CORPO = 4096


def _resposta(dados, status=200):
    resposta = JsonResponse(dados, status=status)
    resposta["Cache-Control"] = "no-store"
    return resposta


def _servico_autenticado(request, token_servico):
    esquema, separador, credencial = request.headers.get(
        "Authorization", ""
    ).partition(" ")
    return bool(
        esquema == "Bearer"
        and separador
        and credencial
        and len(credencial) <= 256
        and secrets.compare_digest(credencial, token_servico)
    )


def _ler_pedido(request):  # pylint: disable=too-many-return-statements
    """Retorna (dados, status_erro), sem registrar a sessão recebida."""
    if request.content_type != "application/json":
        return None, 415
    tamanho_informado = request.META.get("CONTENT_LENGTH", "")
    if tamanho_informado.isdecimal() and int(tamanho_informado) > TAMANHO_MAXIMO_CORPO:
        return None, 413
    try:
        corpo = request.body
    except RequestDataTooBig:
        return None, 413
    if len(corpo) > TAMANHO_MAXIMO_CORPO:
        return None, 413
    try:
        dados = json.loads(corpo)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, 400
    if not isinstance(dados, dict):
        return None, 400

    credenciais_usuario = dados.get("credenciais_usuario")
    permissao = dados.get("acao")
    if not isinstance(credenciais_usuario, list) or not isinstance(permissao, str):
        return None, 400
    if not 1 <= len(credenciais_usuario) <= 8:
        return None, 400
    if not PADRAO_ACAO.fullmatch(permissao):
        return None, 400
    credenciais = {}
    for item in credenciais_usuario:
        if not isinstance(item, dict) or set(item) != {"nome_cookie", "valor"}:
            return None, 400
        nome_cookie, chave_sessao = item["nome_cookie"], item["valor"]
        if not isinstance(nome_cookie, str) or not (
            nome_cookie.startswith("gpp_session_") and len(nome_cookie) <= 100
        ):
            return None, 400
        if not isinstance(chave_sessao, str) or not 1 <= len(chave_sessao) <= 40:
            return None, 400
        if nome_cookie in credenciais:
            return None, 400
        credenciais[nome_cookie] = chave_sessao
    return (credenciais, permissao), None


@method_decorator(csrf_exempt, name="dispatch")
class DecisaoIAMInternaView(View):
    """Autentica o serviço antes de examinar a credencial opaca do usuário."""

    http_method_names = ["post"]
    nome_configuracao_token = "IAM_TOKEN_SERVICO_CARGA"
    codigo_aplicacao = "CARGA_ORG_LOT"

    def _token_servico(self):
        return getattr(settings, self.nome_configuracao_token, "")

    def _decisoes_ativas(self):
        return settings.IAM_DECISOES_INTERNAS_ATIVAS

    def _decidir(self, credenciais, permissao):
        return decidir_acesso_carga(
            credenciais=credenciais, permissao=permissao,
        )

    def dispatch(self, request, *args, **kwargs):
        if (
            not self._decisoes_ativas()
            or not 32 <= len(self._token_servico()) <= 256
        ):
            return _resposta({"erro": "nao_disponivel"}, status=404)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        if not _servico_autenticado(request, self._token_servico()):
            resposta = _resposta({"erro": "servico_nao_autenticado"}, status=401)
            resposta["WWW-Authenticate"] = 'Bearer realm="gpp-iam-interno"'
            return resposta

        pedido, erro = _ler_pedido(request)
        if erro is not None:
            return _resposta({"erro": "conteudo_invalido"}, status=erro)
        credenciais, permissao = pedido

        correlacao = request.headers.get("X-Correlation-ID", "")
        if not PADRAO_CORRELACAO.fullmatch(correlacao):
            correlacao = uuid4().hex
        decisao_id = uuid4().hex
        try:
            resultado = self._decidir(credenciais, permissao)
        except Exception as exc:  # fronteira: nunca liberar acesso em falha do IAM
            security_logger.error(
                "IAM_DECISAO_INDISPONIVEL decisao_id=%s correlacao=%s tipo=%s",
                decisao_id,
                correlacao,
                type(exc).__name__,
            )
            return _resposta(
                {"erro": "iam_indisponivel", "decisao_id": decisao_id},
                status=503,
            )

        security_logger.info(
            "IAM_DECISAO resultado=%s usuario_id=%s decisao_id=%s correlacao=%s app=%s",
            resultado["resultado"],
            resultado.get("usuario_id", "indisponivel"),
            decisao_id,
            correlacao,
            self.codigo_aplicacao,
        )
        return _resposta({"versao": 1, "decisao_id": decisao_id, **resultado})


@method_decorator(csrf_exempt, name="dispatch")
class DecisaoPublicacoesIAMInternaView(DecisaoIAMInternaView):
    """Contrato HTTP opt-in de Publicações, com credencial M2M independente."""

    nome_configuracao_token = "IAM_TOKEN_SERVICO_PUBLICACOES"
    codigo_aplicacao = "PUB_INSTITUCIONAL"

    def _decisoes_ativas(self):
        return settings.IAM_DECISOES_PUBLICACOES_ATIVAS

    def dispatch(self, request, *args, **kwargs):
        token = self._token_servico()
        if token and secrets.compare_digest(token, settings.IAM_TOKEN_SERVICO_CARGA):
            return _resposta({"erro": "nao_disponivel"}, status=404)
        return super().dispatch(request, *args, **kwargs)

    def _decidir(self, credenciais, permissao):
        return decidir_acesso_publicacoes(
            credenciais=credenciais, permissao=permissao,
        )


@method_decorator(csrf_exempt, name="dispatch")
class DecisaoAtividadeIAMInternaView(View):
    """Revalidação M2M de uma atividade persistida, sem cookie de usuário."""

    http_method_names = ["post"]
    nome_configuracao_token = "IAM_TOKEN_SERVICO_CARGA"
    codigo_aplicacao = "CARGA_ORG_LOT"

    def decidir_atividade(self, *, usuario_id, permissao):
        return decidir_atividade_carga(usuario_id=usuario_id, permissao=permissao)

    def _token_servico(self):
        return getattr(settings, self.nome_configuracao_token)

    def _decisoes_ativas(self):
        return settings.IAM_DECISOES_INTERNAS_ATIVAS

    def dispatch(self, request, *args, **kwargs):
        if (
            not self._decisoes_ativas()
            or not 32 <= len(self._token_servico()) <= 256
        ):
            return _resposta({"erro": "nao_disponivel"}, status=404)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):  # pylint: disable=too-many-return-statements
        if not _servico_autenticado(request, self._token_servico()):
            resposta = _resposta({"erro": "servico_nao_autenticado"}, status=401)
            resposta["WWW-Authenticate"] = 'Bearer realm="gpp-iam-interno"'
            return resposta
        if request.content_type != "application/json":
            return _resposta({"erro": "conteudo_invalido"}, status=415)
        tamanho = request.META.get("CONTENT_LENGTH", "")
        if tamanho.isdecimal() and int(tamanho) > 512:
            return _resposta({"erro": "conteudo_invalido"}, status=413)
        try:
            corpo = request.body
            if len(corpo) > 512:
                return _resposta({"erro": "conteudo_invalido"}, status=413)
            dados = json.loads(corpo)
        except (RequestDataTooBig, UnicodeDecodeError, json.JSONDecodeError):
            return _resposta({"erro": "conteudo_invalido"}, status=400)
        if not isinstance(dados, dict) or set(dados) != {"usuario_id", "acao"}:
            return _resposta({"erro": "conteudo_invalido"}, status=400)
        usuario_id, permissao = dados["usuario_id"], dados["acao"]
        if (
            not isinstance(usuario_id, int) or isinstance(usuario_id, bool)
            or usuario_id < 1 or not isinstance(permissao, str)
            or not PADRAO_ACAO.fullmatch(permissao)
        ):
            return _resposta({"erro": "conteudo_invalido"}, status=400)

        correlacao = request.headers.get("X-Correlation-ID", "")
        if not PADRAO_CORRELACAO.fullmatch(correlacao):
            correlacao = uuid4().hex
        decisao_id = uuid4().hex
        try:
            resultado = self.decidir_atividade(
                usuario_id=usuario_id, permissao=permissao
            )
        except Exception as exc:  # nunca liberar execução em falha do IAM
            security_logger.error(
                "IAM_ATIVIDADE_INDISPONIVEL decisao_id=%s correlacao=%s tipo=%s",
                decisao_id, correlacao, type(exc).__name__,
            )
            return _resposta(
                {"erro": "iam_indisponivel", "decisao_id": decisao_id}, status=503
            )
        security_logger.info(
            "IAM_ATIVIDADE resultado=%s usuario_id=%s decisao_id=%s correlacao=%s app=%s",
            resultado["resultado"], usuario_id, decisao_id, correlacao,
            self.codigo_aplicacao,
        )
        return _resposta({"versao": 1, "decisao_id": decisao_id, **resultado})


@method_decorator(csrf_exempt, name="dispatch")
class DecisaoAtividadePublicacoesIAMInternaView(DecisaoAtividadeIAMInternaView):
    """Decisão M2M exclusiva de Publicações, sem cookie de sessão."""

    nome_configuracao_token = "IAM_TOKEN_SERVICO_PUBLICACOES"
    codigo_aplicacao = "PUB_INSTITUCIONAL"

    def _decisoes_ativas(self):
        return settings.IAM_DECISOES_PUBLICACOES_ATIVAS

    def decidir_atividade(self, *, usuario_id, permissao):
        return decidir_atividade_publicacoes(
            usuario_id=usuario_id, permissao=permissao
        )

    def dispatch(self, request, *args, **kwargs):
        token = self._token_servico()
        if token and secrets.compare_digest(token, settings.IAM_TOKEN_SERVICO_CARGA):
            return _resposta({"erro": "nao_disponivel"}, status=404)
        return super().dispatch(request, *args, **kwargs)
