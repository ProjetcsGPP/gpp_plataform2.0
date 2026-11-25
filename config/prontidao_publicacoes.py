"""Checagens locais, sem rede, para o perfil separado de Publicações."""

from urllib.parse import urlsplit


CAMINHO_DECISAO = "/interno/iam/v1/decisoes-publicacoes/"


def _verificar_token(configuracao):
    token = configuracao.IAM_TOKEN_SERVICO_PUBLICACOES
    if not 32 <= len(token) <= 256:
        return ["Token exclusivo de Publicações ausente ou inválido"]
    if token == configuracao.IAM_TOKEN_SERVICO_CARGA:
        return ["Token de Publicações coincide com o de Carga"]
    return []


def verificar_configuracao_publicacoes(configuracao):
    """Verifica o consumidor sem confundir flags do produtor IAM."""
    pendencias = []
    if configuracao.SETTINGS_MODULE != "config.settings.publicacoes_piloto":
        pendencias.append("Perfil de Publicações não selecionado")
    pendencias.extend(_verificar_token(configuracao))

    url = configuracao.IAM_URL_PUBLICACOES
    try:
        partes = urlsplit(url)
        porta = partes.port
        valida = (
            partes.scheme == "http"
            and partes.hostname in {"localhost", "127.0.0.1", "::1"}
            and porta is not None
            and partes.path == CAMINHO_DECISAO
            and not partes.username and not partes.password
            and not partes.query and not partes.fragment
        )
    except (TypeError, ValueError):
        valida = False
    if not valida:
        pendencias.append("URL IAM de Publicações não aponta ao endpoint em loopback")

    for atributo, descricao in (
        ("PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA", "HTTP administrativo"),
        ("PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO", "WebSocket"),
        ("PUBLICACOES_IAM_ATIVIDADES_REMOTAS_ATIVAS", "Tarefas E-Docs"),
    ):
        if not getattr(configuracao, atributo):
            pendencias.append(f"Decisão IAM remota desativada para {descricao}")

    if configuracao.CELERY_BEAT_SCHEDULE:
        pendencias.append("Perfil de Publicações contém agenda Beat")
    if tuple(configuracao.GPP_CELERY_TASK_PACKAGES) != ("apps.pub_institucional",):
        pendencias.append("Pacotes Celery do perfil de Publicações incorretos")
    if not configuracao.GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_PUBLICACOES:
        pendencias.append("Migrações não bloqueadas no perfil de Publicações")
    return pendencias


def verificar_configuracao_iam(configuracao):
    """Verifica separadamente o produtor das decisões de Publicações."""
    pendencias = []
    if configuracao.SETTINGS_MODULE != "config.settings.plataforma_separada_piloto":
        pendencias.append("Perfil IAM/plataforma não selecionado")
    if not configuracao.IAM_DECISOES_PUBLICACOES_ATIVAS:
        pendencias.append("Produtor de decisões de Publicações desativado")
    pendencias.extend(_verificar_token(configuracao))
    if tuple(configuracao.GPP_CELERY_TASK_PACKAGES):
        pendencias.append("Perfil IAM registra tarefas de domínio")
    return pendencias
