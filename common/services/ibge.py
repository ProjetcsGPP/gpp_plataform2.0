"""Cliente compartilhado e cacheado da API de Localidades do IBGE."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ErroIbge(RuntimeError):
    """Falha segura de transporte ou contrato da API do IBGE."""


class ClienteIbge:
    """Acessa somente os dois recursos de localidades aprovados."""

    def __init__(self, *, sessao=None):
        self.url_base = settings.IBGE_LOCALIDADES_BASE_URL.rstrip("/") + "/"
        self.tempo_limite = (
            settings.IBGE_LOCALIDADES_CONNECT_TIMEOUT_SECONDS,
            settings.IBGE_LOCALIDADES_READ_TIMEOUT_SECONDS,
        )
        self.sessao = sessao or self._criar_sessao()
        endereco = urlparse(self.url_base)
        if (
            endereco.scheme != "https"
            or endereco.hostname != "servicodados.ibge.gov.br"
        ):
            raise ErroIbge("A URL configurada para o IBGE não é permitida.")

    @staticmethod
    def _criar_sessao():
        sessao = requests.Session()
        repeticao = Retry(
            total=settings.IBGE_LOCALIDADES_MAX_RETRIES,
            connect=settings.IBGE_LOCALIDADES_MAX_RETRIES,
            read=settings.IBGE_LOCALIDADES_MAX_RETRIES,
            status=settings.IBGE_LOCALIDADES_MAX_RETRIES,
            allowed_methods=frozenset({"GET"}),
            status_forcelist=(429, 502, 503, 504),
            backoff_factor=0.3,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        sessao.mount("https://", HTTPAdapter(max_retries=repeticao))
        return sessao

    def _obter_lista(self, caminho, *, parametros=None):
        try:
            resposta = self.sessao.get(
                urljoin(self.url_base, caminho.lstrip("/")),
                params=parametros,
                headers={"Accept": "application/json"},
                timeout=self.tempo_limite,
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except (requests.RequestException, TypeError, ValueError) as exc:
            raise ErroIbge(
                "O serviço de localidades do IBGE está indisponível."
            ) from exc
        if not isinstance(dados, list):
            raise ErroIbge("O IBGE retornou um formato de resposta inesperado.")
        return dados

    def listar_estados(self):
        dados = self._obter_lista("estados", parametros={"orderBy": "nome"})
        estados = []
        for item in dados:
            regiao = item.get("regiao") if isinstance(item, dict) else None
            if not (
                isinstance(item, dict)
                and isinstance(item.get("id"), int)
                and isinstance(item.get("sigla"), str)
                and isinstance(item.get("nome"), str)
                and isinstance(regiao, dict)
            ):
                raise ErroIbge("O IBGE retornou um estado inválido.")
            estados.append(
                {
                    "id": item["id"],
                    "sigla": item["sigla"],
                    "nome": item["nome"],
                    "regiao": {
                        "id": regiao.get("id"),
                        "sigla": regiao.get("sigla"),
                        "nome": regiao.get("nome"),
                    },
                }
            )
        return estados

    def listar_municipios(self, codigo_uf):
        dados = self._obter_lista(f"estados/{codigo_uf}/municipios")
        municipios = []
        for item in dados:
            if not (
                isinstance(item, dict)
                and isinstance(item.get("id"), int)
                and isinstance(item.get("nome"), str)
            ):
                raise ErroIbge("O IBGE retornou um município inválido.")
            municipios.append(
                {
                    "id": item["id"],
                    "nome": item["nome"],
                    "codigo_uf": codigo_uf,
                }
            )
        return municipios


def listar_estados_ibge(*, cliente=None):
    chave = "common:ibge:localidades:estados:v1"
    dados = cache.get(chave)
    if dados is None:
        dados = (cliente or ClienteIbge()).listar_estados()
        cache.set(chave, dados, settings.IBGE_LOCALIDADES_CACHE_SECONDS)
    return dados


def listar_municipios_ibge(codigo_uf, *, cliente=None):
    if isinstance(codigo_uf, bool) or not isinstance(codigo_uf, int):
        raise ValueError("O código da UF deve ser numérico.")
    if codigo_uf < 1 or codigo_uf > 99:
        raise ValueError("O código da UF deve possuir dois dígitos.")
    chave = f"common:ibge:localidades:municipios:{codigo_uf}:v1"
    dados = cache.get(chave)
    if dados is None:
        dados = (cliente or ClienteIbge()).listar_municipios(codigo_uf)
        # O catálogo municipal é referência estável para preenchimento e mapa.
        # Sem timeout, uma nova chamada externa só ocorre se o cache for
        # explicitamente invalidado, reiniciado ou sofrer evicção.
        cache.set(chave, dados, timeout=None)
    return dados
