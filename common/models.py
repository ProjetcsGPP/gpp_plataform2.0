"""
GPP Plataform 2.0 — AuditableModel
Model base abstrato com campos de auditoria.
Todos os models de negócio devem herdar deste.
"""
from django.conf import settings
from django.db import models


class AuditableModel(models.Model):
    """
    Model base abstrato com campos de auditoria.

    Uso:
        class MinhaEntidade(AuditableModel):
            ...

    created_by e updated_by são preenchidos automaticamente
    pelo serializer via request.user — não pelo model.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_updated",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True
