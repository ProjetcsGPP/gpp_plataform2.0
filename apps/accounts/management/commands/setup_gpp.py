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
  5. Atribui permissões (por codename) a cada auth.Group — idempotente

Uso:
    python manage.py setup_gpp
"""
import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

User = get_user_model()

# ---------------------------------------------------------------------------
# Matriz de permissões: group_name → lista de codenames
# Gerada a partir de public_auth_group_permissions + public_auth_permission.
# Usar codenames garante portabilidade entre ambientes (os IDs numéricos de
# auth_permission variam conforme a ordem das migrations).
# ---------------------------------------------------------------------------
GROUP_PERMISSIONS = {
    "PORTAL_ADMIN": [
        "add_logentry", "change_logentry", "delete_logentry", "view_logentry",
        "add_permission", "change_permission", "delete_permission", "view_permission",
        "add_group", "change_group", "delete_group", "view_group",
        "add_user", "change_user", "delete_user", "view_user",
        "add_contenttype", "change_contenttype", "delete_contenttype", "view_contenttype",
        "add_session", "change_session", "delete_session", "view_session",
        "add_aplicacao", "change_aplicacao", "delete_aplicacao", "view_aplicacao",
        "add_classificacaousuario", "change_classificacaousuario", "delete_classificacaousuario",
        "view_classificacaousuario", "add_statususuario", "change_statususuario", "delete_statususuario",
        "view_statususuario", "add_tipousuario", "change_tipousuario", "delete_tipousuario", "view_tipousuario",
        "add_role", "change_role", "delete_role", "view_role",
        "add_userprofile", "change_userprofile", "delete_userprofile", "view_userprofile",
        "add_userrole", "change_userrole", "delete_userrole", "view_userrole",
        "add_accountssession", "change_accountssession", "delete_accountssession", "view_accountssession",
        "add_attribute", "change_attribute", "delete_attribute", "view_attribute",
    ],
    "GESTOR_PNGI": [
        "add_situacaoacao", "change_situacaoacao", "delete_situacaoacao", "view_situacaoacao",
        "add_tipoanotacaoalinhamento", "change_tipoanotacaoalinhamento", "delete_tipoanotacaoalinhamento",
        "view_tipoanotacaoalinhamento", "add_tipoentravealerta", "change_tipoentravealerta",
        "delete_tipoentravealerta", "view_tipoentravealerta", "add_usuarioresponsavel",
        "change_usuarioresponsavel", "delete_usuarioresponsavel", "view_usuarioresponsavel",
        "add_acoes", "change_acoes", "delete_acoes", "view_acoes",
        "add_anotacaoalinhamento", "change_anotacaoalinhamento", "delete_anotacaoalinhamento",
        "view_anotacaoalinhamento", "add_entravealerta", "change_entravealerta", "delete_entravealerta",
        "view_entravealerta", "add_marcoacoes", "change_marcoacoes", "delete_marcoacoes", "view_marcoacoes",
        "add_marcohistorico", "change_marcohistorico", "delete_marcohistorico", "view_marcohistorico",
        "add_produto", "change_produto", "delete_produto", "view_produto",
        "add_produtohistorico", "change_produtohistorico", "delete_produtohistorico", "view_produtohistorico",
    ],
    "COORDENADOR_PNGI": [
        "view_situacaoacao",
        "add_tipoanotacaoalinhamento", "change_tipoanotacaoalinhamento", "delete_tipoanotacaoalinhamento",
        "view_tipoanotacaoalinhamento", "add_tipoentravealerta", "change_tipoentravealerta", "delete_tipoentravealerta",
        "view_tipoentravealerta", "add_usuarioresponsavel", "change_usuarioresponsavel", "delete_usuarioresponsavel",
        "view_usuarioresponsavel", "add_acoes", "change_acoes", "delete_acoes", "view_acoes", "add_anotacaoalinhamento",
        "change_anotacaoalinhamento", "delete_anotacaoalinhamento", "view_anotacaoalinhamento",
        "add_entravealerta", "change_entravealerta", "delete_entravealerta", "view_entravealerta",
        "view_marcoacoes",
        "add_marcohistorico", "change_marcohistorico", "delete_marcohistorico", "view_marcohistorico",
        "view_produto",
        "add_produtohistorico", "change_produtohistorico", "delete_produtohistorico", "view_produtohistorico",
    ],
    # OPERADOR_ACAO e GESTOR_CARGA: sem permissões definidas ainda.
    # Adicione os codenames aqui quando a matriz for definida.
    "OPERADOR_ACAO": [],
    "GESTOR_CARGA": [],
}


class Command(BaseCommand):
    help = "Inicializa o GPP: carrega fixtures, cria superuser com PORTAL_ADMIN e seed de permissões."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self.stdout.write(self.style.MIGRATE_HEADING("  GPP Platform — Setup Inicial"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))

        # ── 1. Carregar fixture ───────────────────────────────────────────
        self.stdout.write("\n[1/5] Carregando fixture initial_data.json...")
        call_command(
            "loaddata",
            "apps/accounts/fixtures/initial_data.json",
            verbosity=0,
        )
        self.stdout.write(self.style.SUCCESS("    ✔ Fixture carregada."))

        # ── 2. Criar superuser ────────────────────────────────────────────
        self.stdout.write("\n[2/5] Verificando superuser...")
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
        self.stdout.write("\n[3/5] Verificando UserProfile do superuser...")
        from apps.accounts.models import UserProfile

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
        self.stdout.write("\n[4/5] Atribuindo role PORTAL_ADMIN ao superuser...")
        from apps.accounts.models import Aplicacao, Role, UserRole

        try:
            app_portal = Aplicacao.objects.get(codigointerno="PORTAL")
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

        # ── 5. Seed de permissões por grupo (via codename) ────────────────
        self.stdout.write("\n[5/5] Sincronizando permissões dos grupos...")
        from django.contrib.auth.models import Group, Permission

        total_atribuidas = 0

        for group_name, codenames in GROUP_PERMISSIONS.items():
            try:
                group = Group.objects.get(name=group_name)
            except Group.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"    ⚠ Grupo '{group_name}' não encontrado — pulado.")
                )
                continue

            if not codenames:
                self.stdout.write(f"    • {group_name}: sem permissões definidas (pulado).")
                continue

            perms = Permission.objects.filter(codename__in=codenames)
            encontradas = perms.count()
            nao_encontradas = len(codenames) - encontradas

            # set() substitui todas as permissões do grupo — idempotente
            group.permissions.set(perms)
            total_atribuidas += encontradas

            if nao_encontradas:
                codenames_set = set(codenames)
                encontradas_set = set(perms.values_list("codename", flat=True))
                faltando = codenames_set - encontradas_set
                self.stdout.write(
                    self.style.WARNING(
                        f"    ⚠ {group_name}: {nao_encontradas} codename(s) não encontrado(s): {faltando}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"    ✔ {group_name}: {encontradas} permissão(ões) atribuída(s).")
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
        self.stdout.write(f"  Permissões seed (total) : {total_atribuidas}")
        self.stdout.write("─" * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✔ Setup concluído. Acesse com usuário: {username}\n"
            )
        )
