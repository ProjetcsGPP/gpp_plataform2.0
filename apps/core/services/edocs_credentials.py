"""Resolução segura das credenciais compartilhadas do E-Docs."""

from dataclasses import dataclass

from django.conf import settings

from apps.core.services.secret_store import (OpenBaoAppRoleKV2Store,
                                             SecretStoreError)


@dataclass(frozen=True)
class EdocsCredentials:
    client_id: str
    client_secret: str


def get_edocs_credentials(store=None):
    """Obtém as credenciais da fonte configurada, sem fallback implícito."""
    provider = settings.GPP_EDOCS_CREDENTIALS_PROVIDER
    if provider == "environment":
        credentials = EdocsCredentials(
            client_id=settings.GPP_EDOCS_CLIENT_ID.strip(),
            client_secret=settings.GPP_EDOCS_CLIENT_SECRET.strip(),
        )
    elif provider == "openbao":
        environment = settings.GPP_EDOCS_ENVIRONMENT
        if environment not in {"HML", "PRD"}:
            raise SecretStoreError("O ambiente E-Docs não é reconhecido.")
        prefix = f"GPP_EDOCS_{environment}_OPENBAO"
        secret_store = store or OpenBaoAppRoleKV2Store(
            address=settings.OPENBAO_ADDR,
            role_id_file=getattr(settings, f"{prefix}_ROLE_ID_FILE"),
            secret_id_file=getattr(settings, f"{prefix}_SECRET_ID_FILE"),
            mount_point=settings.GPP_EDOCS_OPENBAO_MOUNT_POINT,
            secret_path=getattr(settings, f"{prefix}_SECRET_PATH"),
            timeout=settings.OPENBAO_TIMEOUT_SECONDS,
            allow_insecure_loopback=settings.DEBUG,
        )
        data = secret_store.read()
        credentials = EdocsCredentials(
            client_id=str(data.get("client_id", "")).strip(),
            client_secret=str(data.get("client_secret", "")).strip(),
        )
    else:
        raise SecretStoreError(
            "O provedor de credenciais E-Docs não é reconhecido."
        )
    if not credentials.client_id or not credentials.client_secret:
        raise SecretStoreError("As credenciais E-Docs estão incompletas.")
    return credentials
