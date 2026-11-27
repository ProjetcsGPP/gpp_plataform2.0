"""Contratos do piloto opt-in de três processos, sem ativar o perfil padrão."""

import asyncio
from io import StringIO
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from channels.testing import WebsocketCommunicator
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models.signals import pre_migrate
from django.test import override_settings
from django.urls import Resolver404, resolve

from config.settings import plataforma_separada_piloto, publicacoes_piloto


def _encaminhar_variaveis_pg_para_windows(ambiente):
    """Passa senha/timeout por ambiente no interop WSL, nunca pela CLI."""
    partes = [parte for parte in ambiente.get("WSLENV", "").split(":") if parte]
    for nome in ("PGPASSWORD", "PGCONNECT_TIMEOUT"):
        if not any(parte.split("/")[0] == nome for parte in partes):
            partes.append(f"{nome}/w")
    ambiente["WSLENV"] = ":".join(partes)


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


@pytest.mark.django_db
def test_plano_migracao_e_reversao_sem_alterar_banco_de_testes():
    """Plataforma está atualizada; a reversão é planejada, não executada."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    executor = MigrationExecutor(connection)
    destinos = executor.loader.graph.leaf_nodes()
    assert executor.migration_plan(destinos) == []
    call_command("migrate", check=True, verbosity=0, stdout=StringIO())
    plano_reverso = executor.migration_plan([
        ("pub_institucional", "0015_preferencia_eflow_usuario_logico"),
    ])
    assert (
        executor.loader.graph.nodes[
            ("pub_institucional", "0016_alter_eventoauditoriacoletamensaledocs_tipo_evento")
        ],
        True,
    ) in plano_reverso


@pytest.mark.django_db
def test_backup_restaura_e_reverte_migracao_em_banco_descartavel(tmp_path):
    """Ensaio opt-in: dump, restore, 0016 -> 0015 -> 0016, sem tocar na origem."""
    if os.environ.get("GPP_ENSAIO_RESTAURACAO_DESCARTAVEL") != "1":
        pytest.skip("Exige opt-in explícito para criar banco PostgreSQL descartável")
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    diretorio_binarios = os.environ.get("GPP_PG_BIN_DIR", "")

    def binario(nome):
        if not diretorio_binarios:
            return nome
        sufixo = ".exe" if Path(diretorio_binarios, f"{nome}.exe").exists() else ""
        caminho = Path(diretorio_binarios, f"{nome}{sufixo}")
        assert caminho.is_file(), f"Utilitário ausente: {nome}"
        return str(caminho)

    versao_dump = subprocess.run(
        [binario("pg_dump"), "--version"], capture_output=True, text=True,
        timeout=5, check=False,
    )
    assert versao_dump.returncode == 0
    encontrado = re.search(r"(\d+)\.", versao_dump.stdout)
    assert encontrado and int(encontrado.group(1)) >= connection.pg_version // 10000, (
        "pg_dump incompatível com a versão do servidor PostgreSQL"
    )

    parametros = settings.DATABASES["default"]
    destino = f"gpp_ensaio_iso_{uuid4().hex[:12]}"
    assert destino.startswith("gpp_ensaio_iso_")
    ambiente = os.environ.copy()
    ambiente.update({
        "PGPASSWORD": parametros["PASSWORD"],
        "PGCONNECT_TIMEOUT": "5",
        "DB_NAME": destino,
    })
    host_cli = (
        "127.0.0.1" if binario("pg_dump").endswith(".exe")
        else parametros["HOST"]
    )
    if binario("pg_dump").endswith(".exe"):
        # O interop WSL não encaminha PGPASSWORD por padrão para executáveis
        # Windows. Encaminhar só as variáveis do cliente, nunca via argumento.
        _encaminhar_variaveis_pg_para_windows(ambiente)
    conexao_pg = [
        "-h", host_cli, "-p", str(parametros["PORT"]),
        "-U", parametros["USER"], "--no-password",
    ]

    def executar(comando, *, entrada=None, prazo=120):
        resultado = subprocess.run(
            comando, env=ambiente, input=entrada, capture_output=True,
            timeout=prazo, check=False,
        )
        assert resultado.returncode == 0, (
            f"Falhou {Path(comando[0]).name}: "
            f"{resultado.stderr[-1000:].decode('utf-8', errors='replace')}"
        )
        return resultado

    with connection.cursor() as cursor:
        cursor.execute("SELECT system_identifier FROM pg_control_system()")
        identificador_origem = str(cursor.fetchone()[0])
    identificador_cli = executar([
        binario("psql"), *conexao_pg, "--no-psqlrc", "-At",
        "-d", "test_gpp_plataform", "-c",
        "SELECT system_identifier FROM pg_control_system()",
    ], prazo=10).stdout.decode("ascii").strip()
    assert identificador_cli == identificador_origem, "CLI aponta a outro servidor PostgreSQL"

    arquivo = tmp_path / "test_gpp_plataform.dump"
    dump = executar([binario("pg_dump"), *conexao_pg, "-Fc",
                     "test_gpp_plataform"])
    arquivo.write_bytes(dump.stdout)
    assert arquivo.stat().st_size > 0
    criado = False
    try:
        executar([binario("createdb"), *conexao_pg, destino])
        criado = True
        executar([binario("pg_restore"), *conexao_pg, "--exit-on-error", "--no-owner",
                  "--no-privileges", "-d", destino], entrada=dump.stdout)
        comando_migrar = [sys.executable, "manage.py", "migrate",
                          "pub_institucional", "0015", "--noinput", "--verbosity=0",
                          "--settings=config.settings.test"]
        executar(comando_migrar)
        executar([*comando_migrar[:4], "0016", *comando_migrar[5:]])
        executar([sys.executable, "manage.py", "migrate", "--check",
                  "--settings=config.settings.test"])
    finally:
        if criado:
            executar([binario("dropdb"), *conexao_pg, "--if-exists", destino])


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
