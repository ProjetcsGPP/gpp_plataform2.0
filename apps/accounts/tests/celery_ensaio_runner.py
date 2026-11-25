"""Executa worker ou Beat do piloto apenas com broker e banco de testes."""

import os
import sys
from urllib.parse import urlparse


def main():
    modos = {"worker", "worker-carga", "beat", "beat-duplo"}
    if len(sys.argv) != 2 or sys.argv[1] not in modos:
        raise SystemExit("Uso: celery_ensaio_runner worker|worker-carga|beat|beat-duplo")
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
    }
    os.environ["DJANGO_SETTINGS_MODULE"] = perfis[modo]

    from django.conf import settings  # pylint: disable=import-outside-toplevel

    if settings.DATABASES["default"]["NAME"] == "test_gpp_plataform":
        raise SystemExit("Banco de testes não pode coincidir com o banco normal")
    settings.DATABASES["default"]["NAME"] = "test_gpp_plataform"
    settings.CELERY_BROKER_URL = broker
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CELERY_TASK_IGNORE_RESULT = True
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

    @app.task(name="ensaio.publicacoes.ping")
    def ping_sintetico():
        """Marca processamento exclusivamente no Redis temporário do ensaio."""
        import redis  # pylint: disable=import-outside-toplevel

        redis.Redis.from_url(broker).incr("ensaio:publicacoes:processados")

    @app.task(name="ensaio.carga.ping")
    def ping_carga_sintetico():
        """Marca processamento da Carga somente no broker descartável."""
        import redis  # pylint: disable=import-outside-toplevel

        redis.Redis.from_url(broker).incr("ensaio:carga:processados")

    if modo in {"worker", "worker-carga"}:
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
        app.worker_main([
            "worker", "-Q", fila, "--pool=solo",
            "--concurrency=1", "--loglevel=WARNING",
            f"--hostname={fila}-ensaio@localhost",
            "--without-gossip", "--without-mingle", "--without-heartbeat",
        ])
    else:
        agenda = os.environ["GPP_ENSAIO_BEAT_SCHEDULE_FILE"]
        app.start(["beat", "--loglevel=WARNING", "--schedule", agenda,
                   "--max-interval", "1"])


if __name__ == "__main__":
    main()
