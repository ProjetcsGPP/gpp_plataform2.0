"""Consulta o E-Docs e registra diferenças pendentes de decisão humana."""

from django.core.management.base import BaseCommand, CommandError

from apps.pub_institucional.models import SituacaoColetaPatriarcas
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, sincronizar_patriarcas_edocs)


class Command(BaseCommand):
    help = "Consulta e compara o catálogo de patriarcas do E-Docs."

    def handle(self, *args, **options):
        coleta = sincronizar_patriarcas_edocs(
            ator=AtorAuditoriaEdocs(nome="comando:sincronizar_edocs_patriarcas")
        )
        if coleta.situacao == SituacaoColetaPatriarcas.FALHOU:
            raise CommandError(
                f"Consulta {coleta.pk} falhou: {coleta.mensagem_erro}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Consulta concluída: "
                f"id={coleta.pk}; observados={coleta.quantidade_observados}; "
                f"novos={coleta.quantidade_novos}; "
                f"alterados={coleta.quantidade_alterados}; "
                f"ausentes={coleta.quantidade_ausentes}; "
                f"pendentes={coleta.quantidade_pendentes}."
            )
        )
