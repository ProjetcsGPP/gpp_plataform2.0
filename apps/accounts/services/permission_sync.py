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


def revoke_user_permissions_from_group(user: User, group: Group) -> int:
    """
    Remove do usuário apenas as permissões que eram exclusivas do grupo removido,
    ou seja, permissões que o usuário não possui via nenhum outro grupo ativo.

    ATENÇÃO: Esta função é preparada para a Fase 5 e NÃO é chamada nesta fase.

    Returns:
        int: quantidade de permissões revogadas.
    """
    if group is None:
        security_logger.warning(
            "PERM_REVOKE_SKIP user_id=%s reason=group_is_none",
            user.pk,
        )
        return 0

    # Permissões que o usuário tem via outros grupos ativos (excluindo o grupo removido)
    other_group_perms = set(
        Permission.objects.filter(
            group__userrole__user=user
        ).exclude(
            group=group
        ).values_list("pk", flat=True)
    )

    group_perms = set(group.permissions.values_list("pk", flat=True))
    # Apenas revoga permissões que eram exclusivas deste grupo
    to_revoke = group_perms - other_group_perms

    if to_revoke:
        perms = Permission.objects.filter(pk__in=to_revoke)
        user.user_permissions.remove(*perms)
        security_logger.info(
            "PERM_REVOKE user_id=%s group=%s revoked=%s",
            user.pk,
            group.name,
            len(to_revoke),
        )

    return len(to_revoke)
