"""
Migration: 0009_add_userpermissionoverride

Cria a tabela accounts_userpermissionoverride para representar
overrides individuais de permissão (grant/revoke) por usuário.

Referência: Issue #16 — [Fase 3] Modelagem do modelo UserPermissionOverride
Branch: feat/me_permission
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_accountssession_session_cookie_name_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPermissionOverride",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("grant", "Grant — conceder permissão extra"),
                            ("revoke", "Revoke — retirar permissão da role"),
                        ],
                        help_text=(
                            "'grant' adiciona a permissão ao usuário independentemente da role. "
                            "'revoke' retira a permissão mesmo que a role a conceda."
                        ),
                        max_length=6,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Origem do override (ex: 'admin manual', 'integração XPTO'). Opcional.",
                        max_length=200,
                    ),
                ),
                (
                    "reason",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Justificativa detalhada para o override. Opcional, mas recomendada para auditoria.",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="overrides_criados",
                        to=settings.AUTH_USER_MODEL,
                        help_text="Usuário que criou o override (auditoria).",
                    ),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        help_text="Permissão Django (auth.Permission) que está sendo sobrescrita.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_overrides",
                        to="auth.permission",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="overrides_atualizados",
                        to=settings.AUTH_USER_MODEL,
                        help_text="Último usuário a atualizar o override (auditoria).",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="Usuário ao qual o override se aplica.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permission_overrides",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "User Permission Override",
                "verbose_name_plural": "User Permission Overrides",
                "db_table": "accounts_userpermissionoverride",
                "managed": True,
            },
        ),
        migrations.AddConstraint(
            model_name="userpermissionoverride",
            constraint=models.UniqueConstraint(
                fields=["user", "permission", "mode"],
                name="uq_userpermoverride_user_permission_mode",
            ),
        ),
        migrations.AddIndex(
            model_name="userpermissionoverride",
            index=models.Index(
                fields=["user", "mode"],
                name="accounts_us_user_id_mode_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="userpermissionoverride",
            index=models.Index(
                fields=["permission"],
                name="accounts_us_perm_id_idx",
            ),
        ),
    ]
