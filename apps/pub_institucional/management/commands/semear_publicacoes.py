"""Reconcilia o contrato IAM inicial de Publicações Institucionais."""

from django.core.management.base import BaseCommand, CommandError

from apps.pub_institucional.services.recursos_funcionais import (
    semear_recursos_funcionais_publicacoes,
)


class Command(BaseCommand):
    help = "Cria ou atualiza aplicação, perfil, capabilities, menus e permissões."

    def handle(self, *args, **options):
        try:
            resultado = semear_recursos_funcionais_publicacoes()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Recursos de PUB_INSTITUCIONAL sincronizados: "
                f"{resultado['capabilities']} capabilities, "
                f"{resultado['associacoes']} associações, "
                f"{resultado['menus']} menus e "
                f"{resultado['permissoes']} permissões técnicas."
            )
        )
