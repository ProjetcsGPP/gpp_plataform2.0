"""
GPP Plataform 2.0 — Test Settings

Usar via pytest.ini:
    DJANGO_SETTINGS_MODULE = config.settings.test

Diferencas em relacao a development.py:
  1. CACHES: LocMemCache (processo-local) no lugar de Memcached.
     Contadores de throttle DRF ficam em memoria e sao zerados
     automaticamente a cada nova invocacao de `python -m pytest`.
     Com Memcached, os contadores persistem entre runs e causam 429
     em suites longas com --reuse-db.

  2. DEFAULT_THROTTLE_RATES: 999999/min em todas as classes.
     Nenhuma suite, independente do numero de testes ou logins
     consecutivos, chegara perto do limite.

  3. PASSWORD_HASHERS: MD5PasswordHasher como primario.
     Reduz o tempo de criacao de usuarios em fixtures em ~50x.
     Nunca usar em producao.

  4. EMAIL_BACKEND: dummy — nenhum email real disparado.

  5. LOGGING: handlers de arquivo desabilitados para nao criar
     arquivos de log durante a execucao de testes.
"""
from .development import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# 1. Cache — LocMemCache (in-process, zerado a cada run)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "gpp-test-cache",
    }
}

# ---------------------------------------------------------------------------
# 2. Throttle — limites absurdamente altos para nunca bloquear testes
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon":  "999999/min",
        "user":  "999999/min",
        "login": "999999/min",
    },
}

# ---------------------------------------------------------------------------
# 3. Password hasher rapido para fixtures
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# 4. Email backend dummy
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

# ---------------------------------------------------------------------------
# 5. Logging — sem escrita em arquivo durante testes
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "gpp.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": True,
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
    },
}
