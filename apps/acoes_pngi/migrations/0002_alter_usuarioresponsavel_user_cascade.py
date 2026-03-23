from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("acoes_pngi", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE acoes_pngi.tblusuarioresponsavel
                DROP CONSTRAINT tblusuarioresponsavel_idusuario_1d4b61ef_fk_auth_user_id;

            ALTER TABLE acoes_pngi.tblusuarioresponsavel
                ADD CONSTRAINT tblusuarioresponsavel_idusuario_1d4b61ef_fk_auth_user_id
                FOREIGN KEY (idusuario)
                REFERENCES public.auth_user (id)
                ON DELETE CASCADE
                DEFERRABLE INITIALLY DEFERRED;
            """,
            reverse_sql="""
            ALTER TABLE acoes_pngi.tblusuarioresponsavel
                DROP CONSTRAINT tblusuarioresponsavel_idusuario_1d4b61ef_fk_auth_user_id;

            ALTER TABLE acoes_pngi.tblusuarioresponsavel
                ADD CONSTRAINT tblusuarioresponsavel_idusuario_1d4b61ef_fk_auth_user_id
                FOREIGN KEY (idusuario)
                REFERENCES public.auth_user (id)
                DEFERRABLE INITIALLY DEFERRED;
            """,
        ),
    ]
