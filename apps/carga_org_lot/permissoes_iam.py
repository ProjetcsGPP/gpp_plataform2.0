"""Guard HTTP de Carga com piloto remoto reversível, desativado por padrão."""

import logging

from django.conf import settings
from rest_framework.exceptions import APIException

from apps.core.permissions import CanPermission
from common.authentication import enforce_csrf
from config.iam_boundary import carga_http_iam_remoto

from .services.cliente_iam import (IAMIndisponivel, PermissaoIAMNegada,
                                   SessaoIAMInvalida, decidir_acesso_remoto)
from .services.identidade_iam import IdentidadeIAM

logger = logging.getLogger("gpp.security")


class SessaoCargaInvalida(APIException):
    status_code = 401
    default_detail = "Sessão inválida."
    default_code = "session_invalid"
    structured_errors = {"code": default_code, "detail": default_detail}


class PermissaoCargaNegada(APIException):
    status_code = 403
    default_detail = "Você não tem permissão para executar esta ação."
    default_code = "permission_denied"
    structured_errors = {"code": default_code, "detail": default_detail}


class ServicoIAMIndisponivel(APIException):
    status_code = 503
    default_detail = "Serviço de autorização temporariamente indisponível."
    default_code = "servico_iam_indisponivel"
    structured_errors = {"code": default_code, "detail": default_detail}


class CanPermissionCarga(CanPermission):
    """Decide remotamente no piloto, preservando o modo local por padrão."""

    protege_identidade_iam_remota = True

    def has_permission(self, request, view):
        identidade_remota = carga_http_iam_remoto(request.path)
        if not identidade_remota and not settings.CARGA_IAM_DECISAO_REMOTA_ATIVA:
            return super().has_permission(request, view)

        usuario = request.user
        if not identidade_remota and (not usuario or not usuario.is_authenticated):
            raise SessaoCargaInvalida()
        permissao = getattr(view, "required_permission", None)
        if not permissao or getattr(view, "permission_context", None):
            logger.error("CARGA_IAM_CONTRATO_INSUFICIENTE view=%s", view.__class__.__name__)
            raise ServicoIAMIndisponivel()

        credenciais = {
            nome: valor for nome, valor in request.COOKIES.items()
            if nome.startswith("gpp_session_")
        }
        if not credenciais:
            raise SessaoCargaInvalida()

        try:
            decisao = decidir_acesso_remoto(
                credenciais=credenciais,
                permissao=permissao,
                correlacao=request.headers.get("X-Correlation-ID"),
            )
        except SessaoIAMInvalida as exc:
            raise SessaoCargaInvalida() from exc
        except PermissaoIAMNegada as exc:
            raise PermissaoCargaNegada() from exc
        except IAMIndisponivel as exc:
            raise ServicoIAMIndisponivel() from exc

        if identidade_remota:
            try:
                identidade = IdentidadeIAM(
                    id=decisao.get("usuario_id"),
                    nome=decisao.get("usuario_nome"),
                )
            except ValueError as exc:
                logger.error(
                    "CARGA_IAM_IDENTIDADE_INCOMPLETA decisao_id=%s",
                    decisao.get("decisao_id", "indisponivel"),
                )
                raise ServicoIAMIndisponivel() from exc
            # DRF é isento do CsrfViewMiddleware; não perder a verificação
            # ao dispensar AppContextAuthentication no piloto remoto.
            enforce_csrf(request)
            request.user = identidade
            return True

        if decisao["usuario_id"] != usuario.pk:
            logger.error(
                "CARGA_IAM_IDENTIDADE_DIVERGENTE decisao_id=%s",
                decisao["decisao_id"],
            )
            raise ServicoIAMIndisponivel()
        return True
