"""Cliente do contrato IAM interno v1, usado só no piloto HTTP desligado.

Este módulo não interpreta permissões localmente. Qualquer falha de transporte,
configuração ou contrato impede autorização. A chamada não tem retry/cache.
"""

from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

import requests
from django.conf import settings
from django.utils import timezone


class IAMIndisponivel(RuntimeError):
    """Não foi possível obter uma decisão IAM confiável; responder 503 ao usuário."""


class SessaoIAMInvalida(RuntimeError):
    """O IAM respondeu explicitamente que a sessão do usuário é inválida."""


class PermissaoIAMNegada(RuntimeError):
    """O IAM negou explicitamente a permissão solicitada."""


def _validar_url(url, *, caminho="/interno/iam/v1/decisoes/"):
    # HTTP só é aceito para IAM em loopback no mesmo host. A credencial M2M
    # autentica a chamada, mas não cifra o transporte. Se Carga e IAM forem
    # separados por host, exigir HTTPS com certificado verificado e ensaiar
    # falhas de confiança; nunca liberar HTTP para um endereço de rede.
    try:
        partes = urlsplit(url)
        porta = partes.port  # força validação de porta malformada
    except ValueError as exc:
        raise IAMIndisponivel("Configuração IAM inválida") from exc
    _ = porta
    loopback = partes.hostname in {"localhost", "127.0.0.1", "::1"}
    destino_inseguro = partes.scheme not in {"https", "http"} or (
        partes.scheme == "http" and not loopback
    )
    destino_inesperado = (
        not partes.netloc or partes.username or partes.password
        or partes.query or partes.fragment
        or partes.path != caminho
    )
    if destino_inseguro or destino_inesperado:
        raise IAMIndisponivel("Configuração IAM inválida")


def _validar_credenciais(credenciais):
    if not isinstance(credenciais, dict) or set(credenciais) != {
        "gpp_session_CARGA_ORG_LOT"
    }:
        raise IAMIndisponivel("Credenciais de sessão indisponíveis")
    for valor in credenciais.values():
        if not isinstance(valor, str) or not 1 <= len(valor) <= 40:
            raise IAMIndisponivel("Credenciais de sessão indisponíveis")


def _inteiro_valido(valor, minimo):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= minimo


def _validar_resposta(resposta):
    if resposta.status_code != 200:
        raise IAMIndisponivel("Decisão IAM indisponível")
    try:
        dados = resposta.json()
    except (ValueError, TypeError) as exc:
        raise IAMIndisponivel("Resposta IAM inválida") from exc
    if not isinstance(dados, dict) or not _inteiro_valido(dados.get("versao"), 1):
        raise IAMIndisponivel("Resposta IAM inválida")
    if dados["versao"] != 1 or not isinstance(dados.get("decisao_id"), str):
        raise IAMIndisponivel("Resposta IAM inválida")
    if not dados["decisao_id"] or len(dados["decisao_id"]) > 64:
        raise IAMIndisponivel("Resposta IAM inválida")
    resultado = dados.get("resultado")
    if resultado == "SESSAO_INVALIDA":
        raise SessaoIAMInvalida("Sessão inválida")
    if resultado == "NEGADO":
        if not _inteiro_valido(dados.get("usuario_id"), 1):
            raise IAMIndisponivel("Resposta IAM inválida")
        raise PermissaoIAMNegada("Permissão negada")
    if resultado != "AUTORIZADO":
        raise IAMIndisponivel("Resposta IAM inválida")
    usuario_id = dados.get("usuario_id")
    versao = dados.get("versao_autorizacao")
    if not _inteiro_valido(usuario_id, 1) or not _inteiro_valido(versao, 0):
        raise IAMIndisponivel("Resposta IAM inválida")
    usuario_nome = dados.get("usuario_nome")
    if "usuario_nome" in dados and (
        not isinstance(usuario_nome, str)
        or not usuario_nome.strip()
        or len(usuario_nome) > 200
        or any(ord(caractere) < 32 or ord(caractere) == 127
               for caractere in usuario_nome)
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    try:
        expira_em = datetime.fromisoformat(dados["expira_em"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IAMIndisponivel("Resposta IAM inválida") from exc
    if timezone.is_naive(expira_em) or expira_em <= timezone.now():
        raise IAMIndisponivel("Decisão IAM expirada")
    return {
        "usuario_id": usuario_id,
        "usuario_nome": usuario_nome,
        "versao_autorizacao": versao,
        "expira_em": expira_em,
        "decisao_id": dados["decisao_id"],
    }


def decidir_acesso_remoto(*, credenciais, permissao, correlacao=None):
    """Consulta IAM por ação; retorna dados mínimos somente se autorizado.

    O chamador deve traduzir SessaoIAMInvalida/PermissaoIAMNegada para 401/403;
    IAMIndisponivel para 503, sem limpar cookies no último caso.
    """
    url = settings.IAM_URL_CARGA
    token = settings.IAM_TOKEN_SERVICO_CARGA
    _validar_url(url)
    _validar_credenciais(credenciais)
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise IAMIndisponivel("Configuração IAM inválida")
    if not isinstance(permissao, str) or not permissao.isascii() or not (
        1 <= len(permissao) <= 100 and permissao[0].islower()
        and all(caractere.islower() or caractere.isdigit() or caractere == "_"
                for caractere in permissao)
    ):
        raise IAMIndisponivel("Permissão IAM inválida")
    identificador = correlacao if isinstance(correlacao, str) and (
        1 <= len(correlacao) <= 64
        and all(c.isascii() and (c.isalnum() or c in "._:-") for c in correlacao)
    ) else uuid4().hex
    corpo = {
        "acao": permissao,
        "credenciais_usuario": [
            {"nome_cookie": nome, "valor": valor}
            for nome, valor in credenciais.items()
        ],
    }
    try:
        resposta = requests.post(
            url,
            json=corpo,
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


def decidir_atividade_remota(*, usuario_id, permissao, correlacao=None):
    """Consulta autorização atual de uma atividade persistida, sem sessão.

    A identidade deve vir do registro no banco, nunca do argumento da mensagem
    Celery ou de dados enviados pelo navegador.
    """
    caminho = "/interno/iam/v1/decisoes-atividade/"
    url = settings.IAM_URL_CARGA
    _validar_url(url)
    partes = urlsplit(url)
    url = partes._replace(path=caminho).geturl()
    _validar_url(url, caminho=caminho)
    token = settings.IAM_TOKEN_SERVICO_CARGA
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise IAMIndisponivel("Configuração IAM inválida")
    if not _inteiro_valido(usuario_id, 1):
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
    except (ValueError, TypeError) as exc:
        raise IAMIndisponivel("Resposta IAM inválida") from exc
    if not isinstance(dados, dict) or dados.get("versao") != 1 or not (
        isinstance(dados.get("decisao_id"), str)
        and 1 <= len(dados["decisao_id"]) <= 64
        and dados.get("usuario_id") == usuario_id
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    resultado = dados.get("resultado")
    if resultado == "NEGADO":
        raise PermissaoIAMNegada("Autorização da atividade revogada")
    if resultado != "AUTORIZADO" or not _inteiro_valido(
        dados.get("versao_autorizacao"), 0
    ):
        raise IAMIndisponivel("Resposta IAM inválida")
    return {
        "usuario_id": usuario_id,
        "versao_autorizacao": dados["versao_autorizacao"],
        "decisao_id": dados["decisao_id"],
    }
