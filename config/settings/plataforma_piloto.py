"""Perfil local opt-in: IAM, Portal, Ações e Publicações sem rotas de Carga."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .development import *  # noqa: F401,F403

ROOT_URLCONF = "config.urls_plataforma_piloto"
ASGI_APPLICATION = "config.asgi_plataforma_piloto.application"

# O Beat da plataforma continua sendo o único agendador durante o piloto.
# O worker da plataforma deve escutar apenas a fila padrão (celery).
CELERY_TASK_ROUTES = {"carga_org_lot.*": {"queue": "carga_org_lot"}}
GPP_CELERY_TASK_PACKAGES = ("apps.pub_institucional",)
