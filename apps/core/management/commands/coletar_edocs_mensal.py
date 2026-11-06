"""Gera a planilha mensal a partir dos relatórios quantitativos do E-Docs."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.services.edocs import EdocsError
from apps.core.services.edocs_export import (EdocsExportError,
                                             export_monthly_edocs)


class Command(BaseCommand):
    help = "Coleta relatórios E-Docs e gera JSONs brutos e planilha XLSX."

    def add_arguments(self, parser):
        parser.add_argument("--mes", type=int, required=True)
        parser.add_argument("--ano", type=int, required=True)
        parser.add_argument(
            "--patriarcas-config",
            type=Path,
            default=(
                settings.BASE_DIR
                / "config"
                / "edocs"
                / "patriarcas_disponiveis.json"
            ),
            help=(
                "JSON de seleção. Por padrão, usa a lista canônica "
                "config/edocs/patriarcas_disponiveis.json."
            ),
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=settings.BASE_DIR / "var" / "edocs",
        )

    def handle(self, *args, **options):
        output_directory = options["output_dir"]
        selection_path = options["patriarcas_config"]
        try:
            result = export_monthly_edocs(
                month=options["mes"],
                year=options["ano"],
                selection_path=selection_path,
                output_directory=output_directory,
            )
        except (EdocsError, EdocsExportError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Coleta E-Docs concluída para "
                f"{result.selected_patriarchs} patriarca(s): "
                f"{result.workbook_path}. Seleção preservada em "
                f"{result.selection_path}."
            )
        )
