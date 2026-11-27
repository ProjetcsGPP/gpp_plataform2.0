"""Ensaio de Beat único e worker de Publicações em Redis temporário."""

import os
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest
import redis
from django.db import connection

from apps.accounts.tests.test_isolamento_proxy_tls import _porta_livre


@pytest.mark.django_db
def test_tarefa_em_execucao_retorna_automaticamente_apos_visibility_timeout(tmp_path):
    """Worker reiniciado após visibility timeout restaura unacked sozinho."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    porta = _porta_livre()
    broker = f"redis://127.0.0.1:{porta}/0"
    cliente = redis.Redis.from_url(broker)
    ambiente = os.environ.copy()
    ambiente.update({
        "GPP_ENSAIO_TEST_DB_NAME": "test_gpp_plataform",
        "GPP_ENSAIO_BROKER_URL": broker,
        "CELERY_BROKER_URL": broker,
        "GPP_ENSAIO_VISIBILITY_TIMEOUT": "2",
        "GPP_ENSAIO_LONGA_SEGUNDOS": "30",
    })
    comando_redis = [
        "redis-server", "--bind", "127.0.0.1", "--port", str(porta),
        "--save", "", "--appendonly", "no", "--dir", str(tmp_path),
    ]
    comando_worker = [
        sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner", "worker",
    ]
    log_redis = tmp_path / "redis-redelivery.log"
    with _executar_processo(comando_redis, ambiente, log_redis) as servidor:
        def redis_pronto():
            try:
                return cliente.ping()
            except redis.RedisError:
                return False

        _aguardar(redis_pronto, servidor, log_redis)
        log_primeiro = tmp_path / "worker-longo.log"
        publicacao = subprocess.run(
            [sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
             "publicar-longa"],
            env=ambiente, capture_output=True, text=True, timeout=10,
            check=False,
        )
        assert publicacao.returncode == 0, publicacao.stderr[-500:]
        assert cliente.llen("pub_institucional") == 1, cliente.keys("*")
        with _executar_processo(comando_worker, ambiente, log_primeiro) as primeiro:
            _aguardar(
                lambda: int(cliente.get("ensaio:publicacoes:longa:iniciadas") or 0) == 1,
                primeiro, log_primeiro,
            )
            primeiro.kill()
            primeiro.wait(timeout=5)
        assert int(cliente.get("ensaio:publicacoes:longa:concluidas") or 0) == 0
        assert cliente.hlen("unacked") >= 1, cliente.keys("*")
        time.sleep(3)
        assert cliente.hlen("unacked") >= 1
        ambiente_retomada = dict(ambiente)
        ambiente_retomada["GPP_ENSAIO_LONGA_SEGUNDOS"] = "0"
        log_segundo = tmp_path / "worker-retomada.log"
        with _executar_processo(comando_worker, ambiente_retomada, log_segundo) as segundo:
            _aguardar(
                lambda: int(cliente.get("ensaio:publicacoes:longa:concluidas") or 0) == 1,
                segundo, log_segundo, prazo=20,
            )
            assert int(cliente.get("ensaio:publicacoes:longa:iniciadas") or 0) == 2
            assert cliente.llen("pub_institucional") == 0


@pytest.mark.django_db
def test_dois_workers_publicacoes_dividem_vinte_mensagens_sem_perda(tmp_path):
    """Dois consumidores isolados processam uma carga concorrente sintética."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    porta = _porta_livre()
    broker = f"redis://127.0.0.1:{porta}/0"
    cliente = redis.Redis.from_url(broker)
    ambiente = os.environ.copy()
    ambiente.update({
        "GPP_ENSAIO_TEST_DB_NAME": "test_gpp_plataform",
        "GPP_ENSAIO_BROKER_URL": broker,
        "CELERY_BROKER_URL": broker,
        "GPP_ENSAIO_PING_ATRASO": "0.03",
    })
    log_redis = tmp_path / "redis-concorrencia.log"
    comando_redis = [
        "redis-server", "--bind", "127.0.0.1", "--port", str(porta),
        "--save", "", "--appendonly", "no", "--dir", str(tmp_path),
    ]
    comando_runner = [sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner"]
    with _executar_processo(comando_redis, ambiente, log_redis) as servidor:
        def redis_pronto():
            try:
                return cliente.ping()
            except redis.RedisError:
                return False

        _aguardar(redis_pronto, servidor, log_redis)
        log_a, log_b = tmp_path / "worker-a.log", tmp_path / "worker-b.log"
        ambiente_a = {**ambiente, "GPP_ENSAIO_WORKER_ID": "1"}
        ambiente_b = {**ambiente, "GPP_ENSAIO_WORKER_ID": "2"}
        with (
            _executar_processo(comando_runner + ["worker"], ambiente_a, log_a) as worker_a,
            _executar_processo(comando_runner + ["worker"], ambiente_b, log_b) as worker_b,
        ):
            for processo, log in ((worker_a, log_a), (worker_b, log_b)):
                _aguardar(
                    lambda log=log: "ENSAIO_REGISTRO_PUBLICACOES_EXCLUSIVO"
                    in log.read_text(encoding="utf-8"),
                    processo, log,
                )
            publicacao = subprocess.run(
                comando_runner + ["publicar-pings"], env=ambiente,
                capture_output=True, text=True, timeout=15, check=False,
            )
            assert publicacao.returncode == 0, publicacao.stderr[-500:]
            _aguardar(
                lambda: int(cliente.get("ensaio:publicacoes:processados") or 0) == 20,
                worker_a, log_a, prazo=20,
            )
            assert cliente.llen("pub_institucional") == 0
            assert int(cliente.get("ensaio:publicacoes:processados")) == 20
            assert int(cliente.get("ensaio:publicacoes:worker:1") or 0) > 0
            assert int(cliente.get("ensaio:publicacoes:worker:2") or 0) > 0


def _aguardar(condicao, processo, caminho_log, prazo=12):
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        if condicao():
            return
        if processo.poll() is not None:
            break
        time.sleep(0.1)
    raise AssertionError(
        f"Processo do ensaio não atingiu o estado esperado: "
        f"{caminho_log.read_text(encoding='utf-8')[-1500:]}"
    )


@contextmanager
def _executar_processo(comando, ambiente, caminho_log):
    with caminho_log.open("w", encoding="utf-8") as saida:
        processo = subprocess.Popen(
            comando, env=ambiente, stdout=saida, stderr=subprocess.STDOUT,
        )
        try:
            yield processo
        finally:
            if processo.poll() is None:
                processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)


def test_executor_recusa_broker_operacional_e_destino_divergente():
    """A guarda deve falhar antes de carregar Django/Celery ou abrir conexão."""
    comando = [
        sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
        "worker",
    ]
    ambiente = os.environ.copy()
    ambiente["GPP_ENSAIO_TEST_DB_NAME"] = "test_gpp_plataform"
    for ensaio, celery in [
        ("redis://127.0.0.1:6379/0", "redis://127.0.0.1:6379/0"),
        ("redis://127.0.0.1:16379/0", "redis://127.0.0.1:6379/0"),
    ]:
        ambiente["GPP_ENSAIO_BROKER_URL"] = ensaio
        ambiente["CELERY_BROKER_URL"] = celery
        resultado = subprocess.run(
            comando, env=ambiente, capture_output=True, text=True,
            timeout=5, check=False,
        )
        assert resultado.returncode != 0
        assert "Redis temporário em loopback" in resultado.stderr


@pytest.mark.django_db
def test_beat_e_worker_publicacoes_usam_fila_exclusiva(tmp_path):
    """Beat sintético publica; só o worker de Publicações consome sua fila."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    porta = _porta_livre()
    cliente_redis = redis.Redis(host="127.0.0.1", port=porta)
    ambiente = os.environ.copy()
    ambiente.update({
        "GPP_ENSAIO_TEST_DB_NAME": "test_gpp_plataform",
        "GPP_ENSAIO_BROKER_URL": f"redis://127.0.0.1:{porta}/0",
        "GPP_ENSAIO_BEAT_SCHEDULE_FILE": str(tmp_path / "beat-schedule"),
        "CELERY_BROKER_URL": f"redis://127.0.0.1:{porta}/0",
    })
    log_redis = tmp_path / "redis.log"
    comando_redis = [
        "redis-server", "--bind", "127.0.0.1", "--port", str(porta),
        "--save", "", "--appendonly", "no", "--dir", str(tmp_path),
    ]
    with _executar_processo(comando_redis, ambiente, log_redis) as redis_servidor:
        def redis_pronto():
            try:
                return cliente_redis.ping()
            except redis.RedisError:
                return False

        _aguardar(redis_pronto, redis_servidor, log_redis)
        log_beat = tmp_path / "beat.log"
        comando_beat = [
            sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner", "beat",
        ]
        with _executar_processo(comando_beat, ambiente, log_beat) as beat:
            _aguardar(
                lambda: cliente_redis.llen("pub_institucional") >= 1,
                beat, log_beat,
            )
        assert cliente_redis.llen("carga_org_lot") == 0
        assert cliente_redis.llen("celery") == 0
        # Mensagem de prova inserida somente no Redis descartável. O worker
        # nunca deve ler esta fila, independentemente do formato do corpo.
        cliente_redis.lpush("carga_org_lot", "ensaio-fila-nao-consumida")
        assert cliente_redis.llen("carga_org_lot") == 1

        log_worker = tmp_path / "worker.log"
        comando_worker = [
            sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
            "worker",
        ]
        with _executar_processo(comando_worker, ambiente, log_worker) as worker:
            _aguardar(
                lambda: int(cliente_redis.get("ensaio:publicacoes:processados") or 0) >= 1,
                worker, log_worker,
            )
            log = log_worker.read_text(encoding="utf-8")
            assert "ENSAIO_REGISTRO_PUBLICACOES_EXCLUSIVO" in log
            assert f"transport:   redis://127.0.0.1:{porta}/0" in log
            assert ".> pub_institucional exchange=pub_institucional" in log
            assert cliente_redis.llen("pub_institucional") == 0
            assert cliente_redis.llen("carga_org_lot") == 1

        processados_antes = int(
            cliente_redis.get("ensaio:publicacoes:processados") or 0
        )
        ambiente_reinicio = dict(ambiente)
        ambiente_reinicio["GPP_ENSAIO_BEAT_SCHEDULE_FILE"] = str(
            tmp_path / "beat-schedule-reinicio"
        )
        with _executar_processo(
            comando_beat, ambiente_reinicio, tmp_path / "beat-reinicio.log"
        ) as beat_reiniciado:
            _aguardar(
                lambda: cliente_redis.llen("pub_institucional") >= 1,
                beat_reiniciado, tmp_path / "beat-reinicio.log",
            )
        with _executar_processo(
            comando_worker, ambiente, tmp_path / "worker-reinicio.log"
        ) as worker_reiniciado:
            _aguardar(
                lambda: int(
                    cliente_redis.get("ensaio:publicacoes:processados") or 0
                ) > processados_antes,
                worker_reiniciado, tmp_path / "worker-reinicio.log",
            )
            assert cliente_redis.llen("carga_org_lot") == 1
            assert cliente_redis.llen("celery") == 0


@pytest.mark.django_db
def test_beat_unico_e_workers_exclusivos_preservam_mensagens_pendentes(tmp_path):
    """Carga parada não impede Publicações; reinício recupera sua própria fila."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    porta = _porta_livre()
    broker = f"redis://127.0.0.1:{porta}/0"
    cliente = redis.Redis.from_url(broker)
    ambiente = os.environ.copy()
    ambiente.update({
        "GPP_ENSAIO_TEST_DB_NAME": "test_gpp_plataform",
        "GPP_ENSAIO_BROKER_URL": broker,
        "GPP_ENSAIO_BEAT_SCHEDULE_FILE": str(tmp_path / "beat-duplo-schedule"),
        "CELERY_BROKER_URL": broker,
    })
    log_redis = tmp_path / "redis-duplo.log"
    comando_redis = [
        "redis-server", "--bind", "127.0.0.1", "--port", str(porta),
        "--save", "", "--appendonly", "no", "--dir", str(tmp_path),
    ]
    with _executar_processo(comando_redis, ambiente, log_redis) as servidor:
        def redis_pronto():
            try:
                return cliente.ping()
            except redis.RedisError:
                return False

        _aguardar(redis_pronto, servidor, log_redis)
        log_beat = tmp_path / "beat-duplo.log"
        comando_beat = [
            sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
            "beat-duplo",
        ]
        with _executar_processo(comando_beat, ambiente, log_beat) as beat:
            _aguardar(
                lambda: cliente.llen("carga_org_lot") >= 1
                and cliente.llen("pub_institucional") >= 1,
                beat, log_beat,
            )
        assert cliente.llen("celery") == 0

        comando_publicacoes = [
            sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
            "worker",
        ]
        log_publicacoes = tmp_path / "worker-publicacoes-duplo.log"
        with _executar_processo(
            comando_publicacoes, ambiente, log_publicacoes
        ) as worker:
            _aguardar(
                lambda: int(cliente.get("ensaio:publicacoes:processados") or 0) >= 1,
                worker, log_publicacoes,
            )
            assert cliente.llen("pub_institucional") == 0
            assert cliente.llen("carga_org_lot") >= 1

        comando_carga = [
            sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
            "worker-carga",
        ]
        log_carga = tmp_path / "worker-carga-duplo.log"
        with _executar_processo(comando_carga, ambiente, log_carga) as worker:
            _aguardar(
                lambda: int(cliente.get("ensaio:carga:processados") or 0) >= 1,
                worker, log_carga,
            )
            assert cliente.llen("carga_org_lot") == 0
            assert cliente.llen("pub_institucional") == 0
            assert "ENSAIO_REGISTRO_CARGA_ORG_LOT_EXCLUSIVO" in (
                log_carga.read_text(encoding="utf-8")
            )
        assert cliente.llen("celery") == 0


@pytest.mark.django_db
def test_mensagens_pendentes_resistem_ao_reinicio_do_broker(tmp_path):
    """AOF temporário preserva as duas filas; workers retomam após reconexão."""
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"
    porta = _porta_livre()
    broker = f"redis://127.0.0.1:{porta}/0"
    cliente = redis.Redis.from_url(broker)
    ambiente = os.environ.copy()
    ambiente.update({
        "GPP_ENSAIO_TEST_DB_NAME": "test_gpp_plataform",
        "GPP_ENSAIO_BROKER_URL": broker,
        "GPP_ENSAIO_BEAT_SCHEDULE_FILE": str(tmp_path / "beat-persistente"),
        "CELERY_BROKER_URL": broker,
    })
    comando_redis = [
        "redis-server", "--bind", "127.0.0.1", "--port", str(porta),
        "--save", "", "--appendonly", "yes", "--appendfsync", "always",
        "--dir", str(tmp_path),
    ]

    def pronto():
        try:
            return cliente.ping()
        except redis.RedisError:
            return False

    with _executar_processo(
        comando_redis, ambiente, tmp_path / "redis-antes.log"
    ) as servidor:
        _aguardar(pronto, servidor, tmp_path / "redis-antes.log")
        log_beat = tmp_path / "beat-persistente.log"
        with _executar_processo([
            sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
            "beat-duplo",
        ], ambiente, log_beat) as beat:
            _aguardar(
                lambda: cliente.llen("carga_org_lot") >= 1
                and cliente.llen("pub_institucional") >= 1,
                beat, log_beat,
            )
        assert cliente.llen("celery") == 0

    with _executar_processo(
        comando_redis, ambiente, tmp_path / "redis-depois.log"
    ) as servidor:
        _aguardar(pronto, servidor, tmp_path / "redis-depois.log")
        assert cliente.llen("carga_org_lot") >= 1
        assert cliente.llen("pub_institucional") >= 1
        for modo, chave, fila in [
            ("worker", "ensaio:publicacoes:processados", "pub_institucional"),
            ("worker-carga", "ensaio:carga:processados", "carga_org_lot"),
        ]:
            log_worker = tmp_path / f"{modo}-persistente.log"
            with _executar_processo([
                sys.executable, "-m", "apps.accounts.tests.celery_ensaio_runner",
                modo,
            ], ambiente, log_worker) as worker:
                _aguardar(
                    lambda chave_atual=chave: int(
                        cliente.get(chave_atual) or 0
                    ) >= 1,
                    worker, log_worker,
                )
                assert cliente.llen(fila) == 0
        assert cliente.llen("celery") == 0
