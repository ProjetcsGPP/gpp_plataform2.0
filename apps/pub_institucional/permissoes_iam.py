"""Guarda HTTP opt-in de Publicações com decisão IAM remota e falha fechada."""

import logging

from django.conf import settings
from rest_framework.exceptions import APIException

from apps.accounts.services.authorization_service import AuthorizationService
from apps.core.permissions import CanPermission
from common.authentication import enforce_csrf
from common.services.cliente_iam import (
    IAMIndisponivel, PermissaoIAMNegada, SessaoIAMInvalida,
    decidir_acesso_remoto,
)
from common.services.identidade_iam import IdentidadeIAM
from config.iam_boundary import publicacoes_http_iam_remoto

logger = logging.getLogger("gpp.security")
CAMINHO_IAM = "/interno/iam/v1/decisoes-publicacoes/"
COOKIE_PUBLICACOES = "gpp_session_PUB_INSTITUCIONAL"


class SessaoPublicacoesInvalida(APIException):
    status_code = 401
    default_detail = "Sessão inválida."
    default_code = "session_invalid"
    structured_errors = {"code": default_code, "detail": default_detail}


class PermissaoPublicacoesNegada(APIException):
    status_code = 403
    default_detail = "Você não tem permissão para executar esta ação."
    default_code = "permission_denied"
    structured_errors = {"code": default_code, "detail": default_detail}


class ServicoIAMPublicacoesIndisponivel(APIException):
    status_code = 503
    default_detail = "Serviço de autorização temporariamente indisponível."
    default_code = "servico_iam_indisponivel"
    structured_errors = {"code": default_code, "detail": default_detail}


def _consultar(request, permissao):
    valor_cookie = request.COOKIES.get(COOKIE_PUBLICACOES)
    if not valor_cookie:
        raise SessaoPublicacoesInvalida()
    try:
        return decidir_acesso_remoto(
            url=settings.IAM_URL_PUBLICACOES,
            caminho=CAMINHO_IAM,
            token=settings.IAM_TOKEN_SERVICO_PUBLICACOES,
            credenciais={COOKIE_PUBLICACOES: valor_cookie},
            nome_cookie=COOKIE_PUBLICACOES,
            permissao=permissao,
            correlacao=request.headers.get("X-Correlation-ID"),
        )
    except SessaoIAMInvalida as exc:
        raise SessaoPublicacoesInvalida() from exc
    except PermissaoIAMNegada as exc:
        raise PermissaoPublicacoesNegada() from exc
    except IAMIndisponivel as exc:
        raise ServicoIAMPublicacoesIndisponivel() from exc


def pode_acao_adicional(request, permissao):
    """Responde à projeção de ações sem consultar roles locais no piloto."""
    if not publicacoes_http_iam_remoto(request.path):
        autorizacao = AuthorizationService(
            request.user, getattr(request, "application", None),
        )
        return autorizacao.can(permissao)
    try:
        decisao = _consultar(request, permissao)
    except PermissaoPublicacoesNegada:
        return False
    if decisao["usuario_id"] != request.user.pk:
        logger.error(
            "PUBLICACOES_IAM_IDENTIDADE_DIVERGENTE decisao_id=%s",
            decisao["decisao_id"],
        )
        raise ServicoIAMPublicacoesIndisponivel()
    return True


class CanPermissionPublicacoes(CanPermission):
    """Mantém o modo local; no piloto valida identidade e ação no IAM."""

    protege_identidade_iam_remota = True

    def has_permission(self, request, view):
        if not publicacoes_http_iam_remoto(request.path):
            return super().has_permission(request, view)
        permissao = getattr(view, "required_permission", None)
        if not permissao or getattr(view, "permission_context", None):
            logger.error(
                "PUBLICACOES_IAM_CONTRATO_INSUFICIENTE view=%s",
                view.__class__.__name__,
            )
            raise ServicoIAMPublicacoesIndisponivel()
        decisao = _consultar(request, permissao)
        try:
            identidade = IdentidadeIAM(
                id=decisao["usuario_id"], nome=decisao["usuario_nome"],
            )
        except ValueError as exc:
            raise ServicoIAMPublicacoesIndisponivel() from exc
        # A autenticação DRF baseada no cookie local foi dispensada no piloto.
        enforce_csrf(request)
        request.user = identidade
        return True
