"""Testes do cliente compartilhado E-Docs sem chamadas externas."""

import requests
from django.test import override_settings

from apps.core.services.edocs import EdocsClient, EdocsRequestError
from apps.core.services.edocs_credentials import get_edocs_credentials


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, *, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)


@override_settings(
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_edocs_credentials_environment():
    credentials = get_edocs_credentials()

    assert credentials.client_id == "synthetic-client"
    assert credentials.client_secret == "synthetic-secret"


@override_settings(
    GPP_EDOCS_ENVIRONMENT="HML",
    GPP_EDOCS_HML_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_HML_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_HML_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_client_uses_client_credentials_and_authorization_header():
    session = FakeSession(
        post_responses=[FakeResponse(200, {"access_token": "short-token"})],
        get_responses=[FakeResponse(200, [{"id": "patriarch"}])],
    )
    client = EdocsClient(session=session)

    assert client.list_patriarchs() == [{"id": "patriarch"}]
    assert session.post_calls[0][1]["data"] == {
        "grant_type": "client_credentials",
        "client_id": "synthetic-client",
        "client_secret": "synthetic-secret",
        "scope": "api-sigades-consultar",
    }
    assert session.get_calls[0][1]["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer short-token",
    }
    assert session.get_calls[0][0] == (
        "https://edocs.example/v2/agente/patriarcas"
    )


@override_settings(
    GPP_EDOCS_ENVIRONMENT="PRD",
    GPP_EDOCS_PRD_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_PRD_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_PRD_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_client_refreshes_token_once_after_unauthorized():
    session = FakeSession(
        post_responses=[
            FakeResponse(200, {"access_token": "old-token"}),
            FakeResponse(200, {"access_token": "new-token"}),
        ],
        get_responses=[
            FakeResponse(401, {}),
            FakeResponse(200, []),
        ],
    )
    client = EdocsClient(session=session)

    assert client.document_report("10", 2025) == []
    assert len(session.post_calls) == 2
    assert session.get_calls[1][1]["headers"]["Authorization"] == (
        "Bearer new-token"
    )


@override_settings(
    GPP_EDOCS_ENVIRONMENT="HML",
    GPP_EDOCS_HML_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_HML_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_HML_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_client_redacts_remote_error_details():
    session = FakeSession(
        post_responses=[FakeResponse(403, {"client_secret": "must-not-leak"})]
    )
    client = EdocsClient(session=session)

    try:
        client.list_patriarchs()
    except EdocsRequestError as exc:
        message = str(exc)
    else:
        raise AssertionError("A autenticação inválida deveria falhar.")

    assert "must-not-leak" not in message
    assert "synthetic-secret" not in message


@override_settings(
    GPP_EDOCS_ENVIRONMENT="HML",
    GPP_EDOCS_HML_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_HML_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_HML_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_client_redacts_transport_exception():
    class FailingSession(FakeSession):
        def post(self, url, **kwargs):
            raise requests.ConnectionError("secret in provider response")

    client = EdocsClient(session=FailingSession())

    try:
        client.list_patriarchs()
    except EdocsRequestError as exc:
        message = str(exc)
    else:
        raise AssertionError("A falha de transporte deveria ser propagada.")

    assert "secret in provider response" not in message
