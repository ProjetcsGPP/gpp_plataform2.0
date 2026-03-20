"""
GPP Plataform 2.0 — Production Settings
Segurança máxima, HTTPS obrigatório.

FASE-0: SESSION_COOKIE_SECURE e CSRF_COOKIE_SECURE explicitamente True
        (reafirma o comportamento — já existia, mas agora é crítico
        para o cookie de sessão HttpOnly funcionar de forma segura).
        CORS_ALLOWED_ORIGINS via .env (não hardcoded).
"""
from .base import *  # noqa
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# ─── HTTPS / HSTS ────────────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ─── Cookie / CSRF — HTTPS obrigatório ──────────────────────────────────────────────
SESSION_COOKIE_SECURE = True    # cookie só enviado em HTTPS
CSRF_COOKIE_SECURE = True       # cookie só enviado em HTTPS

# CORS_ALLOWED_ORIGINS herdado do base.py via env CORS_ALLOWED_ORIGINS
# Exemplo .env de produção:
#   CORS_ALLOWED_ORIGINS=https://seu-frontend.gov.br
#   CSRF_TRUSTED_ORIGINS=https://seu-frontend.gov.br
