"""Resolução segura das credenciais usadas pelo cliente CargaRH."""

from dataclasses import dataclass

from django.conf import settings

from apps.core.services.secret_store import OpenBaoAppRoleKV2Store, SecretStoreError


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
            raise SecretStoreError("O ambiente CargaRH não é reconhecido.")
        setting_prefix = f"CARGARH_{environment}_OPENBAO"
        secret_store = store or OpenBaoAppRoleKV2Store(
            address=settings.OPENBAO_ADDR,
            role_id_file=getattr(settings, f"{setting_prefix}_ROLE_ID_FILE"),
            secret_id_file=getattr(settings, f"{setting_prefix}_SECRET_ID_FILE"),
            mount_point=settings.CARGARH_OPENBAO_MOUNT_POINT,
            secret_path=getattr(settings, f"{setting_prefix}_SECRET_PATH"),
            timeout=settings.OPENBAO_TIMEOUT_SECONDS,
            allow_insecure_loopback=settings.DEBUG,
        )
        data = secret_store.read()
        credentials = CargaRHCredentials(
            client_id=str(data.get("client_id", "")).strip(),
            client_secret=str(data.get("client_secret", "")).strip(),
        )
    else:
        raise SecretStoreError("O provedor de credenciais não é reconhecido.")
    if not credentials.client_id or not credentials.client_secret:
        raise SecretStoreError("As credenciais CargaRH estão incompletas.")
    return credentials
