"""Transporte compartilhado da decisão HTTP IAM para aplicações isoladas.

Não interpreta roles. Falhas de rede, configuração ou contrato são fechadas.
"""

from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

import requests
from django.utils import timezone


class IAMIndisponivel(RuntimeError):
    """Não há decisão confiável; o chamador deve responder 503."""


class SessaoIAMInvalida(RuntimeError):
    """O IAM confirmou sessão inválida; o chamador deve responder 401."""


class PermissaoIAMNegada(RuntimeError):
    """O IAM negou a ação; o chamador deve responder 403."""


def _inteiro(valor, minimo):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= minimo


def _validar_url(url, caminho):
    try:
        partes = urlsplit(url)
        _ = partes.port
    except (TypeError, ValueError) as exc:
        raise IAMIndisponivel("Configuração IAM inválida") from exc
    loopback = partes.hostname in {"localhost", "127.0.0.1", "::1"}
    protocolo_invalido = partes.scheme not in {"https", "http"} or (
        partes.scheme == "http" and not loopback
    )
    destino_invalido = (
        not partes.netloc or partes.username or partes.password
        or partes.query or partes.fragment or partes.path != caminho
    )
    if protocolo_invalido or destino_invalido:
        raise IAMIndisponivel("Configuração IAM inválida")


def _validar_pedido(token, credenciais, permissao, nome_cookie):
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise IAMIndisponivel("Configuração IAM inválida")
    if not isinstance(nome_cookie, str) or not (
        nome_cookie.startswith("gpp_session_") and len(nome_cookie) <= 100
    ):
        raise IAMIndisponivel("Nome de cookie IAM inválido")
    if not isinstance(credenciais, dict) or set(credenciais) != {nome_cookie}:
        raise IAMIndisponivel("Credenciais de sessão indisponíveis")
    for valor in credenciais.values():
        if not isinstance(valor, str) or not 1 <= len(valor) <= 40:
            raise IAMIndisponivel("Credenciais de sessão indisponíveis")
    if not isinstance(permissao, str) or not permissao.isascii() or not (
        1 <= len(permissao) <= 100 and permissao[0].islower()
        and all(c.islower() or c.isdigit() or c == "_" for c in permissao)
    ):
        raise IAMIndisponivel("Permissão IAM inválida")


def _validar_resposta(resposta):
    if resposta.status_code != 200:
        raise IAMIndisponivel("Decisão IAM indisponível")
    try:
        dados = resposta.json()
    except (TypeError, ValueError) as exc:
        raise IAMIndisponivel("Resposta IAM inválida") from exc
    if not isinstance(dados, dict) or not _inteiro(dados.get("versao"), 1) or (
        dados["versao"] != 1
    ) or not (
        isinstance(dados.get("decisao_id"), str)
        and 1 <= len(dados["decisao_id"]) <= 64
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    resultado = dados.get("resultado")
    if resultado == "SESSAO_INVALIDA":
        raise SessaoIAMInvalida("Sessão inválida")
    if resultado == "NEGADO":
        if not _inteiro(dados.get("usuario_id"), 1):
            raise IAMIndisponivel("Resposta IAM inválida")
        raise PermissaoIAMNegada("Permissão negada")
    if resultado != "AUTORIZADO" or not (
        _inteiro(dados.get("usuario_id"), 1)
        and _inteiro(dados.get("versao_autorizacao"), 0)
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    nome = dados.get("usuario_nome")
    if not isinstance(nome, str) or not nome.strip() or len(nome) > 200 or any(
        ord(c) < 32 or ord(c) == 127 for c in nome
    ):
        raise IAMIndisponivel("Identidade IAM inválida")
    try:
        expira = datetime.fromisoformat(dados["expira_em"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IAMIndisponivel("Resposta IAM inválida") from exc
    if timezone.is_naive(expira) or expira <= timezone.now():
        raise IAMIndisponivel("Decisão IAM expirada")
    return {
        "usuario_id": dados["usuario_id"],
        "usuario_nome": nome,
        "versao_autorizacao": dados["versao_autorizacao"],
        "expira_em": expira,
        "decisao_id": dados["decisao_id"],
    }


def decidir_acesso_remoto(*, url, caminho, token, credenciais, permissao,
                          nome_cookie, correlacao=None):
    """Consulta o IAM uma vez, sem cache, retry ou redirecionamento."""
    _validar_url(url, caminho)
    _validar_pedido(token, credenciais, permissao, nome_cookie)
    identificador = correlacao if isinstance(correlacao, str) and (
        1 <= len(correlacao) <= 64
        and all(c.isascii() and (c.isalnum() or c in "._:-") for c in correlacao)
    ) else uuid4().hex
    try:
        resposta = requests.post(
            url,
            json={
                "acao": permissao,
                "credenciais_usuario": [
                    {"nome_cookie": nome, "valor": valor}
                    for nome, valor in credenciais.items()
                ],
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-Correlation-ID": identificador,
            },
            timeout=(1, 2),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise IAMIndisponivel("Decisão IAM indisponível") from exc
    return _validar_resposta(resposta)


def decidir_atividade_remota(*, url_decisao, caminho_decisao, caminho_atividade,
                             token, usuario_id, permissao, correlacao=None):
    """Revalida no IAM uma atividade persistida, sem enviar cookie ao serviço."""
    _validar_url(url_decisao, caminho_decisao)
    partes = urlsplit(url_decisao)
    url = partes._replace(path=caminho_atividade).geturl()
    _validar_url(url, caminho_atividade)
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise IAMIndisponivel("Configuração IAM inválida")
    if not _inteiro(usuario_id, 1):
        raise IAMIndisponivel("Usuário da atividade inválido")
    if not isinstance(permissao, str) or not permissao.isascii() or not (
        1 <= len(permissao) <= 100 and permissao[0].islower()
        and all(c.islower() or c.isdigit() or c == "_" for c in permissao)
    ):
        raise IAMIndisponivel("Permissão IAM inválida")
    identificador = correlacao if isinstance(correlacao, str) and (
        1 <= len(correlacao) <= 64
        and all(c.isascii() and (c.isalnum() or c in "._:-") for c in correlacao)
    ) else uuid4().hex
    try:
        resposta = requests.post(
            url,
            json={"usuario_id": usuario_id, "acao": permissao},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-Correlation-ID": identificador,
            },
            timeout=(1, 2),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise IAMIndisponivel("Decisão IAM indisponível") from exc
    if resposta.status_code != 200:
        raise IAMIndisponivel("Decisão IAM indisponível")
    try:
        dados = resposta.json()
    except (TypeError, ValueError) as exc:
        raise IAMIndisponivel("Resposta IAM inválida") from exc
    if not isinstance(dados, dict) or not _inteiro(dados.get("versao"), 1) or (
        dados["versao"] != 1
    ) or not (
        isinstance(dados.get("decisao_id"), str)
        and 1 <= len(dados["decisao_id"]) <= 64
        and _inteiro(dados.get("usuario_id"), 1)
        and dados.get("usuario_id") == usuario_id
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    if dados.get("resultado") == "NEGADO":
        raise PermissaoIAMNegada("Autorização da atividade revogada")
    if dados.get("resultado") != "AUTORIZADO" or not _inteiro(
        dados.get("versao_autorizacao"), 0
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    return {
        "usuario_id": usuario_id,
        "versao_autorizacao": dados["versao_autorizacao"],
        "decisao_id": dados["decisao_id"],
    }
