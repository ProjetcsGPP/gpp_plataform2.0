"""
GPP Plataform 2.0 — Development Settings
Ativa DEBUG, relaxa CORS e usa cache local.

FASE-0: SESSION_COOKIE_SECURE e CSRF_COOKIE_SECURE explicitamente False
        para funcionar em HTTP (localhost). Não alterar para True em dev
        — quebra o fluxo de sessão sem HTTPS.
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

# ─── Cookie / CSRF — HTTP local ──────────────────────────────────────────────────
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False   # False obrigatório em HTTP
CSRF_COOKIE_SECURE = False      # False obrigatório em HTTP

# CSRF_TRUSTED_ORIGINS sobrescreve o default do base.py para dev
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# ─── Debug Toolbar ────────────────────────────────────────────────────────────────
INSTALLED_APPS += [
    "debug_toolbar",
]

MIDDLEWARE += [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = ["127.0.0.1"]
