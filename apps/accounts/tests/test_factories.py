"""
test_factories.py
=================

Testes de validação dos helpers de criação de objetos (factories.py)
criados na Fase 10 (Issue #23).

Verifica que:
  - Cada helper produz a instância correta no banco.
  - make_user_role e make_user_permission_override disparam sync automaticamente.
  - Nenhum helper popula auth_user_groups (ADR-PERM-01).
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
    make_permission,
    make_role,
    make_user,
    make_user_permission_override,
    make_user_role,
)


@pytest.mark.django_db
class TestMakePermission:
    def test_cria_permission(self):
        perm = make_permission()
        assert isinstance(perm, Permission)
        assert perm.pk is not None

    def test_get_or_create_idempotente(self):
        perm1 = make_permission(codename="perm_idempotente")
        perm2 = make_permission(codename="perm_idempotente")
        assert perm1.pk == perm2.pk

    def test_codenames_sequenciais_unicos(self):
        p1 = make_permission()
        p2 = make_permission()
        assert p1.codename != p2.codename


@pytest.mark.django_db
class TestMakeUser:
    def test_cria_user_ativo(self):
        user = make_user()
        assert user.pk is not None
        assert user.is_active

    def test_tem_userprofile(self):
        from apps.accounts.models import UserProfile
        user = make_user()
        assert UserProfile.objects.filter(user=user).exists()

    def test_sem_role_nao_popula_groups(self):
        """ADR-PERM-01: auth_user_groups deve permanecer vazio."""
        user = make_user()
        assert user.groups.count() == 0

    def test_sem_role_permissions_vazias(self):
        """Sem role, auth_user_user_permissions deve estar vazio."""
        user = make_user()
        assert user.user_permissions.count() == 0

    def test_username_sequencial(self):
        u1 = make_user()
        u2 = make_user()
        assert u1.username != u2.username

    def test_superuser(self):
        user = make_user(is_superuser=True)
        assert user.is_superuser


@pytest.mark.django_db
class TestMakeRole:
    def test_cria_role_com_group(self):
        role = make_role()
        assert isinstance(role, Role)
        assert role.group is not None

    def test_cria_role_com_aplicacao(self):
        role = make_role()
        assert role.aplicacao is not None

    def test_codigoperfil_sequencial(self):
        r1 = make_role()
        r2 = make_role()
        assert r1.codigoperfil != r2.codigoperfil


@pytest.mark.django_db
class TestMakeUserRole:
    def test_cria_userrole(self):
        ur = make_user_role()
        assert isinstance(ur, UserRole)
        assert ur.pk is not None

    def test_sync_materializa_permissions(self):
        """
        Cenário-base: usuário com uma role simples.
        sync_user_permissions deve materializar o conjunto base.
        """
        perm = make_permission(codename="view_userprofile_factory")
        role = make_role()
        role.group.permissions.add(perm)

        ur = make_user_role(role=role)
        ur.user.refresh_from_db()

        perm_codes = list(
            ur.user.user_permissions.values_list("codename", flat=True)
        )
        assert "view_userprofile_factory" in perm_codes

    def test_nao_popula_auth_user_groups(self):
        """ADR-PERM-01: helper nunca adiciona user a auth_user_groups."""
        ur = make_user_role()
        assert ur.user.groups.count() == 0

    def test_multiplas_roles_uniao_sem_duplicidade(self):
        """
        Cenário-base: usuário com múltiplas roles.
        União correta em auth_user_user_permissions sem duplicidade.
        """
        from apps.accounts.models import Aplicacao

        perm_a = make_permission(codename="perm_role_a_multi")
        perm_b = make_permission(codename="perm_role_b_multi")
        perm_shared = make_permission(codename="perm_shared_multi")

        app_a, _ = Aplicacao.objects.get_or_create(
            codigointerno="MULTI_APP_A",
            defaults={"nomeaplicacao": "Multi App A", "isappbloqueada": False, "isappproductionready": True},
        )
        app_b, _ = Aplicacao.objects.get_or_create(
            codigointerno="MULTI_APP_B",
            defaults={"nomeaplicacao": "Multi App B", "isappbloqueada": False, "isappproductionready": True},
        )

        role_a = make_role(codigoperfil="MULTI_ROLE_A", aplicacao=app_a)
        role_a.group.permissions.set([perm_a, perm_shared])

        role_b = make_role(codigoperfil="MULTI_ROLE_B", aplicacao=app_b)
        role_b.group.permissions.set([perm_b, perm_shared])

        user = make_user()
        make_user_role(user=user, role=role_a)
        make_user_role(user=user, role=role_b)

        user.refresh_from_db()
        codes = list(user.user_permissions.values_list("codename", flat=True))

        assert "perm_role_a_multi" in codes
        assert "perm_role_b_multi" in codes
        assert "perm_shared_multi" in codes
        # Sem duplicidade
        assert codes.count("perm_shared_multi") == 1

    def test_usuario_sem_role_permissions_vazias(self):
        """Cenário-base: usuário sem role, conjunto vazio."""
        user = make_user()
        assert user.user_permissions.count() == 0

    def test_role_sem_permissoes_conjunto_vazio(self):
        """Cenário-base: role sem permissões, conjunto final vazio."""
        role = make_role()
        role.group.permissions.clear()

        ur = make_user_role(role=role)
        assert ur.user.user_permissions.count() == 0


@pytest.mark.django_db
class TestMakeUserPermissionOverride:
    def test_cria_override_grant(self):
        ov = make_user_permission_override(mode="grant")
        assert isinstance(ov, UserPermissionOverride)
        assert ov.mode == "grant"

    def test_cria_override_revoke(self):
        ov = make_user_permission_override(mode="revoke")
        assert ov.mode == "revoke"

    def test_grant_materializa_permission_extra(self):
        """
        Cenário-base: override positivo (grant).
        Permissão extra deve ser materializada mesmo sem role.
        """
        user = make_user()
        perm = make_permission(codename="extra_grant_perm")

        make_user_permission_override(user=user, permission=perm, mode="grant")

        user.refresh_from_db()
        codes = list(user.user_permissions.values_list("codename", flat=True))
        assert "extra_grant_perm" in codes

    def test_revoke_remove_permissao_herdada(self):
        """
        Cenário-base: override negativo (revoke).
        Permissão herdada deve ser removida do conjunto.
        """
        perm = make_permission(codename="herdada_revogada_perm")
        role = make_role()
        role.group.permissions.add(perm)

        ur = make_user_role(role=role)
        user = ur.user

        # Confirma que herdou antes do revoke
        user.refresh_from_db()
        assert "herdada_revogada_perm" in [
            p.codename for p in user.user_permissions.all()
        ]

        # Aplica o revoke
        make_user_permission_override(user=user, permission=perm, mode="revoke")

        user.refresh_from_db()
        codes = list(user.user_permissions.values_list("codename", flat=True))
        assert "herdada_revogada_perm" not in codes

    def test_nao_popula_auth_user_groups(self):
        """ADR-PERM-01: override nunca adiciona user a auth_user_groups."""
        ov = make_user_permission_override()
        assert ov.user.groups.count() == 0

    def test_get_or_create_idempotente(self):
        user = make_user()
        perm = make_permission(codename="idempotent_override_perm")
        ov1 = make_user_permission_override(user=user, permission=perm)
        ov2 = make_user_permission_override(user=user, permission=perm)
        assert ov1.pk == ov2.pk
