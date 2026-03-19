"""
Testes para UserProfilePolicy.

Estratégia:
  - Zero banco de dados (pytest puro, sem @pytest.mark.django_db)
  - MagicMock para todas as entidades (actor, profile, classificacao)
  - patch via unittest.mock.patch para isolar queries ORM
  - Fixtures estendem o conftest.py existente deste pacote
"""
from unittest.mock import MagicMock, patch
import pytest

from apps.accounts.policies.userprofile_policy import UserProfilePolicy


# ── Factories locais ───────────────────────────────────────────────────────────────────

APP_READY_ID = 99
APP_OTHER_ID = 88


def make_classificacao(pode_editar=False, pode_criar=False):
    c = MagicMock()
    c.pode_editar_usuario = pode_editar
    c.pode_criar_usuario = pode_criar
    return c


def make_actor(
    actor_id,
    is_superuser=False,
    is_portal_admin=False,
    pode_editar=False,
    app_ids=None,
):
    """
    Retorna um actor MagicMock já com profile.classificacao_usuario.
    O parâmetro is_portal_admin é injetado via patch nos testes;
    aqui apenas marca para conveniência.
    """
    actor = MagicMock()
    actor.id = actor_id
    actor.pk = actor_id
    actor.is_superuser = is_superuser
    actor.profile.classificacao_usuario = make_classificacao(pode_editar=pode_editar)
    actor._app_ids = app_ids or set()
    return actor


def make_profile(user_id, app_ids=None):
    """Retorna um UserProfile MagicMock com user_id e user.pk."""
    profile = MagicMock()
    profile.user_id = user_id
    profile.user = MagicMock()
    profile.user.pk = user_id
    profile.user.id = user_id
    profile._app_ids = app_ids or set()
    return profile


def build_policy(
    actor,
    profile,
    actor_is_portal_admin=False,
    actor_app_ids=None,
    profile_app_ids=None,
):
    """
    Constrói UserProfilePolicy com patches aplicados:
      - _is_portal_admin retorna actor_is_portal_admin
      - _get_actor_applications retorna actor_app_ids
      - _has_application_intersection calculado a partir da interseção real
        entre actor_app_ids e profile_app_ids
    """
    policy = UserProfilePolicy(actor, profile)
    policy._is_admin = actor_is_portal_admin

    actor_apps = set(actor_app_ids) if actor_app_ids is not None else set()
    profile_apps = set(profile_app_ids) if profile_app_ids is not None else set()
    has_intersection = bool(actor_apps & profile_apps)

    policy._actor_apps = actor_apps
    # Patch _has_application_intersection to avoid ORM hit
    policy._has_application_intersection = lambda: has_intersection

    return policy


# ── Fixtures ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def actor_portal_admin():
    return make_actor(actor_id=1, is_portal_admin=True)


@pytest.fixture
def actor_superuser():
    return make_actor(actor_id=2, is_superuser=True)


@pytest.fixture
def actor_gestor():
    """Gestor com pode_editar_usuario=True e role em APP_READY_ID."""
    return make_actor(actor_id=3, pode_editar=True, app_ids={APP_READY_ID})


@pytest.fixture
def actor_regular():
    return make_actor(actor_id=4, pode_editar=False)


@pytest.fixture
def profile_same_app():
    """Profile de outro usuário com role na mesma app do gestor."""
    return make_profile(user_id=50, app_ids={APP_READY_ID})


@pytest.fixture
def profile_other_app():
    """Profile de outro usuário com role em app diferente."""
    return make_profile(user_id=60, app_ids={APP_OTHER_ID})


@pytest.fixture
def own_profile(actor_gestor):
    """Profile do próprio actor_gestor."""
    profile = make_profile(user_id=actor_gestor.pk)
    return profile


# ── TestCanViewProfile ────────────────────────────────────────────────────────────────

class TestCanViewProfile:

    def test_portal_admin_can_view_any_profile(
        self, actor_portal_admin, profile_other_app
    ):
        policy = build_policy(
            actor_portal_admin,
            profile_other_app,
            actor_is_portal_admin=True,
        )
        assert policy.can_view_profile() is True

    def test_superuser_can_view_any_profile(
        self, actor_superuser, profile_other_app
    ):
        policy = build_policy(actor_superuser, profile_other_app)
        assert policy.can_view_profile() is True

    def test_user_can_view_own_profile(self, actor_gestor, own_profile):
        policy = build_policy(actor_gestor, own_profile)
        assert policy.can_view_profile() is True

    def test_gestor_can_view_profile_in_same_app(
        self, actor_gestor, profile_same_app
    ):
        policy = build_policy(
            actor_gestor,
            profile_same_app,
            actor_app_ids={APP_READY_ID},
            profile_app_ids={APP_READY_ID},
        )
        assert policy.can_view_profile() is True

    def test_gestor_cannot_view_profile_of_other_app(
        self, actor_gestor, profile_other_app
    ):
        """reason=no_app_intersection"""
        policy = build_policy(
            actor_gestor,
            profile_other_app,
            actor_app_ids={APP_READY_ID},
            profile_app_ids={APP_OTHER_ID},
        )
        assert policy.can_view_profile() is False

    def test_regular_user_cannot_view_other_profile(
        self, actor_regular, profile_same_app
    ):
        """reason=no_permission (pode_editar_usuario=False)"""
        policy = build_policy(
            actor_regular,
            profile_same_app,
            actor_app_ids=set(),
            profile_app_ids={APP_READY_ID},
        )
        assert policy.can_view_profile() is False

    def test_actor_without_classificacao_cannot_view_other_profile(
        self, profile_same_app
    ):
        """
        Actor sem profile.classificacao_usuario (AttributeError) →
        _get_actor_classificacao() retorna None → _can_edit_users()=False.
        Cobre linhas 229–233 de userprofile_policy.py.
        """
        actor_no_class = MagicMock()
        actor_no_class.id = 77
        actor_no_class.pk = 77
        actor_no_class.is_superuser = False
        # Simula AttributeError ao acessar profile.classificacao_usuario
        type(actor_no_class.profile).classificacao_usuario = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no classificacao"))
        )
        policy = UserProfilePolicy(actor_no_class, profile_same_app)
        policy._is_admin = False
        result = policy.can_view_profile()
        assert result is False


# ── TestCanEditProfile ────────────────────────────────────────────────────────────────

class TestCanEditProfile:

    def test_portal_admin_can_edit_any_profile(
        self, actor_portal_admin, profile_other_app
    ):
        policy = build_policy(
            actor_portal_admin,
            profile_other_app,
            actor_is_portal_admin=True,
        )
        assert policy.can_edit_profile() is True

    def test_user_can_edit_own_profile(self, actor_gestor, own_profile):
        policy = build_policy(actor_gestor, own_profile)
        assert policy.can_edit_profile() is True

    def test_gestor_can_edit_profile_in_same_app(
        self, actor_gestor, profile_same_app
    ):
        policy = build_policy(
            actor_gestor,
            profile_same_app,
            actor_app_ids={APP_READY_ID},
            profile_app_ids={APP_READY_ID},
        )
        assert policy.can_edit_profile() is True

    def test_gestor_cannot_edit_profile_of_other_app(
        self, actor_gestor, profile_other_app
    ):
        """reason=no_app_intersection"""
        policy = build_policy(
            actor_gestor,
            profile_other_app,
            actor_app_ids={APP_READY_ID},
            profile_app_ids={APP_OTHER_ID},
        )
        assert policy.can_edit_profile() is False

    def test_regular_user_cannot_edit_other_profile(
        self, actor_regular, profile_same_app
    ):
        """reason=no_edit_permission"""
        policy = build_policy(
            actor_regular,
            profile_same_app,
            actor_app_ids=set(),
            profile_app_ids={APP_READY_ID},
        )
        assert policy.can_edit_profile() is False


# ── TestCanChangeClassificacao ────────────────────────────────────────────────────────

class TestCanChangeClassificacao:

    def test_portal_admin_can_change_classificacao(
        self, actor_portal_admin, profile_same_app
    ):
        policy = build_policy(
            actor_portal_admin,
            profile_same_app,
            actor_is_portal_admin=True,
        )
        assert policy.can_change_classificacao() is True

    def test_superuser_can_change_classificacao(
        self, actor_superuser, profile_same_app
    ):
        policy = build_policy(actor_superuser, profile_same_app)
        assert policy.can_change_classificacao() is True

    def test_gestor_cannot_change_classificacao(
        self, actor_gestor, profile_same_app
    ):
        """reason=not_portal_admin"""
        policy = build_policy(
            actor_gestor,
            profile_same_app,
            actor_app_ids={APP_READY_ID},
            profile_app_ids={APP_READY_ID},
        )
        assert policy.can_change_classificacao() is False

    def test_regular_user_cannot_change_classificacao(
        self, actor_regular, profile_same_app
    ):
        policy = build_policy(
            actor_regular,
            profile_same_app,
        )
        assert policy.can_change_classificacao() is False


# ── TestCanChangeStatus ───────────────────────────────────────────────────────────────

class TestCanChangeStatus:

    def test_portal_admin_can_change_status(
        self, actor_portal_admin, profile_same_app
    ):
        policy = build_policy(
            actor_portal_admin,
            profile_same_app,
            actor_is_portal_admin=True,
        )
        assert policy.can_change_status() is True

    def test_superuser_can_change_status(
        self, actor_superuser, profile_same_app
    ):
        policy = build_policy(actor_superuser, profile_same_app)
        assert policy.can_change_status() is True

    def test_gestor_cannot_change_status(
        self, actor_gestor, profile_same_app
    ):
        """reason=not_portal_admin"""
        policy = build_policy(
            actor_gestor,
            profile_same_app,
            actor_app_ids={APP_READY_ID},
            profile_app_ids={APP_READY_ID},
        )
        assert policy.can_change_status() is False


# ── TestCanViewAllProfiles ───────────────────────────────────────────────────────────

class TestCanViewAllProfiles:

    def test_portal_admin_can_view_all(
        self, actor_portal_admin, profile_same_app
    ):
        policy = build_policy(
            actor_portal_admin,
            profile_same_app,
            actor_is_portal_admin=True,
        )
        assert policy.can_view_all_profiles() is True

    def test_superuser_can_view_all(
        self, actor_superuser, profile_same_app
    ):
        policy = build_policy(actor_superuser, profile_same_app)
        assert policy.can_view_all_profiles() is True

    def test_regular_user_cannot_view_all(
        self, actor_regular, profile_same_app
    ):
        """reason=not_portal_admin"""
        policy = build_policy(actor_regular, profile_same_app)
        assert policy.can_view_all_profiles() is False


# ── TestHasApplicationIntersection (DB real) ─────────────────────────────────────────

class TestHasApplicationIntersection:

    @pytest.mark.django_db
    def test_gestor_with_real_db_intersection_can_view_profile(
        self,
        db_gestor,
        db_app_ready,
        db_role_viewer,
        db_regular_user,
    ):
        """
        Aciona _has_application_intersection() com DB real, exercitando
        as linhas 232–233 e 242 de userprofile_policy.py (o import lazy
        de UserRole e o .exists() final).

        db_gestor tem UserRole em db_app_ready;
        db_regular_user também tem UserRole em db_app_ready → interseção real.
        """
        from apps.accounts.policies.userprofile_policy import UserProfilePolicy

        profile = db_regular_user.profile
        policy = UserProfilePolicy(db_gestor, profile)
        # Não patchamos _has_application_intersection — deixamos o ORM real rodar
        assert policy.can_view_profile() is True

    @pytest.mark.django_db
    def test_gestor_without_real_db_intersection_cannot_view_profile(
        self,
        db_gestor,
        db_isolated_user,
    ):
        """
        db_gestor está em db_app_ready; db_isolated_user está apenas em db_app_other
        → sem interseção → deny.
        Confirma que o caminho False de _has_application_intersection também é coberto.
        """
        from apps.accounts.policies.userprofile_policy import UserProfilePolicy

        profile = db_isolated_user.profile
        policy = UserProfilePolicy(db_gestor, profile)
        assert policy.can_view_profile() is False
