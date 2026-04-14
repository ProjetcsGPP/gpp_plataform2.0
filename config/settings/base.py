"""
GPP Plataform 2.0 — Base Settings
Compartilhado entre development e production.
Nunca usar diretamente — sempre usar development.py ou production.py.

FASE-0: JWT/simplejwt removidos; SessionAuthentication como padrão DRF;
        configurações de sessão, CSRF, CSP e AppContextMiddleware adicionados.
        CSP no formato django-csp >= 4.0 (CONTENT_SECURITY_POLICY dict).
FIX: AUTHORIZATION_EXEMPT_PATHS expandido para incluir /api/accounts/auth/
     (AplicacaoPublicaViewSet — AllowAny) e /api/accounts/logout/.
"""
import os
from pathlib import Path

import environ

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Environ ─────────────────────────────────────────────────────────────────
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ─── Security ────────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY")
DEBUG = False  # sobrescrito em development.py
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# ─── Applications ───────────────────────────────────────────────────────────
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
    "corsheaders",
    "django_extensions",
    "csp",                 # django-csp >= 4.0 (Content Security Policy)
    "drf_spectacular",
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
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ──────────────────────────────────────────────────────────────────────
    # GPP — FASE-0: AppContextMiddleware substitui JWTAuthenticationMiddleware
    "apps.accounts.middleware.AppContextMiddleware",
    # ──────────────────────────────────────────────────────────────────────
    # CORE PLATFORM (mantidos — revisar dependências de JWT em próximas fases)
    "apps.core.middleware.application_context.ApplicationContextMiddleware",
    "apps.core.middleware.role_context.RoleContextMiddleware",
    "apps.core.middleware.authorization.AuthorizationMiddleware",
    # ──────────────────────────────────────────────────────────────────────
    "csp.middleware.CSPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# ─── Templates ──────────────────────────────────────────────────────────────────
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

# ─── Database ──────────────────────────────────────────────────────────────────
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

# ─── Cache (Memcached) ──────────────────────────────────────────────────────────────
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

# ─── Auth ──────────────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internacionalização ───────────────────────────────────────────────────────────
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ─── Static ───────────────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── CORS ───────────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True  # obrigatório para cookie de sessão

# ─── Session ─────────────────────────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
# constante removida para criar cookies por aplicação.
# SESSION_COOKIE_NAME = "gpp_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600          # 1 hora
SESSION_SAVE_EVERY_REQUEST = True
# SESSION_COOKIE_SECURE — definido por ambiente (False em dev, True em prod)

# ─── CSRF ──────────────────────────────────────────────────────────────────────────────
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # Frontend precisa ler o csrftoken para enviar no header
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3000"]
)
# CSRF_COOKIE_SECURE — definido por ambiente (False em dev, True em prod)

# ─── DRF ──────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # FASE-0: JWT removido — sessão Django como único mecanismo
        "rest_framework.authentication.SessionAuthentication",
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
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ─── CSP relaxada para Swagger UI (development only) ─────────────────────────
# O base.py usa nonce-based CSP que bloqueia CDN externo.
# Em dev, liberamos cdn.jsdelivr.net para o Swagger UI funcionar.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src":   ("'self'",),
        "script-src":    ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net"),
        "script-src-elem": ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net"),
        "style-src":     ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net"),
        "style-src-elem":  ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net"),
        "img-src":       ("'self'", "data:", "cdn.jsdelivr.net"),
        "font-src":      ("'self'", "cdn.jsdelivr.net"),
        "worker-src":    ("blob:",),
        "object-src":    ("'none'",),
        "base-uri":      ("'self'",),
        "frame-ancestors": ("'none'",),
    }
}

# ─── Swagger / OpenAPI (drf-spectacular) ──────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "GPP Plataforma 2.0 — API",
    "DESCRIPTION": (
        "Documentação da API REST da Plataforma GPP 2.0. "
        "Autenticação via SessionAuthentication (cookie de sessão + CSRF)."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,

    # Segurança: documenta o fluxo de sessão + CSRF
    "SECURITY": [{"cookieAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "cookieAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "sessionid",
            }
        }
    },

    # ── Ordem das seções no Swagger UI ────────────────────────────────────────
    "TAGS": [
        {"name": "Autenticação",  "description": "Login, logout e sessão do usuário"},
        {"name": "Usuários",      "description": "Perfis, roles e permissões"},
        {"name": "Portal",        "description": "Dashboard e aplicações do portal"},
        {"name": "Ações PNGI",    "description": "Ações, prazos, anotações e destaques"},
        {"name": "Carga Org/Lot", "description": "Carga de organogramas e loteamentos"},
        {"name": "Utilitários",   "description": "Health check e logs de frontend"},
    ],

    # Filtra paths que não devem aparecer na documentação
    "PREPROCESSING_HOOKS": [
        "drf_spectacular.hooks.preprocess_exclude_path_format",
    ],

    # Melhora a aparência no Swagger UI
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayOperationId": False,
        "tagsSorter": "alpha",
        "operationsSorter": "alpha",
    },
}


# ─── Security Headers ───────────────────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ─── Application Domain Map ────────────────────────────────────────────────────────
APPLICATION_DOMAIN_MAP = {
    "pngi.api.gov.br": "acoes_pngi",
    "carga.api.gov.br": "carga_org_lot",
    "portal.api.gov.br": "portal",
}

# ─── Rotas isentas de autenticação ────────────────────────────────────────────────────
# Prefixos: qualquer path que COMECE com estes valores é liberado pelo
# AuthorizationMiddleware sem checagem de autenticação/roles.
AUTHORIZATION_EXEMPT_PATHS = [
    "/api/accounts/login/",    # login via sessão
    "/api/accounts/logout/",   # logout (IsAuthenticated no DRF, mas sem roles)
    "/api/accounts/auth/",     # AplicacaoPublicaViewSet (AllowAny) — seletor de login
    "/admin/",
    "/admin",
    "/api/health/",
    "/__debug__/",
    "/api/schema/",   # ← schema JSON
    "/api/docs/",     # ← Swagger UI
    "/api/redoc/",    # ← ReDoc UI
]

# ─── Logging de Segurança ──────────────────────────────────────────────────────────
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
