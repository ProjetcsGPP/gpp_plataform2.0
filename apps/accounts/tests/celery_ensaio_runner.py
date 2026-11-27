"""Executa worker ou Beat do piloto apenas com broker e banco de testes."""

import os
import sys
import time
from urllib.parse import urlparse


def main():  # pylint: disable=too-many-statements,too-many-branches
    modos = {"worker", "worker-carga", "beat", "beat-duplo", "publicar-longa", "publicar-pings"}
    if len(sys.argv) != 2 or sys.argv[1] not in modos:
        raise SystemExit("Modo de ensaio Celery inválido")
    modo = sys.argv[1]
    if os.environ.get("GPP_ENSAIO_TEST_DB_NAME") != "test_gpp_plataform":
        raise SystemExit("Ensaio Celery exige test_gpp_plataform")
    broker = os.environ.get("GPP_ENSAIO_BROKER_URL", "")
    destino = urlparse(broker)
    if (
        destino.scheme != "redis"
        or destino.hostname != "127.0.0.1"
        or destino.port in {None, 6379}
        or destino.path != "/0"
        or broker != os.environ.get("CELERY_BROKER_URL")
    ):
        raise SystemExit("Ensaio Celery exige Redis temporário em loopback")
    perfis = {
        "worker": "config.settings.publicacoes_piloto",
        "worker-carga": "config.settings.carga_piloto",
        "beat": "config.settings.plataforma_separada_piloto",
        "beat-duplo": "config.settings.plataforma_separada_piloto",
        "publicar-longa": "config.settings.publicacoes_piloto",
        "publicar-pings": "config.settings.publicacoes_piloto",
    }
    os.environ["DJANGO_SETTINGS_MODULE"] = perfis[modo]

    from django.conf import settings  # pylint: disable=import-outside-toplevel

    if settings.DATABASES["default"]["NAME"] == "test_gpp_plataform":
        raise SystemExit("Banco de testes não pode coincidir com o banco normal")
    settings.DATABASES["default"]["NAME"] = "test_gpp_plataform"
    settings.CELERY_BROKER_URL = broker
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CELERY_TASK_IGNORE_RESULT = True
    if os.environ.get("GPP_ENSAIO_VISIBILITY_TIMEOUT"):
        settings.CELERY_BROKER_TRANSPORT_OPTIONS = {
            "visibility_timeout": int(os.environ["GPP_ENSAIO_VISIBILITY_TIMEOUT"]),
        }
    if modo.startswith("beat"):
        # Beat não publica tarefas reais: apenas um ping sintético na fila alvo.
        settings.CELERY_BEAT_SCHEDULE = {
            "ensaio-ping-publicacoes": {
                "task": "ensaio.publicacoes.ping",
                "schedule": 1.0,
                "options": {"queue": "pub_institucional"},
            },
        }
        if modo == "beat-duplo":
            settings.CELERY_BEAT_SCHEDULE["ensaio-ping-carga"] = {
                "task": "ensaio.carga.ping",
                "schedule": 1.0,
                "options": {"queue": "carga_org_lot"},
            }

    from config.celery import app  # pylint: disable=import-outside-toplevel

    if app.conf.broker_url != broker:
        raise SystemExit("Celery não está conectado ao Redis temporário do ensaio")
    if os.environ.get("GPP_ENSAIO_VISIBILITY_TIMEOUT"):
        esperado = int(os.environ["GPP_ENSAIO_VISIBILITY_TIMEOUT"])
        if app.conf.broker_transport_options.get("visibility_timeout") != esperado:
            raise SystemExit("Visibility timeout do ensaio não foi aplicado")

    @app.task(name="ensaio.publicacoes.ping")
    def ping_sintetico():
        """Marca processamento exclusivamente no Redis temporário do ensaio."""
        import redis  # pylint: disable=import-outside-toplevel

        time.sleep(float(os.environ.get("GPP_ENSAIO_PING_ATRASO", "0")))
        cliente = redis.Redis.from_url(broker)
        cliente.incr("ensaio:publicacoes:processados")
        identificador = os.environ.get("GPP_ENSAIO_WORKER_ID")
        if identificador:
            cliente.incr(f"ensaio:publicacoes:worker:{identificador}")

    @app.task(name="ensaio.carga.ping")
    def ping_carga_sintetico():
        """Marca processamento da Carga somente no broker descartável."""
        import redis  # pylint: disable=import-outside-toplevel

        redis.Redis.from_url(broker).incr("ensaio:carga:processados")

    @app.task(name="ensaio.publicacoes.longa", acks_late=True)
    def tarefa_longa_sintetica():
        """Simula queda após recebimento, antes da confirmação ao broker."""
        import redis  # pylint: disable=import-outside-toplevel

        cliente = redis.Redis.from_url(broker)
        cliente.incr("ensaio:publicacoes:longa:iniciadas")
        time.sleep(float(os.environ.get("GPP_ENSAIO_LONGA_SEGUNDOS", "0")))
        cliente.incr("ensaio:publicacoes:longa:concluidas")

    if modo == "publicar-longa":
        app.send_task("ensaio.publicacoes.longa", queue="pub_institucional")
    elif modo == "publicar-pings":
        for _ in range(20):
            app.send_task("ensaio.publicacoes.ping", queue="pub_institucional")
    elif modo in {"worker", "worker-carga"}:
        app.loader.import_default_modules()
        tarefas = set(app.tasks)
        carga = modo == "worker-carga"
        propria = (
            "carga_org_lot.processar_envio_organograma" if carga
            else "pub_institucional.processar_coleta_mensal_edocs"
        )
        indevido = "pub_institucional." if carga else "carga_org_lot."
        fila = "carga_org_lot" if carga else "pub_institucional"
        if propria not in tarefas:
            raise SystemExit(f"Worker não registrou tarefa de {fila}")
        if any(nome.startswith(indevido) for nome in tarefas):
            raise SystemExit(f"Worker de {fila} registrou tarefa de outra app")
        marcador = (
            "ENSAIO_REGISTRO_CARGA_ORG_LOT_EXCLUSIVO" if carga
            else "ENSAIO_REGISTRO_PUBLICACOES_EXCLUSIVO"
        )
        print(marcador, flush=True)
        identificador = os.environ.get("GPP_ENSAIO_WORKER_ID", "0")
        if not identificador.isdigit():
            raise SystemExit("ID de worker de ensaio inválido")
        app.worker_main([
            "worker", "-Q", fila, "--pool=solo",
            "--concurrency=1", "--loglevel=WARNING",
            f"--hostname={fila}-ensaio-{identificador}@localhost",
            "--without-gossip", "--without-mingle", "--without-heartbeat",
        ])
    else:
        agenda = os.environ["GPP_ENSAIO_BEAT_SCHEDULE_FILE"]
        app.start(["beat", "--loglevel=WARNING", "--schedule", agenda,
                   "--max-interval", "1"])


if __name__ == "__main__":
    main()
