"""
Testes de UserPolicy.

Estratégia:
  - Testes de branches de log e cache → MagicMock + patch (zero DB)
  - Testes que exigem UserRole/UserProfile reais → @pytest.mark.django_db
    usando as fixtures DB do conftest.py da pasta policies/.

A UserPolicy é domínio puro: não usa request, DRF nem views.

NOTA DE PATCH:
  UserRole é importado localmente (dentro dos métodos) em user_policy.py,
  por isso o patch correto é "apps.accounts.models.UserRole", não
  "apps.accounts.policies.user_policy.UserRole".
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.policies.user_policy import UserPolicy
from apps.accounts.tests.policies.conftest import make_user, make_aplicacao

# Alvo correto de patch: UserRole é importado dentro dos métodos da policy.
_UR_PATH = "apps.accounts.models.UserRole"


# ── Factories locais ──────────────────────────────────────────────────────────

def make_classificacao(pode_criar=False, pode_editar=False, pk=1, strdescricao="Padrão"):
    c = MagicMock()
    c.pk = pk
    c.strdescricao = strdescricao
    c.pode_criar_usuario = pode_criar
    c.pode_editar_usuario = pode_editar
    return c


def make_policy_user(user_id=1):
    """User MagicMock sem UserRole (não é portal_admin por padrão)."""
    user = make_user(user_id=user_id, is_superuser=False)
    user.pk = user_id
    return user


class _AplicacaoSemCodigo:
    """Objeto simples sem atributo codigointerno — força fallback str()."""
    def __str__(self):
        return "APLICACAO_STR_REPR"


# ── Fixtures base ─────────────────────────────────────────────────────────────

@pytest.fixture
def actor():
    return make_policy_user(user_id=1)


@pytest.fixture
def target_user():
    return make_policy_user(user_id=2)


@pytest.fixture
def classificacao_com_permissao():
    return make_classificacao(pode_criar=True, pode_editar=True, pk=10, strdescricao="Gestor")


@pytest.fixture
def classificacao_sem_permissao():
    return make_classificacao(pode_criar=False, pode_editar=False, pk=1, strdescricao="Padrão")


# ═══════════════════════════════════════════════════════════════════════════════
# TestCanCreateUser
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanCreateUser:

    def test_can_create_user_portal_admin_returns_true(self, actor, caplog):
        """portal_admin → True + log INFO AUTHZ_USER_CREATE reason=portal_admin."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = True
            with caplog.at_level(logging.INFO, logger="gpp.security"):
                result = policy.can_create_user()

        assert result is True
        assert any(
            "AUTHZ_USER_CREATE" in r.message and "portal_admin" in r.message
            for r in caplog.records
        )
        assert all(
            r.levelname == "INFO"
            for r in caplog.records
            if "AUTHZ_USER_CREATE" in r.message and "portal_admin" in r.message
        )

    def test_can_create_user_no_classificacao_returns_false(self, actor, caplog):
        """classificacao is None → False + log WARNING reason=no_classificacao."""
        policy = UserPolicy(actor)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=None):
                    result = policy.can_create_user()

        assert result is False
        assert any("no_classificacao" in r.message for r in caplog.records)
        assert any(
            r.levelname == "WARNING"
            for r in caplog.records if "no_classificacao" in r.message
        )

    def test_can_create_user_classificacao_pode_criar_true_returns_true(
        self, actor, classificacao_com_permissao, caplog
    ):
        """classificacao.pode_criar_usuario=True → True + log INFO."""
        policy = UserPolicy(actor)
        with caplog.at_level(logging.INFO, logger="gpp.security"):
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                    result = policy.can_create_user()

        assert result is True
        assert any("AUTHZ_USER_CREATE" in r.message for r in caplog.records)
        assert any(
            r.levelname == "INFO"
            for r in caplog.records if "AUTHZ_USER_CREATE" in r.message
        )

    def test_can_create_user_classificacao_pode_criar_false_returns_false(
        self, actor, classificacao_sem_permissao, caplog
    ):
        """classificacao.pode_criar_usuario=False → False + log WARNING."""
        policy = UserPolicy(actor)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_sem_permissao):
                    result = policy.can_create_user()

        assert result is False
        assert any("AUTHZ_USER_CREATE" in r.message for r in caplog.records)
        assert any(
            r.levelname == "WARNING"
            for r in caplog.records if "AUTHZ_USER_CREATE" in r.message
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestCanEditUser
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanEditUser:

    def test_can_edit_user_portal_admin_returns_true(self, actor, caplog):
        """portal_admin → True + log INFO AUTHZ_USER_EDIT reason=portal_admin."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = True
            with caplog.at_level(logging.INFO, logger="gpp.security"):
                result = policy.can_edit_user()

        assert result is True
        assert any(
            "AUTHZ_USER_EDIT" in r.message and "portal_admin" in r.message
            for r in caplog.records
        )
        assert all(
            r.levelname == "INFO"
            for r in caplog.records
            if "AUTHZ_USER_EDIT" in r.message and "portal_admin" in r.message
        )

    def test_can_edit_user_no_classificacao_returns_false(self, actor, caplog):
        """classificacao is None → False + log WARNING reason=no_classificacao."""
        policy = UserPolicy(actor)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=None):
                    result = policy.can_edit_user()

        assert result is False
        assert any("no_classificacao" in r.message for r in caplog.records)
        assert any(
            r.levelname == "WARNING"
            for r in caplog.records if "no_classificacao" in r.message
        )

    def test_can_edit_user_classificacao_pode_editar_true_returns_true(
        self, actor, classificacao_com_permissao, caplog
    ):
        """classificacao.pode_editar_usuario=True → True + log INFO."""
        policy = UserPolicy(actor)
        with caplog.at_level(logging.INFO, logger="gpp.security"):
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                    result = policy.can_edit_user()

        assert result is True
        assert any("AUTHZ_USER_EDIT" in r.message for r in caplog.records)
        assert any(
            r.levelname == "INFO"
            for r in caplog.records if "AUTHZ_USER_EDIT" in r.message
        )

    def test_can_edit_user_classificacao_pode_editar_false_returns_false(
        self, actor, classificacao_sem_permissao, caplog
    ):
        """classificacao.pode_editar_usuario=False → False + log WARNING."""
        policy = UserPolicy(actor)
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_sem_permissao):
                    result = policy.can_edit_user()

        assert result is False
        assert any("AUTHZ_USER_EDIT" in r.message for r in caplog.records)
        assert any(
            r.levelname == "WARNING"
            for r in caplog.records if "AUTHZ_USER_EDIT" in r.message
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestCanCreateUserInApplication
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanCreateUserInApplication:

    def test_portal_admin_returns_true_without_checking_userrole(self, actor, caplog):
        """portal_admin → True imediato; UserRole.objects.filter NÃO chamado."""
        aplicacao = make_aplicacao(codigointerno="APP_X")
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            with patch.object(policy, "_is_portal_admin", return_value=True):
                with caplog.at_level(logging.INFO, logger="gpp.security"):
                    result = policy.can_create_user_in_application(aplicacao)

        assert result is True
        mock_ur.objects.filter.assert_not_called()
        assert any("portal_admin" in r.message for r in caplog.records)

    def test_no_create_permission_returns_false_immediately(self, actor, caplog):
        """can_create_user()=False → False imediato + log WARNING reason=no_create_permission."""
        aplicacao = make_aplicacao(codigointerno="APP_Y")
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=None):
                    with caplog.at_level(logging.WARNING, logger="gpp.security"):
                        result = policy.can_create_user_in_application(aplicacao)

        assert result is False
        assert any("no_create_permission" in r.message for r in caplog.records)
        mock_ur.objects.filter.assert_not_called()

    def test_has_role_in_app_returns_true(self, actor, classificacao_com_permissao, caplog):
        """can_create_user()=True + UserRole existe → True + log INFO reason=has_role_in_app."""
        aplicacao = make_aplicacao(codigointerno="APP_Z")
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = True
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                    with caplog.at_level(logging.INFO, logger="gpp.security"):
                        result = policy.can_create_user_in_application(aplicacao)

        assert result is True
        assert any("has_role_in_app" in r.message for r in caplog.records)

    def test_no_role_in_app_returns_false(self, actor, classificacao_com_permissao, caplog):
        """can_create_user()=True + UserRole NÃO existe → False + log WARNING reason=no_role_in_app."""
        aplicacao = make_aplicacao(codigointerno="APP_W")
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = False
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                    with caplog.at_level(logging.WARNING, logger="gpp.security"):
                        result = policy.can_create_user_in_application(aplicacao)

        assert result is False
        assert any("no_role_in_app" in r.message for r in caplog.records)

    def test_aplicacao_sem_codigointerno_usa_str_no_log(self, actor, classificacao_com_permissao, caplog):
        """aplicacao sem atributo codigointerno → fallback str(aplicacao) usado no log."""
        # Usa classe simples sem codigointerno para evitar conflito com spec=[] do MagicMock
        aplicacao = _AplicacaoSemCodigo()
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = True
            with patch.object(policy, "_is_portal_admin", return_value=False):
                with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                    with caplog.at_level(logging.INFO, logger="gpp.security"):
                        result = policy.can_create_user_in_application(aplicacao)

        assert result is True
        assert any("APLICACAO_STR_REPR" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# TestCanEditTargetUser
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanEditTargetUser:

    def test_portal_admin_returns_true(self, actor, target_user, caplog):
        """portal_admin → True + log INFO reason=portal_admin."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = True
            with caplog.at_level(logging.INFO, logger="gpp.security"):
                result = policy.can_edit_target_user(target_user)

        assert result is True
        assert any("portal_admin" in r.message for r in caplog.records)

    def test_no_edit_permission_returns_false_immediately(self, actor, target_user, caplog):
        """can_edit_user()=False → False imediato + log WARNING reason=no_edit_permission."""
        policy = UserPolicy(actor)
        with patch.object(policy, "_is_portal_admin", return_value=False):
            with patch.object(policy, "_get_classificacao", return_value=None):
                with caplog.at_level(logging.WARNING, logger="gpp.security"):
                    result = policy.can_edit_target_user(target_user)

        assert result is False
        assert any("no_edit_permission" in r.message for r in caplog.records)

    def test_with_intersection_returns_true(
        self, actor, target_user, classificacao_com_permissao, caplog
    ):
        """can_edit_user()=True + intersection → True + log INFO reason=app_intersection."""
        policy = UserPolicy(actor)
        with patch.object(policy, "_is_portal_admin", return_value=False):
            with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                with patch.object(policy, "_has_application_intersection", return_value=True):
                    with caplog.at_level(logging.INFO, logger="gpp.security"):
                        result = policy.can_edit_target_user(target_user)

        assert result is True
        assert any("app_intersection" in r.message for r in caplog.records)

    def test_without_intersection_returns_false(
        self, actor, target_user, classificacao_com_permissao, caplog
    ):
        """can_edit_user()=True + sem intersection → False + log WARNING reason=no_app_intersection."""
        policy = UserPolicy(actor)
        with patch.object(policy, "_is_portal_admin", return_value=False):
            with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                with patch.object(policy, "_has_application_intersection", return_value=False):
                    with caplog.at_level(logging.WARNING, logger="gpp.security"):
                        result = policy.can_edit_target_user(target_user)

        assert result is False
        assert any("no_app_intersection" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# TestCanManageTargetUser
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanManageTargetUser:

    def test_portal_admin_returns_true(self, actor, target_user, caplog):
        """portal_admin → True + log INFO AUTHZ_MANAGE_USER_ALLOW reason=portal_admin."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = True
            with caplog.at_level(logging.INFO, logger="gpp.security"):
                result = policy.can_manage_target_user(target_user)

        assert result is True
        assert any(
            "AUTHZ_MANAGE_USER_ALLOW" in r.message and "portal_admin" in r.message
            for r in caplog.records
        )

    def test_no_edit_permission_returns_false_immediately(self, actor, target_user, caplog):
        """can_edit_user()=False → False imediato + log WARNING reason=no_edit_permission."""
        policy = UserPolicy(actor)
        with patch.object(policy, "_is_portal_admin", return_value=False):
            with patch.object(policy, "_get_classificacao", return_value=None):
                with caplog.at_level(logging.WARNING, logger="gpp.security"):
                    result = policy.can_manage_target_user(target_user)

        assert result is False
        assert any("no_edit_permission" in r.message for r in caplog.records)

    def test_with_intersection_returns_true(
        self, actor, target_user, classificacao_com_permissao, caplog
    ):
        """can_edit_user()=True + intersection → True + log INFO reason=app_intersection."""
        policy = UserPolicy(actor)
        with patch.object(policy, "_is_portal_admin", return_value=False):
            with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                with patch.object(policy, "_has_application_intersection", return_value=True):
                    with caplog.at_level(logging.INFO, logger="gpp.security"):
                        result = policy.can_manage_target_user(target_user)

        assert result is True
        assert any(
            "AUTHZ_MANAGE_USER_ALLOW" in r.message and "app_intersection" in r.message
            for r in caplog.records
        )

    def test_without_intersection_returns_false(
        self, actor, target_user, classificacao_com_permissao, caplog
    ):
        """can_edit_user()=True + sem intersection → False + log WARNING reason=no_app_intersection."""
        policy = UserPolicy(actor)
        with patch.object(policy, "_is_portal_admin", return_value=False):
            with patch.object(policy, "_get_classificacao", return_value=classificacao_com_permissao):
                with patch.object(policy, "_has_application_intersection", return_value=False):
                    with caplog.at_level(logging.WARNING, logger="gpp.security"):
                        result = policy.can_manage_target_user(target_user)

        assert result is False
        assert any(
            "AUTHZ_MANAGE_USER_DENY" in r.message and "no_app_intersection" in r.message
            for r in caplog.records
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestHelpers — cache, AttributeError, intersection com set vazio
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpers:

    # ── _is_portal_admin cache hit ────────────────────────────────────────────

    def test_is_portal_admin_cache_hit_filter_called_once(self, actor):
        """
        Chamar can_create_user() + can_edit_user() na mesma instância deve
        disparar UserRole.filter apenas UMA vez (cache _is_admin).
        """
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.exists.return_value = False
            with patch.object(policy, "_get_classificacao", return_value=None):
                policy.can_create_user()
                policy.can_edit_user()

        # O filtro de portal_admin deve ter sido chamado exatamente uma vez.
        # Segunda chamada lê cache _is_admin e não chama o ORM novamente.
        assert mock_ur.objects.filter.call_count == 1

    # ── _get_classificacao caminhos ───────────────────────────────────────────

    def test_get_classificacao_returns_profile_classificacao(self, actor):
        """user.profile existe e retorna classificacao_usuario corretamente."""
        expected = make_classificacao(pode_criar=True)
        actor.profile.classificacao_usuario = expected
        policy = UserPolicy(actor)
        result = policy._get_classificacao()
        assert result is expected

    def test_get_classificacao_returns_none_on_attribute_error(self):
        """user.profile levanta AttributeError → _get_classificacao retorna None."""
        user = MagicMock(spec=["id", "pk"])
        user.id = 99
        user.pk = 99
        type(user).profile = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no profile"))
        )
        policy = UserPolicy(user)
        result = policy._get_classificacao()
        assert result is None

    # ── _get_user_applications cache hit ─────────────────────────────────────

    def test_get_user_applications_cache_hit_no_second_db_call(self, actor):
        """Segunda chamada a _get_user_applications retorna mesmo set sem novo hit no ORM."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.values_list.return_value = [10, 20]
            first = policy._get_user_applications()
            second = policy._get_user_applications()

        assert first == second
        assert mock_ur.objects.filter.call_count == 1

    def test_get_user_applications_returns_set_of_ids(self, actor):
        """_get_user_applications converte QuerySet em set de aplicacao_id."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.values_list.return_value = [3, 7, 15]
            result = policy._get_user_applications()

        assert isinstance(result, set)
        assert result == {3, 7, 15}

    # ── _has_application_intersection ────────────────────────────────────────

    def test_has_application_intersection_shared_app_returns_true(self, actor, target_user):
        """actor e target compartilham aplicacao → True."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.values_list.return_value = [1, 2]
            mock_ur.objects.filter.return_value.exists.return_value = True
            result = policy._has_application_intersection(target_user)

        assert result is True

    def test_has_application_intersection_no_shared_app_returns_false(self, actor, target_user):
        """actor e target NÃO compartilham aplicacao → False."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.values_list.return_value = [1, 2]
            mock_ur.objects.filter.return_value.exists.return_value = False
            result = policy._has_application_intersection(target_user)

        assert result is False

    def test_has_application_intersection_empty_actor_apps_returns_false(self, actor, target_user):
        """actor sem nenhuma aplicacao (set vazio) → False."""
        policy = UserPolicy(actor)
        with patch(_UR_PATH) as mock_ur:
            mock_ur.objects.filter.return_value.values_list.return_value = []
            mock_ur.objects.filter.return_value.exists.return_value = False
            result = policy._has_application_intersection(target_user)

        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Testes com DB real — cenários que exigem UserRole/UserProfile persistidos
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCanCreateUserPortalAdminDB:
    """Valida o fluxo real de _is_portal_admin com UserRole no banco."""

    def test_portal_admin_db_can_create_user(self, db_portal_admin):
        policy = UserPolicy(db_portal_admin)
        assert policy.can_create_user() is True

    def test_regular_user_without_classificacao_db_cannot_create(self, db):
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="no_profile_user", password="Pass123!")
        # Sem UserProfile → AttributeError → classificacao None → False
        policy = UserPolicy(user)
        assert policy.can_create_user() is False


@pytest.mark.django_db
class TestCanEditUserDB:
    """Valida o fluxo real de can_edit_user com ClassificacaoUsuario no banco."""

    def test_portal_admin_db_can_edit_user(self, db_portal_admin):
        policy = UserPolicy(db_portal_admin)
        assert policy.can_edit_user() is True

    def test_gestor_db_can_edit_user(self, db_gestor):
        """Gestor com pode_editar_usuario=True deve retornar True."""
        policy = UserPolicy(db_gestor)
        assert policy.can_edit_user() is True

    def test_regular_user_db_cannot_edit_user(self, db_regular_user):
        """Usuário com ClassificacaoUsuario padrão (pode_editar=False) retorna False."""
        policy = UserPolicy(db_regular_user)
        assert policy.can_edit_user() is False


@pytest.mark.django_db
class TestCanCreateUserInApplicationDB:
    """Valida can_create_user_in_application com objetos reais."""

    def test_gestor_with_role_in_app_can_create(self, db_gestor, db_app_ready):
        """
        Gestor + UserRole na app + pode_criar_usuario=True → True.

        Cria uma ClassificacaoUsuario dedicada (pk=3) para não interferir
        na fixture db_gestor que depende de pk=2 com pode_editar=True.
        Atualiza o profile do gestor para apontar para a nova classificacao.
        """
        from apps.accounts.models import ClassificacaoUsuario

        classificacao_criador, _ = ClassificacaoUsuario.objects.get_or_create(
            idclassificacaousuario=3,
            defaults={
                "strdescricao": "Gestor Criador",
                "pode_criar_usuario": True,
                "pode_editar_usuario": True,
            },
        )
        # Garante pode_criar=True caso o objeto já existia
        if not classificacao_criador.pode_criar_usuario:
            classificacao_criador.pode_criar_usuario = True
            classificacao_criador.save()

        profile = db_gestor.profile
        profile.classificacao_usuario = classificacao_criador
        profile.save()
        db_gestor.refresh_from_db()

        policy = UserPolicy(db_gestor)
        assert policy.can_create_user_in_application(db_app_ready) is True

    def test_portal_admin_db_can_create_in_any_app(self, db_portal_admin, db_app_ready):
        policy = UserPolicy(db_portal_admin)
        assert policy.can_create_user_in_application(db_app_ready) is True


@pytest.mark.django_db
class TestCanEditTargetUserDB:
    """Valida can_edit_target_user com objetos reais no banco."""

    def test_gestor_can_edit_target_in_same_app(self, db_gestor, db_regular_user):
        """Gestor e regular_user compartilham db_app_ready → True."""
        policy = UserPolicy(db_gestor)
        assert policy.can_edit_target_user(db_regular_user) is True

    def test_gestor_cannot_edit_target_in_other_app(self, db_gestor, db_isolated_user):
        """Gestor está em db_app_ready; isolated_user está em db_app_other → False."""
        policy = UserPolicy(db_gestor)
        assert policy.can_edit_target_user(db_isolated_user) is False

    def test_portal_admin_db_can_edit_any_target(self, db_portal_admin, db_isolated_user):
        policy = UserPolicy(db_portal_admin)
        assert policy.can_edit_target_user(db_isolated_user) is True


@pytest.mark.django_db
class TestCanManageTargetUserDB:
    """Valida can_manage_target_user com objetos reais no banco."""

    def test_gestor_can_manage_target_in_same_app(self, db_gestor, db_regular_user):
        """Gestor e regular_user compartilham db_app_ready → True."""
        policy = UserPolicy(db_gestor)
        assert policy.can_manage_target_user(db_regular_user) is True

    def test_gestor_cannot_manage_target_in_other_app(self, db_gestor, db_isolated_user):
        """Gestor não compartilha app com isolated_user → False."""
        policy = UserPolicy(db_gestor)
        assert policy.can_manage_target_user(db_isolated_user) is False

    def test_portal_admin_db_can_manage_any_target(self, db_portal_admin, db_isolated_user):
        policy = UserPolicy(db_portal_admin)
        assert policy.can_manage_target_user(db_isolated_user) is True


@pytest.mark.django_db
class TestIsPortalAdminCacheDB:
    """Confirma comportamento de cache de _is_portal_admin com DB real."""

    def test_is_portal_admin_cache_hit_real_db(self, db_portal_admin):
        """
        Chamar can_create_user() e can_edit_user() na mesma instância deve
        resultar em apenas uma consulta DB para _is_portal_admin.
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        policy = UserPolicy(db_portal_admin)

        with CaptureQueriesContext(connection) as ctx:
            policy.can_create_user()
            policy.can_edit_user()

        portal_admin_queries = [
            q for q in ctx.captured_queries
            if "PORTAL_ADMIN" in q["sql"]
        ]
        assert len(portal_admin_queries) == 1, (
            f"Esperava 1 query para PORTAL_ADMIN, obteve {len(portal_admin_queries)}"
        )


@pytest.mark.django_db
class TestGetUserApplicationsCacheDB:
    """Confirma cache de _get_user_applications com DB real."""

    def test_get_user_applications_cache_hit_real_db(self, db_gestor):
        """Segunda chamada a _get_user_applications não deve gerar nova query."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        policy = UserPolicy(db_gestor)

        with CaptureQueriesContext(connection) as ctx:
            first = policy._get_user_applications()
            second = policy._get_user_applications()

        assert first == second
        app_queries = [
            q for q in ctx.captured_queries
            if "aplicacao_id" in q["sql"].lower()
        ]
        assert len(app_queries) == 1
