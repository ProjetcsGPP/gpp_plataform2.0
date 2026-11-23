"""Proteção contra duas suítes no mesmo PostgreSQL de testes reutilizado."""

import subprocess
import sys
from pathlib import Path

import pytest


def test_segunda_sessao_pytest_e_recusada_antes_da_coleta(pytestconfig):
    if not pytestconfig.getoption("reuse_db", default=False):
        pytest.skip("Trava aplicável somente ao PostgreSQL com --reuse-db")

    raiz = Path(__file__).resolve().parents[2]
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-cov",
            "apps/core/test_pytest_db_exclusivity.py",
        ],
        cwd=raiz,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert resultado.returncode == 4
    assert "Outra sessão pytest já usa este PostgreSQL de testes" in (
        resultado.stderr + resultado.stdout
    )
