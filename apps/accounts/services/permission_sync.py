"""
GPP Plataform 2.0 — Permission Sync Service

GAP-05 — Responsabilidade:
  sync_user_permissions_from_group  : copia auth_group_permissions → auth_user_user_permissions
  revoke_user_permissions_from_group: remove permissões exclusivas de um grupo removido (Fase 5)
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

security_logger = logging.getLogger("gpp.security")
User = get_user_model()


def sync_user_permissions_from_group(user: User, group: Group) -> int:
    """
    Copia as permissões de auth_group_permissions para auth_user_user_permissions.

    Regras:
      R-04: opera como merge — nunca remove permissões existentes do usuário.
      R-05: se group=None (dado legado), registra WARNING e retorna 0 sem exceção.

    Returns:
        int: quantidade de novas permissões adicionadas ao usuário.
    """
    if group is None:
        security_logger.warning(
            "PERM_SYNC_SKIP user_id=%s reason=group_is_none",
            user.pk,
        )
        return 0

    group_perms = set(group.permissions.values_list("pk", flat=True))
    existing_perms = set(user.user_permissions.values_list("pk", flat=True))
    to_add = group_perms - existing_perms

    if to_add:
        perms = Permission.objects.filter(pk__in=to_add)
        user.user_permissions.add(*perms)
        security_logger.info(
            "PERM_SYNC_ADD user_id=%s group=%s added=%s",
            user.pk,
            group.name,
            len(to_add),
        )

    return len(to_add)


def revoke_user_permissions_from_group(user: User, group_removed: Group) -> int:
    """
    Remove de auth_user_user_permissions as permissões do grupo removido,
    exceto aquelas ainda cobertas por outros grupos ativos do usuário.

    Lógica:
      1. Buscar todas as roles ativas remanescentes do usuário (excluindo o grupo removido)
      2. Calcular o conjunto de permissões protegidas (cobertas pelos grupos remanescentes)
      3. Remover do usuário apenas as permissões do grupo removido que NÃO estão protegidas

    Regras:
      R-01: nunca revoga permissões cobertas por outros grupos ativos do usuário.
      R-03: se group_removed=None, registra WARNING e retorna 0 sem exceção.

    Returns:
        int: quantidade de permissões removidas.
    """
    if group_removed is None:
        security_logger.warning(
            "PERM_REVOKE_SKIP user_id=%s reason=group_is_none",
            user.pk,
        )
        return 0

    # Grupos remanescentes do usuário (excluindo o grupo que está sendo removido)
    remaining_groups = Group.objects.filter(
        roles__userrole__user=user
    ).exclude(pk=group_removed.pk).distinct()

    # Permissões protegidas pelos grupos remanescentes
    protected_perm_ids = set(
        Permission.objects.filter(
            group__in=remaining_groups
        ).values_list("pk", flat=True)
    )

    # Permissões candidatas à remoção (do grupo removido)
    candidate_perm_ids = set(
        group_removed.permissions.values_list("pk", flat=True)
    )

    # Remover somente as não protegidas
    to_remove_ids = candidate_perm_ids - protected_perm_ids

    if to_remove_ids:
        perms_to_remove = Permission.objects.filter(pk__in=to_remove_ids)
        user.user_permissions.remove(*perms_to_remove)
        security_logger.info(
            "PERM_REVOKE user_id=%s group=%s removed=%s",
            user.pk, group_removed.name, len(to_remove_ids),
        )

    return len(to_remove_ids)
