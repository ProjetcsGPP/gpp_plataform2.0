"""Perfil local opt-in para a API e o worker exclusivos de Carga Org/Lot."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .development import *  # noqa: F401,F403

# A barra de depuração de DEV exige sua própria rota; não a oferecemos na
# superfície HTTP exclusiva de Carga e tampouco deixamos o middleware ativo.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE
    if middleware != "debug_toolbar.middleware.DebugToolbarMiddleware"
]

ROOT_URLCONF = "config.urls_carga_piloto"
ASGI_APPLICATION = "config.asgi_carga_piloto.application"
GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_CARGA = True

# A Carga não inicia um segundo Beat; a plataforma roteia seus agendamentos.
CELERY_BEAT_SCHEDULE = {}
CELERY_TASK_ROUTES = {"carga_org_lot.*": {"queue": "carga_org_lot"}}
GPP_CELERY_TASK_PACKAGES = ("apps.carga_org_lot",)
