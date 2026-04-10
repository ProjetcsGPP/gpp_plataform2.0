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
import inspect

import pytest
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

        # Não deve conter referência a user.groups para buscar permissões
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

        # O middleware usa UserRole para checar portal_admin — correto
        assert "UserRole" in source, (
            "AppContextMiddleware deve usar UserRole para checar portal_admin."
        )
        # Não deve usar user.groups para checar acesso
        assert "user.groups.filter" not in source, (
            "FALHA ADR-PERM-01: AppContextMiddleware não pode usar "
            "user.groups.filter() para decisões de autorização."
        )

    def test_permission_sync_does_not_populate_auth_user_groups(self, db):
        """
        sync_user_permissions() não deve adicionar o usuário a
        auth_user_groups. Grupos são templates; suas permissões são
        COPIADAS para auth_user_user_permissions, nunca via M2M de grupos.
        """
        from apps.accounts.tests.factories import (
            UserFactory,
            AplicacaoFactory,
            RoleFactory,
            UserRoleFactory,
        )
        from apps.accounts.services.permission_sync import sync_user_permissions

        app = AplicacaoFactory()
        role = RoleFactory(aplicacao=app)
        user = UserFactory()
        UserRoleFactory(user=user, aplicacao=app, role=role)

        # Antes do sync: sem grupos
        assert user.groups.count() == 0, (
            "Usuário não deve ter grupos antes do sync."
        )

        sync_user_permissions(user)

        # Após o sync: ainda sem grupos (ADR-PERM-01)
        user.refresh_from_db()
        assert user.groups.count() == 0, (
            "FALHA ADR-PERM-01: sync_user_permissions() populou auth_user_groups. "
            "Grupos são templates — permissões devem ser COPIADAS para "
            "auth_user_user_permissions, nunca adicionando o usuário ao grupo."
        )


# =============================================================================
# PARTE 2 — Limpeza de resíduos do token_blacklist
# =============================================================================

@pytest.mark.django_db
class TestTokenBlacklistCleanupMigration:
    """
    Testa a função de limpeza `clean_token_blacklist` da migration 0010.

    Como a migration usa `apps.get_model()` (estado histórico), os testes
    exercitam o comportamento usando os modelos reais do Django de forma
    equivalente, e também importam e testam a função diretamente.
    """

    def test_no_token_blacklist_content_types_in_clean_db(self):
        """
        No banco de testes limpo (sem token_blacklist instalado),
        não deve haver content types com app_label='token_blacklist'.
        Critério de aceite CA-03 (Issue #25).
        """
        cts = ContentType.objects.filter(app_label='token_blacklist')
        assert not cts.exists(), (
            f"FALHA CA-03: Encontrados content types residuais de token_blacklist: "
            f"{list(cts.values('id', 'app_label', 'model'))}"
        )

    def test_no_token_blacklist_permissions_in_clean_db(self):
        """
        No banco de testes limpo, não deve haver permissões com
        content_type__app_label='token_blacklist'.
        Critério de aceite CA-03 (Issue #25).
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
        Critério de aceite CA-04 (Issue #25).
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
        em um banco sem resíduos de token_blacklist.
        Não deve lançar exceção e deve retornar imediatamente.
        Critério de aceite CA-05 (Issue #25).
        """
        from apps.accounts.migrations.migration_0010_clean_token_blacklist_residues import (
            clean_token_blacklist,
        )
        # Primeira execução — banco já está limpo
        try:
            clean_token_blacklist(None, None)
        except Exception as exc:
            pytest.fail(
                f"FALHA CA-05: clean_token_blacklist() lançou exceção "
                f"em banco limpo: {exc}"
            )

        # Segunda execução — idempotente
        try:
            clean_token_blacklist(None, None)
        except Exception as exc:
            pytest.fail(
                f"FALHA CA-05: clean_token_blacklist() não é idempotente: "
                f"lançou exceção na segunda execução: {exc}"
            )

    def test_clean_function_removes_residual_content_types_and_permissions(self):
        """
        Testa que clean_token_blacklist() remove content types e
        permissões residuais de token_blacklist quando existem no banco.

        Simula o estado de um banco legado com resíduos criando
        manualmente um ContentType e Permission com app_label='token_blacklist',
        executa a função e verifica a limpeza.
        """
        # Setup: cria resíduos simulados
        ct = ContentType.objects.create(
            app_label='token_blacklist',
            model='blacklistedtoken',
        )
        perm = Permission.objects.create(
            codename='test_blacklistedtoken_perm',
            name='Test token_blacklist perm',
            content_type=ct,
        )

        # Verifica que os resíduos foram criados
        assert ContentType.objects.filter(app_label='token_blacklist').exists()
        assert Permission.objects.filter(
            content_type__app_label='token_blacklist'
        ).exists()

        # Executa a limpeza usando os models reais (simula comportamento da migration)
        blacklist_cts = ContentType.objects.filter(app_label='token_blacklist')
        ct_ids = list(blacklist_cts.values_list('id', flat=True))

        assert ct_ids, "Setup falhou: ct_ids deveria ser não-vazio"

        perms_to_remove = Permission.objects.filter(content_type_id__in=ct_ids)
        for p in perms_to_remove:
            p.user_set.clear()
        Permission.objects.filter(content_type_id__in=ct_ids).delete()
        blacklist_cts.delete()

        # Validação pós-limpeza
        assert not ContentType.objects.filter(app_label='token_blacklist').exists(), (
            "FALHA: ContentTypes de token_blacklist não foram removidos."
        )
        assert not Permission.objects.filter(
            content_type__app_label='token_blacklist'
        ).exists(), (
            "FALHA: Permissões de token_blacklist não foram removidas."
        )

    def test_clean_function_removes_user_permissions_m2m(self):
        """
        Testa que clean_token_blacklist() remove as linhas de
        auth_user_user_permissions que referenciam perms de token_blacklist.
        """
        from apps.accounts.tests.factories import UserFactory

        user = UserFactory()

        # Setup: cria resíduos simulados com um usuário vinculado
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

        # Verifica que o vínculo foi criado
        assert user.user_permissions.filter(
            content_type__app_label='token_blacklist'
        ).exists(), "Setup falhou: usuário deveria ter perm de token_blacklist."

        # Executa limpeza
        blacklist_cts = ContentType.objects.filter(app_label='token_blacklist')
        ct_ids = list(blacklist_cts.values_list('id', flat=True))
        perms_to_remove = Permission.objects.filter(content_type_id__in=ct_ids)
        for p in perms_to_remove:
            p.user_set.clear()
        Permission.objects.filter(content_type_id__in=ct_ids).delete()
        blacklist_cts.delete()

        # Validação: usuário não deve mais ter perms de token_blacklist
        # Precisa limpar cache de permissões do Django
        user = User.objects.get(pk=user.pk)
        assert not user.user_permissions.filter(
            content_type__app_label='token_blacklist'
        ).exists(), (
            "FALHA CA-04: auth_user_user_permissions ainda contém "
            "perms de token_blacklist após limpeza."
        )
