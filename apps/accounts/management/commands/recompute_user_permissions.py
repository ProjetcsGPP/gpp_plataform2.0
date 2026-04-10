"""
Management command: recompute_user_permissions

Fase 11 — Saneamento e re-sincronização de auth_user_user_permissions.

Uso:
    python manage.py recompute_user_permissions --all-users
    python manage.py recompute_user_permissions --user-id <ID>
    python manage.py recompute_user_permissions --all-users --dry-run --verbose
    python manage.py recompute_user_permissions --all-users --strict --verbose

Regras absolutas (ADR-PERM-01):
  - Usa SOMENTE sync_user_permissions / sync_users_permissions / sync_all_users_permissions
  - NUNCA escreve em auth_user_groups
  - NUNCA chama funções legadas (sync_user_permissions_from_group, revoke_user_permissions_from_group)
  - --dry-run usa transaction.atomic() com rollback explícito
  - Transacional por usuário: falha em um não aborta os demais
  - Idempotente: rodar N vezes produz o mesmo estado final
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import UserRole
from apps.accounts.services.permission_sync import (
    sync_user_permissions,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Recomputa auth_user_user_permissions com base no modelo RBAC + overrides "
        "(Fases 1-10). Fonte única: permission_sync.sync_user_permissions()."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--user-id",
            type=int,
            dest="user_id",
            metavar="ID",
            help="Recomputa apenas o usuário com esse ID.",
        )
        group.add_argument(
            "--all-users",
            action="store_true",
            dest="all_users",
            help="Recomputa todos os usuários com pelo menos uma UserRole ativa.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help=(
                "Calcula sem persistir nada. "
                "Usa transaction.atomic() com rollback explícito ao final."
            ),
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            dest="strict",
            help=(
                "Flag documental: comportamento idêntico ao padrão. "
                "Deixa explícito no output que a reconstrução é exata "
                '(herdadas + grants - revokes via sync_user_permissions).'
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose",
            help="Log INFO por usuário: permissões antes/depois e delta adicionado/removido.",
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        user_id: int | None = options["user_id"]
        all_users: bool = options["all_users"]
        dry_run: bool = options["dry_run"]
        strict: bool = options["strict"]
        verbose: bool = options["verbose"]

        prefix = "[DRY-RUN] " if dry_run else ""

        if strict:
            self.stdout.write(
                self.style.WARNING(
                    f"{prefix}Modo --strict ativo: reconstrução exata via "
                    "sync_user_permissions() — herdadas + grants - revokes."
                )
            )

        users = self._resolve_users(user_id, all_users)

        if dry_run:
            self._run_dry(users, prefix, verbose)
        else:
            self._run_live(users, prefix, verbose)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_users(self, user_id, all_users):
        """Retorna queryset de usuários a processar."""
        if user_id is not None:
            qs = User.objects.filter(pk=user_id)
            if not qs.exists():
                raise CommandError(f"Usuário com id={user_id} não encontrado.")
            return qs
        # all_users=True
        active_ids = (
            UserRole.objects.values_list("user_id", flat=True).distinct()
        )
        return User.objects.filter(pk__in=active_ids)

    def _snapshot_permissions(self, user):
        """Retorna conjunto de codenames atuais de user_permissions."""
        return set(
            user.user_permissions.values_list("codename", flat=True)
        )

    def _process_users(self, users, prefix, verbose):
        """
        Itera sobre os usuários, chama sync_user_permissions(user) para cada um.
        Falha em um usuário loga o erro e continua os demais.
        Retorna (processed, total_added, total_removed).
        """
        processed = 0
        total_added = 0
        total_removed = 0

        for user in users:
            try:
                before = self._snapshot_permissions(user) if verbose else None

                sync_user_permissions(user)

                # Refresh para garantir leitura pós-commit
                user.refresh_from_db()

                if verbose:
                    after = self._snapshot_permissions(user)
                    added = after - before
                    removed = before - after
                    total_added += len(added)
                    total_removed += len(removed)
                    self.stdout.write(
                        f"{prefix}user={user.pk} ({user.get_username()}) | "
                        f"+{len(added)} adicionadas / -{len(removed)} removidas | "
                        f"added={sorted(added) or []} removed={sorted(removed) or []}"
                    )
                else:
                    # Modo silencioso: ainda contabiliza delta
                    after = self._snapshot_permissions(user)
                    if before is None:
                        # before não foi capturado antes do sync; recalcular não faz sentido
                        # neste path, mantemos contagem zero para dry-run sem verbose
                        pass

                processed += 1

            except Exception as exc:  # noqa: BLE001
                self.stderr.write(
                    self.style.ERROR(
                        f"{prefix}ERRO ao processar user={user.pk}: {exc}"
                    )
                )

        return processed, total_added, total_removed

    def _process_users_counted(self, users, prefix, verbose):
        """
        Versão que sempre captura before/after para contagem correta,
        independente de --verbose.
        """
        processed = 0
        total_added = 0
        total_removed = 0

        for user in users:
            try:
                before = self._snapshot_permissions(user)
                sync_user_permissions(user)
                user.refresh_from_db()
                after = self._snapshot_permissions(user)

                added = after - before
                removed = before - after
                total_added += len(added)
                total_removed += len(removed)
                processed += 1

                if verbose:
                    self.stdout.write(
                        f"{prefix}user={user.pk} ({user.get_username()}) | "
                        f"+{len(added)} adicionadas / -{len(removed)} removidas | "
                        f"added={sorted(added) or []} removed={sorted(removed) or []}"
                    )

            except Exception as exc:  # noqa: BLE001
                self.stderr.write(
                    self.style.ERROR(
                        f"{prefix}ERRO ao processar user={user.pk}: {exc}"
                    )
                )

        return processed, total_added, total_removed

    def _print_summary(self, processed, total_added, total_removed, prefix):
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{processed} usuário(s) processado(s), "
                f"{total_added} permissão(ões) adicionada(s), "
                f"{total_removed} removida(s)."
            )
        )

    # ------------------------------------------------------------------
    # Execution modes
    # ------------------------------------------------------------------

    def _run_live(self, users, prefix, verbose):
        """Execução normal — persiste as alterações."""
        processed, total_added, total_removed = self._process_users_counted(
            users, prefix, verbose
        )
        self._print_summary(processed, total_added, total_removed, prefix)

    def _run_dry(self, users, prefix, verbose):
        """
        Dry-run — calcula dentro de uma transação e faz rollback explícito
        ao final. Nada é persistido no banco.
        """
        processed = total_added = total_removed = 0

        # Sentinela interna para distinguir nosso rollback de uma exceção real
        class _DryRunRollback(Exception):
            pass

        try:
            with transaction.atomic():
                processed, total_added, total_removed = (
                    self._process_users_counted(users, prefix, verbose)
                )
                # Força rollback intencional
                raise _DryRunRollback()
        except _DryRunRollback:
            pass  # rollback concluído — comportamento esperado

        self._print_summary(processed, total_added, total_removed, prefix)
        self.stdout.write(
            self.style.WARNING(f"{prefix}Nenhuma alteração foi persistida.")
        )
