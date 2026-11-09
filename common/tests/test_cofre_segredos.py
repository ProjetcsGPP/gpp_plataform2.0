"""Testes do adaptador OpenBao sem acesso de rede."""

import pytest
import requests

from common.services.cofre_segredos import (CofreSegredosOpenBaoAppRoleKV2,
                                            ErroCofreSegredos)


class RespostaSimulada:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("resposta interna com dados confidenciais")


class SessaoSimulada:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return RespostaSimulada(
            {"auth": {"client_token": "temporary-vault-token"}}
        )

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return RespostaSimulada(
            {"data": {"data": {"client_id": "id", "client_secret": "secret"}}}
        )


def test_openbao_le_segredo_com_approle_e_token_apenas_no_header(tmp_path):
    role_file = tmp_path / "role_id"
    secret_file = tmp_path / "secret_id"
    role_file.write_text("role-value", encoding="utf-8")
    secret_file.write_text("secret-id-value", encoding="utf-8")
    session = SessaoSimulada()
    store = CofreSegredosOpenBaoAppRoleKV2(
        endereco="http://127.0.0.1:58200",
        arquivo_role_id=role_file,
        arquivo_secret_id=secret_file,
        ponto_montagem="carga-org-lot",
        caminho_segredo="dev/cargarh/hml",
        tempo_limite=3,
        permitir_loopback_inseguro=True,
        sessao=session,
    )

    assert store.ler() == {"client_id": "id", "client_secret": "secret"}
    assert session.post_calls[0][1]["json"] == {
        "role_id": "role-value",
        "secret_id": "secret-id-value",
    }
    assert session.get_calls[0][1]["headers"] == {
        "X-Vault-Token": "temporary-vault-token"
    }


def test_openbao_rejeita_http_fora_do_loopback(tmp_path):
    store = CofreSegredosOpenBaoAppRoleKV2(
        endereco="http://vault.example",
        arquivo_role_id=tmp_path / "role",
        arquivo_secret_id=tmp_path / "secret",
        ponto_montagem="carga-org-lot",
        caminho_segredo="dev/cargarh/hml",
        tempo_limite=3,
        permitir_loopback_inseguro=True,
    )

    with pytest.raises(ErroCofreSegredos, match="HTTPS"):
        store.ler()


def test_openbao_nao_repassa_detalhe_da_resposta_em_erro(tmp_path):
    role_file = tmp_path / "role_id"
    secret_file = tmp_path / "secret_id"
    role_file.write_text("role-value", encoding="utf-8")
    secret_file.write_text("secret-id-value", encoding="utf-8")
    session = SessaoSimulada()
    session.post = lambda *args, **kwargs: RespostaSimulada(
        {}, status_code=403
    )
    store = CofreSegredosOpenBaoAppRoleKV2(
        endereco="https://vault.example",
        arquivo_role_id=role_file,
        arquivo_secret_id=secret_file,
        ponto_montagem="carga-org-lot",
        caminho_segredo="dev/cargarh/prd",
        tempo_limite=3,
        sessao=session,
    )

    with pytest.raises(ErroCofreSegredos) as caught:
        store.ler()

    assert "confidenciais" not in str(caught.value)
    assert "secret-id-value" not in str(caught.value)
