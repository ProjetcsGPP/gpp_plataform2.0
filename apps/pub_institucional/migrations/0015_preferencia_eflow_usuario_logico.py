"""Remove a FK entre Publicações e IAM sem perder preferências existentes."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pub_institucional", "0014_cadastro_municipal_independente_edocs"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE publicacoes.preferencia_exibicao_eflow "
                        "DROP CONSTRAINT "
                        "preferencia_exibicao_eflow_usuario_id_a9888ae2_fk_auth_user_id;"
                    ),
                    reverse_sql=(
                        "ALTER TABLE publicacoes.preferencia_exibicao_eflow "
                        "ADD CONSTRAINT "
                        "preferencia_exibicao_eflow_usuario_id_a9888ae2_fk_auth_user_id "
                        "FOREIGN KEY (usuario_id) REFERENCES public.auth_user(id) "
                        "DEFERRABLE INITIALLY DEFERRED;"
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="preferenciaexibicaoeflow",
                    name="usuario",
                ),
                migrations.AddField(
                    model_name="preferenciaexibicaoeflow",
                    name="usuario_id",
                    field=models.IntegerField(
                        help_text="ID lógico do usuário no IAM, sem FK entre schemas.",
                        unique=True,
                    ),
                ),
            ],
        ),
    ]
