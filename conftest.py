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


def pytest_configure(config):
    """
    Hook chamado antes de qualquer coleta de testes.
    Garante que o Django está configurado via DJANGO_SETTINGS_MODULE.
    pytest-django cuida da configuração automática.
    """
    pass
