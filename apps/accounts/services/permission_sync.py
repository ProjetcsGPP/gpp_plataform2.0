"""
permission_sync.py
==================

Orquestrador oficial, idempotente e transacional do cálculo de permissões
do sistema RBAC da GPP Plataform.

Regra oficial do domínio
------------------------
A tabela ``auth_user_user_permissions`` é a única fonte de verdade consultada
em runtime para decisões de autorização. Permissões **não** são lidas de
``auth_user_groups`` nem derivadas de ``auth_group_permissions`` diretamente
durante a verificação de acesso.

Fluxo de materialização (Fase 4)
---------------------------------
  Para cada usuário com roles ativas:

  1. Busca todas as ``UserRole`` ativas do usuário.
  2. Resolve ``Role → Group`` para cada UserRole.
  3. Busca permissões de cada grupo em ``auth_group_permissions``.
  4. Calcula o conjunto herdado (união de todas as permissões dos grupos).
  5. Aplica overrides de ``UserPermissionOverride``:
       - ``mode=grant``  → adiciona ao conjunto herdado
       - ``mode=revoke`` → remove do conjunto herdado
  6. Materializa o conjunto final em ``auth_user_user_permissions``
     via **substituição completa** (``user.user_permissions.set()``).

  A substituição completa (passo 6) garante idempotência e elimina
  "phantom perms" adicionadas manualmente fora do fluxo — corrige D-04.

Papel residual de auth_user_groups
-----------------------------------
``auth_user_groups`` NÃO é populado nem consultado por este sistema.
Os grupos (``auth.Group``) funcionam apenas como template institucional de
permissões. Veja ADR-PERM-01 em docs/PERMISSIONS_ARCHITECTURE.md.

Regras de negócio
-----------------
  R-01  overrides ``revoke`` são aplicados sobre o conjunto herdado;
        nunca removem permissões concedidas por outro grupo ativo.
  R-04  a substituição completa via ``set()`` substitui todo o estado anterior;
        não é incremental.

Divergências corrigidas nesta fase
-----------------------------------
  D-04  Corrigida: substituição completa elimina phantom perms.
  D-05  Corrigida: ``invalidate_on_group_permission_change`` agora chama
        ``sync_users_permissions`` para re-sincronizar todos os usuários
        afetados pela mudança de permissões no grupo.

API pública
-----------
  calculate_inherited_permissions(user)  → set[Permission]  (pura, sem gravação)
  calculate_effective_permissions(user)  → set[Permission]  (com overrides, sem gravação)
  sync_user_permissions(user)            → None              (grava, idempotente)
  sync_users_permissions(user_ids)       → None              (batch)
  sync_all_users_permissions()           → None              (todos com roles ativas)

  Aliases deprecados (retro-compatibilidade):
  sync_user_permissions_from_group(user, group)             → None
  revoke_user_permissions_from_group(user, group_removed)   → None
"""

import logging

from django.contrib.auth.models import Permission
from django.db import transaction

logger = logging.getLogger("gpp.permission_sync")


# ──────────────────────────────────────────────────────────────────────────────
# Funções de cálculo (puras — não gravam no banco)
# ──────────────────────────────────────────────────────────────────────────────


def calculate_inherited_permissions(user) -> set:
    """
    Calcula o conjunto de permissões herdadas das roles ativas do usuário
    via ``auth_group_permissions``.

    Navega: ``UserRole → Role → Group → auth_group_permissions``.
    Retorna objetos ``Permission`` (não PKs).
    Não grava nada no banco — função pura de leitura.

    Args:
        user: instância de ``django.contrib.auth.models.User``.

    Returns:
        set[Permission]: conjunto de permissões herdadas. Pode ser vazio.
    """
    from apps.accounts.models import UserRole

    group_ids = (
        UserRole.objects.filter(user=user)
        .select_related("role__group")
        .exclude(role__group=None)
        .values_list("role__group_id", flat=True)
        .distinct()
    )

    if not group_ids:
        logger.debug(
            "PERM_INHERIT_EMPTY user_id=%s reason=no_active_roles_with_group",
            user.pk,
        )
        return set()

    perms = set(Permission.objects.filter(group__id__in=list(group_ids)).distinct())

    logger.debug(
        "PERM_INHERIT_CALC user_id=%s inherited=%d",
        user.pk,
        len(perms),
    )
    return perms


def calculate_effective_permissions(user) -> set:
    """
    Aplica overrides de ``UserPermissionOverride`` sobre o conjunto herdado
    e retorna o conjunto final de permissões efetivas do usuário.

    Sequência:
      1. Chama ``calculate_inherited_permissions(user)``.
      2. Adiciona permissões com ``mode='grant'``.
      3. Remove permissões com ``mode='revoke'``.

    Não grava nada no banco — função pura de leitura.

    Args:
        user: instância de ``django.contrib.auth.models.User``.

    Returns:
        set[Permission]: conjunto efetivo de permissões. Pode ser vazio.
    """
    from apps.accounts.models import UserPermissionOverride

    effective = calculate_inherited_permissions(user)

    overrides = UserPermissionOverride.objects.filter(user=user).select_related(
        "permission"
    )

    grants = {o.permission for o in overrides if o.mode == "grant"}
    revokes = {o.permission for o in overrides if o.mode == "revoke"}

    effective = (effective | grants) - revokes

    logger.debug(
        "PERM_EFFECTIVE_CALC user_id=%s inherited=%d grants=%d revokes=%d effective=%d",
        user.pk,
        len(effective) + len(revokes) - len(grants),
        len(grants),
        len(revokes),
        len(effective),
    )
    return effective


# ──────────────────────────────────────────────────────────────────────────────
# Funções de materialização (escrevem em auth_user_user_permissions)
# ──────────────────────────────────────────────────────────────────────────────


def sync_user_permissions(user) -> None:
    """
    Materializa as permissões efetivas do usuário em ``auth_user_user_permissions``
    via **substituição completa** (``set()``).

    Esta é a função central do orquestrador. Deve ser chamada sempre que o
    estado de permissões do usuário puder ter mudado:
      - Atribuição de role (``UserRoleViewSet.create``)
      - Remoção de role (``UserRoleViewSet.destroy``)
      - Criação de usuário com role (``UserCreateWithRoleSerializer.create``)
      - Mudança de permissões em um grupo (signal ``invalidate_on_group_permission_change``)
      - Qualquer alteração em ``UserPermissionOverride``

    Idempotência:
        Chamar esta função duas vezes seguidas para o mesmo usuário produz
        o mesmo resultado em ``auth_user_user_permissions``.

    Correção D-04:
        A substituição completa via ``set()`` elimina quaisquer permissões
        que tenham sido adicionadas manualmente fora do fluxo de sync
        ("phantom perms").

    Args:
        user: instância de ``django.contrib.auth.models.User``.

    Raises:
        Não lança exceções diretamente; erros de banco propagam normalmente.
    """
    with transaction.atomic():
        effective = calculate_effective_permissions(user)
        current_pks = set(user.user_permissions.values_list("pk", flat=True))
        new_pks = {p.pk for p in effective}

        if current_pks == new_pks:
            logger.debug(
                "PERM_SYNC_NOOP user_id=%s reason=already_in_sync count=%d",
                user.pk,
                len(new_pks),
            )
            return

        user.user_permissions.set(effective)

        added = new_pks - current_pks
        removed = current_pks - new_pks

        logger.info(
            "PERM_SYNC user_id=%s total=%d added=%d removed=%d",
            user.pk,
            len(new_pks),
            len(added),
            len(removed),
        )


def sync_users_permissions(user_ids: list) -> None:
    """
    Sincroniza permissões de um conjunto de usuários via ``sync_user_permissions``.

    Útil para re-sync em batch quando um grupo tem suas permissões alteradas
    (corrige D-05), evitando que cada chamador precise iterar manualmente.

    Args:
        user_ids (list[int]): lista de PKs de usuários a re-sincronizar.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    if not user_ids:
        return

    users = User.objects.filter(pk__in=list(user_ids))
    for user in users:
        try:
            sync_user_permissions(user)
        except Exception:
            logger.exception(
                "PERM_SYNC_ERROR user_id=%s",
                user.pk,
            )

    logger.info(
        "PERM_SYNC_BATCH count=%d",
        len(list(user_ids)),
    )


def sync_all_users_permissions() -> None:
    """
    Re-sincroniza as permissões de **todos** os usuários que possuem ao menos
    uma ``UserRole`` ativa.

    Útil para management commands de manutenção e migrações de dados.
    Deve ser usado com cautela em produção — prefira ``sync_users_permissions``
    para re-syncs pontuais.
    """
    from apps.accounts.models import UserRole

    user_ids = UserRole.objects.values_list("user_id", flat=True).distinct()
    total = user_ids.count()

    logger.info("PERM_SYNC_ALL_START total_users=%d", total)

    sync_users_permissions(list(user_ids))

    logger.info("PERM_SYNC_ALL_DONE total_users=%d", total)


# ──────────────────────────────────────────────────────────────────────────────
# Aliases deprecados — retro-compatibilidade
# ──────────────────────────────────────────────────────────────────────────────


def sync_user_permissions_from_group(user, group) -> None:
    """
    .. deprecated::
        Substituído por ``sync_user_permissions(user)`` na Fase 4.
        Mantido para retro-compatibilidade. Chame ``sync_user_permissions``
        diretamente em código novo.

    Dispara um sync completo do usuário, ignorando o argumento ``group``.
    O novo orquestrador calcula o conjunto efetivo a partir de todas as
    roles ativas do usuário — não de um grupo específico.
    """
    logger.debug(
        "PERM_SYNC_COMPAT_CALL user_id=%s alias=sync_user_permissions_from_group",
        user.pk,
    )
    sync_user_permissions(user)


def revoke_user_permissions_from_group(user, group_removed) -> None:
    """
    .. deprecated::
        Substituído por ``sync_user_permissions(user)`` na Fase 4.
        Mantido para retro-compatibilidade. Chame ``sync_user_permissions``
        diretamente em código novo.

    A remoção de permissões agora acontece implicitamente na substituição
    completa realizada por ``sync_user_permissions`` — o argumento
    ``group_removed`` é ignorado.
    """
    logger.debug(
        "PERM_SYNC_COMPAT_CALL user_id=%s alias=revoke_user_permissions_from_group",
        user.pk,
    )
    sync_user_permissions(user)
