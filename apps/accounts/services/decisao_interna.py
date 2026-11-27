"""Decisão IAM para serviços internos, sem expor modelos ao serviço.

O serviço chamador não escolhe a aplicação-alvo: cada endpoint usa credencial
M2M exclusiva e fixa a aplicação no servidor. Não substitui autorização por objeto.
"""

from django.utils import timezone

from django.contrib.auth import get_user_model

from apps.accounts.models import AccountsSession, UserAuthzState
from apps.accounts.services.application_registry import ApplicationRegistry
from apps.accounts.services.authorization_service import AuthorizationService

APLICACAO_CARGA = "CARGA_ORG_LOT"
APLICACAO_PUBLICACOES = "PUB_INSTITUCIONAL"
APLICACAO_ACOES = "ACOES_PNGI"
PREFIXO_COOKIE = "gpp_session_"


def decidir_acesso_carga(*, credenciais, permissao):
    """Retorna resultado e metadados mínimos, sem replicar política no chamador."""
    return _decidir_acesso_aplicacao(
        credenciais=credenciais, permissao=permissao,
        codigo_aplicacao=APLICACAO_CARGA,
    )


def decidir_acesso_publicacoes(*, credenciais, permissao):
    """Decide para Publicações sem aceitar aplicação-alvo do solicitante."""
    return _decidir_acesso_aplicacao(
        credenciais=credenciais, permissao=permissao,
        codigo_aplicacao=APLICACAO_PUBLICACOES,
    )


def decidir_acesso_acoes(*, credenciais, permissao):
    """Decide para Ações PNGI sem aceitar aplicação-alvo do solicitante."""
    return _decidir_acesso_aplicacao(
        credenciais=credenciais, permissao=permissao,
        codigo_aplicacao=APLICACAO_ACOES,
    )


def _decidir_acesso_aplicacao(*, credenciais, permissao, codigo_aplicacao):
    dedicado = PREFIXO_COOKIE + codigo_aplicacao
    chave_sessao = credenciais.get(dedicado)
    if not chave_sessao:
        return {"resultado": "SESSAO_INVALIDA"}
    filtros = {
        "revoked": False,
        "expires_at__gt": timezone.now(),
        "user__is_active": True,
    }
    sessao = (
        AccountsSession.objects.filter(
            session_key=chave_sessao,
            session_cookie_name=dedicado,
            app_context=codigo_aplicacao,
            **filtros,
        )
        .select_related("user")
        .first()
    )
    if sessao is None:
        return {"resultado": "SESSAO_INVALIDA"}

    usuario = sessao.user
    aplicacao = ApplicationRegistry().get(codigo_aplicacao)
    if aplicacao is None:
        raise RuntimeError("Aplicação interna não cadastrada no IAM")

    # O endpoint entre serviços decide sempre sobre o estado confirmado no
    # banco, sem reutilizar uma versão de permissões em cache após revogação.
    if not AuthorizationService(usuario, aplicacao, usar_cache=False).can(permissao):
        return {"resultado": "NEGADO", "usuario_id": usuario.pk}

    nome_usuario = usuario.get_full_name().strip() or usuario.get_username().strip()
    if not nome_usuario or len(nome_usuario) > 200 or any(
        ord(caractere) < 32 or ord(caractere) == 127 for caractere in nome_usuario
    ):
        raise ValueError("Nome do usuário inválido para auditoria")

    versao = (
        UserAuthzState.objects.filter(user_id=usuario.pk)
        .values_list("authz_version", flat=True)
        .first()
    )
    return {
        "resultado": "AUTORIZADO",
        "usuario_id": usuario.pk,
        "usuario_nome": nome_usuario,
        "versao_autorizacao": versao if versao is not None else 0,
        "expira_em": sessao.expires_at.isoformat(),
    }


def decidir_atividade_carga(*, usuario_id, permissao):
    """Revalida autorização atual de uma atividade persistida, sem sessão.

    O chamador M2M é exclusivo de Carga e deve obter `usuario_id` do registro
    persistido da atividade; a mensagem Celery não escolhe a identidade.
    """
    usuario = get_user_model().objects.filter(pk=usuario_id, is_active=True).first()
    if usuario is None:
        return {"resultado": "NEGADO", "usuario_id": usuario_id}
    aplicacao = ApplicationRegistry().get(APLICACAO_CARGA)
    if aplicacao is None:
        raise RuntimeError("Aplicação Carga não cadastrada no IAM")
    if not AuthorizationService(usuario, aplicacao, usar_cache=False).can(permissao):
        return {"resultado": "NEGADO", "usuario_id": usuario_id}
    versao = (
        UserAuthzState.objects.filter(user_id=usuario_id)
        .values_list("authz_version", flat=True)
        .first()
    )
    return {
        "resultado": "AUTORIZADO",
        "usuario_id": usuario_id,
        "versao_autorizacao": versao if versao is not None else 0,
    }


def decidir_atividade_publicacoes(*, usuario_id, permissao):
    """Revalida uma coleta persistida de Publicações sem sessão no worker."""
    usuario = get_user_model().objects.filter(pk=usuario_id, is_active=True).first()
    if usuario is None:
        return {"resultado": "NEGADO", "usuario_id": usuario_id}
    aplicacao = ApplicationRegistry().get("PUB_INSTITUCIONAL")
    if aplicacao is None:
        raise RuntimeError("Aplicação Publicações não cadastrada no IAM")
    if not AuthorizationService(usuario, aplicacao, usar_cache=False).can(permissao):
        return {"resultado": "NEGADO", "usuario_id": usuario_id}
    versao = (
        UserAuthzState.objects.filter(user_id=usuario_id)
        .values_list("authz_version", flat=True)
        .first()
    )
    return {
        "resultado": "AUTORIZADO",
        "usuario_id": usuario_id,
        "versao_autorizacao": versao if versao is not None else 0,
    }
