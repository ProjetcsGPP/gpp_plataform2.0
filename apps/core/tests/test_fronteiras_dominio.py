"""Impede novos acoplamentos diretos entre os domínios do backend."""

import ast
from pathlib import Path

from django.apps import apps


RAIZ_PROJETO = Path(__file__).resolve().parents[3]
DOMINIOS = frozenset({"acoes_pngi", "carga_org_lot", "pub_institucional"})
EXCECOES_IAM_LEGADAS = frozenset({
    (
        "apps/pub_institucional/permissoes_iam.py",
        "apps.accounts.services.authorization_service",
    ),
    (
        "apps/pub_institucional/services/recursos_funcionais.py",
        "apps.accounts.models",
    ),
})


def _modulos_importados(codigo):
    """Extrai imports literais, inclusive ``from apps import dominio``."""
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Import):
            yield from (alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            if no.module == "apps":
                yield from (f"apps.{alias.name}" for alias in no.names)
            elif no.module:
                yield no.module


def _arquivos_producao(pasta):
    for arquivo in pasta.rglob("*.py"):
        if "migrations" in arquivo.parts or "tests" in arquivo.parts:
            continue
        if arquivo.name.startswith("test_"):
            continue
        yield arquivo


def test_dominios_nao_importam_outro_dominio_diretamente():
    violacoes = []
    for origem in DOMINIOS:
        for arquivo in _arquivos_producao(RAIZ_PROJETO / "apps" / origem):
            for modulo in _modulos_importados(arquivo.read_text(encoding="utf-8")):
                partes = modulo.split(".")
                if len(partes) > 1 and partes[0] == "apps":
                    if partes[1] in DOMINIOS - {origem}:
                        violacoes.append(f"{arquivo.relative_to(RAIZ_PROJETO)}: {modulo}")
    assert not violacoes, "Imports entre domínios: " + ", ".join(violacoes)


def test_modelos_de_dominio_nao_relacionam_outro_dominio():
    violacoes = []
    for origem in DOMINIOS:
        for modelo in apps.get_app_config(origem).get_models():
            for campo in modelo._meta.get_fields():
                if not campo.concrete or not campo.is_relation:
                    continue
                destino = campo.remote_field.model
                if destino._meta.app_label in DOMINIOS - {origem}:
                    violacoes.append(
                        f"{modelo._meta.label}.{campo.name} -> {destino._meta.label}"
                    )
    assert not violacoes, "Relações ORM entre domínios: " + ", ".join(violacoes)


def test_core_e_common_nao_importam_dominios_de_negocio():
    violacoes = []
    for pasta in (RAIZ_PROJETO / "apps" / "core", RAIZ_PROJETO / "common"):
        for arquivo in _arquivos_producao(pasta):
            for modulo in _modulos_importados(arquivo.read_text(encoding="utf-8")):
                partes = modulo.split(".")
                if len(partes) > 1 and partes[0] == "apps":
                    if partes[1] in DOMINIOS:
                        violacoes.append(f"{arquivo.relative_to(RAIZ_PROJETO)}: {modulo}")
    assert not violacoes, "Core/common importam domínio: " + ", ".join(violacoes)


def test_dominios_nao_criam_novos_imports_diretos_do_iam():
    """Congela as exceções legadas do modo monolítico, sem ampliá-las."""
    violacoes = []
    for origem in DOMINIOS:
        for arquivo in _arquivos_producao(RAIZ_PROJETO / "apps" / origem):
            relativo = str(arquivo.relative_to(RAIZ_PROJETO))
            for modulo in _modulos_importados(arquivo.read_text(encoding="utf-8")):
                if modulo == "apps.accounts" or modulo.startswith("apps.accounts."):
                    if (relativo, modulo) not in EXCECOES_IAM_LEGADAS:
                        violacoes.append(f"{relativo}: {modulo}")
    assert not violacoes, "Novo import direto do IAM: " + ", ".join(violacoes)
