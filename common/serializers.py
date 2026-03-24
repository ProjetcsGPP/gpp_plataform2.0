"""
GPP Plataform 2.0 — Serializers base de common
"""
from rest_framework import serializers


class AuditableModelSerializer(serializers.ModelSerializer):
    """
    Serializer base para models que herdam de AuditableModel.

    Expoe os campos de auditoria como read-only no output da API.
    Os campos são preenchidos automaticamente pelo AuditableMixin
    no perform_create/perform_update — nunca pelo cliente.

    Uso:
        class AcaoSerializer(AuditableModelSerializer):
            class Meta(AuditableModelSerializer.Meta):
                model = Acoes
                fields = AuditableModelSerializer.Meta.fields + [
                    "strapelido",
                    "strdescricaoacao",
                    # ... campos específicos
                ]

    Campos de auditoria incluídos automaticamente (todos read-only):
      created_by_id   — ID do usuário que criou
      created_by_name — snapshot do username na criação
      updated_by_id   — ID do usuário da última alteração
      updated_by_name — snapshot do username na alteração
      created_at      — timestamp de criação
      updated_at      — timestamp da última alteração
    """

    created_by_id = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(read_only=True)
    updated_by_id = serializers.IntegerField(read_only=True)
    updated_by_name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        fields = [
            "created_by_id",
            "created_by_name",
            "updated_by_id",
            "updated_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_by_id",
            "created_by_name",
            "updated_by_id",
            "updated_by_name",
            "created_at",
            "updated_at",
        ]
