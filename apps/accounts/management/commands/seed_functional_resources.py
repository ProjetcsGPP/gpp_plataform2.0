"""Carga os recursos funcionais e menus das aplicações."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Aplicacao, Role
from apps.accounts.services.functional_resource_seed import (
    seed_carga_org_lot_functional_resources,
)


class Command(BaseCommand):
    help = "Cria ou atualiza capabilities, role capabilities e menus."

    def handle(self, *args, **options):
        try:
            result = seed_carga_org_lot_functional_resources()
        except (Aplicacao.DoesNotExist, Role.DoesNotExist) as exc:
            raise CommandError(
                "Execute a carga inicial de aplicações e roles antes deste comando."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Recursos de CARGA_ORG_LOT sincronizados: "
                f"{result['capabilities']} capabilities, "
                f"{result['role_capabilities']} associações e "
                f"{result['menus']} menus."
            )
        )

