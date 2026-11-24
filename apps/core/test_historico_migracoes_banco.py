"""Confere o histórico de migrações apenas no banco permanente de testes."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader


@pytest.mark.django_db(transaction=True)
def test_historico_migracoes_consistente_no_banco_de_testes():
    """O piloto deve manter o schema de testes íntegro e sem migrações pendentes."""
    assert connection.vendor == "postgresql"
    assert connection.settings_dict["NAME"] == "test_gpp_plataform"

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        assert cursor.fetchone()[0] == "test_gpp_plataform"

    carregador = MigrationLoader(connection)
    carregador.check_consistent_history(connection)
    assert not carregador.detect_conflicts()

    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []

    call_command("makemigrations", check=True, dry_run=True, interactive=False, verbosity=0)
