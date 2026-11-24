"""Contratos do piloto opt-in de três processos, sem ativar o perfil padrão."""

import asyncio
import json
import os
import subprocess
import sys

import pytest
from channels.testing import WebsocketCommunicator
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import pre_migrate
from django.test import override_settings
from django.urls import Resolver404, resolve

from config.settings import plataforma_separada_piloto, publicacoes_piloto


def test_http_exclusivo_e_vivacidade_por_processo():
    assert "debug_toolbar" not in publicacoes_piloto.INSTALLED_APPS
    assert "debug_toolbar.middleware.DebugToolbarMiddleware" not in publicacoes_piloto.MIDDLEWARE
    rotas = {
        "config.urls_publicacoes_piloto": (
            ("/api/pub-institucional/patriarcas/", "/api/public/v1/publicacoes-institucionais/vigente/"),
            ("/api/accounts/me/", "/api/carga-org-lot/patriarcas/", "/api/acoes-pngi/acoes/"),
            "pub_institucional",
        ),
        "config.urls_plataforma_separada_piloto": (
            ("/api/accounts/me/", "/api/portal/dashboard/"),
            ("/api/pub-institucional/patriarcas/", "/api/public/v1/publicacoes-institucionais/vigente/", "/api/carga-org-lot/patriarcas/"),
            "plataforma",
        ),
    }
    for urlconf, (presentes, ausentes, identidade) in rotas.items():
        for caminho in presentes:
            resolve(caminho, urlconf=urlconf)
        for caminho in ausentes:
            with pytest.raises(Resolver404):
                resolve(caminho, urlconf=urlconf)
        health = resolve("/api/health/", urlconf=urlconf)
        assert json.loads(health.func(None).content)["service"] == identidade


def test_filas_e_migracoes_exclusivas():
    assert publicacoes_piloto.CELERY_BEAT_SCHEDULE == {}
    assert "recuperar-coletas-mensais-edocs" in plataforma_separada_piloto.CELERY_BEAT_SCHEDULE
    assert publicacoes_piloto.GPP_CELERY_TASK_PACKAGES == ("apps.pub_institucional",)
    assert plataforma_separada_piloto.GPP_CELERY_TASK_PACKAGES == ()
    for perfil in (publicacoes_piloto, plataforma_separada_piloto):
        assert perfil.CELERY_TASK_ROUTES["pub_institucional.*"]["queue"] == "pub_institucional"
        assert perfil.CELERY_TASK_ROUTES["carga_org_lot.*"]["queue"] == "carga_org_lot"
    with override_settings(GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_PUBLICACOES=True):
        with pytest.raises(ImproperlyConfigured, match="não executa migrações"):
            pre_migrate.send(sender=apps.get_app_config("core"), verbosity=0)


@pytest.mark.parametrize(
    ("perfil", "presentes", "ausentes"),
    [
        ("config.settings.publicacoes_piloto", ("pub_institucional.",), ("carga_org_lot.",)),
        ("config.settings.plataforma_separada_piloto", (), ("pub_institucional.", "carga_org_lot.")),
    ],
)
def test_registro_de_tarefas_por_worker(perfil, presentes, ausentes):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = perfil
    resultado = subprocess.run(
        [sys.executable, "-c", "from config.celery import app; "
         "app.loader.import_default_modules(); print('\\n'.join(sorted(app.tasks)))"],
        env=ambiente, capture_output=True, text=True, check=False, timeout=10,
    )
    assert resultado.returncode == 0, resultado.stderr
    tarefas = resultado.stdout.splitlines()
    for prefixo in presentes:
        assert any(tarefa.startswith(prefixo) for tarefa in tarefas)
    for prefixo in ausentes:
        assert not any(tarefa.startswith(prefixo) for tarefa in tarefas)


@pytest.mark.django_db
def test_asgi_websocket_publicacoes_rejeita_outras_rotas(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.publicacoes_piloto")
    from config import asgi_publicacoes_piloto

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.plataforma_separada_piloto")
    from config import asgi_plataforma_separada_piloto

    async def verificar(aplicacao, caminho, esperado):
        comunicador = WebsocketCommunicator(aplicacao, caminho)
        conectado, codigo = await comunicador.connect(timeout=5)
        assert conectado is False
        assert codigo == esperado

    asyncio.run(verificar(
        asgi_publicacoes_piloto.application, "/ws/pub-institucional/edocs/", 4403
    ))
    asyncio.run(verificar(
        asgi_publicacoes_piloto.application, "/ws/carga-org-lot/dashboard/", 4404
    ))
    asyncio.run(verificar(
        asgi_plataforma_separada_piloto.application,
        "/ws/pub-institucional/edocs/", 4404,
    ))


@pytest.mark.parametrize(
    ("modulo", "perfil_errado"),
    [
        ("config.asgi_publicacoes_piloto", "config.settings.carga_piloto"),
        ("config.asgi_plataforma_separada_piloto", "config.settings.publicacoes_piloto"),
    ],
)
def test_asgi_recusa_settings_incompativeis(modulo, perfil_errado):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = perfil_errado
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {modulo}"], env=ambiente,
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert resultado.returncode != 0
    assert "exige DJANGO_SETTINGS_MODULE" in resultado.stderr
