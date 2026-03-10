"""
GPP Plataform 2.0 — Accounts Signals

Responsabilidades:
1. Criar auth_group automaticamente ao salvar um Role sem group.
2. Invalidar cache de autorização quando permissions mudam.
3. Invalidar cache quando UserRole é criado/deletado.
"""
import logging

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

security_logger = logging.getLogger("gpp.security")


# ─── Auto-criação de auth_group para cada Role ───────────────────────────────────

@receiver(post_save, sender="accounts.Role")
def auto_create_group_for_role(sender, instance, created, **kwargs):
    """
    Ao criar uma Role sem group definido, cria automaticamente
    um auth_group com o nome '{app_code}_{codigoperfil}'.
    """
    if created and instance.group is None:
        app_code = instance.aplicacao.codigointerno if instance.aplicacao else "gpp"
        group_name = f"{app_code}_{instance.codigoperfil}"
        group, _ = Group.objects.get_or_create(name=group_name)
        # Usa update() para evitar loop de signal
        sender.objects.filter(pk=instance.pk).update(group=group)
        security_logger.info(
            "ROLE_GROUP_CREATED role_id=%s group=%s",
            instance.pk, group_name,
        )


# ─── Invalidação de cache ───────────────────────────────────────────────────────────────────

def _invalidate_user_authz_cache(user_id: int, role_id: int, app_code: str):
    """Invalida a chave de cache de autorização de um usuário específico."""
    # Cache version key — incrementar a versão invalida todas as chaves derivadas
    version_key = f"authz_version:{user_id}"
    cache.incr(version_key, delta=1, default=1)

    # Também invalida a chave direta para garantia
    direct_key = f"authz:{user_id}:{role_id}:{app_code}"
    cache.delete(direct_key)

    # Invalida lista de roles do usuário
    cache.delete(f"user_roles:{user_id}")

    security_logger.info(
        "CACHE_INVALIDATED user_id=%s role_id=%s app_code=%s",
        user_id, role_id, app_code,
    )


@receiver(post_save, sender="accounts.UserRole")
@receiver(post_delete, sender="accounts.UserRole")
def invalidate_on_userrole_change(sender, instance, **kwargs):
    """Invalida cache quando UserRole é criado ou removido."""
    app_code = instance.aplicacao.codigointerno if instance.aplicacao else "unknown"
    _invalidate_user_authz_cache(instance.user_id, instance.role_id, app_code)


@receiver(m2m_changed, sender=Group.permissions.through)
def invalidate_on_group_permission_change(sender, instance, action, **kwargs):
    """
    Invalida cache de todos os usuários que têm roles ligadas
    ao grupo que teve suas permissões alteradas.
    Cobre: post_add, post_remove, post_clear.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    from apps.accounts.models import Role, UserRole

    roles = Role.objects.filter(group=instance).prefetch_related("userrole_set")
    invalidated = 0
    for role in roles:
        app_code = role.aplicacao.codigointerno if role.aplicacao else "unknown"
        for user_role in role.userrole_set.all():
            _invalidate_user_authz_cache(user_role.user_id, role.id, app_code)
            invalidated += 1

    security_logger.warning(
        "CACHE_INVALIDATED_GROUP_PERM_CHANGE group=%s affected_user_roles=%s",
        instance.name, invalidated,
    )
