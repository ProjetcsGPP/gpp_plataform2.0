"""
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

import pytest


def pytest_configure(config):
    """
    Hook chamado antes de qualquer coleta de testes.
    Garante que o Django está configurado via DJANGO_SETTINGS_MODULE.
    pytest-django cuida da configuração automática.
    """
    pass


@pytest.fixture(autouse=True)
def _disable_drf_throttle(settings):
    """
    Desabilita o throttle do DRF em CADA teste individualmente.

    Problema resolvido: o LocMemCache (usado em development) é compartilhado
    dentro do mesmo processo pytest. Múltiplos logins em sequência acumulam
    hits no cache e disparam HTTP 429 — bloqueando testes de accounts mesmo
    quando rodados isoladamente múltiplas vezes.

    A fixture sobrescreve DEFAULT_THROTTLE_CLASSES e DEFAULT_THROTTLE_RATES
    via pytest-django settings fixture, que reverte automaticamente ao fim
    de cada teste (sem efeito colateral entre runs).
    """
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    }


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """
    Limpa o cache Django inteiro antes de cada teste.

    Garante que contadores de throttle residuais do LocMemCache não
    contaminem testes subsequentes — especialmente ao rodar a suite
    completa múltiplas vezes consecutivas com --reuse-db.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()
