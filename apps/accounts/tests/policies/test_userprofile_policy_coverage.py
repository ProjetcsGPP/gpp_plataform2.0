# apps/accounts/tests/policies/test_userprofile_policy_coverage.py
"""
Testes adicionais de coverage para UserProfilePolicy.
Cobre linhas: 221–222, 230–231, 235, 238–239, 245, 253

Esses são os branches onde usuários sem privilégio (sem portal_admin
e sem is_superuser) invocam can_change_status(), can_change_classificacao()
e can_edit_profile() → retorno False.
"""
import pytest
from django.contrib.auth.models import User

from apps.accounts.models import ClassificacaoUsuario, UserProfile, UserRole
from apps.accounts.policies import UserProfilePolicy

pytestmark = pytest.mark.django_db


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_profile(user):
    return UserProfile.objects.get(user=user)


# ─── can_change_status() ─────────────────────────────────────────────────────

class TestCanChangeStatusCoverage:
    """
    Linhas 221–222: branch where actor is NOT portal_admin and NOT superuser
    → can_change_status() retorna False.
    """

    def test_gestor_sem_privilegio_nao_pode_mudar_status(
        self, gestor_pngi
    ):
        profile = _get_profile(gestor_pngi)
        policy = UserProfilePolicy(actor=gestor_pngi, profile=profile)
        result = policy.can_change_status()
        assert result is False

    def test_operador_sem_privilegio_nao_pode_mudar_status(
        self, operador_acao
    ):
        profile = _get_profile(operador_acao)
        policy = UserProfilePolicy(actor=operador_acao, profile=profile)
        result = policy.can_change_status()
        assert result is False

    def test_usuario_sem_role_nao_pode_mudar_status(
        self, usuario_sem_role
    ):
        profile = _get_profile(usuario_sem_role)
        policy = UserProfilePolicy(actor=usuario_sem_role, profile=profile)
        result = policy.can_change_status()
        assert result is False

    def test_portal_admin_pode_mudar_status(
        self, portal_admin
    ):
        profile = _get_profile(portal_admin)
        policy = UserProfilePolicy(actor=portal_admin, profile=profile)
        result = policy.can_change_status()
        assert result is True

    def test_superuser_pode_mudar_status(
        self, db_superuser
    ):
        """
        FIX 2: a fixture `superuser` do conftest de policies é um MagicMock
        (sem DB), impossível chamar UserProfile.objects.get(user=mock).
        Usar db_superuser (fixture com User + UserProfile reais no banco).
        """
        profile = _get_profile(db_superuser)
        policy = UserProfilePolicy(actor=db_superuser, profile=profile)
        result = policy.can_change_status()
        assert result is True


# ─── can_change_classificacao() ──────────────────────────────────────────────

class TestCanChangeClassificacaoCoverage:
    """
    Linhas 230–231: branch where actor is NOT portal_admin and NOT superuser
    → can_change_classificacao() retorna False.
    """

    def test_gestor_sem_privilegio_nao_pode_mudar_classificacao(
        self, gestor_pngi
    ):
        profile = _get_profile(gestor_pngi)
        policy = UserProfilePolicy(actor=gestor_pngi, profile=profile)
        result = policy.can_change_classificacao()
        assert result is False

    def test_coordenador_sem_privilegio_nao_pode_mudar_classificacao(
        self, coordenador_pngi
    ):
        profile = _get_profile(coordenador_pngi)
        policy = UserProfilePolicy(actor=coordenador_pngi, profile=profile)
        result = policy.can_change_classificacao()
        assert result is False

    def test_portal_admin_pode_mudar_classificacao(
        self, portal_admin
    ):
        profile = _get_profile(portal_admin)
        policy = UserProfilePolicy(actor=portal_admin, profile=profile)
        result = policy.can_change_classificacao()
        assert result is True


# ─── can_edit_profile() — branches de escopo ─────────────────────────────────

class TestCanEditProfileScopeCoverage:
    """
    Linhas 235, 238–239: branch onde profile.user == request.user (auto-edição)
    mas NÃO é admin — deve retornar True (auto-edição permitida).
    Linhas 245, 253: can_edit_profile retorna False por falta de escopo
    (not _has_application_intersection).
    """

    def test_auto_edicao_sem_admin_retorna_true(
        self, gestor_pngi
    ):
        """
        Linha 235, 238–239: actor edita o PRÓPRIO profile → True
        (independente de ser admin ou não).
        """
        profile = _get_profile(gestor_pngi)
        policy = UserProfilePolicy(actor=gestor_pngi, profile=profile)
        result = policy.can_edit_profile()
        assert result is True

    def test_gestor_sem_intersecao_de_app_nao_pode_editar_profile_alheio(
        self, gestor_pngi, usuario_sem_role
    ):
        """
        Linha 245, 253: gestor tenta editar profile de usuário sem
        intersecção de aplicação → False.
        """
        # usuario_sem_role não tem UserRole, portanto não há intersecção
        profile_alvo = _get_profile(usuario_sem_role)
        # Usa gestor_pngi (classificacao com pode_editar_usuario=True) como actor
        policy = UserProfilePolicy(actor=gestor_pngi, profile=profile_alvo)
        result = policy.can_edit_profile()
        # Sem intersecção de app → False
        assert result is False

    def test_usuario_sem_pode_editar_nao_pode_editar_profile_alheio(
        self, coordenador_pngi, gestor_pngi
    ):
        """
        Linha 238–239: actor sem pode_editar_usuario=True não pode editar
        profile alheio → False.
        """
        profile_alvo = _get_profile(gestor_pngi)
        # coordenador tem classificacao_pk=1 (pode_editar_usuario=False)
        policy = UserProfilePolicy(actor=coordenador_pngi, profile=profile_alvo)
        result = policy.can_edit_profile()
        assert result is False
