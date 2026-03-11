"""
GPP Plataform 2.0 — Migration 0002
Cria os schemas PostgreSQL: acoes_pngi e carga_org_lot.
Deve rodar APÓS 0001_initial (que cria as tabelas no schema public).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "CREATE SCHEMA IF NOT EXISTS acoes_pngi;",
                "CREATE SCHEMA IF NOT EXISTS carga_org_lot;",
            ],
            reverse_sql=[
                # Apenas remove os schemas se estiverem vazios — seguro para rollback
                "DROP SCHEMA IF EXISTS carga_org_lot;",
                "DROP SCHEMA IF EXISTS acoes_pngi;",
            ],
        ),
    ]
