"""Perfil opt-in de Ações PNGI, sem rotas de outros domínios nem Beat."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .development import *  # noqa: F401,F403

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    item for item in MIDDLEWARE
    if item != "debug_toolbar.middleware.DebugToolbarMiddleware"
]

ROOT_URLCONF = "config.urls_acoes_piloto"
ASGI_APPLICATION = "config.asgi_acoes_piloto.application"
ACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA = True
GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_ACOES = True
IAM_URL_ACOES = IAM_URL_ACOES or (
    "http://127.0.0.1:8000/interno/iam/v1/decisoes-acoes/"
)

# Ações PNGI não possui tarefas próprias atualmente. Nunca iniciar Beat aqui.
CELERY_BEAT_SCHEDULE = {}
GPP_CELERY_TASK_PACKAGES = ()
