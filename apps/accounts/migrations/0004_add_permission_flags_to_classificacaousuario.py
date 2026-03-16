# Generated manually
# Migration: 0004_add_permission_flags_to_classificacaousuario

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_replace_userrole_constraint_user_aplicacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="classificacaousuario",
            name="pode_criar_usuario",
            field=models.BooleanField(
                default=False,
                db_column="pode_criar_usuario",
                help_text="Permite criar novos usu\u00e1rios na plataforma.",
            ),
        ),
        migrations.AddField(
            model_name="classificacaousuario",
            name="pode_editar_usuario",
            field=models.BooleanField(
                default=False,
                db_column="pode_editar_usuario",
                help_text="Permite editar usu\u00e1rios existentes na plataforma.",
            ),
        ),
    ]
