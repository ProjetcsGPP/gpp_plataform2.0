"""Perfil local opt-in exclusivo das APIs e do WebSocket de Publicações."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .development import *  # noqa: F401,F403

from .segredo_iam_publicacoes_piloto import carregar_token

# O perfil separado consulta o IAM em HTTP, WebSocket e tarefas. Sem token,
# todas as decisões falham fechadas; o monólito mantém as flags desligadas.
IAM_TOKEN_SERVICO_PUBLICACOES = carregar_token(IAM_TOKEN_SERVICO_PUBLICACOES)
PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA = True
PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO = True
PUBLICACOES_IAM_ATIVIDADES_REMOTAS_ATIVAS = True

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    item for item in MIDDLEWARE
    if item != "debug_toolbar.middleware.DebugToolbarMiddleware"
]

ROOT_URLCONF = "config.urls_publicacoes_piloto"
ASGI_APPLICATION = "config.asgi_publicacoes_piloto.application"
GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_PUBLICACOES = True
# Topologia local do proxy de três processos: IAM/plataforma em 8000.
# Só este perfil usa o padrão; um destino explícito ainda passa pelo preflight.
IAM_URL_PUBLICACOES = IAM_URL_PUBLICACOES or (
    "http://127.0.0.1:8000/interno/iam/v1/decisoes-publicacoes/"
)

# Beat único no IAM/plataforma; este worker consome apenas publicacoes.
CELERY_BEAT_SCHEDULE = {}
CELERY_TASK_ROUTES = {
    "carga_org_lot.*": {"queue": "carga_org_lot"},
    "pub_institucional.*": {"queue": "pub_institucional"},
}
GPP_CELERY_TASK_PACKAGES = ("apps.pub_institucional",)
