"""
GPP Plataform 2.0 — Base Settings
Compartilhado entre development e production.
Nunca usar diretamente — sempre usar development.py ou production.py.
"""
import os
from datetime import timedelta
from pathlib import Path

import environ

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Environ ─────────────────────────────────────────────────────────────────
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ─── Security ────────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY")
DEBUG = False  # sobrescrito em development.py
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# ─── Applications ────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_extensions",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.portal",
    "apps.acoes_pngi",
    "apps.carga_org_lot",
    "common",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────────────
# ORDEM OBRIGATÓRIA — não alterar sem revisar dependências entre middlewares
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",          # mantido para Admin
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ──────────────────────────────────────────────────────────────────────
    # CORE PLATFORM
    "apps.core.middleware.application_context.ApplicationContextMiddleware",
    "apps.core.middleware.jwt_authentication.JWTAuthenticationMiddleware",
    "apps.core.middleware.role_context.RoleContextMiddleware",
    "apps.core.middleware.authorization.AuthorizationMiddleware",
    # ──────────────────────────────────────────────────────────────────────
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# ─── Templates ───────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ─── Database ────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="gpp_plataform"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        "OPTIONS": {
            "options": "-c search_path=public,acoes_pngi,carga_org_lot",
        },
    }
}

DATABASE_ROUTERS = ["config.routers.SchemaRouter"]

# ─── Cache (Memcached) ───────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache",
        "LOCATION": env("MEMCACHED_LOCATION", default="127.0.0.1:11211"),
        "TIMEOUT": 300,
        "BINARY": True,
        "OPTIONS": {
            "tcp_nodelay": True,
            "ketama": True,
        },
    }
}

# ─── Auth ────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internacionalização ──────────────────────────────────────────────────────
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ─── Static ──────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# ─── DRF ─────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",  # ← ADD: necessário pro Admin
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/min",
        "user": "200/min",
        "login": "5/min",
    },
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "common.exceptions.gpp_exception_handler",
}

# ─── JWT (RS256) ──────────────────────────────────────────────────────────────
_JWT_PRIVATE_KEY_PATH = BASE_DIR / "keys" / "private.pem"
_JWT_PUBLIC_KEY_PATH = BASE_DIR / "keys" / "public.pem"

SIMPLE_JWT = {
    "ALGORITHM": "RS256",
    "SIGNING_KEY": _JWT_PRIVATE_KEY_PATH.read_text() if _JWT_PRIVATE_KEY_PATH.exists() else "",
    "VERIFYING_KEY": _JWT_PUBLIC_KEY_PATH.read_text() if _JWT_PUBLIC_KEY_PATH.exists() else "",
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "JTI_CLAIM": "jti",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.GPPTokenObtainPairSerializer",
}

# ─── Security Headers ────────────────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ─── Application Domain Map (fallback por domínio) ───────────────────────────
APPLICATION_DOMAIN_MAP = {
    "pngi.api.gov.br": "acoes_pngi",
    "carga.api.gov.br": "carga_org_lot",
    "portal.api.gov.br": "portal",
}

# ─── Rotas isentas de autenticação ───────────────────────────────────────────
AUTHORIZATION_EXEMPT_PATHS = [
    "/api/auth/token/",
    "/api/auth/token/refresh/",
    "/admin/",
    "/admin",   
    "/api/health/",
    "/__debug__/", 
]

# ─── Logging de Segurança ─────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "security": {
            "format": "{asctime} [{levelname}] {name} | {message}",
            "style": "{",
        },
        "verbose": {
            "format": "{asctime} [{levelname}] {name}:{lineno} | {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(BASE_DIR / "logs" / "security.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 30,
            "formatter": "security",
        },
    },
    "loggers": {
        "gpp.security": {
            "handlers": ["security_file", "console"],
            "level": "INFO",
            "propagate": True,
        },
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
