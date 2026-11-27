"""IAM/Portal do ensaio de quatro perfis; nenhum domínio de negócio."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .plataforma_separada_piloto import *  # noqa: F401,F403


INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    item for item in MIDDLEWARE
    if item != "debug_toolbar.middleware.DebugToolbarMiddleware"
]
ROOT_URLCONF = "config.urls_plataforma_quatro_piloto"
ASGI_APPLICATION = "config.asgi_plataforma_quatro_piloto.application"

# Só este novo perfil oferece a decisão de Ações; sem token exclusivo, 404.
IAM_DECISOES_ACOES_ATIVAS = True
