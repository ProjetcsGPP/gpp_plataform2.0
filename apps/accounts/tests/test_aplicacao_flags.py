"""
Testes para os flags isappbloqueada e isappproductionready do model Aplicacao.

Cobre:
  - Rejeição de app bloqueada no UserCreateWithRoleSerializer (400)
  - Rejeição de app não pronta para produção no UserCreateWithRoleSerializer (400)
  - Aceitação de app válida (não bloqueada + pronta) no serializer
  - AplicacaoSerializer expõe os três flags
  - PORTAL_ADMIN vê todas as apps inclusive bloqueadas (get_queryset)
  - Usuário comum só vê apps com UserRole, não bloqueadas e prontas
"""
import pytest
from django.contrib.auth.models import User
from model_bakery import baker
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.accounts.serializers import AplicacaoSerializer, UserCreateWithRoleSerializer
from apps.accounts.views import AplicacaoViewSet


@pytest.mark.django_db
class TestAplicacaoFlags:
    """Testes de comportamento dos flags de estado da Aplicacao."""

    # ── helpers ──────────────────────────────────────────────────────────────

    def _base_payload(self, aplicacao, role):
        """Payload mínimo válido para UserCreateWithRoleSerializer."""
        return {
            "username": "novo_usuario_test",
            "email": "novo@test.com",
            "password": "SenhaForte@2024!",
            "name": "Novo Usuário",
            "orgao": "SEDU",
            "aplicacao_id": aplicacao.pk,
            "role_id": role.pk,
        }

    def _make_admin_request(self, admin_user):
        """Cria request autenticada com is_portal_admin=True."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = admin_user
        request.is_portal_admin = True
        return request

    def _make_regular_request(self, user):
        """Cria request autenticada como usuário comum."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user
        request.is_portal_admin = False
        return request

    # ── Serializer: rejeição de apps inválidas ────────────────────────────────

    def test_blocked_app_rejected_in_create_with_role_serializer(self):
        """
        App com isappbloqueada=True não deve aparecer no queryset do
        PrimaryKeyRelatedField — serializer deve rejeitar com ValidationError.
        """
        app = baker.make(
            Aplicacao,
            isappbloqueada=True,
            isappproductionready=True,
            isshowinportal=False,
        )
        role = baker.make(Role, aplicacao=app)
        admin = baker.make(User, is_superuser=True)

        serializer = UserCreateWithRoleSerializer(
            data=self._base_payload(app, role),
            context={"request": self._make_admin_request(admin)},
        )
        assert not serializer.is_valid(), "Deveria rejeitar app bloqueada"
        assert "aplicacao_id" in serializer.errors

    def test_not_production_ready_app_rejected_in_create_with_role_serializer(self):
        """
        App com isappproductionready=False não deve ser aceita mesmo
        se não estiver bloqueada.
        """
        app = baker.make(
            Aplicacao,
            isappbloqueada=False,
            isappproductionready=False,
            isshowinportal=False,
        )
        role = baker.make(Role, aplicacao=app)
        admin = baker.make(User, is_superuser=True)

        serializer = UserCreateWithRoleSerializer(
            data=self._base_payload(app, role),
            context={"request": self._make_admin_request(admin)},
        )
        assert not serializer.is_valid(), "Deveria rejeitar app não pronta para produção"
        assert "aplicacao_id" in serializer.errors

    def test_valid_app_accepted_in_create_with_role_serializer(self):
        """
        Apenas app com isappbloqueada=False E isappproductionready=True
        deve ser aceita pelo campo aplicacao_id.
        """
        app = baker.make(
            Aplicacao,
            isappbloqueada=False,
            isappproductionready=True,
            isshowinportal=False,
        )
        role = baker.make(Role, aplicacao=app)
        admin = baker.make(User, is_superuser=True)

        serializer = UserCreateWithRoleSerializer(
            data=self._base_payload(app, role),
            context={"request": self._make_admin_request(admin)},
        )
        # O campo aplicacao_id deve ser válido — outros erros (password policy,
        # FK de status) podem ocorrer dependendo do ambiente, mas o campo alvo
        # não deve constar em errors.
        serializer.is_valid()
        assert "aplicacao_id" not in serializer.errors, (
            f"App válida foi rejeitada. Erros: {serializer.errors}"
        )

    # ── Serializer: exposição de flags ────────────────────────────────────────

    def test_aplicacao_serializer_exposes_all_flags(self):
        """
        AplicacaoSerializer deve retornar isshowinportal, isappbloqueada
        e isappproductionready na resposta.
        """
        app = baker.make(
            Aplicacao,
            isshowinportal=True,
            isappbloqueada=False,
            isappproductionready=True,
        )
        data = AplicacaoSerializer(app).data
        assert "isshowinportal" in data
        assert "isappbloqueada" in data
        assert "isappproductionready" in data
        assert data["isappbloqueada"] is False
        assert data["isappproductionready"] is True

    # ── ViewSet: escopo por perfil de usuário ─────────────────────────────────

    def test_privileged_user_sees_all_apps_including_blocked(self):
        """
        PORTAL_ADMIN deve ver apps bloqueadas e não prontas no get_queryset.
        """
        baker.make(Aplicacao, isappbloqueada=True, isappproductionready=False)
        baker.make(Aplicacao, isappbloqueada=False, isappproductionready=True)
        baker.make(Aplicacao, isappbloqueada=True, isappproductionready=True)

        admin = baker.make(User, is_superuser=True)
        request = self._make_admin_request(admin)

        viewset = AplicacaoViewSet()
        viewset.request = request
        qs = viewset.get_queryset()

        # Admin deve ver todas, incluindo bloqueadas
        total = Aplicacao.objects.count()
        assert qs.count() == total

    def test_regular_user_only_sees_ready_unblocked_apps_with_role(self):
        """
        Usuário comum só vê apps onde tem UserRole, não bloqueadas e prontas.
        """
        user = baker.make(User)

        app_valida = baker.make(
            Aplicacao,
            isappbloqueada=False,
            isappproductionready=True,
        )
        app_bloqueada = baker.make(
            Aplicacao,
            isappbloqueada=True,
            isappproductionready=True,
        )
        app_nao_pronta = baker.make(
            Aplicacao,
            isappbloqueada=False,
            isappproductionready=False,
        )
        app_sem_role = baker.make(
            Aplicacao,
            isappbloqueada=False,
            isappproductionready=True,
        )

        role_valida = baker.make(Role, aplicacao=app_valida)
        role_bloqueada = baker.make(Role, aplicacao=app_bloqueada)
        role_nao_pronta = baker.make(Role, aplicacao=app_nao_pronta)

        baker.make(UserRole, user=user, aplicacao=app_valida, role=role_valida)
        baker.make(UserRole, user=user, aplicacao=app_bloqueada, role=role_bloqueada)
        baker.make(UserRole, user=user, aplicacao=app_nao_pronta, role=role_nao_pronta)
        # app_sem_role propositalmente sem UserRole

        request = self._make_regular_request(user)

        viewset = AplicacaoViewSet()
        viewset.request = request
        qs = viewset.get_queryset()

        pks = list(qs.values_list("pk", flat=True))
        assert app_valida.pk in pks, "App válida deveria aparecer"
        assert app_bloqueada.pk not in pks, "App bloqueada não deveria aparecer"
        assert app_nao_pronta.pk not in pks, "App não pronta não deveria aparecer"
        assert app_sem_role.pk not in pks, "App sem role não deveria aparecer"
