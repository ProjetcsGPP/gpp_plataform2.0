# Generated manually — GPP Plataform 2.0
# Adiciona isappbloqueada e isappproductionready ao model Aplicacao.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_add_permission_flags_to_classificacaousuario"),
    ]

    operations = [
        migrations.AddField(
            model_name="aplicacao",
            name="isappbloqueada",
            field=models.BooleanField(
                default=False,
                null=True,
                db_column="isappbloqueada",
                help_text=(
                    "Indica se a aplicação está bloqueada para uso. "
                    "Quando True, nenhum usuário (exceto PORTAL_ADMIN ou SuperUser) "
                    "pode ter novos vínculos criados nesta aplicação. "
                    "Uma app pode estar bloqueada por manutenção, auditoria ou incidente "
                    "independentemente do seu estado de produção."
                ),
            ),
        ),
        migrations.AddField(
            model_name="aplicacao",
            name="isappproductionready",
            field=models.BooleanField(
                default=False,
                null=True,
                db_column="isappproductionready",
                help_text=(
                    "Indica se a aplicação está homologada e habilitada para uso "
                    "em ambiente de produção. Somente apps com este flag True "
                    "e isappbloqueada=False aceitam novos vínculos de usuários. "
                    "O tratamento de visibilidade no portal é feito no frontend."
                ),
            ),
        ),
    ]
