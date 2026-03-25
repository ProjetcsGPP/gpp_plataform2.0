# apps/core/tests/conftest.py
"""
Conftest local para apps/core/tests.

Reutiliza os fixtures e helpers do conftest de accounts para que
test_permissions_coverage.py possa usar gestor_pngi, portal_admin,
usuario_sem_role e coordenador_pngi sem redefinição.

O autouse _ensure_base_data do conftest de accounts NÃO se propaga
automaticamente para apps irmãs. Por isso declaramos
_ensure_base_data_core (autouse) aqui, que chama _bootstrap_all()
diretamente antes de cada teste deste pacote.
"""
import pytest

from apps.accounts.tests.conftest import (  # noqa: F401 — re-exporta fixtures
    _bootstrap_all,
    gestor_pngi,
    coordenador_pngi,
    portal_admin,
    usuario_sem_role,
    operador_acao,
    gestor_carga,
    superuser,
    usuario_alvo,
    client_gestor,
    client_coordenador,
    client_operador,
    client_gestor_carga,
    client_portal_admin,
    client_superuser,
    client_anonimo,
)


@pytest.fixture(autouse=True)
def _ensure_base_data_core(db):
    """
    Garante que ClassificacaoUsuario, Aplicacao, Role e demais dados base
    existam no banco de teste antes de cada teste deste pacote.

    Necessário porque o _ensure_base_data (autouse) definido em
    apps/accounts/tests/conftest.py só é ativado automaticamente
    para testes dentro de apps/accounts/tests/ — não para apps irmãs.
    """
    _bootstrap_all()
