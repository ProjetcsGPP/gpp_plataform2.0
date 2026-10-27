"""Testes da seleção de credenciais CargaRH por ambiente."""

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.carga_org_lot.services.credentials import get_cargarh_credentials
from apps.core.services.secret_store import SecretStoreError


class FakeStore:
    def __init__(self, data=None, error=None):
        self.data = data or {}
        self.error = error

    def read(self):
        if self.error:
            raise self.error
        return self.data


@override_settings(
    CARGARH_CREDENTIALS_PROVIDER="openbao",
    CARGARH_ENVIRONMENT="HML",
)
def test_credenciais_openbao_sao_lidas_sem_fallback_de_ambiente():
    credentials = get_cargarh_credentials(
        store=FakeStore({"client_id": "hml-id", "client_secret": "hml-secret"})
    )

    assert credentials.client_id == "hml-id"
    assert credentials.client_secret == "hml-secret"


@override_settings(
    CARGARH_CREDENTIALS_PROVIDER="openbao",
    CARGARH_ENVIRONMENT="PRD",
    CARGARH_CLIENT_ID="legacy-id",
    CARGARH_CLIENT_SECRET="legacy-secret",
)
def test_falha_do_openbao_nao_recua_para_segredo_legado():
    with pytest.raises(SecretStoreError):
        get_cargarh_credentials(store=FakeStore(error=SecretStoreError("falha")))


@override_settings(
    CARGARH_CREDENTIALS_PROVIDER="openbao",
    CARGARH_ENVIRONMENT="PRD",
    CARGARH_PRD_OPENBAO_ROLE_ID_FILE="/run/prd-role",
    CARGARH_PRD_OPENBAO_SECRET_ID_FILE="/run/prd-secret",
    CARGARH_PRD_OPENBAO_SECRET_PATH="dev/cargarh/prd",
)
@patch("apps.carga_org_lot.services.credentials.OpenBaoAppRoleKV2Store")
def test_prd_seleciona_identidade_e_caminho_exclusivos(store_class):
    store_class.return_value.read.return_value = {
        "client_id": "prd-id",
        "client_secret": "prd-secret",
    }

    get_cargarh_credentials()

    kwargs = store_class.call_args.kwargs
    assert kwargs["role_id_file"] == "/run/prd-role"
    assert kwargs["secret_id_file"] == "/run/prd-secret"
    assert kwargs["secret_path"] == "dev/cargarh/prd"


@override_settings(
    CARGARH_CREDENTIALS_PROVIDER="openbao",
    CARGARH_ENVIRONMENT="INVALIDO",
)
def test_ambiente_invalido_falha_sem_tentar_resolver_arquivo():
    with pytest.raises(SecretStoreError, match="ambiente"):
        get_cargarh_credentials()
