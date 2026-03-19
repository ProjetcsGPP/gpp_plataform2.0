"""
GPP Plataform 2.0 — Development Settings
Ativa DEBUG, relaxa CORS e usa cache local.
"""
from .base import *  # noqa
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Em dev, aceita todas as origens CORS
CORS_ALLOW_ALL_ORIGINS = True


# Cache em memória local (sem precisar de Memcached rodando)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "gpp-dev-cache",
    }
}

# Permite HTTP em dev (sem HTTPS redirect)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Django Extensions
INSTALLED_APPS += [
    "debug_toolbar",
]

MIDDLEWARE += [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = [
    "127.0.0.1",
]

INTERNAL_IPS = ["127.0.0.1"]
