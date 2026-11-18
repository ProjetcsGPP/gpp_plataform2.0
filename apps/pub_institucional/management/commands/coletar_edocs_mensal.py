"""Gera a planilha mensal a partir dos relatórios quantitativos do E-Docs."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.pub_institucional.services.cliente_edocs import ErroEdocs
from apps.pub_institucional.services.exportacao_edocs import (
    ErroExportacaoEdocs, exportar_edocs_mensal)


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
        diretorio_saida = options["output_dir"]
        caminho_selecao = options["patriarcas_config"]
        try:
            resultado = exportar_edocs_mensal(
                mes=options["mes"],
                ano=options["ano"],
                caminho_selecao=caminho_selecao,
                diretorio_saida=diretorio_saida,
            )
        except (ErroEdocs, ErroExportacaoEdocs) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Coleta E-Docs concluída para "
                f"{resultado.quantidade_patriarcas_selecionados} "
                f"patriarca(s): {resultado.caminho_planilha}. "
                f"Seleção preservada em {resultado.caminho_selecao}."
            )
        )
