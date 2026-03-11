"""
GPP Plataform 2.0 — Management Command: setup_gpp

O que faz:
  1. Carrega a fixture initial_data.json (idempotente via natural keys / PKs fixas)
  2. Cria superuser a partir de variáveis de ambiente:
       GPP_ADMIN_USERNAME  (default: admin)
       GPP_ADMIN_EMAIL     (default: admin@gpp.local)
       GPP_ADMIN_PASSWORD  (obrigatório)
  3. Cria UserProfile para o superuser (caso não exista)
  4. Atribui a role PORTAL_ADMIN ao superuser na aplicação 'portal'
  5. Exibe resumo do que foi criado/já existia

Uso:
    python manage.py setup_gpp
"""
import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Inicializa o GPP: carrega fixtures e cria superuser com PORTAL_ADMIN."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self.stdout.write(self.style.MIGRATE_HEADING("  GPP Platform — Setup Inicial"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))

        # ── 1. Carregar fixture ───────────────────────────────────────────
        self.stdout.write("\n[1/4] Carregando fixture initial_data.json...")
        call_command(
            "loaddata",
            "apps/accounts/fixtures/initial_data.json",
            verbosity=0,
        )
        self.stdout.write(self.style.SUCCESS("    ✔ Fixture carregada."))

        # ── 2. Criar superuser ────────────────────────────────────────────
        self.stdout.write("\n[2/4] Verificando superuser...")
        username = os.environ.get("GPP_ADMIN_USERNAME", "admin")
        email = os.environ.get("GPP_ADMIN_EMAIL", "admin@gpp.local")
        password = os.environ.get("GPP_ADMIN_PASSWORD")

        if not password:
            self.stderr.write(
                self.style.ERROR(
                    "    ✘ Variável de ambiente GPP_ADMIN_PASSWORD não definida. "
                    "Defina antes de executar este comando."
                )
            )
            raise SystemExit(1)

        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if user_created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"    ✔ Superuser '{username}' criado."))
        else:
            self.stdout.write(f"    • Superuser '{username}' já existe (mantido).")

        # ── 3. Criar UserProfile ──────────────────────────────────────────
        self.stdout.write("\n[3/4] Verificando UserProfile do superuser...")
        from apps.accounts.models import ClassificacaoUsuario, StatusUsuario, TipoUsuario, UserProfile

        profile, profile_created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "name": username,
                "status_usuario_id": 1,
                "tipo_usuario_id": 1,
                "classificacao_usuario_id": 2,  # Gestor
            },
        )
        if profile_created:
            self.stdout.write(self.style.SUCCESS("    ✔ UserProfile criado."))
        else:
            self.stdout.write("    • UserProfile já existe (mantido).")

        # ── 4. Atribuir role PORTAL_ADMIN ─────────────────────────────────
        self.stdout.write("\n[4/4] Atribuindo role PORTAL_ADMIN ao superuser...")
        from apps.accounts.models import Aplicacao, Role, UserRole

        try:
            app_portal = Aplicacao.objects.get(codigointerno="portal")
            role_admin = Role.objects.get(codigoperfil="PORTAL_ADMIN", aplicacao=app_portal)
            ur, ur_created = UserRole.objects.get_or_create(
                user=user,
                aplicacao=app_portal,
                role=role_admin,
            )
            if ur_created:
                self.stdout.write(self.style.SUCCESS("    ✔ Role PORTAL_ADMIN atribuída."))
            else:
                self.stdout.write("    • Role PORTAL_ADMIN já estava atribuída (mantida).")
        except (Aplicacao.DoesNotExist, Role.DoesNotExist) as exc:
            self.stderr.write(
                self.style.WARNING(f"    ⚠ Não foi possível atribuir role: {exc}")
            )

        # ── Resumo ────────────────────────────────────────────────────────
        from apps.accounts.models import Aplicacao, Role, UserRole

        self.stdout.write("\n" + "─" * 60)
        self.stdout.write(self.style.SUCCESS("  RESUMO DO SETUP"))
        self.stdout.write("─" * 60)
        self.stdout.write(f"  Aplicações cadastradas : {Aplicacao.objects.count()}")
        self.stdout.write(f"  Roles cadastradas       : {Role.objects.count()}")
        self.stdout.write(f"  Usuários no sistema     : {User.objects.count()}")
        self.stdout.write(f"  UserRoles atribuídas    : {UserRole.objects.count()}")
        self.stdout.write("─" * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✔ Setup concluído. Acesse com usuário: {username}\n"
            )
        )
