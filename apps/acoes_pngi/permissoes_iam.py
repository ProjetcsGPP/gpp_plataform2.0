"""Guarda opt-in de Ações PNGI; o modo monolítico permanece inalterado."""

import logging

from django.conf import settings
from rest_framework.exceptions import APIException

from apps.core.permissions import CanPermission
from common.authentication import enforce_csrf
from common.services.cliente_iam import (
    IAMIndisponivel,
    PermissaoIAMNegada,
    SessaoIAMInvalida,
    decidir_acesso_remoto,
)
from common.services.identidade_iam import IdentidadeIAM
from config.iam_boundary import acoes_http_iam_remoto


registrador = logging.getLogger("gpp.security")
CAMINHO_IAM = "/interno/iam/v1/decisoes-acoes/"
COOKIE_ACOES = "gpp_session_ACOES_PNGI"


class SessaoAcoesInvalida(APIException):
    status_code = 401
    default_detail = "Sessão inválida."
    default_code = "session_invalid"
    structured_errors = {"code": default_code, "detail": default_detail}


class PermissaoAcoesNegada(APIException):
    status_code = 403
    default_detail = "Você não tem permissão para executar esta ação."
    default_code = "permission_denied"
    structured_errors = {"code": default_code, "detail": default_detail}


class ServicoIAMAcoesIndisponivel(APIException):
    status_code = 503
    default_detail = "Serviço de autorização temporariamente indisponível."
    default_code = "servico_iam_indisponivel"
    structured_errors = {"code": default_code, "detail": default_detail}


class CanPermissionAcoes(CanPermission):
    """Decide no IAM remoto quando o perfil de Ações habilita o piloto."""

    protege_identidade_iam_remota = True

    def has_permission(self, request, view):
        if not acoes_http_iam_remoto(request.path):
            return super().has_permission(request, view)

        permissao = getattr(view, "required_permission", None)
        if not permissao or getattr(view, "permission_context", None):
            registrador.error(
                "ACOES_IAM_CONTRATO_INSUFICIENTE view=%s", view.__class__.__name__
            )
            raise ServicoIAMAcoesIndisponivel()
        valor_cookie = request.COOKIES.get(COOKIE_ACOES)
        if not valor_cookie:
            raise SessaoAcoesInvalida()

        try:
            decisao = decidir_acesso_remoto(
                url=settings.IAM_URL_ACOES,
                caminho=CAMINHO_IAM,
                token=settings.IAM_TOKEN_SERVICO_ACOES,
                credenciais={COOKIE_ACOES: valor_cookie},
                nome_cookie=COOKIE_ACOES,
                permissao=permissao,
                correlacao=request.headers.get("X-Correlation-ID"),
            )
        except SessaoIAMInvalida as exc:
            raise SessaoAcoesInvalida() from exc
        except PermissaoIAMNegada as exc:
            raise PermissaoAcoesNegada() from exc
        except IAMIndisponivel as exc:
            raise ServicoIAMAcoesIndisponivel() from exc

        try:
            identidade = IdentidadeIAM(
                id=decisao["usuario_id"], nome=decisao["usuario_nome"]
            )
        except (KeyError, ValueError, TypeError) as exc:
            registrador.error("ACOES_IAM_IDENTIDADE_INCOMPLETA")
            raise ServicoIAMAcoesIndisponivel() from exc

        enforce_csrf(request)
        request.user = identidade
        return True
