"""
Prompt 7 — Testes Cross-Policy (Integração de accounts)

Objetivo:
    Validar a COERÊNCIA entre as policies simulando fluxos reais de operação.
    São testes de domínio — chamam as policies diretamente, sem HTTP/DRF.

Pré-requisito:
    Prompts 1-6 executados. Todas as policies disponíveis via
    apps/accounts/policies/__init__.py.

Convenções:
    - @pytest.mark.django_db em todos os testes (fixtures com DB real)
    - Sem model_bakery — fixtures definidas em conftest.py
    - Nomenclatura: db_* para fixtures com banco de dados

Mudança Fase-0:
    AccountsSession não possui mais o campo jti (removido junto com JWT).
    _make_session() cria sessões apenas com user, expires_at e revoked.
"""
import pytest
from django.utils import timezone

from apps.accounts.models import AccountsSession, Attribute, UserRole
from apps.accounts.policies import (
    ApplicationPolicy,
    AttributePolicy,
    RolePolicy,
    SessionPolicy,
    UserProfilePolicy,
    UserRolePolicy,
)


# ─────────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────────

def _make_userrole_obj(user, role, aplicacao):
    """
    Cria um objeto UserRole persistido no banco para usar como
    argumento nas policies (UserRolePolicy recebe a instância do vínculo).
    Reutiliza UserRole existente se já houver (constraint uq_userrole_user_aplicacao).
    """
    ur, _ = UserRole.objects.get_or_create(
        user=user,
        aplicacao=aplicacao,
        defaults={"role": role},
    )
    return ur


def _make_session(user, revoked=False):
    """
    Cria uma AccountsSession para o user.

    Pós-Fase-0: o campo `jti` foi removido do modelo AccountsSession
    junto com toda a infraestrutura JWT. Sessions agora são puramente
    baseadas em cookie Django (gpp_session) e não armazenam JTI.
    """
    return AccountsSession.objects.create(
        user=user,
        expires_at=timezone.now() + timezone.timedelta(hours=1),
        revoked=revoked,
    )


def _make_attribute(user, aplicacao, key="ATTR_KEY"):
    """Cria um Attribute para o user na aplicação informada."""
    attr, _ = Attribute.objects.get_or_create(
        user=user,
        aplicacao=aplicacao,
        key=key,
        defaults={"value": "test_value"},
    )
    return attr


# ─────────────────────────────────────────────────────────────────────────────────
# CLASS 1: BLOQUEIO DE APP
# ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBlockedAppCoherence:
    """
    Garantir que o bloqueio de app propaga coerentemente por todas as policies.
    """

    def test_blocked_app_denies_view_in_application_and_role_policies(
        self,
        db_app_blocked,
        db_role_viewer,
        db_regular_user,
        db_portal_admin,
        db_app_ready,
    ):
        """
        App bloqueada → ApplicationPolicy.can_view_application() → False para user comum.
        App bloqueada → RolePolicy.can_view_role() → False para user comum.
        PORTAL_ADMIN passa nos dois.
        """
        # A role_viewer está em db_app_ready; precisamos de uma role em db_app_blocked
        from apps.accounts.models import Role
        role_blocked = Role.objects.create(
            codigoperfil="VIEWER_BLOCKED",
            nomeperfil="Viewer Blocked",
            aplicacao=db_app_blocked,
        )

        # --- usuario comum ---
        app_policy = ApplicationPolicy(db_regular_user, db_app_blocked)
        assert app_policy.can_view_application() is False

        role_policy = RolePolicy(db_regular_user, role_blocked)
        assert role_policy.can_view_role() is False

        # --- portal_admin passa em ambos ---
        app_policy_admin = ApplicationPolicy(db_portal_admin, db_app_blocked)
        assert app_policy_admin.can_view_application() is True

        role_policy_admin = RolePolicy(db_portal_admin, role_blocked)
        assert role_policy_admin.can_view_role() is True

    def test_blocked_app_denies_new_userrole_but_allows_deletion(
        self,
        db_app_blocked,
        db_role_viewer,
        db_portal_admin,
        db_regular_user,
        db_app_ready,
    ):
        """
        App bloqueada:
          - UserRolePolicy.can_create_userrole() → False (mesmo para PORTAL_ADMIN)
          - UserRolePolicy.can_delete_userrole() de outro user → True para PORTAL_ADMIN
        Bloqueio impede entrada mas não impede saída.
        """
        from apps.accounts.models import Role
        role_blocked = Role.objects.create(
            codigoperfil="VIEWER_BLK2",
            nomeperfil="Viewer BLK2",
            aplicacao=db_app_blocked,
        )
        # Simula um UserRole alvo em app_blocked pertencente a regular_user
        # (criado diretamente, pois o policy check não exige que já exista)
        userrole_target = UserRole.objects.create(
            user=db_regular_user,
            role=role_blocked,
            aplicacao=db_app_blocked,
        )

        # Criação → bloqueada mesmo para portal_admin
        policy_create = UserRolePolicy(db_portal_admin, userrole_target)
        assert policy_create.can_create_userrole() is False

        # Remoção → permitida para portal_admin (não é auto-remoção)
        policy_delete = UserRolePolicy(db_portal_admin, userrole_target)
        assert policy_delete.can_delete_userrole() is True

    def test_blocked_app_denies_attribute_creation(
        self,
        db_app_blocked,
        db_portal_admin,
        db_regular_user,
    ):
        """
        AttributePolicy.can_create_attribute() com app bloqueada → False
        inclusive para PORTAL_ADMIN.
        """
        attr = _make_attribute(db_regular_user, db_app_blocked, key="ATTR_BLK")

        policy = AttributePolicy(db_portal_admin, attr)
        assert policy.can_create_attribute() is False


# ─────────────────────────────────────────────────────────────────────────────────
# CLASS 2: APP EM STAGING
# ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStagingAppCoherence:
    """
    App em staging (isappproductionready=False) deve ter comportamento
    diferente de app bloqueada em alguns métodos.
    """

    def test_staging_app_denies_userrole_creation(
        self,
        db_app_staging,
        db_portal_admin,
        db_regular_user,
    ):
        """
        UserRolePolicy.can_create_userrole() com app em staging → False
        reason: app_not_production_ready
        """
        from apps.accounts.models import Role
        role_staging = Role.objects.create(
            codigoperfil="VIEWER_STG",
            nomeperfil="Viewer Staging",
            aplicacao=db_app_staging,
        )
        userrole = UserRole(
            user=db_regular_user,
            role=role_staging,
            aplicacao=db_app_staging,
        )
        # Não persiste — policy avalia os campos da instância
        policy = UserRolePolicy(db_portal_admin, userrole)
        assert policy.can_create_userrole() is False

    def test_staging_app_still_allows_deletion_of_existing_userrole(
        self,
        db_app_staging,
        db_portal_admin,
        db_regular_user,
    ):
        """
        Se UserRole já existe em app que entrou em staging,
        UserRolePolicy.can_delete_userrole() ainda deve ser True para PORTAL_ADMIN.
        Não bloqueamos limpeza retroativa.
        """
        from apps.accounts.models import Role
        role_staging = Role.objects.create(
            codigoperfil="VIEWER_STG2",
            nomeperfil="Viewer Staging 2",
            aplicacao=db_app_staging,
        )
        userrole = UserRole.objects.create(
            user=db_regular_user,
            role=role_staging,
            aplicacao=db_app_staging,
        )
        policy = UserRolePolicy(db_portal_admin, userrole)
        assert policy.can_delete_userrole() is True

    def test_staging_app_visible_to_portal_admin_but_not_regular_user(
        self,
        db_app_staging,
        db_portal_admin,
        db_regular_user,
    ):
        """
        ApplicationPolicy.can_view_application():
          PORTAL_ADMIN → True
          regular_user → False, reason=app_not_production_ready
        """
        policy_admin = ApplicationPolicy(db_portal_admin, db_app_staging)
        assert policy_admin.can_view_application() is True

        policy_regular = ApplicationPolicy(db_regular_user, db_app_staging)
        assert policy_regular.can_view_application() is False


# ─────────────────────────────────────────────────────────────────────────────────
# CLASS 3: PROTEÇÃO DA ROLE RAIZ
# ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPortalAdminRootProtection:
    """
    A role PORTAL_ADMIN é a role raiz. Sua proteção deve ser consistente
    em todos os pontos do sistema.
    """

    def test_portal_admin_role_cannot_be_deleted_anywhere(
        self,
        db_role_admin,
        db_portal_admin,
        db_superuser,
        db_regular_user,
    ):
        """
        RolePolicy.can_delete_role(role=PORTAL_ADMIN) → False
        para qualquer ator, inclusive SuperUser.
        """
        for actor in [db_regular_user, db_portal_admin, db_superuser]:
            policy = RolePolicy(actor, db_role_admin)
            assert policy.can_delete_role() is False, (
                f"can_delete_role deveria ser False para ator={actor.username}"
            )

    def test_portal_admin_role_cannot_be_assigned_by_portal_admin(
        self,
        db_role_admin,
        db_portal_admin,
        db_regular_user,
    ):
        """
        RolePolicy.can_assign_role_to_user(role=PORTAL_ADMIN, actor=portal_admin) → False
        UserRolePolicy.can_create_userrole(userrole.role=PORTAL_ADMIN, actor=portal_admin) → False
        Ambas as policies devem ser coerentes.
        """
        # RolePolicy
        role_policy = RolePolicy(db_portal_admin, db_role_admin)
        assert role_policy.can_assign_role_to_user(db_regular_user) is False

        # UserRolePolicy — monta instância não persistida com role=PORTAL_ADMIN
        userrole = UserRole(
            user=db_regular_user,
            role=db_role_admin,
            aplicacao=None,
        )
        ur_policy = UserRolePolicy(db_portal_admin, userrole)
        assert ur_policy.can_create_userrole() is False

    def test_superuser_can_assign_portal_admin_role(
        self,
        db_role_admin,
        db_superuser,
        db_regular_user,
        db_app_ready,
    ):
        """
        RolePolicy.can_assign_role_to_user(role=PORTAL_ADMIN, actor=superuser) → True
        UserRolePolicy.can_create_userrole(role=PORTAL_ADMIN, actor=superuser) → True
        """
        # RolePolicy — role_admin sem aplicacao; o check de app blocked/staging
        # usa getattr(role.aplicacao, ...) seguro
        role_policy = RolePolicy(db_superuser, db_role_admin)
        assert role_policy.can_assign_role_to_user(db_regular_user) is True

        # UserRolePolicy — role PORTAL_ADMIN, app None (sem bloqueio de app)
        userrole = UserRole(
            user=db_regular_user,
            role=db_role_admin,
            aplicacao=None,
        )
        ur_policy = UserRolePolicy(db_superuser, userrole)
        assert ur_policy.can_create_userrole() is True

    def test_nobody_can_revoke_own_role(
        self,
        db_role_viewer,
        db_app_ready,
        db_portal_admin,
        db_role_admin,
        db_superuser,
        db_regular_user,
        db_gestor,
    ):
        """
        RolePolicy.can_revoke_role_from_user(target=actor) → False
        UserRolePolicy.can_delete_userrole onde userrole.user == actor → False
        para qualquer tipo de user (regular, gestor, portal_admin, superuser).
        """
        actors = [
            (db_regular_user, db_role_viewer),
            (db_gestor, db_role_viewer),
            (db_portal_admin, db_role_admin),
            (db_superuser, db_role_viewer),
        ]
        for actor, role in actors:
            # RolePolicy — tenta revogar a própria role
            role_policy = RolePolicy(actor, role)
            assert role_policy.can_revoke_role_from_user(actor) is False, (
                f"can_revoke_role_from_user deveria ser False para ator={actor.username}"
            )

            # UserRolePolicy — userrole.user == actor
            userrole = UserRole(user=actor, role=role, aplicacao=db_app_ready)
            # Ajuste para superuser que não tem UserRole em app_ready
            userrole.user_id = actor.pk
            ur_policy = UserRolePolicy(actor, userrole)
            assert ur_policy.can_delete_userrole() is False, (
                f"can_delete_userrole deveria ser False (auto-remoção) para ator={actor.username}"
            )


# ─────────────────────────────────────────────────────────────────────────────────
# CLASS 4: ESCOPO DO GESTOR
# ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGestorScopeCoherence:
    """
    Gestor tem pode_editar_usuario=True mas sem privilégio total.
    Seu escopo deve ser coerente por todas as policies.
    """

    def test_gestor_can_view_profile_and_userroles_of_user_in_same_app(
        self,
        db_gestor,
        db_regular_user,
        db_app_ready,
        db_role_viewer,
    ):
        """
        UserProfilePolicy.can_view_profile(profile=regular_user.profile) → True
        UserRolePolicy.can_view_userroles_of_user(target=regular_user) → True
        (regular_user está na mesma app que gestor)
        """
        profile_policy = UserProfilePolicy(db_gestor, db_regular_user.profile)
        assert profile_policy.can_view_profile() is True

        userrole_of_regular = UserRole.objects.get(
            user=db_regular_user, aplicacao=db_app_ready
        )
        ur_policy = UserRolePolicy(db_gestor, userrole_of_regular)
        assert ur_policy.can_view_userroles_of_user(db_regular_user) is True

    def test_gestor_cannot_view_profile_or_userroles_of_isolated_user(
        self,
        db_gestor,
        db_isolated_user,
        db_app_other,
        db_role_other,
    ):
        """
        UserProfilePolicy.can_view_profile(profile=isolated_user.profile) → False
        UserRolePolicy.can_view_userroles_of_user(target=isolated_user) → False
        (isolated_user está em app diferente — sem interseção)
        """
        profile_policy = UserProfilePolicy(db_gestor, db_isolated_user.profile)
        assert profile_policy.can_view_profile() is False

        userrole_of_isolated = UserRole.objects.get(
            user=db_isolated_user, aplicacao=db_app_other
        )
        ur_policy = UserRolePolicy(db_gestor, userrole_of_isolated)
        assert ur_policy.can_view_userroles_of_user(db_isolated_user) is False

    def test_gestor_cannot_change_classificacao_or_status_even_in_same_app(
        self,
        db_gestor,
        db_regular_user,
    ):
        """
        UserProfilePolicy.can_change_classificacao() → False para gestor
        UserProfilePolicy.can_change_status() → False para gestor
        Mesmo com interseção de app, campos sensíveis exigem privilégio.
        """
        policy = UserProfilePolicy(db_gestor, db_regular_user.profile)
        assert policy.can_change_classificacao() is False
        assert policy.can_change_status() is False

    def test_gestor_cannot_create_or_delete_userroles(
        self,
        db_gestor,
        db_regular_user,
        db_app_ready,
        db_role_viewer,
    ):
        """
        UserRolePolicy.can_create_userrole() → False para gestor
        UserRolePolicy.can_delete_userrole() → False para gestor
        Gestor nunca gerencia vínculos — apenas visualiza.
        """
        userrole = UserRole.objects.get(
            user=db_regular_user, aplicacao=db_app_ready
        )
        policy_create = UserRolePolicy(db_gestor, userrole)
        assert policy_create.can_create_userrole() is False

        policy_delete = UserRolePolicy(db_gestor, userrole)
        assert policy_delete.can_delete_userrole() is False


# ─────────────────────────────────────────────────────────────────────────────────
# CLASS 5: ISOLAMENTO DE SESSÃO
# ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSessionIsolation:
    """
    Sessões Django são estritamente isoladas por usuário.

    Pós-Fase-0: a autentição é baseada em cookie de sessão Django
    (gpp_session), sem JWT. AccountsSession registra a sessão ativa
    sem campo jti.
    """

    def test_user_cannot_see_session_of_another_user(
        self,
        db_gestor,
        db_regular_user,
    ):
        """
        SessionPolicy.can_view_session(session.user != actor) → False
        Mesmo que actor seja gestor com pode_editar_usuario=True.
        Sessões não seguem escopo de app — são estritamente por ownership.
        """
        session_of_regular = _make_session(db_regular_user)

        # gestor tentando ver sessão de outro usuário
        policy = SessionPolicy(db_gestor, session_of_regular)
        assert policy.can_view_session() is False

        # regular tentando ver sessão do gestor
        session_of_gestor = _make_session(db_gestor)
        policy_reverse = SessionPolicy(db_regular_user, session_of_gestor)
        assert policy_reverse.can_view_session() is False

    def test_portal_admin_can_revoke_session_of_any_user(
        self,
        db_portal_admin,
        db_regular_user,
        db_gestor,
    ):
        """
        SessionPolicy.can_revoke_session(session.user=qualquer) → True para PORTAL_ADMIN
        Útil para resposta a incidentes de segurança.
        """
        session_regular = _make_session(db_regular_user)
        session_gestor = _make_session(db_gestor)

        policy_regular = SessionPolicy(db_portal_admin, session_regular)
        assert policy_regular.can_revoke_session() is True

        policy_gestor = SessionPolicy(db_portal_admin, session_gestor)
        assert policy_gestor.can_revoke_session() is True
