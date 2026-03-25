"""
GPP Plataform 2.0 — Production Settings
Segurança máxima, HTTPS obrigatório.

FASE-0: SESSION_COOKIE_SECURE e CSRF_COOKIE_SECURE explicitamente True
        (reafirma o comportamento — já existia, mas agora é crítico
        para o cookie de sessão HttpOnly funcionar de forma segura).
        CORS_ALLOWED_ORIGINS via .env (não hardcoded).

FIX: CSRF_TRUSTED_ORIGINS agora é obrigatório em produção.
     Se não definido no .env, o servidor levanta ImproperlyConfigured
     na inicialização — evita que o default de desenvolvimento
     (http://localhost:3000) vaze para produção silenciosamente.
"""
from django.core.exceptions import ImproperlyConfigured

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

# ─── CSRF_TRUSTED_ORIGINS — obrigatório em produção ─────────────────────────────────
# Em desenvolvimento, base.py define default=["http://localhost:3000"].
# Em produção esse default é inaceitável — falha imediata se não configurado.
#
# .env de produção (exemplo):
#   CSRF_TRUSTED_ORIGINS=https://seu-frontend.gov.br,https://outro-frontend.gov.br
_csrf_origins = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if not _csrf_origins:
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS não está definido no .env de produção. "
        "Defina com as origens HTTPS do frontend (ex: https://app.gov.br). "
        "Esta variável é obrigatória em produção para prevenir CSRF."
    )
CSRF_TRUSTED_ORIGINS = _csrf_origins

# ─── CORS_ALLOWED_ORIGINS herdado do base.py via env CORS_ALLOWED_ORIGINS ───────────
# .env de produção (exemplo):
#   CORS_ALLOWED_ORIGINS=https://seu-frontend.gov.br
