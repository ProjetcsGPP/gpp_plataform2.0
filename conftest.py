"""

conftest.py

Conftest raíz do projeto GPP Plataform 2.0.
Configurações globais de pytest que se aplicam a todas as apps.
"""

# conftest.py (raiz do projeto)
#
# Necessário para que o unittest loader (Python 3.12+) resolva corretamente
# os subpacotes de testes (ex.: apps/core/tests/) sem colidir com o nome
# "tests" como módulo top-level.
#
# Também carregado automaticamente pelo pytest, garantindo que o sys.path
# parta sempre da raiz do projeto em ambos os runners.

import fcntl
import hashlib
import os
import re
import tempfile

import pytest


def pytest_sessionstart(session):
    """Impede duas sessões pytest de usarem o mesmo PostgreSQL reutilizado."""
    config = session.config
    if not config.getoption("reuse_db", default=False):
        return

    from django.conf import settings as dj_settings

    database = dj_settings.DATABASES["default"]
    if "postgresql" not in database["ENGINE"]:
        return
    # Não incluir senha nem nome do usuário na chave ou na mensagem.
    identidade = "|".join(str(database.get(campo, "")) for campo in (
        "HOST", "PORT", "NAME",
    ))
    sufixo = hashlib.sha256(identidade.encode()).hexdigest()[:16]
    caminho = os.path.join(
        tempfile.gettempdir(),
        f"gpp-pytest-db-{os.getuid()}-{sufixo}.lock",
    )
    descritor = os.open(
        caminho,
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
        0o600,
    )
    try:
        fcntl.flock(descritor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descritor)
        raise pytest.UsageError(
            "Outra sessão pytest já usa este PostgreSQL de testes com "
            "--reuse-db. Aguarde o término antes de iniciar nova suíte."
        ) from exc
    config._gpp_test_db_lock_fd = descritor  # pylint: disable=protected-access


def pytest_sessionfinish(session, exitstatus):  # pylint: disable=unused-argument
    """Libera a trava mesmo quando a suíte falha ou é interrompida."""
    descritor = getattr(session.config, "_gpp_test_db_lock_fd", None)
    if descritor is not None:
        fcntl.flock(descritor, fcntl.LOCK_UN)
        os.close(descritor)


@pytest.fixture(scope="session", autouse=True)
def _disable_throttle_session(django_db_setup):
    """
    Desabilita throttle do DRF e limpa o cache UMA VEZ para toda a sessão.

    POR QUE session-scoped com django.conf.settings diretamente:
    A fixture `settings` do pytest-django é function-scoped por design.
    As fixtures de login (client_gestor, client_portal_admin, etc.) são
    chamadas no `setup` do pytest — o throttle é avaliado no momento do
    POST /api/accounts/login/, ANTES de qualquer fixture function-scoped
    ter efeito. Usar `settings` function-scoped aqui não resolve o timing.

    SOLUÇÃO: sobrescrever django.conf.settings diretamente no escopo de
    sessão. O cache.clear() elimina contadores remanescentes de runs
    anteriores (problema típico com --reuse-db).

    IMPORTANTE: este clear() é feito UMA VEZ no início da sessão, não
    entre testes — para não destruir sessões Django autenticadas criadas
    pelas fixtures de login com escopo maior (module/class).
    """
    from django.conf import settings as dj_settings
    from django.core.cache import cache

    original = dj_settings.REST_FRAMEWORK.copy()

    dj_settings.REST_FRAMEWORK = {
        **original,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    }

    # Limpa contadores de throttle remanescentes de runs anteriores
    cache.clear()

    yield

    # Restaura ao fim da sessão (boa prática, sem efeito prático em CI)
    dj_settings.REST_FRAMEWORK = original


@pytest.fixture(autouse=True)
def _clear_throttle_keys():
    """
    Limpa APENAS as chaves de throttle do LocMemCache antes de cada teste.

    Não usa cache.clear() — isso destruiria sessões Django autenticadas
    criadas por fixtures de escopo maior (module/class/session).

    O LocMemCache expõe _cache (dict interno) — acesso seguro apenas
    em testes. Chaves de throttle do DRF seguem o padrão:
    ':1:throttle_<scope>_<identifier>'
    """
    from django.core.cache import cache

    raw = getattr(cache, "_cache", None)
    if raw is not None:
        throttle_keys = [
            k for k in list(raw.keys()) if re.search(r"throttle", k, re.IGNORECASE)
        ]
        for key in throttle_keys:
            cache.delete(key)
