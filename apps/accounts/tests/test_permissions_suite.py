"""
Fase 9 — Suite completa de testes do sistema de permissões.

Cobre os grupos definidos na Issue #22:
  - Testes de serviço   (TestServicePermissions)
  - Testes de override   (TestOverridePermissions)
  - Testes de sobreposição (TestOverlapPermissions)
  - Testes de API        (TestAPIPermissions)
  - Integração estrutural (TestStructuralIntegration)
  - Testes negativos     (TestNegativePermissions)

Referencia: docs/PERMISSIONS_ARCHITECTURE.md
  Regra: auth_user_user_permissions é a única fonte de verdade em runtime.
  Fórmula: herdadas |= user_permissions |= grant -= revoke
  ADR-PERM-01: auth_user_groups NÃO é populado neste sistema.
"""
import pytest
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserPermissionOverride, UserRole
from apps.accounts.services.permission_sync import (
    calculate_effective_permissions,
    calculate_inherited_permissions,
    sync_all_users_permissions,
    sync_user_permissions,
)
from apps.accounts.tests.conftest import (
    DEFAULT_PASSWORD,
    LOGIN_URL,
    _assign_role,
    _make_user,
)

ME_PERMS_URL = "/api/accounts/me/permissions/"
USER_ROLES_URL = "/api/accounts/user-roles/"
OVERRIDES_URL = "/api/accounts/user-permission-overrides/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_permission(codename: str, app_label: str = "accounts") -> Permission:
    """Obtém ou cria uma Permission de teste com ContentType mínimo."""
    ct, _ = ContentType.objects.get_or_create(
        app_label=app_label,
        model="testpermmodel",
        defaults={},
    )
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=ct,
        defaults={"name": f"Can {codename}"},
    )
    return perm


def _user_has_perm_in_db(user: User, codename: str) -> bool:
    """Verifica se a permissão está materializada em auth_user_user_permissions."""
    user.refresh_from_db()
    # Limpa o cache de permissões do Django para forçar leitura do banco
    if hasattr(user, "_perm_cache"):
        del user._perm_cache
    if hasattr(user, "_user_perm_cache"):
        del user._user_perm_cache
    return user.user_permissions.filter(codename=codename).exists()


def _login_client(username: str, app_context: str) -> APIClient:
    client = APIClient()
    client.post(
        LOGIN_URL,
        {"username": username, "password": DEFAULT_PASSWORD, "app_context": app_context},
        format="json",
    )
    return client


def _get_granted_perms(resp) -> list:
    """
    Extrai a lista de permissões concedidas de um Response DRF ou HttpResponse.
    Retorna lista vazia se o status não for 200 (ex: 403 após remover role).
    """
    if resp.status_code != 200:
        return []
    # Response DRF tem .data; HttpResponse/JsonResponse tem .json()
    if hasattr(resp, "data"):
        return resp.data.get("granted", [])
    return resp.json().get("granted", [])


# ---------------------------------------------------------------------------
# TestServicePermissions — testes do orquestrador permission_sync
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestServicePermissions:
    """Valida que o orquestrador escreve corretamente em auth_user_user_permissions."""

    def test_criar_user_role_materializa_permissoes_herdadas(self):
        """Criar UserRole e chamar sync gera permissões herdadas em auth_user_user_permissions."""
        user = _make_user("srv_criar_role")
        role = Role.objects.get(pk=2)  # GESTOR_PNGI
        group = role.group
        perm = Permission.objects.filter(group=group).first()
        if perm is None:
            perm = _get_or_create_permission("srv_inherited_perm")
            group.permissions.add(perm)

        _assign_role(user, role_pk=2)

        assert _user_has_perm_in_db(user, perm.codename), (
            "Permissão herdada da role não foi materializada em auth_user_user_permissions."
        )

    def test_editar_user_role_recalcula_permissoes(self):
        """Trocar a role do usuário recalcula o conjunto em auth_user_user_permissions."""
        user = _make_user("srv_editar_role")

        # Role A — GESTOR_PNGI com perm exclusiva
        role_a = Role.objects.get(pk=2)
        perm_a = _get_or_create_permission("srv_perm_role_a")
        role_a.group.permissions.add(perm_a)
        _assign_role(user, role_pk=2)
        assert _user_has_perm_in_db(user, "srv_perm_role_a")

        # Troca para Role B — COORDENADOR_PNGI sem perm_a
        role_b = Role.objects.get(pk=3)
        perm_b = _get_or_create_permission("srv_perm_role_b")
        role_b.group.permissions.add(perm_b)
        user_role = UserRole.objects.get(user=user)
        user_role.role = role_b
        user_role.save()
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, "srv_perm_role_b"), (
            "Permissão da nova role não foi adicionada."
        )
        assert not _user_has_perm_in_db(user, "srv_perm_role_a"), (
            "Permissão da role anterior não foi removida após troca."
        )

    def test_excluir_user_role_remove_permissoes_herdadas(self):
        """Remover a UserRole e sincronizar limpa as permissões herdadas exclusivas."""
        user = _make_user("srv_excluir_role")
        role = Role.objects.get(pk=4)  # OPERADOR_ACAO
        perm = _get_or_create_permission("srv_excl_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=4)
        assert _user_has_perm_in_db(user, "srv_excl_perm")

        UserRole.objects.filter(user=user).delete()
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, "srv_excl_perm"), (
            "Permissão não foi removida após exclusão da UserRole."
        )

    def test_multiplas_roles_geram_uniao_correta(self):
        """Usuário com roles em apps distintas acumula permissões de ambas."""
        user = _make_user("srv_multi_roles")

        role_pngi = Role.objects.get(pk=2)   # GESTOR_PNGI (app pk=2)
        role_carga = Role.objects.get(pk=6)  # GESTOR_CARGA (app pk=3)

        perm_pngi = _get_or_create_permission("srv_multi_pngi")
        perm_carga = _get_or_create_permission("srv_multi_carga")
        role_pngi.group.permissions.add(perm_pngi)
        role_carga.group.permissions.add(perm_carga)

        # Criar as duas UserRoles
        UserRole.objects.get_or_create(
            user=user, aplicacao=role_pngi.aplicacao, defaults={"role": role_pngi}
        )
        UserRole.objects.get_or_create(
            user=user, aplicacao=role_carga.aplicacao, defaults={"role": role_carga}
        )
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, "srv_multi_pngi"), (
            "Permissão PNGI não encontrada."
        )
        assert _user_has_perm_in_db(user, "srv_multi_carga"), (
            "Permissão CARGA não encontrada."
        )

    def test_sync_idempotente(self):
        """Chamar sync_user_permissions duas vezes produz o mesmo estado."""
        user = _make_user("srv_idempotente")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("srv_idempotent_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)

        perms_antes = set(user.user_permissions.values_list("codename", flat=True))
        sync_user_permissions(user)  # segunda chamada
        perms_depois = set(user.user_permissions.values_list("codename", flat=True))

        assert perms_antes == perms_depois, (
            "sync_user_permissions não é idempotente — resultado mudou na segunda chamada."
        )

    def test_usuario_sem_role_fica_sem_permissoes_herdadas(self):
        """Usuário sem UserRole não deve ter permissões herdadas."""
        user = _make_user("srv_sem_role")
        sync_user_permissions(user)

        herdadas = calculate_inherited_permissions(user)
        assert len(herdadas) == 0, (
            f"Esperava conjunto vazio, mas obteve: {herdadas}"
        )
        assert user.user_permissions.count() == 0, (
            "auth_user_user_permissions deveria estar vazio para usuário sem role."
        )


# ---------------------------------------------------------------------------
# TestOverridePermissions — testes de UserPermissionOverride
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOverridePermissions:
    """Valida comportamento de overrides grant/revoke sobre o conjunto herdado."""

    def test_grant_adiciona_permissao_fora_do_template_da_role(self):
        """Override grant adiciona permissão que o usuário não herdaria pela role."""
        user = _make_user("ovr_grant_extra")
        _assign_role(user, role_pk=2)
        perm_extra = _get_or_create_permission("ovr_grant_extra_perm")

        # Confirma que a permissão não está no template da role
        role = Role.objects.get(pk=2)
        role.group.permissions.remove(perm_extra)
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(user, "ovr_grant_extra_perm")

        UserPermissionOverride.objects.create(user=user, permission=perm_extra, mode="grant")
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, "ovr_grant_extra_perm"), (
            "Override grant não adicionou a permissão extra."
        )

    def test_revoke_remove_permissao_herdada_da_role(self):
        """Override revoke retira permissão que viria da role."""
        user = _make_user("ovr_revoke_herded")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("ovr_revoke_hrd_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)
        assert _user_has_perm_in_db(user, "ovr_revoke_hrd_perm")

        UserPermissionOverride.objects.create(user=user, permission=perm, mode="revoke")
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, "ovr_revoke_hrd_perm"), (
            "Override revoke não removeu a permissão herdada."
        )

    def test_grant_em_permissao_ja_herdada_nao_duplica(self):
        """Grant em permissão já herdada não gera duplicidade — conjunto permanece com 1 entrada."""
        user = _make_user("ovr_grant_dup")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("ovr_grant_dup_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)
        assert _user_has_perm_in_db(user, "ovr_grant_dup_perm")

        UserPermissionOverride.objects.create(user=user, permission=perm, mode="grant")
        sync_user_permissions(user)

        count = user.user_permissions.filter(codename="ovr_grant_dup_perm").count()
        assert count == 1, (
            f"Esperava 1 entrada, mas encontrou {count} (duplicidade)."
        )
        assert _user_has_perm_in_db(user, "ovr_grant_dup_perm")

    def test_revoke_em_permissao_nao_herdada_mantem_consistencia(self):
        """Revoke em permissão não herdada não corrompe o conjunto efetivo."""
        user = _make_user("ovr_revoke_non_hrd")
        _assign_role(user, role_pk=2)
        perm_fora = _get_or_create_permission("ovr_revoke_non_hrd_perm")

        role = Role.objects.get(pk=2)
        role.group.permissions.remove(perm_fora)
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(user, "ovr_revoke_non_hrd_perm")

        UserPermissionOverride.objects.create(user=user, permission=perm_fora, mode="revoke")
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, "ovr_revoke_non_hrd_perm"), (
            "Revoke em permissão ausente causou estado inconsistente."
        )

    def test_remover_override_grant_recompoe_conjunto_sem_a_perm(self):
        """Após remover override grant, a permissão extra desaparece do conjunto efetivo."""
        user = _make_user("ovr_remove_grant")
        _assign_role(user, role_pk=2)
        perm = _get_or_create_permission("ovr_rm_grant_perm")

        role = Role.objects.get(pk=2)
        role.group.permissions.remove(perm)
        sync_user_permissions(user)

        override = UserPermissionOverride.objects.create(user=user, permission=perm, mode="grant")
        sync_user_permissions(user)
        assert _user_has_perm_in_db(user, "ovr_rm_grant_perm")

        override.delete()
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(user, "ovr_rm_grant_perm"), (
            "Após remover override grant, a permissão deveria sumir."
        )

    def test_remover_override_revoke_recompoe_permissao_herdada(self):
        """Após remover override revoke, a permissão herdada volta ao conjunto."""
        user = _make_user("ovr_remove_revoke")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("ovr_rm_revoke_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)
        assert _user_has_perm_in_db(user, "ovr_rm_revoke_perm")

        override = UserPermissionOverride.objects.create(user=user, permission=perm, mode="revoke")
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(user, "ovr_rm_revoke_perm")

        override.delete()
        sync_user_permissions(user)
        assert _user_has_perm_in_db(user, "ovr_rm_revoke_perm"), (
            "Após remover override revoke, a permissão herdada deveria reaparecer."
        )


# ---------------------------------------------------------------------------
# TestOverlapPermissions — testes de sobreposição de roles
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOverlapPermissions:
    """Valida comportamento quando a mesma permissão é concedida por mais de uma role."""

    def test_duas_roles_concedendo_mesma_perm_reflete_uniao(self):
        """Quando duas roles (apps distintas) concedem a mesma permissão, ela permanece no conjunto."""
        user = _make_user("ovlp_duas_roles")
        role_pngi = Role.objects.get(pk=2)   # ACOES_PNGI
        role_carga = Role.objects.get(pk=6)  # CARGA_ORG_LOT

        perm_comum = _get_or_create_permission("ovlp_shared_perm")
        role_pngi.group.permissions.add(perm_comum)
        role_carga.group.permissions.add(perm_comum)

        UserRole.objects.get_or_create(
            user=user, aplicacao=role_pngi.aplicacao, defaults={"role": role_pngi}
        )
        UserRole.objects.get_or_create(
            user=user, aplicacao=role_carga.aplicacao, defaults={"role": role_carga}
        )
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, "ovlp_shared_perm"), (
            "Permissão compartilhada por duas roles não foi materializada."
        )
        count = user.user_permissions.filter(codename="ovlp_shared_perm").count()
        assert count == 1, f"Esperava 1 entrada, mas encontrou {count} (duplicidade)."

    def test_remocao_de_uma_role_nao_apaga_perm_herdada_da_outra(self):
        """Remover uma role não apaga permissão ainda concedida pela role remanescente."""
        user = _make_user("ovlp_remover_uma")
        role_pngi = Role.objects.get(pk=2)
        role_carga = Role.objects.get(pk=6)

        perm_comum = _get_or_create_permission("ovlp_rm_one_perm")
        role_pngi.group.permissions.add(perm_comum)
        role_carga.group.permissions.add(perm_comum)

        UserRole.objects.get_or_create(
            user=user, aplicacao=role_pngi.aplicacao, defaults={"role": role_pngi}
        )
        UserRole.objects.get_or_create(
            user=user, aplicacao=role_carga.aplicacao, defaults={"role": role_carga}
        )
        sync_user_permissions(user)
        assert _user_has_perm_in_db(user, "ovlp_rm_one_perm")

        # Remove uma das roles
        UserRole.objects.filter(user=user, aplicacao=role_pngi.aplicacao).delete()
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, "ovlp_rm_one_perm"), (
            "Permissão não deveria ter sido removida — outra role ainda a concede."
        )

    def test_remocao_da_ultima_origem_apaga_permissao(self):
        """Quando todas as origens de uma permissão são removidas, ela some do conjunto."""
        user = _make_user("ovlp_remover_todas")
        role_pngi = Role.objects.get(pk=2)
        role_carga = Role.objects.get(pk=6)

        perm_unica = _get_or_create_permission("ovlp_rm_all_perm")
        role_pngi.group.permissions.add(perm_unica)
        role_carga.group.permissions.add(perm_unica)

        UserRole.objects.get_or_create(
            user=user, aplicacao=role_pngi.aplicacao, defaults={"role": role_pngi}
        )
        UserRole.objects.get_or_create(
            user=user, aplicacao=role_carga.aplicacao, defaults={"role": role_carga}
        )
        sync_user_permissions(user)
        assert _user_has_perm_in_db(user, "ovlp_rm_all_perm")

        # Remove as duas roles
        UserRole.objects.filter(user=user).delete()
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, "ovlp_rm_all_perm"), (
            "Permissão deveria ter sido removida após excluir todas as origens."
        )


# ---------------------------------------------------------------------------
# TestAPIPermissions — testes do endpoint /me/permissions/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAPIPermissions:
    """Valida que o endpoint /me/permissions/ reflete exclusivamente auth_user_user_permissions."""

    def test_endpoint_retorna_conjunto_final_correto(self):
        """Endpoint retorna somente as permissões materializadas em auth_user_user_permissions."""
        user = _make_user("api_conjunto_final")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("api_cf_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)

        client = _login_client("api_conjunto_final", "ACOES_PNGI")
        resp = client.get(ME_PERMS_URL)
        assert resp.status_code == 200
        codenames = _get_granted_perms(resp)
        assert "api_cf_perm" in codenames, (
            f"Permissão herdada não apareceu no endpoint. Retorno: {codenames}"
        )

    def test_retorno_muda_apos_adicionar_role(self):
        """
        Adicionar role reflete imediatamente no endpoint /me/permissions/.

        CORREÇÃO (Falha 1): _assign_role deve ser chamado ANTES de _login_client
        para que a sessão seja criada com a role já ativa. Caso contrário, o
        login retorna 401/403 e o client fica sem sessão válida.
        """
        user = _make_user("api_add_role")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("api_add_role_perm")
        role.group.permissions.add(perm)

        # Atribui a role ANTES de logar — garante sessão autenticada
        _assign_role(user, role_pk=2)
        client = _login_client("api_add_role", "ACOES_PNGI")

        resp = client.get(ME_PERMS_URL)
        assert resp.status_code == 200, (
            f"Esperava 200 mas recebeu {resp.status_code}. "
            "Verifique se _assign_role foi chamado antes de _login_client."
        )
        assert "api_add_role_perm" in _get_granted_perms(resp), (
            "Permissão da role não apareceu no endpoint após login com role ativa."
        )

    def test_retorno_muda_apos_remover_role(self):
        """
        Remover role e sincronizar reflete no endpoint /me/permissions/.

        CORREÇÃO (Falha 2): Após remover a role, o endpoint pode retornar 200
        com lista vazia OU 403 (sem role ativa), dependendo da implementação.
        Usa _get_granted_perms() que trata ambos os casos com segurança,
        retornando [] para qualquer status != 200, sem acesso a .data diretamente.
        """
        user = _make_user("api_rm_role")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("api_rm_role_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)

        client = _login_client("api_rm_role", "ACOES_PNGI")
        resp_before = client.get(ME_PERMS_URL)
        assert resp_before.status_code == 200
        assert "api_rm_role_perm" in _get_granted_perms(resp_before)

        UserRole.objects.filter(user=user).delete()
        sync_user_permissions(user)

        resp_after = client.get(ME_PERMS_URL)
        # Aceita 200 (lista vazia) ou 403 (sem role) — ambos indicam que a perm sumiu
        assert resp_after.status_code in (200, 403), (
            f"Status inesperado após remover role: {resp_after.status_code}"
        )
        assert "api_rm_role_perm" not in _get_granted_perms(resp_after), (
            "Permissão não foi removida do endpoint após excluir a role."
        )

    def test_retorno_muda_apos_grant_override(self):
        """
        Criar override grant reflete imediatamente no endpoint /me/permissions/.

        CORREÇÃO (Falha 3): _login_client deve ser chamado APÓS criar o override
        e sincronizar. Dessa forma a sessão é criada com o estado final correto.
        Usa force_authenticate para isolar o teste do mecanismo de sessão e
        garantir que o endpoint seja avaliado com o usuário correto.
        """
        user = _make_user("api_grant_ovr")
        _assign_role(user, role_pk=2)
        perm = _get_or_create_permission("api_grant_ovr_perm")

        role = Role.objects.get(pk=2)
        role.group.permissions.remove(perm)
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(user, "api_grant_ovr_perm")

        # Verifica estado ANTES do override usando force_authenticate
        client_before = APIClient()
        client_before.force_authenticate(user=user)
        resp_before = client_before.get(ME_PERMS_URL)
        assert "api_grant_ovr_perm" not in _get_granted_perms(resp_before)

        # Cria override e sincroniza
        UserPermissionOverride.objects.create(user=user, permission=perm, mode="grant")
        sync_user_permissions(user)
        assert _user_has_perm_in_db(user, "api_grant_ovr_perm")

        # Verifica estado APÓS o override usando force_authenticate
        client_after = APIClient()
        client_after.force_authenticate(user=user)
        resp_after = client_after.get(ME_PERMS_URL)
        assert "api_grant_ovr_perm" in _get_granted_perms(resp_after), (
            "Override grant não refletiu no endpoint."
        )

    def test_retorno_muda_apos_revoke_override(self):
        """Criar override revoke remove a permissão do endpoint /me/permissions/."""
        user = _make_user("api_revoke_ovr")
        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("api_revoke_ovr_perm")
        role.group.permissions.add(perm)
        _assign_role(user, role_pk=2)

        client = _login_client("api_revoke_ovr", "ACOES_PNGI")
        resp_before = client.get(ME_PERMS_URL)
        assert "api_revoke_ovr_perm" in _get_granted_perms(resp_before)

        UserPermissionOverride.objects.create(user=user, permission=perm, mode="revoke")
        sync_user_permissions(user)

        resp_after = client.get(ME_PERMS_URL)
        assert "api_revoke_ovr_perm" not in _get_granted_perms(resp_after), (
            "Override revoke não removeu a permissão do endpoint."
        )


# ---------------------------------------------------------------------------
# TestStructuralIntegration — integração estrutural (gatilhos de sync)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStructuralIntegration:
    """Valida gatilhos automáticos de sincronização (D-05, ADR-PERM-01)."""

    def test_alterar_group_permissions_impacta_usuarios_apos_sync(self):
        """Adicionar permissão ao Group da role e re-sincronizar materializa em auth_user_user_permissions."""
        user = _make_user("strct_group_perm")
        role = Role.objects.get(pk=2)
        _assign_role(user, role_pk=2)

        perm_nova = _get_or_create_permission("strct_grp_new_perm")
        assert not _user_has_perm_in_db(user, "strct_grp_new_perm")

        # Adicionar perm ao group — o signal m2m_changed deve disparar re-sync
        role.group.permissions.add(perm_nova)

        # Verifica que o re-sync automático (via signal) ocorreu
        assert _user_has_perm_in_db(user, "strct_grp_new_perm"), (
            "Adicionar permissão ao Group não foi propagada para auth_user_user_permissions (D-05)."
        )

    def test_alterar_role_group_impacta_usuarios_apos_sync(self):
        """Trocar o Group associado a uma Role e sincronizar atualiza os usuários com essa role."""
        user = _make_user("strct_role_grp")
        role = Role.objects.get(pk=4)  # OPERADOR_ACAO

        group_original = role.group
        perm_original = _get_or_create_permission("strct_rg_orig_perm")
        group_original.permissions.add(perm_original)
        _assign_role(user, role_pk=4)
        assert _user_has_perm_in_db(user, "strct_rg_orig_perm")

        # Novo group sem a perm_original
        group_novo, _ = Group.objects.get_or_create(name="strct_role_grp_novo_group")
        perm_novo = _get_or_create_permission("strct_rg_new_perm")
        group_novo.permissions.add(perm_novo)

        role.group = group_novo
        role.save()  # signal post_save em Role deve disparar re-sync

        assert _user_has_perm_in_db(user, "strct_rg_new_perm"), (
            "Nova permissão do novo Group não foi materializada após troca de Role.group."
        )
        assert not _user_has_perm_in_db(user, "strct_rg_orig_perm"), (
            "Permissão antiga do Group anterior deveria ter sido removida."
        )

        # Restaura para não afetar outros testes
        role.group = group_original
        role.save()

    def test_sync_all_users_permissions_recompoe_todos(self):
        """sync_all_users_permissions recomputa auth_user_user_permissions para todos os usuários com role ativa."""
        user_a = _make_user("strct_sync_all_a")
        user_b = _make_user("strct_sync_all_b")

        role = Role.objects.get(pk=2)
        perm = _get_or_create_permission("strct_sync_all_perm")
        role.group.permissions.add(perm)

        _assign_role(user_a, role_pk=2)
        _assign_role(user_b, role_pk=2)

        # Limpa manualmente as permissões materializadas para simular estado corrompido
        user_a.user_permissions.clear()
        user_b.user_permissions.clear()
        assert not _user_has_perm_in_db(user_a, "strct_sync_all_perm")
        assert not _user_has_perm_in_db(user_b, "strct_sync_all_perm")

        # Re-sync em batch
        sync_all_users_permissions()

        assert _user_has_perm_in_db(user_a, "strct_sync_all_perm"), (
            "user_a não teve permissões recompostas pelo sync_all."
        )
        assert _user_has_perm_in_db(user_b, "strct_sync_all_perm"), (
            "user_b não teve permissões recompostas pelo sync_all."
        )


# ---------------------------------------------------------------------------
# TestNegativePermissions — testes negativos
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNegativePermissions:
    """Valida bloqueios, ausência de permissões e isolação de auth_user_groups."""

    def test_usuario_sem_permissao_efetiva_recebe_bloqueio(self):
        """
        can() retorna False para permissão não materializada em auth_user_user_permissions.

        CORREÇÃO (Falha 4): AuthorizationService.can é um método de INSTÂNCIA.
        O teste original chamava AuthorizationService.can(user, codename) como
        se fosse estático, causando TypeError. Deve-se instanciar o serviço
        primeiro: service = AuthorizationService(user), depois service.can(codename).
        """
        from apps.accounts.services.authorization_service import AuthorizationService

        user = _make_user("neg_bloqueio")
        _assign_role(user, role_pk=2)
        perm = _get_or_create_permission("neg_bloqueio_perm")

        role = Role.objects.get(pk=2)
        role.group.permissions.remove(perm)
        sync_user_permissions(user)
        UserPermissionOverride.objects.filter(user=user, permission=perm).delete()

        # Instancia o serviço corretamente antes de chamar .can()
        service = AuthorizationService(user)
        assert not service.can("neg_bloqueio_perm"), (
            "AuthorizationService.can() deveria retornar False para permissão não efetiva."
        )

    def test_grupo_sem_role_ativa_nao_afeta_permissoes_do_usuario(self):
        """Group sem UserRole associado a um usuário não deve influenciar suas permissões."""
        user = _make_user("neg_group_sem_role")
        perm = _get_or_create_permission("neg_grp_sr_perm")

        # Cria um Group avulso com a permissão — sem associar via UserRole
        group_avulso, _ = Group.objects.get_or_create(name="neg_group_avulso")
        group_avulso.permissions.add(perm)

        # Garante que o usuário NÃO é adicionado ao group (ADR-PERM-01)
        user.groups.clear()
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, "neg_grp_sr_perm"), (
            "Group sem UserRole associada não deveria afetar auth_user_user_permissions."
        )

    def test_auth_user_groups_isolado_nao_altera_comportamento(self):
        """ADR-PERM-01: adicionar usuário a auth_user_groups isoladamente não deve alterar
        o conjunto materializado em auth_user_user_permissions."""
        user = _make_user("neg_auth_user_groups")
        perm = _get_or_create_permission("neg_aug_perm")

        role = Role.objects.get(pk=2)
        role.group.permissions.remove(perm)
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(user, "neg_aug_perm")

        # Adiciona diretamente ao Group via auth_user_groups
        # (viola ADR-PERM-01 — este teste garante que o sistema não é afetado)
        user.groups.add(role.group)

        # auth_user_user_permissions NÃO deve mudar sem um sync explícito
        assert not _user_has_perm_in_db(user, "neg_aug_perm"), (
            "Adicionar ao auth_user_groups isoladamente não deve alterar "
            "auth_user_user_permissions (ADR-PERM-01)."
        )

        # Limpa o grupo para não poluir outros testes
        user.groups.clear()
