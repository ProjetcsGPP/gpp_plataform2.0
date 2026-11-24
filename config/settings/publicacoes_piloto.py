"""Perfil local opt-in exclusivo das APIs e do WebSocket de Publicações."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .development import *  # noqa: F401,F403

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    item for item in MIDDLEWARE
    if item != "debug_toolbar.middleware.DebugToolbarMiddleware"
]

ROOT_URLCONF = "config.urls_publicacoes_piloto"
ASGI_APPLICATION = "config.asgi_publicacoes_piloto.application"
GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_PUBLICACOES = True

# Beat único no IAM/plataforma; este worker consome apenas publicacoes.
CELERY_BEAT_SCHEDULE = {}
CELERY_TASK_ROUTES = {
    "carga_org_lot.*": {"queue": "carga_org_lot"},
    "pub_institucional.*": {"queue": "pub_institucional"},
}
GPP_CELERY_TASK_PACKAGES = ("apps.pub_institucional",)
