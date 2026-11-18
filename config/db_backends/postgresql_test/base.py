"""Permite a limpeza transacional de FKs entre schemas no banco de teste."""

from django.db.backends.postgresql.base import DatabaseWrapper as PostgresWrapper

from .operations import DatabaseOperations


class DatabaseWrapper(PostgresWrapper):
    """Usa operações de teste sem modificar o backend de produção."""

    ops_class = DatabaseOperations
