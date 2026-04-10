"""
test_serializers_coverage.py
============================
Cobre as linhas de apps/accounts/serializers.py identificadas como
não cobertas na Issue #23 (Fase 10).

Linhas-alvo por serializer:
  - UserCreateSerializer      : 74 (validate_email dup), 191 (validate_password),
                                282 (validate FK lookup miss), 368-375 (create/to_repr)
  - UserRoleSerializer        : validate() role not in app
  - UserCreateWithRoleSerializer: 488-511 (validate + create com defaults),
                                  532-537 (validate role/app mismatch)
  - UserPermissionOverrideSerializer: 552-553 (conflict grant/revoke),
                                       _extract_audit_fields, create, update
  - MePermissionSerializer    : 677 (get_granted sem group)
  - MeSerializer              : campos derived (name, orgao, is_portal_admin)

Todos usam banco real (pytest.mark.django_db) e as factories make_*.
"""
import pytest
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIRequestFactory

from apps.accounts.models import (
    Aplicacao,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserPermissionOverride,
    UserProfile,
    UserRole,
)
from apps.accounts.serializers import (
    MePermissionSerializer,
    MeSerializer,
    UserCreateSerializer,
    UserCreateWithRoleSerializer,
    UserPermissionOverrideSerializer,
    UserRoleSerializer,
)
from apps.accounts.tests.factories import (
    make_permission,
    make_role,
    make_user,
    make_user_permission_override,
    make_user_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(user=None):
    factory = APIRequestFactory()
    request = factory.get("/")
    if user is not None:
        request.user = user
    return request


# ---------------------------------------------------------------------------
# UserCreateSerializer
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserCreateSerializer:

    def test_validate_username_duplicado(self):
        """linha 74 — username já existente levanta ValidationError."""
        make_user(username="joao_dup")
        s = UserCreateSerializer(data={
            "username": "joao_dup",
            "email": "novo@test.br",
            "password": "TestPass@2026",
            "name": "Joao",
            "orgao": "SEGER",
        })
        assert not s.is_valid()
        assert "username" in s.errors

    def test_validate_email_duplicado(self):
        """linha 191 — e-mail já existente levanta ValidationError."""
        make_user(username="maria_orig", email="maria@test.br")
        s = UserCreateSerializer(data={
            "username": "maria_nova",
            "email": "maria@test.br",
            "password": "TestPass@2026",
            "name": "Maria",
            "orgao": "SEGER",
        })
        assert not s.is_valid()
        assert "email" in s.errors

    def test_validate_password_fraca(self):
        """linha 191 — senha fraca lança ValidationError via validate_password."""
        s = UserCreateSerializer(data={
            "username": "user_fraco",
            "email": "fraco@test.br",
            "password": "123",
            "name": "Fraco",
            "orgao": "SEGER",
        })
        assert not s.is_valid()
        assert "password" in s.errors

    def test_validate_fk_status_inexistente(self):
        """linha 282 — FK status_usuario inexistente levanta ValidationError."""
        s = UserCreateSerializer(data={
            "username": "fk_test",
            "email": "fk@test.br",
            "password": "TestPass@2026",
            "name": "FK Test",
            "orgao": "SEGER",
            "status_usuario": 9999,
        })
        assert not s.is_valid()
        assert "status_usuario" in s.errors

    def test_create_e_to_representation(self):
        """linhas 368-375 — create() retorna UserProfile; to_representation() serializa."""
        admin = make_user(username="admin_creator", is_superuser=True)
        request = _make_request(user=admin)
        s = UserCreateSerializer(
            data={
                "username": "novo_criado",
                "email": "novo_criado@test.br",
                "password": "TestPass@2026",
                "name": "Novo Criado",
                "orgao": "SEGER",
            },
            context={"request": request},
        )
        assert s.is_valid(), s.errors
        profile = s.save()
        repr_data = s.to_representation(profile)
        assert repr_data["username"] == "novo_criado"
        assert repr_data["orgao"] == "SEGER"


# ---------------------------------------------------------------------------
# UserRoleSerializer
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserRoleSerializer:

    def test_validate_role_nao_pertence_a_app(self):
        """linha 368 — role de outra aplicação levanta ValidationError."""
        user = make_user()
        role_a = make_role()
        role_b = make_role()  # role_b pertence a outra aplicacao
        s = UserRoleSerializer(data={
            "user": user.pk,
            "aplicacao": role_a.aplicacao.pk,
            "role": role_b.pk,  # role de outra app
        })
        assert not s.is_valid()
        assert "role" in s.errors

    def test_validate_unicidade_user_aplicacao(self):
        """valida que (user, aplicacao) duplicado levanta erro."""
        ur = make_user_role()
        s = UserRoleSerializer(data={
            "user": ur.user.pk,
            "aplicacao": ur.aplicacao.pk,
            "role": ur.role.pk,
        })
        assert not s.is_valid()
        assert "non_field_errors" in s.errors


# ---------------------------------------------------------------------------
# UserCreateWithRoleSerializer
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserCreateWithRoleSerializer:

    def _base_data(self, aplicacao, role):
        return {
            "username": "cwrole_user",
            "email": "cwrole@test.br",
            "password": "TestPass@2026",
            "name": "CW Role",
            "orgao": "SEGER",
            "aplicacao_id": aplicacao.pk,
            "role_id": role.pk,
        }

    def test_validate_role_app_mismatch(self):
        """linhas 532-537 — role não pertence à aplicação → ValidationError."""
        role_a = make_role()
        role_b = make_role()  # role de outra app
        admin = make_user(username="admin_cwr", is_superuser=True)
        request = _make_request(user=admin)
        s = UserCreateWithRoleSerializer(
            data={
                "username": "mismatch_user",
                "email": "mismatch@test.br",
                "password": "TestPass@2026",
                "name": "Mismatch",
                "orgao": "SEGER",
                "aplicacao_id": role_a.aplicacao.pk,
                "role_id": role_b.pk,
            },
            context={"request": request},
        )
        assert not s.is_valid()
        assert "role_id" in s.errors

    def test_create_com_defaults_retorna_dict(self):
        """linhas 488-511 — create() retorna dicionário com permissions_added."""
        role = make_role()
        role.aplicacao.isappbloqueada = False
        role.aplicacao.isappproductionready = True
        role.aplicacao.save()

        admin = make_user(username="admin_cwr2", is_superuser=True)
        request = _make_request(user=admin)
        s = UserCreateWithRoleSerializer(
            data=self._base_data(role.aplicacao, role),
            context={"request": request},
        )
        assert s.is_valid(), s.errors
        result = s.save()
        assert "user_id" in result
        assert "permissions_added" in result
        assert isinstance(result["permissions_added"], int)

    def test_validate_username_duplicado(self):
        """validate_username() levanta ValidationError para username existente."""
        make_user(username="existente_cwr")
        role = make_role()
        role.aplicacao.isappbloqueada = False
        role.aplicacao.isappproductionready = True
        role.aplicacao.save()
        admin = make_user(username="admin_cwr3", is_superuser=True)
        request = _make_request(user=admin)
        s = UserCreateWithRoleSerializer(
            data={
                "username": "existente_cwr",
                "email": "novo_email@test.br",
                "password": "TestPass@2026",
                "name": "Existente",
                "orgao": "SEGER",
                "aplicacao_id": role.aplicacao.pk,
                "role_id": role.pk,
            },
            context={"request": request},
        )
        assert not s.is_valid()
        assert "username" in s.errors

    def test_validate_email_duplicado(self):
        """validate_email() levanta ValidationError para e-mail existente."""
        make_user(username="orig_email_cwr", email="dup_cwr@test.br")
        role = make_role()
        role.aplicacao.isappbloqueada = False
        role.aplicacao.isappproductionready = True
        role.aplicacao.save()
        admin = make_user(username="admin_cwr4", is_superuser=True)
        request = _make_request(user=admin)
        s = UserCreateWithRoleSerializer(
            data={
                "username": "novo_email_cwr",
                "email": "dup_cwr@test.br",
                "password": "TestPass@2026",
                "name": "Dup Email",
                "orgao": "SEGER",
                "aplicacao_id": role.aplicacao.pk,
                "role_id": role.pk,
            },
            context={"request": request},
        )
        assert not s.is_valid()
        assert "email" in s.errors


# ---------------------------------------------------------------------------
# UserPermissionOverrideSerializer
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserPermissionOverrideSerializer:

    def test_validate_conflito_grant_revoke(self):
        """linhas 552-553 — grant existente impede revoke do mesmo par."""
        user = make_user()
        perm = make_permission()
        # cria override grant existente
        UserPermissionOverride.objects.create(
            user=user,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
        )
        s = UserPermissionOverrideSerializer(data={
            "user": user.pk,
            "permission": perm.pk,
            "mode": UserPermissionOverride.MODE_REVOKE,
        })
        assert not s.is_valid()
        assert "mode" in s.errors

    def test_validate_conflito_revoke_grant(self):
        """revoke existente impede grant do mesmo par."""
        user = make_user()
        perm = make_permission()
        UserPermissionOverride.objects.create(
            user=user,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
        )
        s = UserPermissionOverrideSerializer(data={
            "user": user.pk,
            "permission": perm.pk,
            "mode": UserPermissionOverride.MODE_GRANT,
        })
        assert not s.is_valid()
        assert "mode" in s.errors

    def test_validate_sem_conflito_cria_ok(self):
        """sem conflito o serializer é válido."""
        user = make_user()
        perm = make_permission()
        s = UserPermissionOverrideSerializer(data={
            "user": user.pk,
            "permission": perm.pk,
            "mode": UserPermissionOverride.MODE_GRANT,
            "source": "manual",
            "reason": "teste",
        })
        assert s.is_valid(), s.errors

    def test_create_com_audit_fields_nome_descartados(self):
        """create() descarta created_by_name/updated_by_name do AuditableMixin."""
        user = make_user()
        perm = make_permission()
        s = UserPermissionOverrideSerializer(data={
            "user": user.pk,
            "permission": perm.pk,
            "mode": UserPermissionOverride.MODE_GRANT,
        })
        assert s.is_valid(), s.errors
        # Injecta campos de auditoria como se fossem do AuditableMixin
        s.validated_data["created_by_name"] = "usuario_nome"
        s.validated_data["updated_by_name"] = "usuario_nome"
        s.validated_data["created_by_id"] = user.pk
        s.validated_data["updated_by_id"] = user.pk
        override = s.save()
        assert override.pk is not None
        assert override.created_by == user

    def test_update_com_audit_fields(self):
        """update() descarta _name e mapeia _id para FK."""
        user = make_user()
        perm = make_permission()
        override = UserPermissionOverride.objects.create(
            user=user,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
        )
        s = UserPermissionOverrideSerializer(
            instance=override,
            data={
                "user": user.pk,
                "permission": perm.pk,
                "mode": UserPermissionOverride.MODE_GRANT,
                "reason": "atualizado",
            },
            partial=True,
        )
        assert s.is_valid(), s.errors
        s.validated_data["updated_by_name"] = "nome_qualquer"
        s.validated_data["updated_by_id"] = user.pk
        updated = s.save()
        assert updated.reason == "atualizado"
        assert updated.updated_by == user

    def test_validate_update_sem_conflito_exclui_instance(self):
        """validate() com instance exclui o próprio override do conflict check."""
        user = make_user()
        perm = make_permission()
        override = UserPermissionOverride.objects.create(
            user=user,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
        )
        # Atualizar com o mesmo modo não deve gerar conflito
        s = UserPermissionOverrideSerializer(
            instance=override,
            data={
                "user": user.pk,
                "permission": perm.pk,
                "mode": UserPermissionOverride.MODE_GRANT,
                "reason": "reconfirmado",
            },
        )
        assert s.is_valid(), s.errors


# ---------------------------------------------------------------------------
# MePermissionSerializer
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMePermissionSerializer:

    def test_get_granted_sem_group(self):
        """linha 677 — role sem group retorna todas as user_permissions diretas."""
        user = make_user()
        perm = make_permission(codename="solo_perm")
        user.user_permissions.add(perm)

        # Role sem group
        role = make_role()
        role.group = None
        role.save()

        s = MePermissionSerializer({"role": role, "user": user})
        data = s.data
        assert data["role"] == role.codigoperfil
        assert "solo_perm" in data["granted"]

    def test_get_granted_com_group_e_override_grant(self):
        """get_granted() inclui permissões extras de grant override fora do grupo."""
        role = make_role()
        perm_base = make_permission(codename="perm_base_grp")
        role.group.permissions.add(perm_base)

        user = make_user()
        ur = make_user_role(user=user, role=role)

        perm_extra = make_permission(codename="perm_extra_grant")
        make_user_permission_override(user=user, permission=perm_extra, mode="grant")

        s = MePermissionSerializer({"role": role, "user": user})
        data = s.data
        assert "perm_base_grp" in data["granted"]
        assert "perm_extra_grant" in data["granted"]

    def test_get_granted_revoke_remove_do_resultado(self):
        """get_granted() não retorna permissão com override revoke."""
        role = make_role()
        perm = make_permission(codename="perm_revogavel")
        role.group.permissions.add(perm)

        user = make_user()
        make_user_role(user=user, role=role)
        make_user_permission_override(user=user, permission=perm, mode="revoke")

        s = MePermissionSerializer({"role": role, "user": user})
        assert "perm_revogavel" not in s.data["granted"]

    def test_get_role_retorna_codigoperfil(self):
        role = make_role()
        user = make_user()
        s = MePermissionSerializer({"role": role, "user": user})
        assert s.data["role"] == role.codigoperfil


# ---------------------------------------------------------------------------
# MeSerializer
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMeSerializer:

    def test_get_name_com_profile(self):
        user = make_user(username="me_test_user")
        profile = UserProfile.objects.get(user=user)
        ur_qs = UserRole.objects.filter(user=user)
        s = MeSerializer({"user": user, "profile": profile, "user_roles": ur_qs})
        assert s.data["name"] == profile.name

    def test_get_name_sem_profile(self):
        user = make_user(username="me_noprofile")
        s = MeSerializer({"user": user, "profile": None, "user_roles": []})
        assert s.data["name"] is None

    def test_get_is_portal_admin_true(self):
        user = make_user(username="admin_me")
        role_admin = Role.objects.get(pk=1)  # PORTAL_ADMIN from conftest
        make_user_role(user=user, role=role_admin)
        profile = UserProfile.objects.get(user=user)
        ur_qs = UserRole.objects.filter(user=user)
        s = MeSerializer({"user": user, "profile": profile, "user_roles": ur_qs})
        assert s.data["is_portal_admin"] is True

    def test_get_is_portal_admin_false(self):
        user = make_user(username="noadmin_me")
        profile = UserProfile.objects.get(user=user)
        s = MeSerializer({"user": user, "profile": profile, "user_roles": []})
        assert s.data["is_portal_admin"] is False

    def test_get_orgao_com_profile(self):
        user = make_user(username="orgao_me")
        profile = UserProfile.objects.get(user=user)
        s = MeSerializer({"user": user, "profile": profile, "user_roles": []})
        assert s.data["orgao"] == profile.orgao

    def test_get_status_usuario_id_com_profile(self):
        user = make_user(username="status_me")
        profile = UserProfile.objects.get(user=user)
        s = MeSerializer({"user": user, "profile": profile, "user_roles": []})
        assert s.data["status_usuario_id"] == profile.status_usuario_id
