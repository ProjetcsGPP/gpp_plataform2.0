"""
Testes das 3 lacunas de cobertura identificadas na auditoria (Issue #14).

Lacuna 1: override ``grant`` — permissão não herdada pela role é concedida
Lacuna 2: override ``revoke`` — permissão da role é removida
Lacuna 3: ``user.user_permissions`` diretas são incluídas no set final

Estratégia:
  - Banco real (pytest.mark.django_db) — sem mocks no service.
  - auth.Permission criada via ContentType genérico (ContentType do próprio
    modelo User) para não depender de ContentType específico da aplicação.
  - cache.clear() antes de cada teste para garantir cache miss.
  - UserPermissionOverride criado via .objects.create() (invoca full_clean).
  - Cada teste verifica o comportamento positivo E o negativo quando
    relevança (ex: sem override a permissão NÃO aparece; com override, aparece).
"""
import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

from apps.accounts.models import UserPermissionOverride
from apps.accounts.services.authorization_service import AuthorizationService

# CORRIGIDO (Issue #22 Falha 2): pytestmark no nível de módulo não é herdado
# por classes em pytest — o marcador precisa estar em cada classe ou método.
# Removido o pytestmark global e adicionado @pytest.mark.django_db em cada classe.


def _make_permission(codename: str, name: str = None) -> Permission:
    ct = ContentType.objects.get_for_model(User)
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=ct,
        defaults={"name": name or codename},
    )
    return perm


@pytest.mark.django_db
class TestOverrideGrant:
    """
    Lacuna 1: um override mode='grant' deve adicionar ao set final uma
    permissão que o usuário NÃO herdaria pelo grupo da sua role.
    """

    def test_sem_grant_override_permissao_ausente(self, gestor_pngi):
        _make_permission("perm_exclusiva_grant_test")
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        perms = service._load_permissions()
        assert "perm_exclusiva_grant_test" not in perms

    def test_grant_override_adiciona_permissao(self, gestor_pngi):
        perm = _make_permission("perm_exclusiva_grant_test")
        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
            defaults={"source": "teste lacuna 1"},
        )
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        perms = service._load_permissions()
        assert "perm_exclusiva_grant_test" in perms

    def test_grant_override_permite_can(self, gestor_pngi):
        perm = _make_permission("perm_can_grant_test")
        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
            defaults={"source": "teste can + grant"},
        )
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        assert service.can("perm_can_grant_test") is True

    def test_grant_override_nao_afeta_outro_usuario(self, gestor_pngi, operador_acao):
        perm = _make_permission("perm_isolada_por_usuario")
        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
            defaults={"source": "isolamento"},
        )
        cache.clear()
        service_outro = AuthorizationService(operador_acao)
        perms = service_outro._load_permissions()
        assert "perm_isolada_por_usuario" not in perms


@pytest.mark.django_db
class TestOverrideRevoke:
    """
    Lacuna 2: um override mode='revoke' deve remover do set final uma
    permissão que o usuário HERDARIA pelo grupo da sua role.
    """

    def _grant_perm_to_group(self, user, codename: str) -> Permission:
        perm = _make_permission(codename)
        from apps.accounts.models import UserRole
        user_role = UserRole.objects.filter(user=user).select_related("role__group").first()
        assert user_role is not None, "usuário precisa ter ao menos uma role"
        assert user_role.role.group is not None, "role precisa ter grupo"
        user_role.role.group.permissions.add(perm)
        return perm

    def test_sem_revoke_permissao_herdada_presente(self, gestor_pngi):
        perm = self._grant_perm_to_group(gestor_pngi, "perm_herdada_revoke_test")
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        perms = service._load_permissions()
        assert "perm_herdada_revoke_test" in perms

    def test_revoke_override_remove_permissao_herdada(self, gestor_pngi):
        perm = self._grant_perm_to_group(gestor_pngi, "perm_herdada_revoke_test")
        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
            defaults={"source": "teste lacuna 2"},
        )
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        perms = service._load_permissions()
        assert "perm_herdada_revoke_test" not in perms

    def test_revoke_faz_can_retornar_false(self, gestor_pngi):
        perm = self._grant_perm_to_group(gestor_pngi, "perm_can_revoke_test")
        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
            defaults={"source": "teste can + revoke"},
        )
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        assert service.can("perm_can_revoke_test") is False

    def test_revoke_nao_afeta_outro_usuario(self, gestor_pngi, operador_acao):
        perm = self._grant_perm_to_group(gestor_pngi, "perm_revoke_isolamento")
        from apps.accounts.models import UserRole
        op_role = UserRole.objects.filter(user=operador_acao).select_related("role__group").first()
        if op_role and op_role.role.group:
            op_role.role.group.permissions.add(perm)

        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
            defaults={"source": "isolamento revoke"},
        )
        cache.clear()
        service_outro = AuthorizationService(operador_acao)
        perms = service_outro._load_permissions()
        assert "perm_revoke_isolamento" in perms


@pytest.mark.django_db
class TestUserPermissoesDiretas:
    """
    Lacuna 3: permissões atribuídas diretamente ao usuário via
    auth_user_user_permissions devem aparecer no set de _load_permissions().
    """

    def test_sem_user_permission_direta_ausente(self, operador_acao):
        _make_permission("perm_direta_user_test")
        cache.clear()
        service = AuthorizationService(operador_acao)
        perms = service._load_permissions()
        assert "perm_direta_user_test" not in perms

    def test_user_permission_direta_incluida_no_set(self, operador_acao):
        perm = _make_permission("perm_direta_user_test")
        operador_acao.user_permissions.add(perm)
        cache.clear()
        service = AuthorizationService(operador_acao)
        perms = service._load_permissions()
        assert "perm_direta_user_test" in perms

    def test_user_permission_direta_permite_can(self, operador_acao):
        perm = _make_permission("perm_can_direta_test")
        operador_acao.user_permissions.add(perm)
        cache.clear()
        service = AuthorizationService(operador_acao)
        assert service.can("perm_can_direta_test") is True

    def test_user_permission_direta_nao_afeta_outro_usuario(self, operador_acao, gestor_carga):
        perm = _make_permission("perm_direta_isolada")
        operador_acao.user_permissions.add(perm)
        cache.clear()
        service_outro = AuthorizationService(gestor_carga)
        perms = service_outro._load_permissions()
        assert "perm_direta_isolada" not in perms

    def test_user_permission_direta_pode_ser_revocada_por_override(self, operador_acao):
        perm = _make_permission("perm_direta_override_revoke")
        operador_acao.user_permissions.add(perm)
        UserPermissionOverride.objects.get_or_create(
            user=operador_acao,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
            defaults={"source": "revoke sobre direta"},
        )
        cache.clear()
        service = AuthorizationService(operador_acao)
        perms = service._load_permissions()
        assert "perm_direta_override_revoke" not in perms


@pytest.mark.django_db
class TestInteracaoFontes:
    """
    Garante que as 3 fontes (grupo, user_permissions, overrides)
    se combinam corretamente no resultado final.
    """

    def test_grant_plus_role_group_union(self, gestor_pngi):
        perm_grupo = _make_permission("perm_grupo_union")
        perm_grant = _make_permission("perm_grant_union")

        from apps.accounts.models import UserRole
        ur = UserRole.objects.filter(user=gestor_pngi).select_related("role__group").first()
        ur.role.group.permissions.add(perm_grupo)

        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm_grant,
            mode=UserPermissionOverride.MODE_GRANT,
            defaults={"source": "união teste"},
        )
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        perms = service._load_permissions()
        assert "perm_grupo_union" in perms
        assert "perm_grant_union" in perms

    def test_revoke_vence_grant_do_grupo(self, gestor_pngi):
        perm = _make_permission("perm_revoke_vence_grupo")

        from apps.accounts.models import UserRole
        ur = UserRole.objects.filter(user=gestor_pngi).select_related("role__group").first()
        ur.role.group.permissions.add(perm)

        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
            defaults={"source": "revoke vence grupo"},
        )
        cache.clear()
        service = AuthorizationService(gestor_pngi)
        perms = service._load_permissions()
        assert "perm_revoke_vence_grupo" not in perms

    def test_revoke_vence_user_permissions_diretas(self, operador_acao):
        perm = _make_permission("perm_revoke_vence_direta")
        operador_acao.user_permissions.add(perm)
        UserPermissionOverride.objects.get_or_create(
            user=operador_acao,
            permission=perm,
            mode=UserPermissionOverride.MODE_REVOKE,
            defaults={"source": "revoke vence direta"},
        )
        cache.clear()
        service = AuthorizationService(operador_acao)
        perms = service._load_permissions()
        assert "perm_revoke_vence_direta" not in perms

    def test_cache_invalida_apos_novo_override(self, gestor_pngi):
        perm = _make_permission("perm_cache_invalida")
        cache.clear()

        service1 = AuthorizationService(gestor_pngi)
        perms1 = service1._load_permissions()
        assert "perm_cache_invalida" not in perms1

        UserPermissionOverride.objects.get_or_create(
            user=gestor_pngi,
            permission=perm,
            mode=UserPermissionOverride.MODE_GRANT,
            defaults={"source": "pós-cache"},
        )
        cache.clear()

        service2 = AuthorizationService(gestor_pngi)
        perms2 = service2._load_permissions()
        assert "perm_cache_invalida" in perms2
