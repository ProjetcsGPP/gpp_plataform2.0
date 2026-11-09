"""Contrato mínimo para leitura de segredos em um cofre externo."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests


class ErroCofreSegredos(RuntimeError):
    """Falha segura ao obter um segredo, sem incluir valores confidenciais."""


class CofreSegredosOpenBaoAppRoleKV2:
    """Lê um único caminho KV v2 usando uma AppRole de privilégio mínimo."""

    def __init__(
        self,
        *,
        endereco,
        arquivo_role_id,
        arquivo_secret_id,
        ponto_montagem,
        caminho_segredo,
        tempo_limite,
        permitir_loopback_inseguro=False,
        sessao=None,
    ):
        self.endereco = endereco.rstrip("/")
        self.arquivo_role_id = Path(arquivo_role_id)
        self.arquivo_secret_id = Path(arquivo_secret_id)
        self.ponto_montagem = ponto_montagem.strip("/")
        self.caminho_segredo = caminho_segredo.strip("/")
        self.tempo_limite = tempo_limite
        self.permitir_loopback_inseguro = permitir_loopback_inseguro
        self.sessao = sessao or requests.Session()

    def ler(self):
        """Autentica, lê o caminho permitido e devolve somente o dicionário."""
        self._validar_configuracao()
        role_id = self._ler_arquivo_identidade(self.arquivo_role_id)
        secret_id = self._ler_arquivo_identidade(self.arquivo_secret_id)
        try:
            resposta_login = self.sessao.post(
                f"{self.endereco}/v1/auth/approle/login",
                json={"role_id": role_id, "secret_id": secret_id},
                timeout=self.tempo_limite,
            )
            resposta_login.raise_for_status()
            token = resposta_login.json()["auth"]["client_token"]
            resposta_segredo = self.sessao.get(
                f"{self.endereco}/v1/{self.ponto_montagem}/data/"
                f"{self.caminho_segredo}",
                headers={"X-Vault-Token": token},
                timeout=self.tempo_limite,
            )
            resposta_segredo.raise_for_status()
            dados = resposta_segredo.json()["data"]["data"]
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise ErroCofreSegredos(
                "Não foi possível obter o segredo solicitado no cofre."
            ) from exc
        if not isinstance(dados, dict):
            raise ErroCofreSegredos(
                "O cofre retornou um segredo em formato inválido."
            )
        return dados

    def _validar_configuracao(self):
        endereco_analisado = urlparse(self.endereco)
        loopback = endereco_analisado.hostname in {"127.0.0.1", "localhost", "::1"}
        desenvolvimento_inseguro = (
            endereco_analisado.scheme == "http"
            and loopback
            and self.permitir_loopback_inseguro
        )
        if endereco_analisado.scheme != "https" and not desenvolvimento_inseguro:
            raise ErroCofreSegredos("O endereço do cofre deve usar HTTPS.")
        if not self.ponto_montagem or not self.caminho_segredo:
            raise ErroCofreSegredos("O caminho do segredo não foi configurado.")

    @staticmethod
    def _ler_arquivo_identidade(caminho):
        try:
            valor = caminho.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ErroCofreSegredos(
                "A identidade de acesso ao cofre não está disponível."
            ) from exc
        if not valor:
            raise ErroCofreSegredos(
                "A identidade de acesso ao cofre não está disponível."
            )
        return valor
