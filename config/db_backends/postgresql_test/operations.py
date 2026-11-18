"""Operações PostgreSQL específicas da suíte de testes."""

from django.db.backends.postgresql.operations import (
    DatabaseOperations as PostgresOperations,
)


class DatabaseOperations(PostgresOperations):
    """Limpa também dependências em schemas não visíveis na introspecção."""

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        nome_banco = self.connection.settings_dict["NAME"]
        return super().sql_flush(
            style,
            tables,
            reset_sequences=reset_sequences,
            allow_cascade=allow_cascade or str(nome_banco).startswith("test_"),
        )
