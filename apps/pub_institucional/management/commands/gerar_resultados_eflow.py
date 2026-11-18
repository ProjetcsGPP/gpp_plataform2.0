"""Garante os dois perfis de resultado para snapshots E-Flow existentes."""

from django.core.management.base import BaseCommand, CommandError

from apps.pub_institucional.models import ColetaEflow, SituacaoColetaEflow
from apps.pub_institucional.services.eflow import (
    AtorAuditoriaEflow, ErroValidacaoEflow, garantir_resultados_calculo_eflow)


class Command(BaseCommand):
    help = "Gera resultados ausentes dos dois perfis fechados do E-Flow."

    def add_arguments(self, parser):
        parser.add_argument("--coleta-id")

    def handle(self, *args, **options):
        consultas = ColetaEflow.objects.filter(
            situacao=SituacaoColetaEflow.CONCLUIDA
        )
        if options["coleta_id"]:
            consultas = consultas.filter(pk=options["coleta_id"])
        if not consultas.exists():
            raise CommandError("Nenhuma coleta E-Flow concluída foi encontrada.")

        criados = 0
        ator = AtorAuditoriaEflow(nome="comando:gerar_resultados_eflow")
        for coleta in consultas.iterator():
            quantidade_anterior = coleta.resultados_calculo.count()
            try:
                resultados = garantir_resultados_calculo_eflow(coleta, ator=ator)
            except ErroValidacaoEflow as exc:
                raise CommandError(
                    f"Coleta {coleta.pk}: {exc.codigo}: {exc}"
                ) from exc
            criados += len(resultados) - quantidade_anterior

        self.stdout.write(
            self.style.SUCCESS(
                f"Resultados E-Flow reconciliados; novos={criados}."
            )
        )
