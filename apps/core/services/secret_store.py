"""Contrato mínimo para leitura de segredos em um cofre externo."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests


class SecretStoreError(RuntimeError):
    """Falha segura ao obter um segredo, sem incluir valores confidenciais."""


class OpenBaoAppRoleKV2Store:
    """Lê um único caminho KV v2 usando uma AppRole de privilégio mínimo."""

    def __init__(
        self,
        *,
        address,
        role_id_file,
        secret_id_file,
        mount_point,
        secret_path,
        timeout,
        allow_insecure_loopback=False,
        session=None,
    ):
        self.address = address.rstrip("/")
        self.role_id_file = Path(role_id_file)
        self.secret_id_file = Path(secret_id_file)
        self.mount_point = mount_point.strip("/")
        self.secret_path = secret_path.strip("/")
        self.timeout = timeout
        self.allow_insecure_loopback = allow_insecure_loopback
        self.session = session or requests.Session()

    def read(self):
        """Autentica, lê o caminho permitido e devolve somente o dicionário."""
        self._validate_configuration()
        role_id = self._read_identity_file(self.role_id_file)
        secret_id = self._read_identity_file(self.secret_id_file)
        try:
            login_response = self.session.post(
                f"{self.address}/v1/auth/approle/login",
                json={"role_id": role_id, "secret_id": secret_id},
                timeout=self.timeout,
            )
            login_response.raise_for_status()
            token = login_response.json()["auth"]["client_token"]
            secret_response = self.session.get(
                f"{self.address}/v1/{self.mount_point}/data/{self.secret_path}",
                headers={"X-Vault-Token": token},
                timeout=self.timeout,
            )
            secret_response.raise_for_status()
            data = secret_response.json()["data"]["data"]
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise SecretStoreError(
                "Não foi possível obter o segredo solicitado no cofre."
            ) from exc
        if not isinstance(data, dict):
            raise SecretStoreError("O cofre retornou um segredo em formato inválido.")
        return data

    def _validate_configuration(self):
        parsed = urlparse(self.address)
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        insecure_dev = (
            parsed.scheme == "http"
            and loopback
            and self.allow_insecure_loopback
        )
        if parsed.scheme != "https" and not insecure_dev:
            raise SecretStoreError("O endereço do cofre deve usar HTTPS.")
        if not self.mount_point or not self.secret_path:
            raise SecretStoreError("O caminho do segredo não foi configurado.")

    @staticmethod
    def _read_identity_file(path):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SecretStoreError(
                "A identidade de acesso ao cofre não está disponível."
            ) from exc
        if not value:
            raise SecretStoreError(
                "A identidade de acesso ao cofre não está disponível."
            )
        return value
