"""Resolução segura das credenciais usadas pelo cliente CargaRH."""

from dataclasses import dataclass

from django.conf import settings

from common.services.cofre_segredos import (CofreSegredosOpenBaoAppRoleKV2,
                                            ErroCofreSegredos)


@dataclass(frozen=True)
class CargaRHCredentials:
    client_id: str
    client_secret: str


def get_cargarh_credentials(store=None):
    """Obtém credenciais da fonte explicitamente configurada, sem fallback."""
    provider = settings.CARGARH_CREDENTIALS_PROVIDER
    if provider == "environment":
        credentials = CargaRHCredentials(
            client_id=settings.CARGARH_CLIENT_ID.strip(),
            client_secret=settings.CARGARH_CLIENT_SECRET.strip(),
        )
    elif provider == "openbao":
        environment = settings.CARGARH_ENVIRONMENT
        if environment not in {"HML", "PRD"}:
            raise ErroCofreSegredos("O ambiente CargaRH não é reconhecido.")
        setting_prefix = f"CARGARH_{environment}_OPENBAO"
        secret_store = store or CofreSegredosOpenBaoAppRoleKV2(
            endereco=settings.OPENBAO_ADDR,
            arquivo_role_id=getattr(settings, f"{setting_prefix}_ROLE_ID_FILE"),
            arquivo_secret_id=getattr(settings, f"{setting_prefix}_SECRET_ID_FILE"),
            ponto_montagem=settings.CARGARH_OPENBAO_MOUNT_POINT,
            caminho_segredo=getattr(settings, f"{setting_prefix}_SECRET_PATH"),
            tempo_limite=settings.OPENBAO_TIMEOUT_SECONDS,
            permitir_loopback_inseguro=settings.DEBUG,
        )
        data = secret_store.ler()
        credentials = CargaRHCredentials(
            client_id=str(data.get("client_id", "")).strip(),
            client_secret=str(data.get("client_secret", "")).strip(),
        )
    else:
        raise ErroCofreSegredos("O provedor de credenciais não é reconhecido.")
    if not credentials.client_id or not credentials.client_secret:
        raise ErroCofreSegredos("As credenciais CargaRH estão incompletas.")
    return credentials
