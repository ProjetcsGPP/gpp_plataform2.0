"""
Helpers e fixtures reutilizáveis para testes de ApplicationPolicy.

Estratégia idêntica ao test_user_policy.py:
  - Zero banco de dados
  - MagicMock para user e aplicacao
  - patch em apps.accounts.policies.application_policy.UserRole
"""
from unittest.mock import MagicMock


# ── Factories de objetos mock ─────────────────────────────────────────────────

def make_user(user_id=1, is_superuser=False):
    """Retorna um user MagicMock com id e is_superuser configurados."""
    user = MagicMock()
    user.id = user_id
    user.is_superuser = is_superuser
    return user


def make_aplicacao(
    codigointerno="APP_TEST",
    isappbloqueada=False,
    isappproductionready=True,
):
    """Retorna uma aplicacao MagicMock com os campos de flag configurados."""
    app = MagicMock()
    app.codigointerno = codigointerno
    app.isappbloqueada = isappbloqueada
    app.isappproductionready = isappproductionready
    return app


def make_user_role():
    """Retorna um UserRole MagicMock simples."""
    return MagicMock()
