"""
GPP Plataform 2.0 — Testes da Fase 12 (Issue #25)

PARTE 1 — Auditoria de leituras de auth_user_groups (ADR-PERM-01)
PARTE 2 — Validação da limpeza de resíduos do token_blacklist

Critérios de aceite cobertos:
  ✅ Nenhuma leitura operacional de auth_user_groups em código de autorização
  ✅ ADR-PERM-01 confirmado: user.user_permissions é a única fonte de verdade
  ✅ Zero registros de token_blacklist em django_content_type
  ✅ Zero registros de token_blacklist em auth_permission
  ✅ Zero usuários com perms de token_blacklist em auth_user_user_permissions
  ✅ Migration de limpeza é idempotente (pode rodar N vezes sem erro)

Referências: ADR-PERM-01, PERMISSIONS_ARCHITECTURE.md, Issue #25 Fase 12.
"""
import importlib
import inspect

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


# =============================================================================
# PARTE 1 — Auditoria de auth_user_groups
# =============================================================================

@pytest.mark.django_db
class TestAuthUserGroupsAudit:
    """
    Verifica que o código operacional de autorização NÃO usa
    user.groups como fonte de verdade (ADR-PERM-01).

    auth_user_groups é legado passivo — não é populada e não deve
    ser lida para decisões de autorização.
    """

    def test_authorization_service_does_not_read_user_groups_for_authz(self):
        """
        AuthorizationService._load_permissions() não deve consultar
        user.groups — deve usar apenas:
          - auth_group_permissions via role.group_id (template)
          - user.user_permissions (fonte de verdade em runtime)
          - UserPermissionOverride (grants e revokes)
        """
        from apps.accounts.services.authorization_service import AuthorizationService

        source = inspect.getsource(AuthorizationService._load_permissions)

        assert "user.groups" not in source, (
            "FALHA ADR-PERM-01: AuthorizationService._load_permissions() "
            "não pode consultar user.groups para decisões de autorização. "
            "Use user.user_permissions (auth_user_user_permissions)."
        )
        assert "auth_user_groups" not in source, (
            "FALHA ADR-PERM-01: AuthorizationService._load_permissions() "
            "não pode referenciar auth_user_groups."
        )

    def test_authorization_service_reads_user_permissions_as_source_of_truth(self):
        """
        AuthorizationService._load_permissions() deve ler de
        user.user_permissions (fonte de verdade per ADR-PERM-01).
        """
        from apps.accounts.services.authorization_service import AuthorizationService

        source = inspect.getsource(AuthorizationService._load_permissions)

        assert "user.user_permissions" in source, (
            "FALHA ADR-PERM-01: AuthorizationService._load_permissions() "
            "deve ler de user.user_permissions como fonte de verdade."
        )

    def test_me_permission_serializer_does_not_use_user_groups_for_granted(self):
        """
        MePermissionSerializer.get_granted() não deve usar user.groups
        para decidir quais permissões retornar.
        """
        from apps.accounts.serializers import MePermissionSerializer

        source = inspect.getsource(MePermissionSerializer.get_granted)

        assert "user.groups" not in source, (
            "FALHA ADR-PERM-01: MePermissionSerializer.get_granted() "
            "não pode usar user.groups para determinar permissões concedidas."
        )

    def test_me_permission_serializer_reads_user_permissions_as_source_of_truth(self):
        """
        MePermissionSerializer.get_granted() deve ler de
        user.user_permissions como fonte de verdade.
        """
        from apps.accounts.serializers import MePermissionSerializer

        source = inspect.getsource(MePermissionSerializer.get_granted)

        assert "user.user_permissions" in source, (
            "FALHA ADR-PERM-01: MePermissionSerializer.get_granted() "
            "deve ler de user.user_permissions como fonte de verdade."
        )

    def test_middleware_does_not_use_user_groups_for_authz(self):
        """
        AppContextMiddleware não deve usar user.groups para decisões
        de autorização. Verifica a checagem de portal_admin que usa
        UserRole, não user.groups.
        """
        from apps.accounts import middleware

        source = inspect.getsource(middleware)

        assert "UserRole" in source, (
            "AppContextMiddleware deve usar UserRole para checar portal_admin."
        )
        assert "user.groups.filter" not in source, (
            "FALHA ADR-PERM-01: AppContextMiddleware não pode usar "
            "user.groups.filter() para decisões de autorização."
        )

    def test_permission_sync_does_not_populate_auth_user_groups(self, db):
        """
        sync_user_permissions() não deve adicionar o usuário a
        auth_user_groups. Grupos são templates; suas permissões são
        COPIADAS para auth_user_user_permissions, nunca via M2M de grupos.

        FIX: factories.py não exporta AplicacaoFactory. make_role() já
        cria Aplicacao internamente. Usa make_user() + make_user_role()
        que é o padrão correto do projeto.
        """
        from apps.accounts.tests.factories import UserFactory, make_user_role
        from apps.accounts.services.permission_sync import sync_user_permissions

        # make_user_role cria user + role + aplicacao + dispara sync
        user = UserFactory()
        make_user_role(user=user)  # cria role com aplicacao interna

        # Verifica estado pós-sync: user.groups deve continuar vazio
        user.refresh_from_db()
        assert user.groups.count() == 0, (
            "FALHA ADR-PERM-01: sync_user_permissions() populou auth_user_groups. "
            "Grupos são templates — permissões devem ser COPIADAS para "
            "auth_user_user_permissions, nunca adicionando o usuário ao grupo."
        )

        # Segundo sync (idempotente) — ainda não deve popular auth_user_groups
        sync_user_permissions(user)
        user.refresh_from_db()
        assert user.groups.count() == 0, (
            "FALHA ADR-PERM-01: segundo sync_user_permissions() populou "
            "auth_user_groups."
        )


# =============================================================================
# PARTE 2 — Limpeza de resíduos do token_blacklist
# =============================================================================

@pytest.mark.django_db
class TestTokenBlacklistCleanupMigration:
    """
    Testa a função de limpeza `clean_token_blacklist` da migration 0010.

    O import do módulo é feito via importlib (nome começa com dígito,
    não é identificador Python válido para import direto).

    Para invocar a função fora do contexto da migration, passamos
    `django_apps` (registry real) como argumento `apps`, que suporta
    .get_model() de forma idêntica ao registry histórico das migrations
    em um banco já migrado.
    """

    def _load_clean_fn(self):
        """Carrega clean_token_blacklist via importlib (nome com dígito)."""
        module = importlib.import_module(
            'apps.accounts.migrations.0010_clean_token_blacklist_residues'
        )
        return module.clean_token_blacklist

    def test_no_token_blacklist_content_types_in_clean_db(self):
        """
        No banco de testes limpo, não deve haver content types com
        app_label='token_blacklist'. Critério de aceite CA-03.
        """
        cts = ContentType.objects.filter(app_label='token_blacklist')
        assert not cts.exists(), (
            f"FALHA CA-03: Encontrados content types residuais de token_blacklist: "
            f"{list(cts.values('id', 'app_label', 'model'))}"
        )

    def test_no_token_blacklist_permissions_in_clean_db(self):
        """
        No banco de testes limpo, não deve haver permissões com
        content_type__app_label='token_blacklist'. Critério de aceite CA-03.
        """
        perms = Permission.objects.filter(
            content_type__app_label='token_blacklist'
        )
        assert not perms.exists(), (
            f"FALHA CA-03: Encontradas permissões residuais de token_blacklist: "
            f"{list(perms.values('id', 'codename'))}"
        )

    def test_no_users_with_token_blacklist_permissions_in_clean_db(self):
        """
        No banco de testes limpo, nenhum usuário deve ter permissões
        de token_blacklist em auth_user_user_permissions.
        Critério de aceite CA-04.
        """
        affected = User.objects.filter(
            user_permissions__content_type__app_label='token_blacklist'
        ).exists()
        assert not affected, (
            "FALHA CA-04: Existem usuários com perms de token_blacklist "
            "em auth_user_user_permissions."
        )

    def test_clean_function_is_idempotent_on_empty_db(self):
        """
        Testa que clean_token_blacklist() é idempotente quando chamada
        em banco sem resíduos. Critério de aceite CA-05.

        FIX: passa django_apps (registry real) em vez de None.
        A função usa apps.get_model() — django_apps suporta isso
        identicamente ao registry histórico das migrations em banco
        já migrado. schema_editor não é usado pela função, pode ser None.
        """
        clean_fn = self._load_clean_fn()

        # 1ª execução — banco limpo, deve retornar imediatamente via guard
        try:
            clean_fn(django_apps, None)
        except Exception as exc:
            pytest.fail(
                f"FALHA CA-05: clean_token_blacklist() lançou exceção "
                f"em banco limpo (1ª execução): {exc}"
            )

        # 2ª execução — idempotente
        try:
            clean_fn(django_apps, None)
        except Exception as exc:
            pytest.fail(
                f"FALHA CA-05: clean_token_blacklist() não é idempotente: "
                f"lançou exceção na 2ª execução: {exc}"
            )

    def test_clean_function_removes_residual_content_types_and_permissions(self):
        """
        Testa que a lógica de limpeza remove ContentTypes e Permissions
        residuais de token_blacklist. Simula banco legado.
        Critério de aceite CA-03.
        """
        # Setup: cria resíduos simulados
        ct = ContentType.objects.create(
            app_label='token_blacklist',
            model='blacklistedtoken',
        )
        Permission.objects.create(
            codename='test_blacklistedtoken_perm',
            name='Test token_blacklist perm',
            content_type=ct,
        )

        assert ContentType.objects.filter(app_label='token_blacklist').exists(), (
            "Setup falhou: ContentType de token_blacklist deveria existir."
        )
        assert Permission.objects.filter(
            content_type__app_label='token_blacklist'
        ).exists(), "Setup falhou: Permission de token_blacklist deveria existir."

        # Executa a função de limpeza real via django_apps
        clean_fn = self._load_clean_fn()
        clean_fn(django_apps, None)

        # Validação pós-limpeza
        assert not ContentType.objects.filter(app_label='token_blacklist').exists(), (
            "FALHA CA-03: ContentTypes de token_blacklist não foram removidos."
        )
        assert not Permission.objects.filter(
            content_type__app_label='token_blacklist'
        ).exists(), (
            "FALHA CA-03: Permissões de token_blacklist não foram removidas."
        )

    def test_clean_removes_user_permissions_m2m_links(self):
        """
        Testa que a limpeza remove linhas de auth_user_user_permissions
        que referenciam perms de token_blacklist.
        Critério de aceite CA-04.
        """
        from apps.accounts.tests.factories import UserFactory

        user = UserFactory()

        # Setup: cria resíduos simulados e vincula ao usuário
        ct = ContentType.objects.create(
            app_label='token_blacklist',
            model='outstandingtoken',
        )
        perm = Permission.objects.create(
            codename='test_outstandingtoken_perm',
            name='Test token_blacklist outstanding perm',
            content_type=ct,
        )
        user.user_permissions.add(perm)

        assert user.user_permissions.filter(
            content_type__app_label='token_blacklist'
        ).exists(), "Setup falhou: usuário deveria ter perm de token_blacklist."

        # Executa a função de limpeza real via django_apps
        clean_fn = self._load_clean_fn()
        clean_fn(django_apps, None)

        # Recarrega do banco para limpar cache de permissões do Django
        user = User.objects.get(pk=user.pk)
        assert not user.user_permissions.filter(
            content_type__app_label='token_blacklist'
        ).exists(), (
            "FALHA CA-04: auth_user_user_permissions ainda contém "
            "perms de token_blacklist após limpeza."
        )

    def test_clean_function_is_idempotent_after_cleanup(self):
        """
        Testa que clean_token_blacklist() pode ser chamada N vezes
        após já ter limpado o banco, sem lançar exceção.
        Critério de aceite CA-05 — idempotência completa.
        """
        clean_fn = self._load_clean_fn()

        # Cria resíduos e executa limpeza
        ct = ContentType.objects.create(
            app_label='token_blacklist',
            model='blacklistedtoken_idempotent',
        )
        Permission.objects.create(
            codename='test_idempotent_perm',
            name='Test idempotent perm',
            content_type=ct,
        )

        clean_fn(django_apps, None)  # 1ª execução: limpa

        # 2ª e 3ª execuções — banco já limpo, guard deve proteger
        try:
            clean_fn(django_apps, None)
            clean_fn(django_apps, None)
        except Exception as exc:
            pytest.fail(
                f"FALHA CA-05: clean_token_blacklist() não é idempotente: "
                f"lançou exceção em execuções subsequentes: {exc}"
            )
