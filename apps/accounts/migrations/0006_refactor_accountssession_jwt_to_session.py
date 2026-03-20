"""
FASE-0 — Migration destrutiva de AccountsSession.

O que faz:
  1. Apaga todos os registros existentes (dados de sessão JWT são inválidos após a migração).
  2. Remove campo `jti` e seus índices.
  3. Adiciona campo `session_key` (CharField 40, db_index=True).
  4. Adiciona campo `app_context` (CharField 50, null/blank).
  5. Recria índices compostos em (session_key, revoked) e (user, revoked).
  6. Remove unique_together/index em jti que existia na 0001_initial.

Seguro porque:
  - Ambiente de desenvolvimento, sem dados de sessão relevantes.
  - Sessões JWT anteriores já seriam inválidas com o novo fluxo.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_add_aplicacao_bloqueada_productionready"),
    ]

    operations = [
        # 1. Limpa registros existentes (JWT sessions inválidas)
        migrations.RunSQL(
            sql="DELETE FROM accounts_session;",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # 2. Remove índices antigos que referenciam jti
        migrations.RunSQL(
            sql="""
                DROP INDEX IF EXISTS accounts_session_jti_revoked;
                DROP INDEX IF EXISTS accounts_accounts_jti_revoked_idx;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # 3. Remove campo jti
        migrations.RemoveField(
            model_name="accountssession",
            name="jti",
        ),

        # 4. Adiciona session_key
        migrations.AddField(
            model_name="accountssession",
            name="session_key",
            field=models.CharField(
                db_index=True,
                help_text="Chave da sessão Django (request.session.session_key)",
                max_length=40,
                default="",
            ),
            preserve_default=False,
        ),

        # 5. Adiciona app_context
        migrations.AddField(
            model_name="accountssession",
            name="app_context",
            field=models.CharField(
                blank=True,
                help_text="Código interno da aplicação (ex: PORTAL, ACOES_PNGI)",
                max_length=50,
                null=True,
            ),
        ),

        # 6. Garante que user_agent aceita blank (era default="" na 0001, confirma)
        migrations.AlterField(
            model_name="accountssession",
            name="user_agent",
            field=models.TextField(blank=True, default=""),
        ),

        # 7. Recria índices compostos corretos
        migrations.AddIndex(
            model_name="accountssession",
            index=models.Index(
                fields=["session_key", "revoked"],
                name="accounts_session_key_revoked_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="accountssession",
            index=models.Index(
                fields=["user", "revoked"],
                name="accounts_session_user_revoked_idx",
            ),
        ),
    ]
