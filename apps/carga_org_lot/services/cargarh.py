"""Cliente servidor-servidor para a API CargaRH/PRODEST."""

from __future__ import annotations

import hashlib
import logging
import time
from urllib.parse import urlparse
from uuid import UUID, uuid4

import requests
from django.conf import settings
from django.core.cache import cache

from apps.carga_org_lot.models import (
    EventoIntegracaoProdest,
    OperacaoIntegracaoProdest,
    ResultadoIntegracaoProdest,
)
from apps.carga_org_lot.services.credentials import get_cargarh_credentials
from apps.core.services.secret_store import SecretStoreError


logger = logging.getLogger(__name__)


class CargaRHConfigurationError(RuntimeError):
    """Indica configuração ausente ou insegura, sem revelar credenciais."""


class CargaRHRequestError(RuntimeError):
    """Erro seguro ocorrido na comunicação com a PRODEST."""

    def __init__(self, message, *, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def configuration_status(credential_store=None, credentials=None) -> dict:
    credentials_missing = False
    credential_provider_invalid = False
    if settings.CARGARH_CREDENTIALS_PROVIDER == "environment":
        credentials_missing = not (
            settings.CARGARH_CLIENT_ID and settings.CARGARH_CLIENT_SECRET
        )
    else:
        try:
            resolved = credentials or get_cargarh_credentials(
                store=credential_store
            )
            credentials_missing = not (
                resolved.client_id and resolved.client_secret
            )
        except SecretStoreError:
            credential_provider_invalid = True
    required = {
        "CARGARH_TOKEN_URL": settings.CARGARH_TOKEN_URL,
        "CARGARH_API_BASE_URL": settings.CARGARH_API_BASE_URL,
        "CARGARH_CLIENT_SCOPE": settings.CARGARH_CLIENT_SCOPE,
    }
    missing = [name for name, value in required.items() if not value]
    if credentials_missing:
        missing.append("CARGARH_CREDENTIALS")
    invalid = []
    if credential_provider_invalid:
        invalid.append("CARGARH_CREDENTIALS_PROVIDER")
    for name in ("CARGARH_TOKEN_URL", "CARGARH_API_BASE_URL"):
        value = required[name]
        if value and urlparse(value).scheme not in {"http", "https"}:
            invalid.append(name)
        if value and not settings.DEBUG and urlparse(value).scheme != "https":
            invalid.append(name)
    if settings.CARGARH_ENVIRONMENT not in {"HML", "PRD"}:
        invalid.append("CARGARH_ENVIRONMENT")
    if settings.CARGARH_CONNECT_TIMEOUT_SECONDS <= 0:
        invalid.append("CARGARH_CONNECT_TIMEOUT_SECONDS")
    if settings.CARGARH_READ_TIMEOUT_SECONDS <= 0:
        invalid.append("CARGARH_READ_TIMEOUT_SECONDS")
    if settings.CARGARH_GET_MAX_RETRIES < 0:
        invalid.append("CARGARH_GET_MAX_RETRIES")
    if settings.CARGARH_RETRY_BACKOFF_SECONDS < 0:
        invalid.append("CARGARH_RETRY_BACKOFF_SECONDS")
    return {
        "configurado": not missing and not invalid,
        "ambiente": settings.CARGARH_ENVIRONMENT,
        "ausentes": missing,
        "invalidas": sorted(set(invalid)),
    }


class CargaRHClient:
    """Autentica, reutiliza o token em cache e chama a API CargaRH v3."""

    def __init__(
        self,
        session=None,
        *,
        patriarch_id=None,
        process_id=None,
        submission_id=None,
        external_load_id=None,
        actor=None,
        correlation_id=None,
        credential_store=None,
    ):
        self.session = session or self._build_session()
        self.timeout = (
            settings.CARGARH_CONNECT_TIMEOUT_SECONDS,
            settings.CARGARH_READ_TIMEOUT_SECONDS,
        )
        self.patriarch_id = patriarch_id
        self.process_id = process_id
        self.submission_id = submission_id
        self.external_load_id = external_load_id
        self.actor = actor
        self.correlation_id = correlation_id or uuid4()
        self.credential_store = credential_store
        self._resolved_credentials = None
        self._token_attempt = 0

    def test_authentication(self):
        """Valida as credenciais sem revelar o access token ao chamador."""
        self._ensure_configuration()
        return bool(self._get_access_token())

    def test_connection(self):
        """Valida token e autorização efetiva no endpoint seguro de ping."""
        response = self._request(
            "GET",
            "/v3/ping",
            operation=OperacaoIntegracaoProdest.TESTAR_CONEXAO,
        )
        self._require_status(response, {200}, "testar a conexão")
        return True

    def submit_organogram(self, patriarch_id, payload, *, dry_run):
        response = self._request(
            "POST",
            f"/v3/importacoes-iniciais/patriarcas/{patriarch_id}/organograma",
            operation=OperacaoIntegracaoProdest.ENVIAR_ORGANOGRAMA_INICIAL,
            params={"dryRun": str(bool(dry_run)).lower()},
            json=payload,
        )
        self._require_status(response, {201}, "enviar o organograma")
        try:
            carga_id = response.json()
        except ValueError:
            carga_id = response.text.strip().strip('"')
        try:
            carga_id = str(UUID(str(carga_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise CargaRHRequestError(
                "A PRODEST retornou um identificador de carga inválido.",
                status_code=response.status_code,
            ) from exc
        return carga_id

    def get_status(self, carga_id):
        response = self._request(
            "GET",
            f"/v3/importacoes-iniciais/{carga_id}",
            operation=OperacaoIntegracaoProdest.CONSULTAR_STATUS,
        )
        self._require_status(response, {200}, "consultar a carga")
        return self._json_object(response, "situação da carga")

    def get_report(self, carga_id):
        response = self._request(
            "GET",
            f"/v3/importacoes-iniciais/{carga_id}/relatorio",
            operation=OperacaoIntegracaoProdest.CONSULTAR_RELATORIO,
        )
        self._require_status(response, {200}, "consultar o relatório")
        return self._json_object(response, "relatório da carga")

    def list_initial_imports(self, patriarch_id, *, limit=10):
        response = self._request(
            "GET",
            f"/v3/importacoes-iniciais/patriarcas/{patriarch_id}",
            operation=OperacaoIntegracaoProdest.LISTAR_CARGAS_INICIAIS,
            params={"limit": limit},
        )
        self._require_status(response, {200}, "consultar as cargas iniciais")
        return self._json_list(response, "lista de cargas iniciais")

    def _request(self, method, path, *, operation, **kwargs):
        self._ensure_configuration()
        attempt = [0]
        response = self._authorized_request(
            method,
            path,
            operation=operation,
            attempt=attempt,
            **kwargs,
        )
        if response.status_code == 401:
            self._discard_cached_token()
            response = self._authorized_request(
                method,
                path,
                operation=operation,
                attempt=attempt,
                **kwargs,
            )
        return response

    def _authorized_request(self, method, path, *, operation, attempt, **kwargs):
        token = self._get_access_token()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if settings.CARGARH_TARGET_ENVIRONMENT:
            headers["X-Target-Environment"] = settings.CARGARH_TARGET_ENVIRONMENT
        endpoint = f"{settings.CARGARH_API_BASE_URL}{path}"
        max_attempts = 1 + (
            settings.CARGARH_GET_MAX_RETRIES if method.upper() == "GET" else 0
        )
        for retry_index in range(max_attempts):
            attempt[0] += 1
            started_at = time.monotonic()
            try:
                response = self.session.request(
                    method,
                    endpoint,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.Timeout as exc:
                self._record_event(
                    operation=operation,
                    method=method,
                    endpoint=endpoint,
                    attempt=attempt[0],
                    result=ResultadoIntegracaoProdest.TIMEOUT,
                    duration_ms=self._duration_ms(started_at),
                    message="A PRODEST não respondeu dentro do tempo limite.",
                )
                if retry_index + 1 < max_attempts:
                    self._retry_pause(retry_index)
                    continue
                raise CargaRHRequestError(
                    "A PRODEST não respondeu dentro do tempo limite."
                ) from exc
            except requests.RequestException as exc:
                self._record_event(
                    operation=operation,
                    method=method,
                    endpoint=endpoint,
                    attempt=attempt[0],
                    result=ResultadoIntegracaoProdest.ERRO_CONEXAO,
                    duration_ms=self._duration_ms(started_at),
                    message="Não foi possível estabelecer comunicação com a PRODEST.",
                    details={"tipo_erro": type(exc).__name__},
                )
                logger.warning("CARGARH_REQUEST_FAILED type=%s", type(exc).__name__)
                if retry_index + 1 < max_attempts:
                    self._retry_pause(retry_index)
                    continue
                raise CargaRHRequestError(
                    "Não foi possível estabelecer comunicação com a PRODEST."
                ) from exc

            success = 200 <= response.status_code < 300
            self._record_event(
                operation=operation,
                method=method,
                endpoint=endpoint,
                attempt=attempt[0],
                result=(
                    ResultadoIntegracaoProdest.SUCESSO
                    if success
                    else ResultadoIntegracaoProdest.ERRO_HTTP
                ),
                duration_ms=self._duration_ms(started_at),
                message=self._response_message(response.status_code),
                status_code=response.status_code,
                details=self._safe_response_details(response),
            )
            retryable = response.status_code in {502, 503, 504}
            if retryable and retry_index + 1 < max_attempts:
                self._retry_pause(retry_index)
                continue
            return response

        raise AssertionError("A tentativa de comunicação terminou sem resposta.")

    def _get_access_token(self):
        credentials = self._credentials()
        cache_key = self._token_cache_key()
        cached_token = cache.get(cache_key)
        if cached_token:
            return cached_token
        self._token_attempt += 1
        started_at = time.monotonic()
        try:
            response = self.session.post(
                settings.CARGARH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "scope": settings.CARGARH_CLIENT_SCOPE,
                },
                auth=(
                    credentials.client_id,
                    credentials.client_secret,
                ),
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            self._record_event(
                operation=OperacaoIntegracaoProdest.OBTER_TOKEN,
                method="POST",
                endpoint=settings.CARGARH_TOKEN_URL,
                attempt=self._token_attempt,
                result=ResultadoIntegracaoProdest.TIMEOUT,
                duration_ms=self._duration_ms(started_at),
                message="O serviço de autenticação excedeu o tempo limite.",
            )
            raise CargaRHRequestError(
                "O serviço de autenticação da PRODEST excedeu o tempo limite."
            ) from exc
        except requests.RequestException as exc:
            self._record_event(
                operation=OperacaoIntegracaoProdest.OBTER_TOKEN,
                method="POST",
                endpoint=settings.CARGARH_TOKEN_URL,
                attempt=self._token_attempt,
                result=ResultadoIntegracaoProdest.ERRO_CONEXAO,
                duration_ms=self._duration_ms(started_at),
                message="Não foi possível acessar o serviço de autenticação.",
                details={"tipo_erro": type(exc).__name__},
            )
            logger.warning("CARGARH_AUTH_FAILED type=%s", type(exc).__name__)
            raise CargaRHRequestError(
                "Não foi possível autenticar no serviço da PRODEST."
            ) from exc
        token_success = response.status_code == 200
        self._record_event(
            operation=OperacaoIntegracaoProdest.OBTER_TOKEN,
            method="POST",
            endpoint=settings.CARGARH_TOKEN_URL,
            attempt=self._token_attempt,
            result=(
                ResultadoIntegracaoProdest.SUCESSO
                if token_success
                else ResultadoIntegracaoProdest.ERRO_HTTP
            ),
            duration_ms=self._duration_ms(started_at),
            message=(
                "A autenticação segura foi concluída."
                if token_success
                else "O Acesso Cidadão recusou a autenticação."
            ),
            status_code=response.status_code,
            details={
                **self._safe_response_details(response),
                "escopos_solicitados": settings.CARGARH_CLIENT_SCOPE.split(),
            },
        )
        self._require_status(response, {200}, "autenticar na PRODEST")
        data = self._json_object(response, "autenticação")
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise CargaRHRequestError(
                "A autenticação da PRODEST não retornou um token válido."
            )
        try:
            expires_in = int(data.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600
        timeout = max(
            1,
            expires_in - settings.CARGARH_TOKEN_SAFETY_MARGIN_SECONDS,
        )
        cache.set(cache_key, token, timeout=timeout)
        return token

    def _ensure_configuration(self):
        try:
            credentials = self._credentials()
        except SecretStoreError as exc:
            raise CargaRHConfigurationError(
                "As credenciais CargaRH não estão disponíveis no cofre."
            ) from exc
        status = configuration_status(
            self.credential_store,
            credentials=credentials,
        )
        if not status["configurado"]:
            fields = status["ausentes"] + status["invalidas"]
            raise CargaRHConfigurationError(
                "Configuração CargaRH incompleta ou inválida: "
                + ", ".join(sorted(set(fields)))
            )

    @staticmethod
    def _json_object(response, description):
        try:
            data = response.json()
        except ValueError as exc:
            raise CargaRHRequestError(
                f"A PRODEST retornou {description} em formato inválido.",
                status_code=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise CargaRHRequestError(
                f"A PRODEST retornou {description} em formato inválido.",
                status_code=response.status_code,
            )
        return data

    @staticmethod
    def _json_list(response, description):
        try:
            data = response.json()
        except ValueError as exc:
            raise CargaRHRequestError(
                f"A PRODEST retornou {description} em formato inválido.",
                status_code=response.status_code,
            ) from exc
        if not isinstance(data, list) or not all(
            isinstance(item, dict) for item in data
        ):
            raise CargaRHRequestError(
                f"A PRODEST retornou {description} em formato inválido.",
                status_code=response.status_code,
            )
        return data

    @staticmethod
    def _build_session():
        return requests.Session()

    @staticmethod
    def _duration_ms(started_at):
        return max(0, round((time.monotonic() - started_at) * 1000))

    @staticmethod
    def _safe_response_details(response):
        try:
            body = response.json()
        except ValueError:
            return {}
        if not isinstance(body, dict):
            return {}
        allowed = {"title", "detail", "status", "errors", "traceId", "error"}
        return {key: body[key] for key in allowed if key in body}

    @staticmethod
    def _response_message(status_code):
        if 200 <= status_code < 300:
            return "Comunicação concluída com sucesso."
        if status_code == 401:
            return "A PRODEST não autorizou a integração."
        if status_code == 403:
            return "A PRODEST recusou o acesso a esta operação."
        if status_code in {502, 503, 504}:
            return "O serviço da PRODEST está temporariamente indisponível."
        return "A PRODEST respondeu com erro à solicitação."

    @staticmethod
    def _retry_pause(retry_index):
        delay = settings.CARGARH_RETRY_BACKOFF_SECONDS * (2**retry_index)
        if delay > 0:
            time.sleep(delay)

    def _record_event(
        self,
        *,
        operation,
        method,
        endpoint,
        attempt,
        result,
        duration_ms,
        message,
        status_code=None,
        details=None,
    ):
        actor_id = getattr(self.actor, "user_id", None)
        actor_name = getattr(self.actor, "user_name", "")
        EventoIntegracaoProdest.objects.create(
            idcorrelacao=self.correlation_id,
            idpatriarca_id=self.patriarch_id,
            idprocessocargainicial_id=self.process_id,
            idenvioorganograma_id=self.submission_id,
            idexternocarga=self.external_load_id,
            stroperacao=operation,
            strmetodo=method.upper(),
            strendpoint=endpoint,
            inttentativa=attempt,
            strresultado=result,
            inthttpstatus=status_code,
            intduracaoms=duration_ms,
            strmensagem=message,
            jsondetalhes=details or {},
            created_by_id=actor_id,
            created_by_name=actor_name,
            updated_by_id=actor_id,
            updated_by_name=actor_name,
        )

    @staticmethod
    def _require_status(response, expected, operation):
        if response.status_code in expected:
            return
        details = {}
        try:
            body = response.json()
            if isinstance(body, dict):
                allowed = {"title", "detail", "status", "errors", "traceId"}
                details = {key: body[key] for key in allowed if key in body}
        except ValueError:
            pass
        raise CargaRHRequestError(
            f"A PRODEST recusou a solicitação ao {operation}.",
            status_code=response.status_code,
            details=details,
        )

    def _token_cache_key(self):
        credentials = self._credentials()
        identity = "|".join(
            [
                settings.CARGARH_TOKEN_URL,
                credentials.client_id,
                settings.CARGARH_CLIENT_SCOPE,
                hashlib.sha256(
                    credentials.client_secret.encode("utf-8")
                ).hexdigest(),
            ]
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"cargarh:access-token:{digest}"

    def _discard_cached_token(self):
        cache.delete(self._token_cache_key())

    def _credentials(self):
        if self._resolved_credentials is None:
            self._resolved_credentials = get_cargarh_credentials(
                store=self.credential_store
            )
        return self._resolved_credentials
