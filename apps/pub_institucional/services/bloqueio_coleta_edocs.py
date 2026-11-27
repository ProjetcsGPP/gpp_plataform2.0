"""Bloqueio de sessão PostgreSQL para uma execução mensal E-Docs."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.db import connection

logger = logging.getLogger(__name__)
_CONEXAO_BLOQUEADA = ContextVar("conexao_bloqueada_edocs", default=None)


def _chave(coleta_id):
    # Namespace fixo e 48 bits do UUID; não compartilha chaves com outros fluxos.
    return (0x4544 << 48) | (UUID(str(coleta_id)).int & ((1 << 48) - 1))


@contextmanager
def bloquear_coleta_edocs(coleta_id):
    """Concede o bloqueio a um worker; duplicatas não executam em paralelo."""
    if connection.vendor != "postgresql":
        raise RuntimeError("A recuperação E-Docs requer PostgreSQL.")
    chave = _chave(coleta_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [chave])
        adquirido = cursor.fetchone()[0]
    conexao_original = connection.connection
    token = _CONEXAO_BLOQUEADA.set(conexao_original if adquirido else None)
    try:
        yield adquirido
    finally:
        _CONEXAO_BLOQUEADA.reset(token)
        if adquirido:
            if connection.connection is conexao_original:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [chave])
            else:
                logger.error(
                    "Conexão PostgreSQL mudou durante coleta E-Docs %s; "
                    "bloqueio de sessão anterior não pode ser liberado aqui",
                    coleta_id,
                )


def confirmar_bloqueio_coleta_edocs():
    """Impede prosseguir se uma reconexão perdeu o bloqueio de sessão."""
    original = _CONEXAO_BLOQUEADA.get()
    if original is None or connection.connection is not original:
        raise RuntimeError("O bloqueio da coleta E-Docs foi perdido.")
