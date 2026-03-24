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

    IMPORTANTE: NAO fazer cache.clear() aqui. O LocMemCache armazena sessoes
    Django alem dos contadores de throttle. Limpar o cache apos o login de
    fixtures (ex: client_gestor) destroi a sessao autenticada, causando 401
    ou lista vazia nos testes que dependem de sessao valida.
    Cada conftest de app e responsavel por limpar seu proprio cache ANTES
    de criar usuarios/logins, na ordem correta.
    """
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    }
