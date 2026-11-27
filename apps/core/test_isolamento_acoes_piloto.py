"""Fronteiras opt-in do quarto processo, sem alterar o piloto de três."""

import os
import subprocess
import sys

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import pre_migrate
from django.test import override_settings
from django.urls import Resolver404, resolve

from config.settings import acoes_piloto, plataforma_quatro_piloto


def test_rotas_exclusivas_e_perfil_iam_sem_acoes():
    acoes = "config.urls_acoes_piloto"
    iam = "config.urls_plataforma_quatro_piloto"
    resolve("/api/acoes-pngi/eixos/", urlconf=acoes)
    for caminho in (
        "/api/accounts/me/", "/api/portal/dashboard/",
        "/api/carga-org-lot/patriarcas/",
        "/api/pub-institucional/patriarcas/",
        "/interno/iam/v1/decisoes-acoes/",
    ):
        with pytest.raises(Resolver404):
            resolve(caminho, urlconf=acoes)
    resolve("/api/accounts/me/", urlconf=iam)
    resolve("/api/portal/dashboard/", urlconf=iam)
    resolve("/interno/iam/v1/decisoes-acoes/", urlconf=iam)
    with pytest.raises(Resolver404):
        resolve("/api/acoes-pngi/eixos/", urlconf=iam)


def test_perfil_sem_worker_ou_beat_e_bloqueia_migracao():
    assert acoes_piloto.ACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA is True
    assert acoes_piloto.GPP_CELERY_TASK_PACKAGES == ()
    assert plataforma_quatro_piloto.GPP_CELERY_TASK_PACKAGES == ()
    assert acoes_piloto.CELERY_BEAT_SCHEDULE == {}
    assert plataforma_quatro_piloto.IAM_DECISOES_ACOES_ATIVAS is True
    assert "debug_toolbar" not in acoes_piloto.INSTALLED_APPS
    assert "debug_toolbar" not in plataforma_quatro_piloto.INSTALLED_APPS
    with override_settings(GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_ACOES=True):
        with pytest.raises(ImproperlyConfigured, match="não executa migrações"):
            pre_migrate.send(sender=apps.get_app_config("core"), verbosity=0)


@pytest.mark.parametrize(
    "perfil",
    ("config.settings.acoes_piloto", "config.settings.plataforma_quatro_piloto"),
)
def test_perfil_sem_registro_de_tarefas_de_dominio(perfil):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = perfil
    resultado = subprocess.run(
        [
            sys.executable, "-c",
            "from config.celery import app; "
            "app.loader.import_default_modules(); print('\\n'.join(sorted(app.tasks)))",
        ],
        env=ambiente, capture_output=True, text=True, check=False, timeout=10,
    )
    assert resultado.returncode == 0, resultado.stderr
    for prefixo in ("acoes_pngi.", "carga_org_lot.", "pub_institucional."):
        assert prefixo not in resultado.stdout


@pytest.mark.parametrize(
    ("modulo", "perfil_errado"),
    [
        ("config.asgi_acoes_piloto", "config.settings.plataforma_quatro_piloto"),
        ("config.asgi_plataforma_quatro_piloto", "config.settings.acoes_piloto"),
    ],
)
def test_asgi_recusa_settings_de_outro_processo(modulo, perfil_errado):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = perfil_errado
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {modulo}"],
        env=ambiente, capture_output=True, text=True, check=False, timeout=10,
    )
    assert resultado.returncode != 0
    assert "RuntimeError" in resultado.stderr
