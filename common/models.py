"""
GPP Plataform 2.0 — AuditableModel
Model base abstrato com campos de auditoria.
Todos os models de negócio devem herdar deste.
"""
from django.db import models


class AuditableModel(models.Model):
    """
    Model base abstrato com campos de auditoria.

    Campos de auditoria usam chave lógica (IntegerField) + snapshot de nome
    em vez de ForeignKey para AUTH_USER_MODEL. Isso garante:

      1. Independência total entre apps de negócio e o schema de auth/accounts.
         Nenhuma FK cross-schema/cross-db é criada — cada app pode ter seu
         próprio banco de dados no futuro sem alteração de modelo.

      2. Histórico imutável: mesmo que o usuário seja deletado ou renomeado,
         o registro de quem criou/alterou permanece íntegro.

      3. Teardown limpo no pytest-django: TRUNCATE auth_user não é bloqueado
         por restrição de chave estrangeira em nenhuma app de negócio.

    Preenchimento automático:
      Os campos são preenchidos pelo AuditableMixin (common/mixins.py)
      via perform_create/perform_update — nunca pelo model diretamente.
      O user_id e username chegam de request.user, resolvido pelo
      AppContextMiddleware a partir da sessão Django (cookie-based IAM).

    Uso:
        class MinhaEntidade(AuditableModel):
            ...
    """

    # --- Auditoria de criação ---
    created_by_id = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        db_column="created_by_id",
        help_text="ID lógico do usuário que criou o registro (sem FK para auth_user).",
    )
    created_by_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        editable=False,
        db_column="created_by_name",
        help_text="Snapshot do username no momento da criação — imutável.",
    )

    # --- Auditoria de alteração ---
    updated_by_id = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        db_column="updated_by_id",
        help_text="ID lógico do usuário que fez a última alteração (sem FK para auth_user).",
    )
    updated_by_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        editable=False,
        db_column="updated_by_name",
        help_text="Snapshot do username no momento da última alteração — imutável.",
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        db_column="created_at",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_column="updated_at",
    )

    class Meta:
        abstract = True
