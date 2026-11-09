"""Resolução segura das credenciais usadas pelo cliente E-Docs."""

from dataclasses import dataclass

from django.conf import settings

from common.services.cofre_segredos import (CofreSegredosOpenBaoAppRoleKV2,
                                            ErroCofreSegredos)


@dataclass(frozen=True)
class CredenciaisEdocs:
    id_cliente: str
    segredo_cliente: str


def obter_credenciais_edocs(cofre=None):
    """Obtém as credenciais da fonte configurada, sem fallback implícito."""
    provedor = settings.GPP_EDOCS_CREDENTIALS_PROVIDER
    if provedor == "environment":
        credenciais = CredenciaisEdocs(
            id_cliente=settings.GPP_EDOCS_CLIENT_ID.strip(),
            segredo_cliente=settings.GPP_EDOCS_CLIENT_SECRET.strip(),
        )
    elif provedor == "openbao":
        ambiente = settings.GPP_EDOCS_ENVIRONMENT
        if ambiente not in {"HML", "PRD"}:
            raise ErroCofreSegredos("O ambiente E-Docs não é reconhecido.")
        prefixo = f"GPP_EDOCS_{ambiente}_OPENBAO"
        cofre_configurado = cofre or CofreSegredosOpenBaoAppRoleKV2(
            endereco=settings.OPENBAO_ADDR,
            arquivo_role_id=getattr(settings, f"{prefixo}_ROLE_ID_FILE"),
            arquivo_secret_id=getattr(settings, f"{prefixo}_SECRET_ID_FILE"),
            ponto_montagem=settings.GPP_EDOCS_OPENBAO_MOUNT_POINT,
            caminho_segredo=getattr(settings, f"{prefixo}_SECRET_PATH"),
            tempo_limite=settings.OPENBAO_TIMEOUT_SECONDS,
            permitir_loopback_inseguro=settings.DEBUG,
        )
        dados = cofre_configurado.ler()
        credenciais = CredenciaisEdocs(
            id_cliente=str(dados.get("client_id", "")).strip(),
            segredo_cliente=str(dados.get("client_secret", "")).strip(),
        )
    else:
        raise ErroCofreSegredos(
            "O provedor de credenciais E-Docs não é reconhecido."
        )
    if not credenciais.id_cliente or not credenciais.segredo_cliente:
        raise ErroCofreSegredos("As credenciais E-Docs estão incompletas.")
    return credenciais
