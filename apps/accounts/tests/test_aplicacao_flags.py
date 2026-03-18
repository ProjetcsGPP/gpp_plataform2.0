"""
GPP Plataform 2.0 — Accounts Tests: Aplicacao Flags (POLICY-EXPANSION)

Cobre os 6 cenários de validação dos flags isappbloqueada e isappproductionready.

Padrão do projeto: django.test.TestCase + fixture JSON declarativa.
Sem dependência de model_bakery.

Fixture: apps/accounts/fixtures/policy_expansion_flags.json
  Registros utilizados:
    aplicacao  pk=10  APP_BLOQUEADA    (bloqueada=True,  pronta=True)   → rejeitada
    aplicacao  pk=11  APP_NAO_PRONTA   (bloqueada=False, pronta=False)  → rejeitada
    aplicacao  pk=12  APP_VALIDA       (bloqueada=False, pronta=True)   → aceita
    aplicacao  pk=13  APP_PORTAL_FLAG  (isshowinportal=True, válida)   → admin vê
    aplicacao  pk=14  APP_SEM_ROLE     (válida, sem UserRole do user)   → user comum não vê
    role       pk=10  ROLE_BLOQUEADA   → pertence à pk=10
    role       pk=11  ROLE_NAO_PRONTA  → pertence à pk=11
    role       pk=12  ROLE_VALIDA      → pertence à pk=12
    statususuario / tipousuario / classificacaousuario pk=10

Cenários:
  T-F01  App bloqueada rejeitada em UserCreateWithRoleSerializer → 400
  T-F02  App não pronta rejeitada em UserCreateWithRoleSerializer → 400
  T-F03  App válida aceita em UserCreateWithRoleSerializer (aplicacao_id sem erro)
  T-F04  AplicacaoSerializer expõe isshowinportal, isappbloqueada, isappproductionready
  T-F05  PORTAL_ADMIN vê todas as apps incluindo bloqueadas no get_queryset
  T-F06  Usuário comum só vê apps com UserRole, não bloqueadas e prontas
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.accounts.serializers import AplicacaoSerializer, UserCreateWithRoleSerializer
from apps.accounts.views import AplicacaoViewSet


class TestAplicacaoFlags(TestCase):
    """
    Testes de comportamento dos flags de estado da Aplicacao.
    Usa fixture declarativa — sem model_bakery.
    """
    fixtures = ["policy_expansion_flags"]

    @classmethod
    def setUpTestData(cls):
        # Apps carregadas da fixture
        cls.app_bloqueada   = Aplicacao.objects.get(pk=10)
        cls.app_nao_pronta  = Aplicacao.objects.get(pk=11)
        cls.app_valida      = Aplicacao.objects.get(pk=12)
        cls.app_portal_flag = Aplicacao.objects.get(pk=13)
        cls.app_sem_role    = Aplicacao.objects.get(pk=14)

        # Roles carregadas da fixture
        cls.role_bloqueada  = Role.objects.get(pk=10)
        cls.role_nao_pronta = Role.objects.get(pk=11)
        cls.role_valida     = Role.objects.get(pk=12)

        # Usuários de teste (criados em memória, não na fixture)
        cls.admin_user = User.objects.create_user(
            username="flags_admin", password="Admin@Flags2026!"
        )
        cls.common_user = User.objects.create_user(
            username="flags_common", password="Common@Flags2026!"
        )

        # UserRole: common_user tem vínculo apenas na app_valida (pk=12)
        # e na app_bloqueada (pk=10) e app_nao_pronta (pk=11),
        # mas estas últimas devem ser filtradas pelo get_queryset.
        # app_sem_role (pk=14) propositalmente sem UserRole.
        UserRole.objects.create(
            user=cls.common_user,
            aplicacao=cls.app_valida,
            role=cls.role_valida,
        )
        UserRole.objects.create(
            user=cls.common_user,
            aplicacao=cls.app_bloqueada,
            role=cls.role_bloqueada,
        )
        UserRole.objects.create(
            user=cls.common_user,
            aplicacao=cls.app_nao_pronta,
            role=cls.role_nao_pronta,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _base_payload(self, aplicacao, role):
        """Payload mínimo para UserCreateWithRoleSerializer."""
        return {
            "username": "novo_flags_test",
            "email": "novo_flags@test.com",
            "password": "SenhaForte@2026!",
            "name": "Novo Flags",
            "orgao": "SEDU",
            "aplicacao_id": aplicacao.pk,
            "role_id": role.pk,
        }

    def _admin_request(self):
        """Request com is_portal_admin=True para AplicacaoViewSet.get_queryset()."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = self.admin_user
        request.is_portal_admin = True
        return request

    def _common_request(self):
        """Request de usuário comum (is_portal_admin=False)."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = self.common_user
        request.is_portal_admin = False
        return request

    # ── T-F01: app bloqueada rejeitada no serializer ────────────────

    def test_F01_blocked_app_rejected_in_create_with_role_serializer(self):
        """
        T-F01: app com isappbloqueada=True não aparece no queryset do
        PrimaryKeyRelatedField → serializer rejeita com 'aplicacao_id' em errors.
        """
        serializer = UserCreateWithRoleSerializer(
            data=self._base_payload(self.app_bloqueada, self.role_bloqueada),
            context={"request": self._admin_request()},
        )
        self.assertFalse(serializer.is_valid(), "Deveria rejeitar app bloqueada")
        self.assertIn("aplicacao_id", serializer.errors)

    # ── T-F02: app não pronta rejeitada no serializer ──────────────

    def test_F02_not_production_ready_app_rejected_in_create_with_role_serializer(self):
        """
        T-F02: app com isappproductionready=False não é aceita mesmo não bloqueada.
        """
        serializer = UserCreateWithRoleSerializer(
            data=self._base_payload(self.app_nao_pronta, self.role_nao_pronta),
            context={"request": self._admin_request()},
        )
        self.assertFalse(serializer.is_valid(), "Deveria rejeitar app não pronta")
        self.assertIn("aplicacao_id", serializer.errors)

    # ── T-F03: app válida aceita no serializer ────────────────────

    def test_F03_valid_app_accepted_in_create_with_role_serializer(self):
        """
        T-F03: app com isappbloqueada=False E isappproductionready=True
        deve passar a validação do campo aplicacao_id.
        """
        serializer = UserCreateWithRoleSerializer(
            data=self._base_payload(self.app_valida, self.role_valida),
            context={"request": self._admin_request()},
        )
        serializer.is_valid()
        self.assertNotIn(
            "aplicacao_id", serializer.errors,
            f"App válida foi rejeitada. Erros: {serializer.errors}"
        )

    # ── T-F04: serializer expõe os três flags ─────────────────────

    def test_F04_aplicacao_serializer_exposes_all_flags(self):
        """
        T-F04: AplicacaoSerializer deve retornar isshowinportal,
        isappbloqueada e isappproductionready com os valores corretos.
        """
        data = AplicacaoSerializer(self.app_valida).data
        self.assertIn("isshowinportal", data)
        self.assertIn("isappbloqueada", data)
        self.assertIn("isappproductionready", data)
        self.assertFalse(data["isshowinportal"])
        self.assertFalse(data["isappbloqueada"])
        self.assertTrue(data["isappproductionready"])

    # ── T-F05: admin vê todas as apps inclusive bloqueadas ────────

    def test_F05_privileged_user_sees_all_apps_including_blocked(self):
        """
        T-F05: PORTAL_ADMIN (is_portal_admin=True ou is_superuser) deve
        receber todas as apps no get_queryset, sem filtro de flags.
        """
        viewset = AplicacaoViewSet()
        viewset.request = self._admin_request()
        qs = viewset.get_queryset()

        total = Aplicacao.objects.count()
        self.assertEqual(
            qs.count(), total,
            f"Admin deveria ver {total} apps, mas viu {qs.count()}"
        )

    # ── T-F06: usuário comum só vê apps válidas com role ────────

    def test_F06_regular_user_only_sees_ready_unblocked_apps_with_role(self):
        """
        T-F06: usuário comum só vê apps onde tem UserRole,
        não bloqueadas (isappbloqueada=False) e prontas (isappproductionready=True).
        """
        viewset = AplicacaoViewSet()
        viewset.request = self._common_request()
        qs = viewset.get_queryset()
        pks = list(qs.values_list("pk", flat=True))

        self.assertIn(
            self.app_valida.pk, pks,
            "App válida com UserRole deveria aparecer"
        )
        self.assertNotIn(
            self.app_bloqueada.pk, pks,
            "App bloqueada não deveria aparecer"
        )
        self.assertNotIn(
            self.app_nao_pronta.pk, pks,
            "App não pronta não deveria aparecer"
        )
        self.assertNotIn(
            self.app_sem_role.pk, pks,
            "App sem UserRole não deveria aparecer"
        )
        self.assertNotIn(
            self.app_portal_flag.pk, pks,
            "App sem UserRole (portal flag) não deveria aparecer"
        )
