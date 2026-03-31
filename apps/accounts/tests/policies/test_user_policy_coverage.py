# apps/accounts/tests/policies/test_user_policy_coverage.py
"""
Testes adicionais de coverage para UserPolicy.
Cobre linhas: 45–49, 83–87, 170–174

Branches não cobertos:
  45–49: can_view_user() — usuário sem role e sem superuser → False
         (função não existe explicitamente, mas o analysis aponta
          can_create_user branch: no_classificacao → False)
  83–87: can_create_user() — gestor sem permissão na app → False
  170–174: branch is_active=False ou outro edge case de policy
"""
import pytest
from django.contrib.auth.models import User

from apps.accounts.models import ClassificacaoUsuario, UserProfile, UserRole
from apps.accounts.policies.user_policy import UserPolicy

pytestmark = pytest.mark.django_db


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_profile(user):
    return UserProfile.objects.get(user=user)


# ─── can_create_user() — linhas 45–49 ────────────────────────────────────────

class TestCanCreateUserCoverage:
    """
    Linhas 45–49: can_create_user() com usuário sem classificacao (profile sem FK)
    → classificacao=None → retorna False (branch no_classificacao).
    """

    def test_usuario_sem_classificacao_nao_pode_criar_usuario(
        self, usuario_sem_role
    ):
        """
        Usuário sem role → classificacao_usuario pk=1 (pode_criar_usuario=False)
        → UserPolicy.can_create_user() retorna False.
        """
        policy = UserPolicy(user=usuario_sem_role)
        result = policy.can_create_user()
        assert result is False

    def test_operador_sem_classificacao_criacao_nao_pode_criar(
        self, operador_acao
    ):
        """
        Operador tem classificacao_pk=1 (pode_criar_usuario=False) → False.
        """
        policy = UserPolicy(user=operador_acao)
        result = policy.can_create_user()
        assert result is False

    def test_superuser_pode_criar(
        self, superuser
    ):
        policy = UserPolicy(user=superuser)
        result = policy.can_create_user()
        assert result is True

    def test_portal_admin_pode_criar(
        self, portal_admin
    ):
        policy = UserPolicy(user=portal_admin)
        result = policy.can_create_user()
        assert result is True


# ─── can_create_user_in_application() — linhas 83–87 ─────────────────────────

class TestCanCreateUserInApplicationCoverage:
    """
    Linhas 83–87: can_create_user_in_application() com gestor que tem
    pode_criar_usuario=True mas não tem role na aplicação alvo → False.
    """

    def test_gestor_sem_role_na_app_alvo_retorna_false(
        self, gestor_pngi
    ):
        """
        gestor_pngi tem role em ACOES_PNGI; tenta criar em CARGA_ORG_LOT
        (onde não tem role) → False.
        """
        from apps.accounts.models import Aplicacao
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")

        policy = UserPolicy(user=gestor_pngi)
        result = policy.can_create_user_in_application(app_carga)
        assert result is False

    def test_gestor_com_role_na_app_alvo_retorna_true(
        self, gestor_pngi
    ):
        """
        gestor_pngi tem role em ACOES_PNGI → pode criar nessa app.
        """
        from apps.accounts.models import Aplicacao
        app_pngi = Aplicacao.objects.get(codigointerno="ACOES_PNGI")

        policy = UserPolicy(user=gestor_pngi)
        result = policy.can_create_user_in_application(app_pngi)
        assert result is True

    def test_usuario_sem_pode_criar_nao_pode_criar_em_app(
        self, operador_acao
    ):
        """
        Operador (pode_criar_usuario=False) não pode criar em nenhuma app.
        """
        from apps.accounts.models import Aplicacao
        app_pngi = Aplicacao.objects.get(codigointerno="ACOES_PNGI")

        policy = UserPolicy(user=operador_acao)
        result = policy.can_create_user_in_application(app_pngi)
        assert result is False


# ─── can_edit_target_user() / can_manage_target_user() — linhas 170–174 ──────

class TestCanManageTargetUserCoverage:
    """
    Linhas 170–174: branch onde actor não tem edit_user permission
    → can_manage_target_user() / can_edit_target_user() retornam False.
    """

    def test_operador_sem_permissao_editar_nao_pode_gerenciar_alvo(
        self, operador_acao, gestor_pngi
    ):
        """
        operador tem pode_editar_usuario=False → False independente de
        intersecção de app.
        """
        policy = UserPolicy(user=operador_acao)
        result = policy.can_manage_target_user(gestor_pngi)
        assert result is False

    def test_operador_nao_pode_editar_target_user(
        self, operador_acao, gestor_pngi
    ):
        policy = UserPolicy(user=operador_acao)
        result = policy.can_edit_target_user(gestor_pngi)
        assert result is False

    def test_gestor_com_intersecao_pode_editar_alvo(
        self, gestor_pngi, coordenador_pngi
    ):
        """
        gestor_pngi e coordenador_pngi estão na mesma app (ACOES_PNGI) →
        can_edit_target_user retorna True.
        """
        policy = UserPolicy(user=gestor_pngi)
        result = policy.can_edit_target_user(coordenador_pngi)
        assert result is True

    def test_usuario_inativo_nao_pode_gerenciar(
        self, usuario_sem_role, gestor_pngi
    ):
        """
        Linha 170–174: actor sem classificacao de edição
        → False (branch no_edit_permission).
        """
        policy = UserPolicy(user=usuario_sem_role)
        result = policy.can_manage_target_user(gestor_pngi)
        assert result is False
