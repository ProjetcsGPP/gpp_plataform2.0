"""Testes do adapter OpenBao sem acesso de rede."""

import pytest
import requests

from apps.core.services.secret_store import OpenBaoAppRoleKV2Store, SecretStoreError


class FakeResponse:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("resposta interna com dados confidenciais")


class FakeSession:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return FakeResponse({"auth": {"client_token": "temporary-vault-token"}})

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return FakeResponse(
            {"data": {"data": {"client_id": "id", "client_secret": "secret"}}}
        )


def test_openbao_le_segredo_com_approle_e_token_apenas_no_header(tmp_path):
    role_file = tmp_path / "role_id"
    secret_file = tmp_path / "secret_id"
    role_file.write_text("role-value", encoding="utf-8")
    secret_file.write_text("secret-id-value", encoding="utf-8")
    session = FakeSession()
    store = OpenBaoAppRoleKV2Store(
        address="http://127.0.0.1:58200",
        role_id_file=role_file,
        secret_id_file=secret_file,
        mount_point="carga-org-lot",
        secret_path="dev/cargarh/hml",
        timeout=3,
        allow_insecure_loopback=True,
        session=session,
    )

    assert store.read() == {"client_id": "id", "client_secret": "secret"}
    assert session.post_calls[0][1]["json"] == {
        "role_id": "role-value",
        "secret_id": "secret-id-value",
    }
    assert session.get_calls[0][1]["headers"] == {
        "X-Vault-Token": "temporary-vault-token"
    }


def test_openbao_rejeita_http_fora_do_loopback(tmp_path):
    store = OpenBaoAppRoleKV2Store(
        address="http://vault.example",
        role_id_file=tmp_path / "role",
        secret_id_file=tmp_path / "secret",
        mount_point="carga-org-lot",
        secret_path="dev/cargarh/hml",
        timeout=3,
        allow_insecure_loopback=True,
    )

    with pytest.raises(SecretStoreError, match="HTTPS"):
        store.read()


def test_openbao_nao_repassa_detalhe_da_resposta_em_erro(tmp_path):
    role_file = tmp_path / "role_id"
    secret_file = tmp_path / "secret_id"
    role_file.write_text("role-value", encoding="utf-8")
    secret_file.write_text("secret-id-value", encoding="utf-8")
    session = FakeSession()
    session.post = lambda *args, **kwargs: FakeResponse({}, status_code=403)
    store = OpenBaoAppRoleKV2Store(
        address="https://vault.example",
        role_id_file=role_file,
        secret_id_file=secret_file,
        mount_point="carga-org-lot",
        secret_path="dev/cargarh/prd",
        timeout=3,
        session=session,
    )

    with pytest.raises(SecretStoreError) as caught:
        store.read()

    assert "confidenciais" not in str(caught.value)
    assert "secret-id-value" not in str(caught.value)
