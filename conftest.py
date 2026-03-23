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
def _clear_usuario_responsavel(db):
    yield
    with connection.cursor() as cursor:
        # Força verificação imediata para que o TRUNCATE subsequente
        # do pytest-django funcione sem violar a FK deferida
        cursor.execute(
            'SET CONSTRAINTS "acoes_pngi"."tblusuarioresponsavel_idusuario_1d4b61ef_fk_auth_user_id" IMMEDIATE'
        )
        cursor.execute(
            'DELETE FROM "acoes_pngi"."tblusuarioresponsavel"'
        )
