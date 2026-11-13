"""Reconcilia nomes municipais com o catálogo oficial do IBGE."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.pub_institucional.models import MunicipioEdocs
from apps.pub_institucional.services.municipios_edocs import (
    AtorAuditoriaMunicipioEdocs, corrigir_cadastro_municipio_edocs)
from common.services.ibge import ErroIbge, listar_municipios_ibge


class Command(BaseCommand):
    help = (
        "Compara municipio_edocs com o IBGE e, com --aplicar, corrige os "
        "nomes preservando versão e auditoria."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Aplica as correções; sem esta opção, apenas apresenta o plano.",
        )

    def handle(self, *args, **options):
        try:
            catalogo = listar_municipios_ibge(settings.IBGE_UF_PADRAO)
        except (ErroIbge, ValueError) as exc:
            raise CommandError(
                "Não foi possível obter o catálogo municipal do IBGE."
            ) from exc

        nomes_oficiais = {item["id"]: item["nome"] for item in catalogo}
        municipios = list(MunicipioEdocs.objects.order_by("codigo_ibge"))
        codigos_ausentes = [
            item.codigo_ibge
            for item in municipios
            if item.codigo_ibge not in nomes_oficiais
        ]
        if codigos_ausentes:
            raise CommandError(
                "Existem códigos ausentes do catálogo oficial do IBGE: "
                + ", ".join(str(codigo) for codigo in codigos_ausentes)
            )

        divergencias = [
            (item, nomes_oficiais[item.codigo_ibge])
            for item in municipios
            if item.nome != nomes_oficiais[item.codigo_ibge]
        ]
        for municipio, nome_oficial in divergencias:
            self.stdout.write(
                f"{municipio.codigo_ibge}: {municipio.nome!r} -> "
                f"{nome_oficial!r}"
            )

        if not options["aplicar"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Simulação: {len(divergencias)} correção(ões) pendente(s)."
                )
            )
            return

        ator = AtorAuditoriaMunicipioEdocs(
            usuario_id=0,
            nome="sincronizacao_nomes_municipios_ibge",
        )
        with transaction.atomic():
            for municipio, nome_oficial in divergencias:
                corrigir_cadastro_municipio_edocs(
                    municipio.pk,
                    codigo_ibge=municipio.codigo_ibge,
                    nome=nome_oficial,
                    versao=municipio.versao,
                    justificativa=(
                        "Nome reconciliado com o catálogo oficial de "
                        "Localidades do IBGE."
                    ),
                    ator=ator,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Nomes municipais reconciliados: {len(divergencias)} "
                "alteração(ões)."
            )
        )
