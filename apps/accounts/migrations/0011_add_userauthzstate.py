"""
Migração: adiciona UserAuthzState

Cria a tabela accounts_userauthzstate para o sistema de versionamento
leve de autorização por usuário.

Esta tabela é usada EXCLUSIVAMENTE para invalidação de cache no frontend.
Não é parte do sistema de segurança e não afeta permissões reais.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_clean_token_blacklist_residues"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAuthzState",
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
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="authz_state",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "authz_version",
                    models.BigIntegerField(
                        default=0,
                        help_text=(
                            "Contador de versão de autorização. Incrementado atomicamente "
                            "a cada mudança de permissão. Usado APENAS pelo frontend para "
                            "invalidação de cache — não representa permissões reais."
                        ),
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                "verbose_name": "User AuthZ State",
                "verbose_name_plural": "User AuthZ States",
                "db_table": "accounts_userauthzstate",
                "managed": True,
            },
        ),
    ]
