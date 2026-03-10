"""
GPP Plataform 2.0 — Accounts Signals

Responsabilidades:
  1. Criar auth_group automaticamente ao salvar um Role sem group.
  2. Invalidar cache de autorização quando:
     - UserRole é criado/deletado
     - auth_group_permissions muda (m2m_changed)
     - Aplicacao é criada/alterada (invalida ApplicationRegistry)
"""
import logging

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

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
            instance.pk, group_name,
        )


# ─── Helpers de invalidação ─────────────────────────────────────────────────

def _bump_user_version(user_id: int):
    """
    Incrementa a version key do usuário.
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
    """Invalida cache quando UserRole é criado, alterado ou removido."""
    app_code = instance.aplicacao.codigointerno if instance.aplicacao else "all"
    _bump_user_version(instance.user_id)
    # Invalida também a chave de roles específica desta app
    cache.delete(f"user_roles:{instance.user_id}:{app_code}")
    security_logger.warning(
        "USERROLE_CHANGED user_id=%s role_id=%s app=%s",
        instance.user_id, instance.role_id, app_code,
    )


# ─── Invalidação por alteração de permissões do grupo ─────────────────────

@receiver(m2m_changed, sender=Group.permissions.through)
def invalidate_on_group_permission_change(sender, instance, action, **kwargs):
    """
    Quando auth_group_permissions muda, invalida cache de todos os
    usuários que têm roles ligadas a esse grupo.
    Cobre: post_add, post_remove, post_clear.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    from apps.accounts.models import Role, UserRole

    roles = Role.objects.filter(group=instance)
    affected_user_ids = (
        UserRole.objects
        .filter(role__in=roles)
        .values_list("user_id", flat=True)
        .distinct()
    )

    for user_id in affected_user_ids:
        _bump_user_version(user_id)

    security_logger.warning(
        "GROUP_PERM_CHANGED group=%s affected_users=%s",
        instance.name, list(affected_user_ids),
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
