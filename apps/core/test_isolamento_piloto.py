"""Contratos de composição do ensaio local, sem ativar o isolamento padrão."""

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

from config.settings import carga_piloto, plataforma_piloto


def test_urls_do_piloto_sao_exclusivas_por_processo():
    assert "debug_toolbar" not in carga_piloto.INSTALLED_APPS
    assert (
        "debug_toolbar.middleware.DebugToolbarMiddleware"
        not in carga_piloto.MIDDLEWARE
    )
    assert resolve(
        "/api/carga-org-lot/patriarcas/",
        urlconf="config.urls_carga_piloto",
    )
    rota_carga = resolve("/api/health/", urlconf="config.urls_carga_piloto")
    assert json.loads(rota_carga.func(None).content)["service"] == "carga_org_lot"
    with pytest.raises(Resolver404):
        resolve(
            "/api/pub-institucional/patriarcas/",
            urlconf="config.urls_carga_piloto",
        )

    assert resolve(
        "/api/pub-institucional/patriarcas/",
        urlconf="config.urls_plataforma_piloto",
    )
    assert resolve(
        "/api/accounts/me/",
        urlconf="config.urls_plataforma_piloto",
    )
    rota_plataforma = resolve("/api/health/", urlconf="config.urls_plataforma_piloto")
    assert json.loads(rota_plataforma.func(None).content)["service"] == "plataforma"
    with pytest.raises(Resolver404):
        resolve(
            "/api/carga-org-lot/patriarcas/",
            urlconf="config.urls_plataforma_piloto",
        )


def test_agendador_unico_e_fila_exclusiva_de_carga():
    assert carga_piloto.CELERY_BEAT_SCHEDULE == {}
    assert "monitorar-envios-organograma-prodest" in (
        plataforma_piloto.CELERY_BEAT_SCHEDULE
    )
    assert "recuperar-coletas-mensais-edocs" in (plataforma_piloto.CELERY_BEAT_SCHEDULE)
    for perfil in (carga_piloto, plataforma_piloto):
        assert perfil.CELERY_TASK_ROUTES["carga_org_lot.*"]["queue"] == (
            "carga_org_lot"
        )


def test_websocket_do_piloto_nao_compartilha_rotas(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.carga_piloto")
    from config import asgi_carga_piloto

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.plataforma_piloto")
    from config import asgi_plataforma_piloto

    def rotas(modulo):
        middleware = modulo.application.application_mapping["websocket"]
        return {str(rota.pattern) for rota in middleware.aplicacao.routes}

    assert all(
        rota.startswith("ws/carga-org-lot/")
        for rota in rotas(asgi_carga_piloto)
        if rota != "^.*$"
    )
    assert all(
        rota.startswith("ws/pub-institucional/")
        for rota in rotas(asgi_plataforma_piloto)
        if rota != "^.*$"
    )
    assert "^.*$" in rotas(asgi_carga_piloto)
    assert "^.*$" in rotas(asgi_plataforma_piloto)


def test_websocket_anonimo_dos_perfis_piloto_e_recusado(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.carga_piloto")
    from config import asgi_carga_piloto

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.plataforma_piloto")
    from config import asgi_plataforma_piloto

    async def cenario(aplicacao, caminho):
        comunicador = WebsocketCommunicator(aplicacao, caminho)
        conectado, codigo = await comunicador.connect(timeout=2)
        assert conectado is False
        assert codigo == 4403

    asyncio.run(
        cenario(asgi_carga_piloto.application, "/ws/carga-org-lot/dashboard/")
    )
    asyncio.run(
        cenario(
            asgi_plataforma_piloto.application,
            "/ws/pub-institucional/edocs/",
        )
    )


def test_websocket_de_outra_app_e_recusado_sem_erro_interno(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.carga_piloto")
    from config import asgi_carga_piloto

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.plataforma_piloto")
    from config import asgi_plataforma_piloto

    async def cenario(aplicacao, caminho):
        comunicador = WebsocketCommunicator(aplicacao, caminho)
        conectado, codigo = await comunicador.connect(timeout=2)
        assert conectado is False
        assert codigo == 4404

    asyncio.run(
        cenario(asgi_carga_piloto.application, "/ws/pub-institucional/edocs/")
    )
    asyncio.run(
        cenario(
            asgi_plataforma_piloto.application,
            "/ws/carga-org-lot/dashboard/",
        )
    )


@pytest.mark.parametrize(
    ("modulo", "perfil_errado"),
    [
        ("config.asgi_carga_piloto", "config.settings.plataforma_piloto"),
        ("config.asgi_plataforma_piloto", "config.settings.carga_piloto"),
    ],
)
def test_asgi_piloto_recusa_perfil_incompativel(modulo, perfil_errado):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = perfil_errado
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {modulo}"],
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert resultado.returncode != 0
    assert "exige DJANGO_SETTINGS_MODULE" in resultado.stderr


def test_migracoes_sao_bloqueadas_no_perfil_de_carga():
    assert carga_piloto.GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_CARGA is True
    with override_settings(GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_CARGA=True):
        with pytest.raises(ImproperlyConfigured, match="não executa migrações"):
            pre_migrate.send(sender=apps.get_app_config("core"), verbosity=0)


@pytest.mark.parametrize(
    ("perfil", "prefixos_presentes", "prefixos_ausentes"),
    [
        (
            "config.settings.carga_piloto",
            ("carga_org_lot.",),
            ("pub_institucional.",),
        ),
        (
            "config.settings.plataforma_piloto",
            ("pub_institucional.",),
            ("carga_org_lot.",),
        ),
        (
            "config.settings.test",
            ("carga_org_lot.", "pub_institucional."),
            (),
        ),
    ],
)
def test_descoberta_de_tarefas_respeita_o_perfil(
    perfil, prefixos_presentes, prefixos_ausentes
):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = perfil
    resultado = subprocess.run(
        [
            sys.executable,
            "-c",
            "from config.celery import app; "
            "app.loader.import_default_modules(); "
            "print('\\n'.join(sorted(app.tasks)))",
        ],
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert resultado.returncode == 0, resultado.stderr
    tarefas = resultado.stdout.splitlines()
    for prefixo in prefixos_presentes:
        assert any(tarefa.startswith(prefixo) for tarefa in tarefas)
    for prefixo in prefixos_ausentes:
        assert not any(tarefa.startswith(prefixo) for tarefa in tarefas)
