"""Cliente E-Docs pertencente ao contexto de PUBLICAÇÕES."""

from __future__ import annotations

from urllib.parse import urlparse

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from apps.pub_institucional.services.credenciais_edocs import (
    obter_credenciais_edocs,
)
from common.services.cofre_segredos import ErroCofreSegredos


class ErroEdocs(RuntimeError):
    """Falha segura da integração E-Docs, sem credenciais ou respostas brutas."""


class ErroConfiguracaoEdocs(ErroEdocs):
    """Configuração local inválida ou incompleta."""


class ErroRequisicaoEdocs(ErroEdocs):
    """Falha de autenticação, transporte ou contrato remoto."""


class ClienteEdocs:
    """Acessa somente os endpoints aprovados para a coleta mensal."""

    def __init__(self, *, sessao=None, cofre_credenciais=None):
        self.ambiente = settings.GPP_EDOCS_ENVIRONMENT
        if self.ambiente not in {"HML", "PRD"}:
            raise ErroConfiguracaoEdocs("O ambiente E-Docs não é reconhecido.")
        prefixo = f"GPP_EDOCS_{self.ambiente}"
        self.url_base_api = getattr(settings, f"{prefixo}_API_BASE_URL")
        self.url_token = getattr(settings, f"{prefixo}_TOKEN_URL")
        self.escopo = getattr(settings, f"{prefixo}_SCOPE")
        self.tempo_limite = (
            settings.GPP_EDOCS_CONNECT_TIMEOUT_SECONDS,
            settings.GPP_EDOCS_READ_TIMEOUT_SECONDS,
        )
        self.cofre_credenciais = cofre_credenciais
        self.sessao = sessao or self._criar_sessao()
        self._token_acesso = None
        self._validar_configuracao()

    @staticmethod
    def _criar_sessao():
        sessao = requests.Session()
        repeticao = Retry(
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
        sessao.mount("https://", HTTPAdapter(max_retries=repeticao))
        return sessao

    def listar_patriarcas(self):
        return self._obter_lista("/v2/agente/patriarcas")

    def relatorio_processos(self, mes, ano):
        return self._obter_lista(
            f"/v2/processos/relatorio-quantitativos/mes/{mes}/ano/{ano}"
        )

    def relatorio_processos_por_patriarca(self, id_patriarca, mes, ano):
        return self._obter_lista(
            "/v2/processos/relatorio-quantitativos/"
            f"{id_patriarca}/mes/{mes}/ano/{ano}"
        )

    def relatorio_documentos(self, mes, ano):
        return self._obter_lista(
            f"/v2/documentos/relatorio-quantitativos/mes/{mes}/ano/{ano}"
        )

    def relatorio_documentos_por_patriarca(self, id_patriarca, mes, ano):
        return self._obter_lista(
            "/v2/documentos/relatorio-quantitativos/"
            f"{id_patriarca}/mes/{mes}/ano/{ano}"
        )

    def _validar_configuracao(self):
        for valor, rotulo in (
            (self.url_base_api, "URL da API"),
            (self.url_token, "URL do token"),
        ):
            endereco = urlparse(valor)
            if endereco.scheme != "https" or not endereco.hostname:
                raise ErroConfiguracaoEdocs(
                    f"{rotulo} E-Docs deve usar HTTPS."
                )
        if not self.escopo:
            raise ErroConfiguracaoEdocs("O escopo E-Docs não foi configurado.")

    def _obter_credenciais(self):
        try:
            return obter_credenciais_edocs(self.cofre_credenciais)
        except ErroCofreSegredos as exc:
            raise ErroConfiguracaoEdocs(
                "As credenciais E-Docs não estão disponíveis."
            ) from exc

    def _obter_token(self, *, renovar=False):
        if self._token_acesso and not renovar:
            return self._token_acesso
        credenciais = self._obter_credenciais()
        try:
            resposta = self.sessao.post(
                self.url_token,
                data={
                    "grant_type": "client_credentials",
                    "client_id": credenciais.id_cliente,
                    "client_secret": credenciais.segredo_cliente,
                    "scope": self.escopo,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.tempo_limite,
            )
        except requests.RequestException as exc:
            raise ErroRequisicaoEdocs(
                "Não foi possível acessar a autenticação do E-Docs."
            ) from exc
        if resposta.status_code != 200:
            raise ErroRequisicaoEdocs("A autenticação do E-Docs foi recusada.")
        try:
            conteudo = resposta.json()
            token = conteudo["access_token"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ErroRequisicaoEdocs(
                "A autenticação do E-Docs não retornou um token válido."
            ) from exc
        if not isinstance(token, str) or not token:
            raise ErroRequisicaoEdocs(
                "A autenticação do E-Docs não retornou um token válido."
            )
        self._token_acesso = token
        return token

    def _obter_lista(self, caminho):
        url = f"{self.url_base_api}{caminho}"
        resposta = self._obter(url, self._obter_token())
        if resposta.status_code == 401:
            resposta = self._obter(url, self._obter_token(renovar=True))
        if resposta.status_code != 200:
            raise ErroRequisicaoEdocs(
                f"O E-Docs recusou a consulta com HTTP {resposta.status_code}."
            )
        try:
            conteudo = resposta.json()
        except ValueError as exc:
            raise ErroRequisicaoEdocs(
                "O E-Docs retornou JSON inválido para a consulta."
            ) from exc
        if not isinstance(conteudo, list) or not all(
            isinstance(registro, dict) for registro in conteudo
        ):
            raise ErroRequisicaoEdocs(
                "O E-Docs retornou um formato inesperado para a consulta."
            )
        return conteudo

    def _obter(self, url, token):
        try:
            return self.sessao.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=self.tempo_limite,
            )
        except requests.RequestException as exc:
            raise ErroRequisicaoEdocs(
                "Não foi possível consultar a API do E-Docs."
            ) from exc
