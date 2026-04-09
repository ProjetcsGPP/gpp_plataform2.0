"""
test_factories.py
=================

Testes de validação das factories criadas na Fase 10 (Issue #23).

Verifica que:
  - Cada factory produz a instância correta no banco.
  - UserRoleFactory e UserPermissionOverrideFactory disparam sync automaticamente.
  - Nenhuma factory popula auth_user_groups (ADR-PERM-01).
  - Os cenários-base obrigatórios da issue são atingidos.
"""
import pytest
from django.contrib.auth.models import Permission, User

from apps.accounts.models import (
    Role,
    UserPermissionOverride,
    UserRole,
)
from apps.accounts.tests.factories import (
    PermissionFactory,
    RoleFactory,
    UserFactory,
    UserPermissionOverrideFactory,
    UserRoleFactory,
)


@pytest.mark.django_db
class TestPermissionFactory:
    def test_cria_permission(self):
        perm = PermissionFactory()
        assert isinstance(perm, Permission)
        assert perm.pk is not None

    def test_get_or_create_idempotente(self):
        perm1 = PermissionFactory(codename="perm_idempotente")
        perm2 = PermissionFactory(codename="perm_idempotente")
        assert perm1.pk == perm2.pk

    def test_codenames_sequenciais_unicos(self):
        p1 = PermissionFactory()
        p2 = PermissionFactory()
        assert p1.codename != p2.codename


@pytest.mark.django_db
class TestUserFactory:
    def test_cria_user_ativo(self):
        user = UserFactory()
        assert user.pk is not None
        assert user.is_active

    def test_tem_userprofile(self):
        from apps.accounts.models import UserProfile
        user = UserFactory()
        assert UserProfile.objects.filter(user=user).exists()

    def test_sem_role_nao_popula_groups(self):
        """ADR-PERM-01: auth_user_groups deve permanecer vazio."""
        user = UserFactory()
        assert user.groups.count() == 0

    def test_sem_role_permissions_vazias(self):
        """Sem role, auth_user_user_permissions deve estar vazio."""
        user = UserFactory()
        assert user.user_permissions.count() == 0

    def test_username_sequencial(self):
        u1 = UserFactory()
        u2 = UserFactory()
        assert u1.username != u2.username

    def test_superuser(self):
        user = UserFactory(is_superuser=True)
        assert user.is_superuser


@pytest.mark.django_db
class TestRoleFactory:
    def test_cria_role_com_group(self):
        role = RoleFactory()
        assert isinstance(role, Role)
        assert role.group is not None

    def test_cria_role_com_aplicacao(self):
        role = RoleFactory()
        assert role.aplicacao is not None

    def test_codigoperfil_sequencial(self):
        r1 = RoleFactory()
        r2 = RoleFactory()
        assert r1.codigoperfil != r2.codigoperfil


@pytest.mark.django_db
class TestUserRoleFactory:
    def test_cria_userrole(self):
        ur = UserRoleFactory()
        assert isinstance(ur, UserRole)
        assert ur.pk is not None

    def test_sync_materializa_permissions(self):
        """
        Cenário-base: usuário com uma role simples.
        sync_user_permissions deve materializar o conjunto base.
        """
        perm = PermissionFactory(codename="view_userprofile_factory")
        role = RoleFactory()
        role.group.permissions.add(perm)

        ur = UserRoleFactory(role=role)
        ur.user.refresh_from_db()

        perm_codes = list(
            ur.user.user_permissions.values_list("codename", flat=True)
        )
        assert "view_userprofile_factory" in perm_codes

    def test_nao_popula_auth_user_groups(self):
        """ADR-PERM-01: factory nunca adiciona user a auth_user_groups."""
        ur = UserRoleFactory()
        assert ur.user.groups.count() == 0

    def test_multiplas_roles_uniao_sem_duplicidade(self):
        """
        Cenário-base: usuário com múltiplas roles.
        união correta em auth_user_user_permissions sem duplicidade.
        """
        from apps.accounts.models import Aplicacao

        perm_a = PermissionFactory(codename="perm_role_a_multi")
        perm_b = PermissionFactory(codename="perm_role_b_multi")
        perm_shared = PermissionFactory(codename="perm_shared_multi")

        app_a, _ = Aplicacao.objects.get_or_create(
            codigointerno="MULTI_APP_A",
            defaults={"nomeaplicacao": "Multi App A", "isappbloqueada": False, "isappproductionready": True},
        )
        app_b, _ = Aplicacao.objects.get_or_create(
            codigointerno="MULTI_APP_B",
            defaults={"nomeaplicacao": "Multi App B", "isappbloqueada": False, "isappproductionready": True},
        )

        role_a = RoleFactory(codigoperfil="MULTI_ROLE_A", aplicacao=app_a)
        role_a.group.permissions.set([perm_a, perm_shared])

        role_b = RoleFactory(codigoperfil="MULTI_ROLE_B", aplicacao=app_b)
        role_b.group.permissions.set([perm_b, perm_shared])

        user = UserFactory()
        UserRoleFactory(user=user, role=role_a)
        UserRoleFactory(user=user, role=role_b)

        user.refresh_from_db()
        codes = list(user.user_permissions.values_list("codename", flat=True))

        assert "perm_role_a_multi" in codes
        assert "perm_role_b_multi" in codes
        assert "perm_shared_multi" in codes
        # Sem duplicidade
        assert codes.count("perm_shared_multi") == 1

    def test_usuario_sem_role_permissions_vazias(self):
        """Cenário-base: usuário sem role, conjunto vazio."""
        user = UserFactory()
        assert user.user_permissions.count() == 0

    def test_role_sem_permissoes_conjunto_vazio(self):
        """Cenário-base: role sem permissões, conjunto final vazio."""
        role = RoleFactory()
        role.group.permissions.clear()

        ur = UserRoleFactory(role=role)
        assert ur.user.user_permissions.count() == 0


@pytest.mark.django_db
class TestUserPermissionOverrideFactory:
    def test_cria_override_grant(self):
        ov = UserPermissionOverrideFactory(mode="grant")
        assert isinstance(ov, UserPermissionOverride)
        assert ov.mode == "grant"

    def test_cria_override_revoke(self):
        ov = UserPermissionOverrideFactory(mode="revoke")
        assert ov.mode == "revoke"

    def test_grant_materializa_permission_extra(self):
        """
        Cenário-base: override positivo (grant).
        Permissão extra deve ser materializada mesmo sem role.
        """
        user = UserFactory()
        perm = PermissionFactory(codename="extra_grant_perm")

        UserPermissionOverrideFactory(user=user, permission=perm, mode="grant")

        user.refresh_from_db()
        codes = list(user.user_permissions.values_list("codename", flat=True))
        assert "extra_grant_perm" in codes

    def test_revoke_remove_permissao_herdada(self):
        """
        Cenário-base: override negativo (revoke).
        Permissão herdada deve ser removida do conjunto.
        """
        perm = PermissionFactory(codename="herdada_revogada_perm")
        role = RoleFactory()
        role.group.permissions.add(perm)

        ur = UserRoleFactory(role=role)
        user = ur.user

        # Confirma que herdou antes do revoke
        user.refresh_from_db()
        assert "herdada_revogada_perm" in [
            p.codename for p in user.user_permissions.all()
        ]

        # Aplica o revoke
        UserPermissionOverrideFactory(user=user, permission=perm, mode="revoke")

        user.refresh_from_db()
        codes = list(user.user_permissions.values_list("codename", flat=True))
        assert "herdada_revogada_perm" not in codes

    def test_nao_popula_auth_user_groups(self):
        """ADR-PERM-01: override nunca adiciona user a auth_user_groups."""
        ov = UserPermissionOverrideFactory()
        assert ov.user.groups.count() == 0

    def test_get_or_create_idempotente(self):
        user = UserFactory()
        perm = PermissionFactory(codename="idempotent_override_perm")
        ov1 = UserPermissionOverrideFactory(user=user, permission=perm)
        ov2 = UserPermissionOverrideFactory(user=user, permission=perm)
        assert ov1.pk == ov2.pk
