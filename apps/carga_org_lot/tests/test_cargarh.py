"""Testes do cliente HTTP CargaRH sem realizar chamadas externas."""

import pytest
import requests
from django.core.cache import cache
from django.test import override_settings

from apps.carga_org_lot.services.cargarh import (
    CargaRHClient,
    CargaRHRequestError,
    configuration_status,
)
from apps.carga_org_lot.models import (
    EventoIntegracaoProdest,
    OperacaoIntegracaoProdest,
    ResultadoIntegracaoProdest,
)


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, *, token_responses=None, request_responses=None):
        self.token_responses = list(token_responses or [])
        self.request_responses = list(request_responses or [])
        self.post_calls = []
        self.request_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.token_responses.pop(0)

    def request(self, method, url, **kwargs):
        self.request_calls.append((method, url, kwargs))
        return self.request_responses.pop(0)


VALID_SETTINGS = {
    "DEBUG": False,
    "CARGARH_ENVIRONMENT": "HML",
    "CARGARH_TOKEN_URL": "https://auth.example/token",
    "CARGARH_API_BASE_URL": "https://api.example",
    "CARGARH_CLIENT_ID": "client-id",
    "CARGARH_CLIENT_SECRET": "client-secret",
    "CARGARH_CLIENT_SCOPE": "scope-a scope-b",
    "CARGARH_TARGET_ENVIRONMENT": "",
    "CARGARH_CONNECT_TIMEOUT_SECONDS": 3,
    "CARGARH_READ_TIMEOUT_SECONDS": 7,
    "CARGARH_TOKEN_SAFETY_MARGIN_SECONDS": 60,
}


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(**VALID_SETTINGS)
def test_reutiliza_token_em_cache_e_nao_o_envia_no_payload():
    session = FakeSession(
        token_responses=[
            FakeResponse(200, {"access_token": "temporary-token", "expires_in": 3600})
        ],
        request_responses=[
            FakeResponse(201, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            FakeResponse(201, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        ],
    )
    client = CargaRHClient(session=session)
    payload = {"patriarcaId": "patriarch", "orgaos": []}

    first = client.submit_organogram("patriarch", payload, dry_run=True)
    second = client.submit_organogram("patriarch", payload, dry_run=False)

    assert first.startswith("aaaaaaaa")
    assert second.startswith("bbbbbbbb")
    assert len(session.post_calls) == 1
    assert len(session.request_calls) == 2
    token_request = session.post_calls[0][1]
    assert token_request["auth"] == ("client-id", "client-secret")
    assert "client_id" not in token_request["data"]
    assert "client_secret" not in token_request["data"]
    for _, _, kwargs in session.request_calls:
        assert kwargs["headers"]["Authorization"] == "Bearer temporary-token"
        assert "temporary-token" not in str(kwargs["json"])
        assert kwargs["timeout"] == (3, 7)
    events = list(EventoIntegracaoProdest.objects.order_by("ideventointegracao"))
    assert [event.stroperacao for event in events] == [
        OperacaoIntegracaoProdest.OBTER_TOKEN,
        OperacaoIntegracaoProdest.ENVIAR_ORGANOGRAMA_INICIAL,
        OperacaoIntegracaoProdest.ENVIAR_ORGANOGRAMA_INICIAL,
    ]
    assert all(
        event.strresultado == ResultadoIntegracaoProdest.SUCESSO
        for event in events
    )
    serialized_events = str(
        [
            {
                "endpoint": event.strendpoint,
                "details": event.jsondetalhes,
                "message": event.strmensagem,
            }
            for event in events
        ]
    )
    assert "temporary-token" not in serialized_events
    assert "client-secret" not in serialized_events


@override_settings(**VALID_SETTINGS)
def test_descarta_token_e_repete_uma_vez_apos_401():
    session = FakeSession(
        token_responses=[
            FakeResponse(200, {"access_token": "old-token", "expires_in": 3600}),
            FakeResponse(200, {"access_token": "new-token", "expires_in": 3600}),
        ],
        request_responses=[
            FakeResponse(401, {"title": "Unauthorized"}),
            FakeResponse(200, {"guid": "load", "finalizada": False, "etapas": []}),
        ],
    )

    result = CargaRHClient(session=session).get_status("load")

    assert result["finalizada"] is False
    assert len(session.post_calls) == 2
    assert session.request_calls[0][2]["headers"]["Authorization"] == (
        "Bearer old-token"
    )
    assert session.request_calls[1][2]["headers"]["Authorization"] == (
        "Bearer new-token"
    )
    assert list(
        EventoIntegracaoProdest.objects.filter(
            stroperacao=OperacaoIntegracaoProdest.CONSULTAR_STATUS
        ).values_list("inthttpstatus", flat=True)
    ) == [200, 401]


@override_settings(**VALID_SETTINGS)
def test_lista_cargas_iniciais_com_limite_oficial():
    session = FakeSession(
        token_responses=[
            FakeResponse(200, {"access_token": "temporary-token", "expires_in": 3600})
        ],
        request_responses=[
            FakeResponse(
                200,
                [{"guid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}],
            )
        ],
    )

    result = CargaRHClient(session=session).list_initial_imports(
        "patriarch",
        limit=7,
    )

    assert len(result) == 1
    method, url, kwargs = session.request_calls[0]
    assert method == "GET"
    assert url.endswith("/v3/importacoes-iniciais/patriarcas/patriarch")
    assert kwargs["params"] == {"limit": 7}


@override_settings(**VALID_SETTINGS)
def test_lista_cargas_iniciais_rejeita_formato_inesperado():
    session = FakeSession(
        token_responses=[
            FakeResponse(200, {"access_token": "temporary-token", "expires_in": 3600})
        ],
        request_responses=[FakeResponse(200, {"guid": "load"})],
    )

    with pytest.raises(CargaRHRequestError, match="formato inválido"):
        CargaRHClient(session=session).list_initial_imports("patriarch")


@override_settings(**VALID_SETTINGS)
def test_timeout_retorna_erro_seguro_sem_credenciais():
    class TimeoutSession(FakeSession):
        def request(self, method, url, **kwargs):
            raise requests.ReadTimeout("contains internal transport details")

    session = TimeoutSession(
        token_responses=[
            FakeResponse(200, {"access_token": "temporary-token", "expires_in": 3600})
        ]
    )

    with pytest.raises(CargaRHRequestError) as caught:
        CargaRHClient(session=session).get_status("load")

    assert "tempo limite" in str(caught.value)
    assert "temporary-token" not in str(caught.value)


@override_settings(
    **{
        **VALID_SETTINGS,
        "CARGARH_CLIENT_SECRET": "",
        "CARGARH_API_BASE_URL": "http://insecure.example",
    }
)
def test_diagnostico_informa_campos_sem_expor_valores():
    result = configuration_status()

    assert result["configurado"] is False
    assert result["ausentes"] == ["CARGARH_CLIENT_SECRET"]
    assert result["invalidas"] == ["CARGARH_API_BASE_URL"]
    assert "client-secret" not in str(result)
