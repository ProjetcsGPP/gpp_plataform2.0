"""Garantias do backend PostgreSQL usado apenas na suíte."""

from types import SimpleNamespace

from django.core.management.color import no_style

from config.db_backends.postgresql_test.operations import DatabaseOperations


def test_flush_cascade_apenas_no_banco_de_teste():
    conexao = SimpleNamespace(settings_dict={"NAME": "test_gpp_plataform"})
    operacoes = DatabaseOperations(conexao)

    comando = operacoes.sql_flush(no_style(), ["auth_user"])
    assert "CASCADE" in comando[0]

    conexao.settings_dict["NAME"] = "gpp_plataform"
    comando = operacoes.sql_flush(no_style(), ["auth_user"])
    assert "CASCADE" not in comando[0]
