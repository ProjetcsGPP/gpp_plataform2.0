"""
GPP Plataform 2.0 — Accounts Migration 0010
Fase 12 (Issue #25) — Parte 2: Limpeza de resíduos do token_blacklist

Remove content types, permissões e vínculos de auth_user_user_permissions
residuais do app token_blacklist, que foi removido em fase anterior mas
pode ter deixado dados órfãos no banco.

Esta migration é IDEMPOTENTE: retorna imediatamente se não houver
content types de token_blacklist (guard `if not ct_ids: return`).
Pode ser executada N vezes sem erro.

Ordem de operações:
  1. Localizar ContentTypes com app_label='token_blacklist'
  2. Limpar M2M auth_user_user_permissions via perm.user_set.clear()
  3. Deletar as Permissions residuais
  4. Deletar os ContentTypes residuais

Critérios de aceite (Issue #25):
  - Zero registros de token_blacklist em django_content_type
  - Zero registros de token_blacklist em auth_permission
  - Zero usuários com perms de token_blacklist em auth_user_user_permissions
  - Migration idempotente (N execuções sem erro)

Referências: ADR-PERM-01, PERMISSIONS_ARCHITECTURE.md, Issue #25 Fase 12.
"""
from django.db import migrations


def clean_token_blacklist(apps, schema_editor):
    """
    Remove resíduos do app token_blacklist das tabelas do Django auth.

    Idempotente: se não houver content types de token_blacklist, retorna
    imediatamente sem executar nenhuma operação de escrita.
    """
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')

    # Encontrar content types do token_blacklist
    blacklist_cts = ContentType.objects.filter(app_label='token_blacklist')
    ct_ids = list(blacklist_cts.values_list('id', flat=True))

    if not ct_ids:
        # Idempotente: já limpo — nada a fazer
        return

    # Remover vínculos em auth_user_user_permissions (tabela M2M)
    # perm.user_set.clear() remove todas as linhas de auth_user_user_permissions
    # que referenciam esta permissão, sem deletar usuários nem permissões ainda.
    perms_to_remove = Permission.objects.filter(content_type_id__in=ct_ids)
    for perm in perms_to_remove:
        perm.user_set.clear()

    # Remover as permissões residuais de auth_permission
    Permission.objects.filter(content_type_id__in=ct_ids).delete()

    # Remover os content types residuais de django_content_type
    blacklist_cts.delete()


def reverse_clean(apps, schema_editor):
    """
    Reversão não implementada: a limpeza de dados órfãos não é reversível.
    Uma migração de rollback recriaria content types e permissões sem dados
    reais para restaurar, o que não faria sentido semântico.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_add_userpermissionoverride'),
    ]

    operations = [
        migrations.RunPython(clean_token_blacklist, reverse_clean),
    ]
