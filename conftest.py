# conftest.py — raiz do projeto
#
# Necessário para que o unittest loader (Python 3.12+) resolva corretamente
# os subpacotes de testes (ex.: apps/core/tests/) sem colidir com o nome
# "tests" como módulo top-level.
#
# Também carregado automaticamente pelo pytest, garantindo que o sys.path
# parta sempre da raiz do projeto em ambos os runners.
# conftest.py (raiz)


import pytest
from django.db import connection


@pytest.fixture(autouse=True)
def _clear_usuario_responsavel(request, django_db_setup, django_db_blocker):
    """
    Limpa tblusuarioresponsavel antes do teardown transacional do pytest-django,
    evitando FeatureNotSupported no TRUNCATE ... auth_user.
    """
    yield
    # Só executa quando o banco está disponível
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        return
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute(
                'DELETE FROM "acoes_pngi"."tblusuarioresponsavel"'
            )