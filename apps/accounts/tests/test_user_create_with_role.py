from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
import uuid

from apps.accounts.models import (
    UserProfile,
    UserRole,
    ClassificacaoUsuario,
    StatusUsuario,
    TipoUsuario,
    Aplicacao,
    Role,
)
from apps.core.tests.utils import patch_security


class UserCreateWithRoleIntegrationTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("accounts:user-create-with-role")

        cls.status, _ = StatusUsuario.objects.get_or_create(
            idstatususuario=1, defaults={"strdescricao": "Ativo"}
        )
        cls.tipo, _ = TipoUsuario.objects.get_or_create(
            idtipousuario=1, defaults={"strdescricao": "Padrão"}
        )

        cls.classificacao_gestor = ClassificacaoUsuario.objects.create(
            idclassificacaousuario=100,
            strdescricao="Gestor",
            pode_criar_usuario=True,
            pode_editar_usuario=True,
        )

        cls.aplicacao = cls._create_aplicacao()
        cls.role = cls._create_role(cls.aplicacao)

        cls.gestor = User.objects.create_user(
            username="gestor_test",
            password="Teste@123"
        )

        UserProfile.objects.create(
            user=cls.gestor,
            name="Gestor Teste",
            orgao="SEDU",
            status_usuario=cls.status,
            tipo_usuario=cls.tipo,
            classificacao_usuario=cls.classificacao_gestor,
        )

        UserRole.objects.create(
            user=cls.gestor,
            role=cls.role,
            aplicacao=cls.aplicacao
        )

    @classmethod
    def _create_aplicacao(cls):
        """Cria Aplicacao com isappproductionready=True para passar na validação do serializer."""
        return Aplicacao.objects.create(
            codigointerno=f"APP_TEST_{uuid.uuid4().hex[:6]}",
            nomeaplicacao="App Teste",
            base_url="http://test/",
            isshowinportal=False,
            isappproductionready=True,
            isappbloqueada=False,
        )

    @classmethod
    def _create_role(cls, aplicacao):
        group = Group.objects.create(
            name=f"GROUP_ROLE_TEST_{uuid.uuid4().hex[:6]}"
        )
        content_type = ContentType.objects.get_for_model(User)
        permission = Permission.objects.get(
            codename="add_user",
            content_type=content_type
        )
        group.permissions.add(permission)
        return Role.objects.create(
            nomeperfil="Role Teste",
            codigoperfil=f"ROLE_{uuid.uuid4().hex[:6]}",
            aplicacao=aplicacao,
            group=group
        )

    def setUp(self):
        self.authenticate(self.gestor)

    def authenticate(self, user):
        self.client.force_authenticate(user=user)
        self.client.credentials(
            HTTP_X_APPLICATION=self.aplicacao.codigointerno
        )

    def _payload(self):
        unique = uuid.uuid4().hex[:6]
        return {
            "username": f"novo_usuario_{unique}",
            "email": f"novo_{unique}@test.com",
            "password": "Senha@123",
            "first_name": "Novo",
            "last_name": "Usuario",
            "name": "Novo Usuario",
            "orgao": "SEDU",
            "status_usuario": self.status.idstatususuario,
            "tipo_usuario": self.tipo.idtipousuario,
            "classificacao_usuario": self.classificacao_gestor.idclassificacaousuario,
            "aplicacao_id": self.aplicacao.idaplicacao,
            "role_id": self.role.id,
        }

    def test_create_user_with_role_full_flow(self):
        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        user = User.objects.get(id=response.data["user_id"])
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

        user_role = UserRole.objects.get(user=user)
        self.assertEqual(user_role.role, self.role)
        self.assertEqual(user_role.aplicacao, self.aplicacao)

        self.assertTrue(user.has_perm("auth.add_user"))
        self.assertIn("role", response.data)
        self.assertIn("aplicacao", response.data)
        self.assertIn("permissions_added", response.data)

    def test_fail_when_role_not_from_application(self):
        outra_app = self._create_aplicacao()
        role_invalida = self._create_role(outra_app)

        payload = self._payload()
        payload["role_id"] = role_invalida.id

        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fail_when_user_has_no_permission(self):
        classificacao_sem_perm = ClassificacaoUsuario.objects.create(
            idclassificacaousuario=200,
            strdescricao="SemPermissao",
            pode_criar_usuario=False,
            pode_editar_usuario=False,
        )
        user_sem_perm = User.objects.create_user(
            username=f"no_perm_{uuid.uuid4().hex[:6]}",
            password="123"
        )
        UserProfile.objects.create(
            user=user_sem_perm,
            name="No Perm",
            orgao="SEDU",
            status_usuario=self.status,
            tipo_usuario=self.tipo,
            classificacao_usuario=classificacao_sem_perm,
        )
        UserRole.objects.create(
            user=user_sem_perm,
            role=self.role,
            aplicacao=self.aplicacao
        )
        self.authenticate(user_sem_perm)

        patches = patch_security(user_sem_perm, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_transaction_rollback_on_failure(self):
        payload = self._payload()
        payload["username"] = ""  # força erro de validação

        patches = patch_security(self.gestor, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            response = self.client.post(self.url, payload, format="json")

        self.assertNotEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(User.objects.filter(email=payload["email"]).exists())
