#!/usr/bin/env python3
"""Exclui importações e conjuntos de lotação usados em testes locais.

Exemplos:
    .venv/bin/python scripts/limpar_importacoes_lotacao.py --patriarca 1
    .venv/bin/python scripts/limpar_importacoes_lotacao.py --all --yes
    .venv/bin/python scripts/limpar_importacoes_lotacao.py \
        --all --reset-cargos --yes
"""

from __future__ import annotations

import argparse

from _reset_carga_org_lot import (
    delete_lotation_data,
    lotation_preview,
    print_counts,
    require_confirmation,
    reset_global_position_catalog,
    scope_description,
    setup_django,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Limpa importações dos tipos 4 e 5, itens, validações, conjuntos "
            "e históricos de lotação."
        )
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--patriarca", type=int, help="ID do patriarca a limpar.")
    scope.add_argument("--all", action="store_true", help="Limpa todos os patriarcas.")
    parser.add_argument(
        "--reset-cargos",
        action="store_true",
        help="Limpa também todo o catálogo global aprendido de cargos.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma a exclusão sem solicitar digitação interativa.",
    )
    args = parser.parse_args()
    if args.reset_cargos and not args.all:
        parser.error("--reset-cargos só pode ser usado junto com --all.")
    return args


def main() -> None:
    args = parse_args()
    setup_django()
    patriarch_id = None if args.all else args.patriarca
    preview = lotation_preview(patriarch_id=patriarch_id)
    print_counts("Dados encontrados:", preview)
    if not any(preview.values()) and not args.reset_cargos:
        print("Nenhum dado de lotação foi encontrado para o escopo informado.")
        return

    description = f"lotação de {scope_description(patriarch_id)}"
    if args.reset_cargos:
        description += " e todo o catálogo global de cargos"
    require_confirmation(description=description, assume_yes=args.yes)

    from django.db import transaction

    with transaction.atomic():
        deleted = delete_lotation_data(patriarch_id=patriarch_id)
        if args.reset_cargos:
            deleted.update(reset_global_position_catalog())
    print_counts("Exclusões concluídas:", deleted)


if __name__ == "__main__":
    main()
