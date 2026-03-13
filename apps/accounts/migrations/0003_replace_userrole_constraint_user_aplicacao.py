"""
Fase 7 — Substitui UniqueConstraint de UserRole.

Anterior (Fase 4 — nível de serializer):
    UniqueConstraint(fields=["user", "aplicacao", "role"],
                     name="uq_userrole_user_aplicacao_role")

Nova (Fase 7 — nível de banco):
    UniqueConstraint(fields=["user", "aplicacao"],
                     name="uq_userrole_user_aplicacao")

GAPs resolvidos: GAP-04 (nível de banco) · GAP-06

Reversão:
    python manage.py migrate accounts 0002_create_schemas
Aplicação:
    python manage.py migrate accounts 0003_replace_userrole_constraint_user_aplicacao
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_create_schemas"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="userrole",
            name="uq_userrole_user_aplicacao_role",
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(
                fields=["user", "aplicacao"],
                name="uq_userrole_user_aplicacao",
            ),
        ),
    ]
