"""
GPP Plataform 2.0 — Accounts Signals

Responsabilidades:
  1. Criar auth_group automaticamente ao salvar um Role sem group.
  2. Invalidar cache de autorização quando:
     - UserRole é criado/deletado
     - auth_group_permissions muda (m2m_changed)
     - Aplicacao é criada/alterada (invalida ApplicationRegistry)
  3. Re-sincronizar auth_user_user_permissions sempre que qualquer
     fonte do cálculo de permissões mudar.
  4. [feat/authz_versioning] Incrementar authz_version em banco sempre
     que qualquer mudança de autorização ocorrer — usado EXCLUSIVAMENTE
     para invalidação de cache no frontend (não é parte da segurança).

FASE-6-PERM (Issue #19):
  sync_user_permissions e sync_users_permissions são agora importadas
  explicitamente no topo do módulo. Isso é necessário para que
  mocker.patch("apps.accounts.signals.sync_user_permissions") funcione
  corretamente nos testes — o símbolo precisa existir no namespace do
  módulo no momento em que o patch é aplicado.

FASE-5-PERM (Issue #18):
  invalidate_on_userrole_change agora chama sync_user_permissions(user)
  após invalidar o cache — garante que auth_user_user_permissions reflita
  imediatamente a criação ou remoção de uma UserRole.

  sync_on_role_group_change detecta quando o group de uma Role muda e
  dispara sync_users_permissions para todos os usuários com essa role,
  garantindo que auth_user_user_permissions seja recalculado quando o
  template de permissões de um perfil é trocado.

FASE-4-PERM (corrige D-05):
  invalidate_on_group_permission_change re-sincroniza auth_user_user_permissions
  para todos os usuários afetados pela mudança, além de invalidar o cache.
  Antes desta correção, a invalidação de cache não garantia que os dados em
  auth_user_user_permissions fossem consistentes com as novas permissões do grupo.
"""

import logging

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

# Importação explícita de bump_authz_version para patchabilidade em testes.
# Segue o mesmo padrão de sync_user_permissions (Issue #19).
from apps.accounts.models import bump_authz_version  # noqa: E402

# Importação explícita no topo do módulo — obrigatória para que mocker.patch
# funcione em test_permission_sync_triggers.py (Issue #19).
# O mocker.patch exige que o símbolo exista em apps.accounts.signals no momento
# em que o patch é aplicado; lazy imports dentro das funções não satisfazem isso.
from apps.accounts.services.permission_sync import (  # noqa: E402
    sync_user_permissions,
    sync_users_permissions,
)

security_logger = logging.getLogger("gpp.security")


# ─── Auto-criação de auth_group ─────────────────────────────────────────────


@receiver(post_save, sender="accounts.Role")
def auto_create_group_for_role(sender, instance, created, **kwargs):
    """
    Ao criar uma Role sem group definido, cria automaticamente
    um auth_group com nome '{app_code}_{codigoperfil}'.
    """
    if created and instance.group is None:
        app_code = instance.aplicacao.codigointerno if instance.aplicacao else "gpp"
        group_name = f"{app_code}_{instance.codigoperfil}"
        group, _ = Group.objects.get_or_create(name=group_name)
        sender.objects.filter(pk=instance.pk).update(group=group)
        security_logger.info(
            "ROLE_GROUP_CREATED role_id=%s group=%s",
            instance.pk,
            group_name,
        )


# ─── Helpers de invalidação ─────────────────────────────────────────────────


def _bump_user_version(user_id: int):
    """
    Incrementa a version key do usuário no cache Redis.
    Invalida automaticamente todas as chaves de cache
    que incluem a versão (authz, user_roles).
    """
    key = f"authz_version:{user_id}"
    try:
        cache.incr(key)
    except Exception:
        cache.set(key, 2, 300 * 10)

    # Invalida também a chave direta de user_roles (sem versão)
    cache.delete(f"user_roles:{user_id}:all")
    security_logger.info("CACHE_VERSION_BUMPED user_id=%s", user_id)


# ─── Invalidação por UserRole ───────────────────────────────────────────────


@receiver(post_save, sender="accounts.UserRole")
@receiver(post_delete, sender="accounts.UserRole")
def invalidate_on_userrole_change(sender, instance, **kwargs):
    """
    Invalida cache E re-sincroniza auth_user_user_permissions quando
    UserRole é criado, alterado ou removido.

    [feat/authz_versioning] Também chama bump_authz_version() para
    incrementar o contador de versão em banco — usado pelo frontend
    para invalidação de cache local.

    FASE-5-PERM (Issue #18):
        Além de invalidar o cache, chama sync_user_permissions(user) para
        garantir que auth_user_user_permissions reflita imediatamente a
        mudança. Sem este re-sync, o signal apenas invalidava o cache mas
        deixava auth_user_user_permissions desatualizado.

    FASE-6-PERM (Issue #19):
        sync_user_permissions é referenciada via import de topo de módulo,
        tornando-a patchável por mocker.patch no namespace de signals.
    """
    from django.contrib.auth import get_user_model

    app_code = instance.aplicacao.codigointerno if instance.aplicacao else "all"
    _bump_user_version(instance.user_id)
    # Invalida também a chave de roles específica desta app
    cache.delete(f"user_roles:{instance.user_id}:{app_code}")
    security_logger.warning(
        "USERROLE_CHANGED user_id=%s role_id=%s app=%s",
        instance.user_id,
        instance.role_id,
        app_code,
    )

    # [feat/authz_versioning] Incrementa versão de banco para frontend.
    bump_authz_version(instance.user_id)

    # Re-sincroniza auth_user_user_permissions para o usuário afetado
    User = get_user_model()
    try:
        user = User.objects.get(pk=instance.user_id)
        sync_user_permissions(user)
        security_logger.info(
            "USERROLE_PERM_RESYNC_TRIGGERED user_id=%s action=%s",
            instance.user_id,
            "delete" if kwargs.get("signal") is post_delete else "save",
        )
    except User.DoesNotExist:
        security_logger.warning(
            "USERROLE_PERM_RESYNC_SKIP user_id=%s reason=user_not_found",
            instance.user_id,
        )
    except Exception:
        security_logger.exception(
            "USERROLE_PERM_RESYNC_ERROR user_id=%s",
            instance.user_id,
        )


# ─── Re-sync por mudança de group em Role ───────────────────────────────────


@receiver(pre_save, sender="accounts.Role")
def _store_old_role_group(sender, instance, **kwargs):
    """
    Armazena o group anterior da Role antes de salvar, para que
    sync_on_role_group_change possa detectar a mudança.
    """
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_group_id = old.group_id
        except sender.DoesNotExist:
            instance._old_group_id = None
    else:
        instance._old_group_id = None


@receiver(post_save, sender="accounts.Role")
def sync_on_role_group_change(sender, instance, created, **kwargs):
    """
    Detecta mudança no campo ``group`` de uma Role e dispara
    ``sync_users_permissions`` para todos os usuários que possuem essa role.

    [feat/authz_versioning] Também chama bump_authz_version() para cada
    usuário afetado — notifica o frontend que as permissões mudaram.

    Quando o group de um perfil é trocado, os usuários com aquela role passam
    a herdar um conjunto de permissões completamente diferente. Sem este signal,
    auth_user_user_permissions ficaria desatualizado até a próxima ação manual.

    FASE-5-PERM (Issue #18): novo signal.

    FASE-6-PERM (Issue #19):
        sync_users_permissions é referenciada via import de topo de módulo,
        tornando-a patchável por mocker.patch no namespace de signals.
    """
    if created:
        return

    old_group_id = getattr(instance, "_old_group_id", None)
    new_group_id = instance.group_id

    if old_group_id == new_group_id:
        return  # group não mudou

    from apps.accounts.models import UserRole

    affected_user_ids = list(
        UserRole.objects.filter(role=instance)
        .values_list("user_id", flat=True)
        .distinct()
    )

    if not affected_user_ids:
        return

    for user_id in affected_user_ids:
        _bump_user_version(user_id)
        # [feat/authz_versioning] Notifica frontend via versão persistida.
        bump_authz_version(user_id)

    security_logger.warning(
        "ROLE_GROUP_CHANGED role_id=%s old_group=%s new_group=%s affected_users=%s",
        instance.pk,
        old_group_id,
        new_group_id,
        affected_user_ids,
    )

    sync_users_permissions(affected_user_ids)
    security_logger.info(
        "ROLE_GROUP_RESYNC_TRIGGERED role_id=%s users=%s",
        instance.pk,
        affected_user_ids,
    )


# ─── Invalidação por alteração de permissões do grupo ─────────────────────


@receiver(m2m_changed, sender=Group.permissions.through)
def invalidate_on_group_permission_change(sender, instance, action, **kwargs):
    """
    Quando auth_group_permissions muda, invalida cache E re-sincroniza
    auth_user_user_permissions para todos os usuários que têm roles ligadas
    a esse grupo.

    [feat/authz_versioning] Também chama bump_authz_version() para cada
    usuário afetado — notifica o frontend que as permissões mudaram.

    Cobre: post_add, post_remove, post_clear.

    FASE-4-PERM (corrige D-05):
        Além de invalidar o cache, chama sync_users_permissions() para garantir
        que auth_user_user_permissions reflita imediatamente as novas permissões
        do grupo. Sem este re-sync, usuários com cache expirado receberiam as
        permissões novas, mas usuários com dados em auth_user_user_permissions
        desatualizados continuariam com o conjunto antigo.

    FASE-6-PERM (Issue #19):
        sync_users_permissions é referenciada via import de topo de módulo,
        tornando-a patchável por mocker.patch no namespace de signals.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    from apps.accounts.models import Role, UserRole

    roles = Role.objects.filter(group=instance)
    affected_user_ids = list(
        UserRole.objects.filter(role__in=roles)
        .values_list("user_id", flat=True)
        .distinct()
    )

    for user_id in affected_user_ids:
        _bump_user_version(user_id)
        # [feat/authz_versioning] Notifica frontend via versão persistida.
        bump_authz_version(user_id)

    security_logger.warning(
        "GROUP_PERM_CHANGED group=%s affected_users=%s action=%s",
        instance.name,
        affected_user_ids,
        action,
    )

    # D-05: re-sincroniza auth_user_user_permissions para os usuários afetados
    if affected_user_ids:
        sync_users_permissions(affected_user_ids)
        security_logger.info(
            "GROUP_PERM_RESYNC_TRIGGERED group=%s users=%s",
            instance.name,
            affected_user_ids,
        )


# ─── Invalidação do ApplicationRegistry ────────────────────────────────────


@receiver(post_save, sender="accounts.Aplicacao")
@receiver(post_delete, sender="accounts.Aplicacao")
def invalidate_application_registry(sender, instance, **kwargs):
    """Invalida o cache do ApplicationRegistry quando Aplicacao muda."""
    from apps.accounts.services.application_registry import ApplicationRegistry

    ApplicationRegistry().invalidate()
    security_logger.info(
        "APP_REGISTRY_INVALIDATED_BY_SIGNAL app=%s",
        instance.codigointerno,
    )


# ─── bump_authz_version em UserPermissionOverride ──────────────────────────


@receiver(post_save, sender="accounts.UserPermissionOverride")
@receiver(post_delete, sender="accounts.UserPermissionOverride")
def bump_on_permission_override_change(sender, instance, **kwargs):
    """
    Incrementa authz_version quando um UserPermissionOverride é
    criado, atualizado ou removido.

    [feat/authz_versioning] Garante que o frontend seja notificado de
    mudanças individuais de permissão via override, complementando o
    bump que já ocorre dentro de sync_user_permissions.
    """
    bump_authz_version(instance.user_id)
    security_logger.info(
        "AUTHZ_VERSION_BUMPED_BY_OVERRIDE user_id=%s override_id=%s mode=%s",
        instance.user_id,
        instance.pk,
        instance.mode,
    )
