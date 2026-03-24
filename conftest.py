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


@pytest.fixture(scope="session", autouse=True)
def _disable_drf_throttle_session(django_db_setup):
    """
    Desabilita o throttle do DRF no settings ANTES de qualquer fixture de
    login/sessão ser criada.

    POR QUE session-scope:
    As fixtures de login (client_portaladmin, client_gestor, etc.) são
    'db'-scoped ou 'session'-scoped e rodam ANTES das fixtures function-scoped.
    O throttle do DRF é avaliado no momento do POST /api/accounts/login/ —
    se o settings ainda carrega AnonRateThrottle/UserRateThrottle nesse
    momento, o 429 dispara antes do _disable_drf_throttle function-scoped
    ter qualquer efeito.

    SOLUCAO: sobrescrever REST_FRAMEWORK diretamente no objeto settings do
    Django (django.conf.settings) no escopo de session, antes da primeira
    fixture de login. A fixture function-scoped abaixo continua existindo
    para garantir isolamento entre testes individuais.

    NAO usa a fixture 'settings' do pytest-django aqui pois ela e
    function-scoped por design — usamos django.conf.settings diretamente.
    """
    from django.conf import settings as django_settings
    from django.test.signals import setting_changed

    original = django_settings.REST_FRAMEWORK.copy()

    django_settings.REST_FRAMEWORK = {
        **original,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    }

    yield

    # Restaura ao fim de toda a suite (boa prática, sem efeito em CI)
    django_settings.REST_FRAMEWORK = original


@pytest.fixture(autouse=True)
def _disable_drf_throttle(settings):
    """
    Garante throttle zerado para cada teste individualmente.

    Complementa _disable_drf_throttle_session: mesmo que o settings já
    esteja zerado a nível de session, esta fixture garante que qualquer
    reset feito por outras fixtures (ex.: override de REST_FRAMEWORK em
    conftest de app) não reative o throttle durante o corpo do teste.

    Também limpa CIRURGICAMENTE as chaves de throttle do LocMemCache
    antes de cada teste, sem destruir sessões Django:
    - O LocMemCache armazena sessões com chave prefixada ':1:django.contrib.sessions.*'
    - Chaves de throttle do DRF usam padrão ':1:throttle_*'
    - Iteramos apenas sobre as chaves de throttle e as removemos

    IMPORTANTE: cache.clear() NAO e usado aqui — destruiria sessões
    autenticadas de fixtures de escopo maior (session/module/class).
    """
    import re
    from django.core.cache import cache

    # Remove apenas entradas de throttle do LocMemCache sem tocar em sessões
    # LocMemCache expoe _cache (dict interno) — acesso seguro apenas em testes
    raw = getattr(cache, "_cache", None)
    if raw is not None:
        throttle_keys = [k for k in list(raw.keys()) if re.search(r"throttle", k, re.IGNORECASE)]
        for key in throttle_keys:
            cache.delete(key)

    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    }
