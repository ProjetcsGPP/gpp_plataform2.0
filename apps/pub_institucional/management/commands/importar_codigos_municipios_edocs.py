"""Importa códigos IBGE da seleção operacional para o catálogo definitivo."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.pub_institucional.models import PatriarcaEdocs
from apps.pub_institucional.services.exportacao_edocs import (
    ErroExportacaoEdocs, carregar_selecao_patriarcas)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, definir_indicadores_municipais_patriarca)


class Command(BaseCommand):
    help = "Importa COD_MUNIC do JSON validado para patriarca_edocs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--arquivo",
            type=Path,
            default=(
                settings.BASE_DIR
                / "config"
                / "edocs"
                / "patriarcas_disponiveis.json"
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            selecao = carregar_selecao_patriarcas(options["arquivo"])
        except ErroExportacaoEdocs as exc:
            raise CommandError(str(exc)) from exc
        por_id = {
            str(item.id_externo): item
            for item in PatriarcaEdocs.objects.select_for_update().all()
        }
        ausentes = [item.id for item in selecao if item.id not in por_id]
        if ausentes:
            raise CommandError(
                "Há IDs do JSON ausentes no catálogo definitivo: "
                + ", ".join(ausentes)
            )
        alterados = 0
        ator = AtorAuditoriaEdocs(nome="importacao_codigos_municipios")
        for item in selecao:
            patriarca = por_id[item.id]
            if patriarca.codigo_municipio == item.codigo_municipio:
                continue
            definir_indicadores_municipais_patriarca(
                patriarca.pk,
                codigo_municipio=item.codigo_municipio,
                justificativa=(
                    "Importação do mapeamento COD_MUNIC validado no arquivo "
                    "canônico do projeto."
                ),
                ator=ator,
            )
            alterados += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Códigos municipais reconciliados: {alterados} alteração(ões)."
            )
        )
