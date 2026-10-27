"""Suíte backend contra o PostgreSQL isolado de PUBLICACOES em DEV.

A senha não integra o settings nem a linha de comando. O executor em
``infra/publicacoes-dev/scripts/run-backend-security-tests.sh`` cria um
PGPASSFILE temporário, restrito ao usuário, e o remove ao terminar.
"""

import os

# Este módulo especializa deliberadamente o namespace completo de teste.
# pylint: disable=wildcard-import,unused-wildcard-import
from .test import *  # noqa: F401,F403

# pylint: enable=wildcard-import,unused-wildcard-import


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "gpp_plataform_dev",
        "USER": "gpp_test_runner",
        "HOST": "127.0.0.1",
        "PORT": "55432",
        "OPTIONS": {
            "options": "-c search_path=public,acoes_pngi,carga_org_lot",
            "passfile": os.environ["PGPASSFILE"],
        },
        "TEST": {"NAME": "test_gpp_publicacoes_dev"},
    }
}
