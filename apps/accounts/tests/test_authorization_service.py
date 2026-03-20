# apps/accounts/tests/test_authorization_service.py
"""
Testes do AuthorizationService com banco de dados real.

Nao usa transaction=True: savepoints sao suficientes.
Os helpers _make_user_with_classificacao criam dados via get_or_create,
portanto funcionam tanto com quanto sem fixtures pre-carregadas.
"""
import pytest
from django.contrib.auth.models import User

from apps.accounts.models import (
    Aplicacao,
    ClassificacaoUsuario,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
    Role,
)
from apps.accounts.services.authorization_service import AuthorizationService

pytestmark = pytest.mark.django_db


def _make_user_with_classificacao(username, pode_criar=False, pode_editar=False):
    """Cria usuario com ClassificacaoUsuario customizada usando get_or_create."""
    from apps.accounts.tests.conftest import _get_status_usuario, _get_tipo_usuario
    # pk 90+ para nao colidir com dados do initial_data
    pk = 90 + (abs(hash(username)) % 9)
    classificacao, _ = ClassificacaoUsuario.objects.get_or_create(
        pk=pk,
        defaults={
            "strdescricao": f"Classificacao {username}",
            "pode_criar_usuario": pode_criar,
            "pode_editar_usuario": pode_editar,
        },
    )
    user = User.objects.create_user(username=username, password="pass")
    UserProfile.objects.create(
        user=user,
        name=username,
        status_usuario=_get_status_usuario(),
        tipo_usuario=_get_tipo_usuario(),
        classificacao_usuario=classificacao,
    )
    return user


# --- can_create_user ---------------------------------------------------------

class TestCanCreateUser:

    def test_classificacao_sem_permissao_retorna_false(self, gestor_pngi):
        """ClassificacaoUsuario pk=1 tem pode_criar_usuario=False."""
        service = AuthorizationService(gestor_pngi)
        assert service.can_create_user() is False

    def test_classificacao_com_permissao_retorna_true(self, db):
        user = _make_user_with_classificacao("criador_svc", pode_criar=True)
        service = AuthorizationService(user)
        assert service.can_create_user() is True

    def test_superuser_pode_criar(self, superuser):
        service = AuthorizationService(superuser)
        assert service.can_create_user() is True


# --- can_edit_user -----------------------------------------------------------

class TestCanEditUser:

    def test_classificacao_sem_permissao_editar_retorna_false(self, gestor_pngi):
        service = AuthorizationService(gestor_pngi)
        assert service.can_edit_user() is False

    def test_classificacao_com_permissao_editar_retorna_true(self, db):
        user = _make_user_with_classificacao("editor_svc", pode_editar=True)
        service = AuthorizationService(user)
        assert service.can_edit_user() is True

    def test_superuser_pode_editar(self, superuser):
        service = AuthorizationService(superuser)
        assert service.can_edit_user() is True


# --- user_can_manage_target_user ---------------------------------------------

class TestUserCanManageTargetUser:

    def test_usuarios_com_app_em_comum(self, gestor_pngi, operador_acao):
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_manage_target_user(operador_acao) is True

    def test_usuarios_sem_app_em_comum(self, gestor_pngi, gestor_carga):
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_manage_target_user(gestor_carga) is False

    def test_superuser_pode_gerenciar_qualquer_usuario(
        self, superuser, gestor_pngi
    ):
        service = AuthorizationService(superuser)
        assert service.user_can_manage_target_user(gestor_pngi) is True

    def test_usuario_sem_role_nao_gerencia_ninguem(
        self, usuario_sem_role, gestor_pngi
    ):
        service = AuthorizationService(usuario_sem_role)
        assert service.user_can_manage_target_user(gestor_pngi) is False


# --- user_can_create_user_in_application ------------------------------------

class TestUserCanCreateUserInApplication:

    def test_gestor_pode_criar_na_propria_app(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_create_user_in_application(app) is True

    def test_gestor_nao_pode_criar_em_app_alheia(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_create_user_in_application(app) is False

    def test_superuser_pode_criar_em_qualquer_app(self, superuser):
        app = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        service = AuthorizationService(superuser)
        assert service.user_can_create_user_in_application(app) is True

    def test_usuario_sem_role_nao_pode_criar_em_nenhuma_app(
        self, usuario_sem_role
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(usuario_sem_role)
        assert service.user_can_create_user_in_application(app) is False


# --- get_user_roles_for_app --------------------------------------------------

class TestGetUserRolesForApp:

    def test_retorna_roles_do_usuario_para_app(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi)
        roles = service.get_user_roles_for_app(app)
        assert roles.exists()
        assert roles.filter(user=gestor_pngi).count() == 1

    def test_retorna_vazio_quando_sem_role_na_app(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        service = AuthorizationService(gestor_pngi)
        roles = service.get_user_roles_for_app(app)
        assert not roles.exists()

    def test_retorna_role_correta_pelo_codigoperfil(self, gestor_pngi):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        service = AuthorizationService(gestor_pngi)
        roles = service.get_user_roles_for_app(app)
        codigos = list(roles.values_list("role__codigoperfil", flat=True))
        assert "GESTOR_PNGI" in codigos
