"""Cliente compartilhado para os relatórios quantitativos do E-Docs."""

from __future__ import annotations

from urllib.parse import urlparse

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from apps.core.services.edocs_credentials import get_edocs_credentials
from apps.core.services.secret_store import SecretStoreError


class EdocsError(RuntimeError):
    """Falha segura da integração E-Docs, sem credenciais ou respostas brutas."""


class EdocsConfigurationError(EdocsError):
    """Configuração local inválida ou incompleta."""


class EdocsRequestError(EdocsError):
    """Falha de autenticação, transporte ou contrato remoto."""


class EdocsClient:
    """Acessa somente os endpoints aprovados para a coleta mensal."""

    def __init__(self, *, session=None, credential_store=None):
        self.environment = settings.GPP_EDOCS_ENVIRONMENT
        if self.environment not in {"HML", "PRD"}:
            raise EdocsConfigurationError("O ambiente E-Docs não é reconhecido.")
        prefix = f"GPP_EDOCS_{self.environment}"
        self.api_base_url = getattr(settings, f"{prefix}_API_BASE_URL")
        self.token_url = getattr(settings, f"{prefix}_TOKEN_URL")
        self.scope = getattr(settings, f"{prefix}_SCOPE")
        self.timeout = (
            settings.GPP_EDOCS_CONNECT_TIMEOUT_SECONDS,
            settings.GPP_EDOCS_READ_TIMEOUT_SECONDS,
        )
        self.credential_store = credential_store
        self.session = session or self._build_session()
        self._access_token = None
        self._validate_configuration()

    @staticmethod
    def _build_session():
        session = requests.Session()
        retry = Retry(
            total=settings.GPP_EDOCS_GET_MAX_RETRIES,
            connect=settings.GPP_EDOCS_GET_MAX_RETRIES,
            read=settings.GPP_EDOCS_GET_MAX_RETRIES,
            status=settings.GPP_EDOCS_GET_MAX_RETRIES,
            allowed_methods=frozenset({"GET"}),
            status_forcelist=(429, 502, 503, 504),
            backoff_factor=settings.GPP_EDOCS_RETRY_BACKOFF_SECONDS,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def list_patriarchs(self):
        return self._get_list("/v2/agente/patriarcas")

    def process_report(self, month, year):
        return self._get_list(
            f"/v2/processos/relatorio-quantitativos/mes/{month}/ano/{year}"
        )

    def process_report_by_patriarch(self, patriarch_id, month, year):
        return self._get_list(
            "/v2/processos/relatorio-quantitativos/"
            f"{patriarch_id}/mes/{month}/ano/{year}"
        )

    def document_report(self, month, year):
        return self._get_list(
            f"/v2/documentos/relatorio-quantitativos/mes/{month}/ano/{year}"
        )

    def document_report_by_patriarch(self, patriarch_id, month, year):
        return self._get_list(
            "/v2/documentos/relatorio-quantitativos/"
            f"{patriarch_id}/mes/{month}/ano/{year}"
        )

    def _validate_configuration(self):
        for value, label in (
            (self.api_base_url, "URL da API"),
            (self.token_url, "URL do token"),
        ):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname:
                raise EdocsConfigurationError(
                    f"{label} E-Docs deve usar HTTPS."
                )
        if not self.scope:
            raise EdocsConfigurationError("O escopo E-Docs não foi configurado.")

    def _credentials(self):
        try:
            return get_edocs_credentials(self.credential_store)
        except SecretStoreError as exc:
            raise EdocsConfigurationError(
                "As credenciais E-Docs não estão disponíveis."
            ) from exc

    def _token(self, *, refresh=False):
        if self._access_token and not refresh:
            return self._access_token
        credentials = self._credentials()
        try:
            response = self.session.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                    "scope": self.scope,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EdocsRequestError(
                "Não foi possível acessar a autenticação do E-Docs."
            ) from exc
        if response.status_code != 200:
            raise EdocsRequestError("A autenticação do E-Docs foi recusada.")
        try:
            payload = response.json()
            token = payload["access_token"]
        except (KeyError, TypeError, ValueError) as exc:
            raise EdocsRequestError(
                "A autenticação do E-Docs não retornou um token válido."
            ) from exc
        if not isinstance(token, str) or not token:
            raise EdocsRequestError(
                "A autenticação do E-Docs não retornou um token válido."
            )
        self._access_token = token
        return token

    def _get_list(self, path):
        url = f"{self.api_base_url}{path}"
        response = self._get(url, self._token())
        if response.status_code == 401:
            response = self._get(url, self._token(refresh=True))
        if response.status_code != 200:
            raise EdocsRequestError(
                f"O E-Docs recusou a consulta com HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EdocsRequestError(
                "O E-Docs retornou JSON inválido para a consulta."
            ) from exc
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise EdocsRequestError(
                "O E-Docs retornou um formato inesperado para a consulta."
            )
        return payload

    def _get(self, url, token):
        try:
            return self.session.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EdocsRequestError(
                "Não foi possível consultar a API do E-Docs."
            ) from exc
