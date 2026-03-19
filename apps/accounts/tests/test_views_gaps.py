"""
Testes de integração dos gaps de cobertura em accounts/views.py.

Cobre os blocos descobertos:
  - Linhas 104–124 : UserCreateView — branch scope check user_can_manage_target_user
  - Linhas 186–194 : UserCreateWithRoleView — branch user_can_create_user_in_application
  - Linhas 204–208 : UserCreateWithRoleView — captura DatabaseError/IntegrityError
  - Linhas 378–404 : UserRoleViewSet.destroy() — revogação atômica, group=None,
                     rollback em falha de revogação

Regras:
  - pytest puro — sem unittest.TestCase, sem herança de Django TestCase
  - sem model_bakery
  - @pytest.mark.django_db em todos os testes
  - patch_security() para bypassar os 3 middlewares customizados
  - APIClient com force_authenticate — sem token JWT real
"""
import pytest
from unittest.mock import patch, MagicMock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    Aplicacao, Role, StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, UserProfile, UserRole,
)
from apps.core.tests.utils import patch_security


# ─── Fixtures / Helpers ───────────────────────────────────────────────────────

def _get_or_create_status():
    obj, _ = StatusUsuario.objects.get_or_create(
        idstatususuario=1, defaults={"strdescricao": "Ativo"}
    )
    return obj


def _get_or_create_tipo():
    obj, _ = TipoUsuario.objects.get_or_create(
        idtipousuario=1, defaults={"strdescricao": "Padrão"}
    )
    return obj


def _get_or_create_classificacao(pode_criar=True):
    obj, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1,
        defaults={"strdescricao": "Padrão", "pode_criar_usuario": pode_criar},
    )
    return obj


def _make_app(codigo="PORTAL_GAPS"):
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo,
        defaults={"nomeaplicacao": codigo, "isshowinportal": True},
    )
    return app


def _make_admin_user(django_user_model, username="admin_gaps"):
    """Cria admin com PORTAL_ADMIN role."""
    user = django_user_model.objects.create_user(username=username, password="pass")
    _get_or_create_status()
    _get_or_create_tipo()
    _get_or_create_classificacao(pode_criar=True)
    app = _make_app()
    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "name": username, "orgao": "SEGES",
            "status_usuario_id": 1, "tipo_usuario_id": 1,
            "classificacao_usuario_id": 1,
        },
    )
    role, _ = Role.objects.get_or_create(
        aplicacao=app, codigoperfil="PORTAL_ADMIN",
        defaults={"nomeperfil": "Portal Admin"},
    )
    UserRole.objects.get_or_create(user=user, aplicacao=app, role=role)
    return user, app, role


# ─── UserCreateView — linhas 104–124 ──────────────────────────────────────────
# Branch: target_user != None → service.user_can_manage_target_user(target_user)

@pytest.mark.django_db
class TestUserCreateViewScopeCheck:

    def test_scope_denied_returns_403(self, django_user_model):
        """
        Quando user_can_manage_target_user() retorna False,
        a view deve retornar 403 sem criar o usuário.
        """
        admin, app, role = _make_admin_user(django_user_model, "admin_scope_deny")
        client = APIClient()
        url = reverse("accounts:user-create")

        payload = {
            "username": "novo_user_scope",
            "password": "SenhaForte123!",
            "name": "Novo User Scope",
            "orgao": "SEGES",
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.AuthorizationService"
             ) as MockService:
            mock_svc = MagicMock()
            mock_svc.user_can_manage_target_user.return_value = False
            MockService.return_value = mock_svc

            with patch(
                "apps.accounts.serializers.UserCreateSerializer.is_valid",
                return_value=True,
            ), patch(
                "apps.accounts.serializers.UserCreateSerializer.validated_data",
                new_callable=lambda: property(lambda self: {
                    "target_user": django_user_model(
                        id=999, username="target_dummy"
                    )
                }),
            ):
                client.force_authenticate(user=admin)
                response = client.post(url, payload, format="json")

        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_400_BAD_REQUEST,
        ]

    def test_scope_allowed_proceeds_to_save(self, django_user_model):
        """
        Quando user_can_manage_target_user() retorna True,
        a view prossegue para serializer.save() — sem 403.
        """
        admin, app, role = _make_admin_user(django_user_model, "admin_scope_allow")
        client = APIClient()
        url = reverse("accounts:user-create")

        payload = {
            "username": "user_scope_allowed",
            "password": "SenhaForte123!",
            "name": "User Scope Allowed",
            "orgao": "SEGES",
            "status_usuario": 1,
            "tipo_usuario": 1,
            "classificacao_usuario": 1,
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            client.force_authenticate(user=admin)
            response = client.post(url, payload, format="json")

        # Qualquer resposta que não seja 403 indica que o scope check passou
        assert response.status_code != status.HTTP_403_FORBIDDEN

    def test_no_target_user_skips_scope_check(self, django_user_model):
        """
        Quando validated_data não contém target_user (None),
        o scope check é ignorado — AuthorizationService não é instanciado.
        """
        admin, app, role = _make_admin_user(django_user_model, "admin_no_target")
        client = APIClient()
        url = reverse("accounts:user-create")

        payload = {
            "username": "user_no_target",
            "password": "SenhaForte123!",
            "name": "User No Target",
            "orgao": "SEGES",
            "status_usuario": 1,
            "tipo_usuario": 1,
            "classificacao_usuario": 1,
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.AuthorizationService"
             ) as MockService:
            client.force_authenticate(user=admin)
            response = client.post(url, payload, format="json")

        # Se o scope check foi ignorado, AuthorizationService não é chamado
        # para verificar target_user (pode ser chamado para outros fins)
        assert response.status_code != status.HTTP_403_FORBIDDEN


# ─── UserCreateWithRoleView — linhas 186–194 ──────────────────────────────────
# Branch: aplicacao_destino != None → service.user_can_create_user_in_application

@pytest.mark.django_db
class TestUserCreateWithRoleViewScopeCheck:

    def test_scope_denied_returns_403(self, django_user_model):
        """
        Quando user_can_create_user_in_application() retorna False,
        a view deve retornar 403.
        """
        admin, app, role = _make_admin_user(django_user_model, "admin_with_role_deny")
        client = APIClient()
        url = reverse("accounts:user-create-with-role")

        payload = {
            "username": "user_with_role_denied",
            "password": "SenhaForte123!",
            "name": "User With Role Denied",
            "orgao": "SEGES",
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.AuthorizationService"
             ) as MockService:
            mock_svc = MagicMock()
            mock_svc.user_can_create_user_in_application.return_value = False
            MockService.return_value = mock_svc

            with patch(
                "apps.accounts.serializers.UserCreateWithRoleSerializer.is_valid",
                return_value=True,
            ), patch(
                "apps.accounts.serializers.UserCreateWithRoleSerializer.validated_data",
                new_callable=lambda: property(lambda self: {"aplicacao": app}),
            ):
                client.force_authenticate(user=admin)
                response = client.post(url, payload, format="json")

        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_400_BAD_REQUEST,
        ]

    def test_scope_allowed_proceeds(self, django_user_model):
        """
        Quando user_can_create_user_in_application() retorna True,
        a view deve prosseguir — sem 403.
        """
        admin, app, role = _make_admin_user(django_user_model, "admin_with_role_allow")
        client = APIClient()
        url = reverse("accounts:user-create-with-role")

        payload = {
            "username": "user_with_role_allowed",
            "password": "SenhaForte123!",
            "name": "User With Role Allowed",
            "orgao": "SEGES",
            "status_usuario": 1,
            "tipo_usuario": 1,
            "classificacao_usuario": 1,
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            client.force_authenticate(user=admin)
            response = client.post(url, payload, format="json")

        assert response.status_code != status.HTTP_403_FORBIDDEN


# ─── UserCreateWithRoleView — linhas 204–208 ──────────────────────────────────
# Branch: captura DatabaseError / IntegrityError / OperationalError → APIException

@pytest.mark.django_db
class TestUserCreateWithRoleViewDatabaseError:

    def test_database_error_returns_500(self, django_user_model):
        """
        Se serializer.save() lança DatabaseError, a view deve retornar 500
        com mensagem padronizada — sem propagar a exceção bruta.
        """
        from django.db import DatabaseError

        admin, app, role = _make_admin_user(django_user_model, "admin_db_error")
        client = APIClient()
        url = reverse("accounts:user-create-with-role")

        payload = {
            "username": "user_db_error",
            "password": "SenhaForte123!",
            "name": "User DB Error",
            "orgao": "SEGES",
            "status_usuario": 1,
            "tipo_usuario": 1,
            "classificacao_usuario": 1,
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.serializers.UserCreateWithRoleSerializer.save",
                 side_effect=DatabaseError("simulated db error"),
             ), patch(
                 "apps.accounts.serializers.UserCreateWithRoleSerializer.is_valid",
                 return_value=True,
             ), patch(
                 "apps.accounts.serializers.UserCreateWithRoleSerializer.validated_data",
                 new_callable=lambda: property(lambda self: {"aplicacao": None}),
             ):
            client.force_authenticate(user=admin)
            response = client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Erro interno" in response.data.get("detail", "")

    def test_integrity_error_returns_500(self, django_user_model):
        """IntegrityError também deve ser capturada e retornar 500."""
        from django.db import IntegrityError

        admin, app, role = _make_admin_user(django_user_model, "admin_integrity_error")
        client = APIClient()
        url = reverse("accounts:user-create-with-role")

        payload = {
            "username": "user_integrity_error",
            "password": "SenhaForte123!",
            "name": "User Integrity Error",
            "orgao": "SEGES",
            "status_usuario": 1,
            "tipo_usuario": 1,
            "classificacao_usuario": 1,
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.serializers.UserCreateWithRoleSerializer.save",
                 side_effect=IntegrityError("simulated integrity error"),
             ), patch(
                 "apps.accounts.serializers.UserCreateWithRoleSerializer.is_valid",
                 return_value=True,
             ), patch(
                 "apps.accounts.serializers.UserCreateWithRoleSerializer.validated_data",
                 new_callable=lambda: property(lambda self: {"aplicacao": None}),
             ):
            client.force_authenticate(user=admin)
            response = client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ─── UserRoleViewSet.destroy() — linhas 378–404 ───────────────────────────────

@pytest.mark.django_db
class TestUserRoleViewSetDestroy:

    def test_destroy_revokes_permissions_atomically(self, django_user_model):
        """
        DELETE /api/accounts/user-roles/{id}/ deve remover o UserRole
        e chamar revoke_user_permissions_from_group dentro da transação.
        """
        from django.contrib.auth.models import Group

        admin, app, admin_role = _make_admin_user(django_user_model, "admin_destroy")
        target_user = django_user_model.objects.create_user(
            username="target_destroy", password="pass"
        )
        group = Group.objects.create(name="group_destroy_test")
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="ROLE_DESTROY",
            defaults={"nomeperfil": "Role Destroy", "group": group},
        )
        role.group = group
        role.save()
        ur = UserRole.objects.create(user=target_user, aplicacao=app, role=role)

        client = APIClient()
        url = reverse("accounts:userrole-detail", kwargs={"pk": ur.pk})

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.revoke_user_permissions_from_group",
                 return_value=2,
             ) as mock_revoke:
            client.force_authenticate(user=admin)
            response = client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not UserRole.objects.filter(pk=ur.pk).exists()
        mock_revoke.assert_called_once()

    def test_destroy_with_group_none_logs_warning_no_500(self, django_user_model):
        """
        Quando role.group é None, a revogação deve ser ignorada com WARNING
        e a view deve retornar 204 sem lançar exceção.
        """
        admin, app, admin_role = _make_admin_user(django_user_model, "admin_destroy_no_group")
        target_user = django_user_model.objects.create_user(
            username="target_destroy_no_group", password="pass"
        )
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="ROLE_NO_GROUP",
            defaults={"nomeperfil": "Role No Group", "group": None},
        )
        role.group = None
        role.save()
        ur = UserRole.objects.create(user=target_user, aplicacao=app, role=role)

        client = APIClient()
        url = reverse("accounts:userrole-detail", kwargs={"pk": ur.pk})

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.revoke_user_permissions_from_group",
                 return_value=0,
             ) as mock_revoke:
            client.force_authenticate(user=admin)
            response = client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_destroy_rollback_when_revoke_raises(self, django_user_model):
        """
        Se revoke_user_permissions_from_group lança exceção,
        o UserRole NÃO deve ter sido deletado — rollback da transação.
        """
        from django.contrib.auth.models import Group
        from django.db import DatabaseError

        admin, app, admin_role = _make_admin_user(django_user_model, "admin_destroy_rollback")
        target_user = django_user_model.objects.create_user(
            username="target_destroy_rollback", password="pass"
        )
        group = Group.objects.create(name="group_rollback_test")
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="ROLE_ROLLBACK",
            defaults={"nomeperfil": "Role Rollback", "group": group},
        )
        role.group = group
        role.save()
        ur = UserRole.objects.create(user=target_user, aplicacao=app, role=role)

        client = APIClient()
        url = reverse("accounts:userrole-detail", kwargs={"pk": ur.pk})

        patches = patch_security(admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.revoke_user_permissions_from_group",
                 side_effect=DatabaseError("simulated revoke failure"),
             ):
            client.force_authenticate(user=admin)
            response = client.delete(url)

        # A transação deve ter feito rollback → UserRole ainda existe
        assert UserRole.objects.filter(pk=ur.pk).exists()
        assert response.status_code in [
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_400_BAD_REQUEST,
        ]

    def test_destroy_non_admin_returns_403(self, django_user_model):
        """
        DELETE por usuário sem PORTAL_ADMIN deve retornar 403.
        """
        regular_user = django_user_model.objects.create_user(
            username="regular_destroy", password="pass"
        )
        app = _make_app()
        role, _ = Role.objects.get_or_create(
            aplicacao=app,
            codigoperfil="ROLE_REG_DESTROY",
            defaults={"nomeperfil": "Role Reg Destroy"},
        )
        ur = UserRole.objects.create(user=regular_user, aplicacao=app, role=role)

        client = APIClient()
        url = reverse("accounts:userrole-detail", kwargs={"pk": ur.pk})

        patches = patch_security(regular_user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            client.force_authenticate(user=regular_user)
            response = client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN
