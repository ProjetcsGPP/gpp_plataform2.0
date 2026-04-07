"""
permission_sync.py
==================

Serviço de materialização de permissões do sistema RBAC da GPP Plataform.

Regra oficial do domínio
------------------------
A tabela `auth_user_user_permissions` é a Única fonte de verdade consultada
em runtime para decisões de autorização. Permissões não são lidas de
`auth_user_groups` nem derivadas de `auth_group_permissions` diretamente
durante a verificação de acesso.

Fluxo de materialização
-----------------------
  1. Atribuição de role (UserRoleViewSet.create / UserCreateWithRoleSerializer):
       sync_user_permissions_from_group(user, role.group)
       └─► merge de auth_group_permissions → auth_user_user_permissions

  2. Remoção de role (UserRoleViewSet.destroy):
       revoke_user_permissions_from_group(user, group_removed)
       └─► remoção seletiva de auth_user_user_permissions

Papel residual de auth_user_groups
-----------------------------------
`auth_user_groups` NÃO é populado nem consultado por este sistema.
Os grupos (`auth.Group`) funcionam apenas como template institucional de
permissões. As permissões são copiadas (materializadas) individualmente em
`auth_user_user_permissions` durante o sync. Veja ADR-PERM-01 em
docs/PERMISSIONS_ARCHITECTURE.md.

Regras de negócio
-----------------
  R-01  revoke nunca remove permissões cobertas por outro grupo ativo do usuário.
  R-04  sync nunca remove permissões existentes em auth_user_user_permissions
        (operação exclusivamente aditiva).

Divergências abertas (ver Issue #14 — Fase 1)
---------------------------------------------
  D-04  revoke_user_permissions_from_group deriva grupos remanescentes via ORM
        (Group.filter(roles__userrole__user=user)) sem confirmar contra
        auth_user_user_permissions. Pode gerar phantom perms se permissões
        forem adicionadas fora do fluxo de sync. A correção está planejada
        para a Fase 3 da refatoração.
  D-05  A invalidação de cache disparada por signals ao alterar
        auth_group_permissions não re-sincroniza auth_user_user_permissions.
        Alterações de permissões no grupo exigem re-sync manual dos usuários
        afetados até que D-05 seja corrigido.
"""

import logging

from django.contrib.auth.models import Permission
from django.db import transaction

logger = logging.getLogger("gpp.permission_sync")


def sync_user_permissions_from_group(user, group) -> None:
    """
    Materializa as permissões de `group` em `auth_user_user_permissions`
    para o usuário informado.

    Operação: **merge aditivo** — nunca remove permissões já existentes
    (Regra R-04). Garante que usuários com múltiplas roles acumulem
    todas as permissões dos respectivos grupos.

    Fluxo:
        1. Obtém as permissões de `group` via `auth_group_permissions`.
        2. Calcula a diferença em relação ao que o usuário já possui.
        3. Adiciona apenas as permissões novas em `auth_user_user_permissions`.

    Esta função deve ser chamada dentro de uma transação atômica,
    junto com a criação do `UserRole` correspondente.

    Args:
        user (User): instância de `django.contrib.auth.models.User`.
        group (Group | None): instância de `django.contrib.auth.models.Group`.
            Se `None` (role sem grupo), a função retorna imediatamente
            sem efeito colateral.

    Raises:
        Não lança exceções diretamente; erros de banco propagam normalmente.

    Exemplo::

        with transaction.atomic():
            user_role = UserRole.objects.create(
                user=user, aplicacao=app, role=role
            )
            sync_user_permissions_from_group(user, role.group)
    """
    if group is None:
        logger.debug(
            "PERM_SYNC_SKIP user_id=%s reason=group_is_none",
            user.pk,
        )
        return

    group_perms = set(group.permissions.values_list("pk", flat=True))
    user_perms = set(user.user_permissions.values_list("pk", flat=True))
    to_add_pks = group_perms - user_perms

    if not to_add_pks:
        logger.debug(
            "PERM_SYNC_NOOP user_id=%s group=%s reason=already_synced",
            user.pk,
            group.name,
        )
        return

    to_add = Permission.objects.filter(pk__in=to_add_pks)
    user.user_permissions.add(*to_add)

    logger.info(
        "PERM_SYNC_ADD user_id=%s group=%s added=%d",
        user.pk,
        group.name,
        len(to_add_pks),
    )


def revoke_user_permissions_from_group(user, group_removed) -> None:
    """
    Remove de `auth_user_user_permissions` as permissões que eram exclusivas
    do grupo removido, respeitando a Regra R-01.

    Operação: **remoção seletiva** — só remove permissões que não estão
    cobertas por nenhum outro grupo ativo do usuário (grupos de outras
    `UserRole` ainda ativas).

    Fluxo:
        1. Calcula permissões do grupo removido.
        2. Calcula permissões protegidas por todos os outros grupos ativos.
        3. Remove de `auth_user_user_permissions` apenas
           `perms_do_grupo_removido - perms_protegidas`.

    .. warning::
        **Divergência D-04 (aberta):** Os grupos remanescentes são derivados
        via ``Group.filter(roles__userrole__user=user)`` (ORM), sem confirmar
        contra ``auth_user_user_permissions``. Isso pode gerar inconsistência
        caso permissões tenham sido adicionadas manualmente fora do fluxo de
        sync. Correção planejada para a Fase 3.

    Esta função deve ser chamada dentro de uma transação atômica,
    após a exclusão do `UserRole` correspondente.

    Args:
        user (User): instância de `django.contrib.auth.models.User`.
        group_removed (Group | None): instância do grupo cuja role foi
            revogada. Se `None`, a função retorna imediatamente.

    Raises:
        Não lança exceções diretamente; erros de banco propagam normalmente.

    Exemplo::

        with transaction.atomic():
            user_role.delete()
            revoke_user_permissions_from_group(user, role.group)
    """
    if group_removed is None:
        logger.debug(
            "PERM_REVOKE_SKIP user_id=%s reason=group_is_none",
            user.pk,
        )
        return

    from django.contrib.auth.models import Group

    removed_perms = set(
        group_removed.permissions.values_list("pk", flat=True)
    )

    if not removed_perms:
        logger.debug(
            "PERM_REVOKE_NOOP user_id=%s group=%s reason=no_perms_in_group",
            user.pk,
            group_removed.name,
        )
        return

    # Grupos remanescentes (roles ainda ativas após a exclusão)
    # NOTA D-04: deriva via ORM, não confirma contra auth_user_user_permissions
    remaining_groups = Group.objects.filter(
        roles__userrole__user=user
    ).exclude(pk=group_removed.pk)

    protected_perms = set(
        Permission.objects
        .filter(group__in=remaining_groups)
        .values_list("pk", flat=True)
    )

    to_remove_pks = removed_perms - protected_perms

    if not to_remove_pks:
        logger.debug(
            "PERM_REVOKE_NOOP user_id=%s group=%s reason=all_perms_protected",
            user.pk,
            group_removed.name,
        )
        return

    to_remove = Permission.objects.filter(pk__in=to_remove_pks)
    user.user_permissions.remove(*to_remove)

    logger.info(
        "PERM_REVOKE_REMOVE user_id=%s group=%s removed=%d",
        user.pk,
        group_removed.name,
        len(to_remove_pks),
    )
