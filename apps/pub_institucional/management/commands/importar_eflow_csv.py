"""Importa uma exportação CSV do E-Flow Admin."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.pub_institucional.models import SituacaoColetaEflow
from apps.pub_institucional.services.eflow import (AtorAuditoriaEflow,
                                                   ErroValidacaoEflow,
                                                   importar_csv_eflow)


class Command(BaseCommand):
    help = "Importa e consolida uma exportação CSV do E-Flow Admin."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", type=Path)

    def handle(self, *args, **options):
        caminho = options["arquivo"]
        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        try:
            coleta = importar_csv_eflow(
                nome_arquivo=caminho.name,
                conteudo=caminho.read_bytes(),
                ator=AtorAuditoriaEflow(nome="comando:importar_eflow_csv"),
            )
        except ErroValidacaoEflow as exc:
            raise CommandError(f"{exc.codigo}: {exc}") from exc

        if coleta.situacao == SituacaoColetaEflow.FALHOU:
            raise CommandError(
                f"Coleta {coleta.pk} falhou: "
                f"{coleta.codigo_erro}: {coleta.mensagem_erro}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Coleta E-Flow concluída: "
                f"id={coleta.pk}; fluxos={coleta.quantidade_fluxos}; "
                f"órgãos={coleta.quantidade_orgaos_participantes}; "
                f"setores={coleta.quantidade_setores_ativos}."
            )
        )
