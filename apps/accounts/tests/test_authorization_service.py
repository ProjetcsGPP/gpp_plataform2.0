# apps/accounts/tests/test_authorization_service.py
"""
Testes do AuthorizationService com banco de dados real.

Sem mocks. Todos os metodos sao testados com objetos reais
criados a partir das fixtures (initial_data.json).

Metodos validados:
  can_create_user():
    - False quando ClassificacaoUsuario.pode_criar_usuario=False
    - True  quando ClassificacaoUsuario.pode_criar_usuario=True

  can_edit_user():
    - False quando ClassificacaoUsuario.pode_editar_usuario=False
    - True  quando ClassificacaoUsuario.pode_editar_usuario=True

  user_can_manage_target_user(target):
    - True  quando ambos tem UserRole na mesma Aplicacao
    - False quando nao ha intersecao de Aplicacao
    - True  quando requester e superuser

  user_can_create_user_in_application(app):
    - True  quando requester tem UserRole na app
    - False quando requester nao tem UserRole na app
    - True  quando requester e superuser

  get_user_roles_for_app(app):
    - Retorna UserRoles do usuario para a app informada
    - Retorna queryset vazio quando usuario nao tem role na app
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

pytestmark = pytest.mark.django_db(transaction=True)


def _make_user_with_classificacao(username, pode_criar=False, pode_editar=False):
    """Cria usuario com ClassificacaoUsuario customizada."""
    classificacao, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=90 + hash(username) % 9,
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
        status_usuario=StatusUsuario.objects.get(pk=1),
        tipo_usuario=TipoUsuario.objects.get(pk=1),
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
        """Gestor e Operador ambos tem UserRole em ACOES_PNGI."""
        service = AuthorizationService(gestor_pngi)
        assert service.user_can_manage_target_user(operador_acao) is True

    def test_usuarios_sem_app_em_comum(self, db, gestor_pngi, gestor_carga):
        """Gestor PNGI e Gestor CARGA nao compartilham app."""
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

    def test_retorna_vazio_quando_sem_role_na_app(
        self, gestor_pngi
    ):
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
