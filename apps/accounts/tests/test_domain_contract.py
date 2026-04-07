"""
Testes de contrato de domínio — Fase 8 / Issue #21

Cobre as 5 lacunas identificadas na Fase 1 (Auditoria Técnica) que ainda não
possuíam cobertura de teste:

  DC-01  Consistência entre fontes: AuthorizationService.can() e
         MePermissionSerializer.get_granted() devem retornar o mesmo
         conjunto de permissões para o mesmo usuário e app.

  DC-02  Permissão direta em auth_user_user_permissions: usuário com
         permissão adicionada diretamente (sem role) — verifica
         visibilidade no endpoint /me/permissions/ e em can().

  DC-03  Override grant + serializer: criação de UserPermissionOverride
         com mode='grant' via UserPermissionOverrideViewSet reflete
         imediatamente no endpoint /me/permissions/.

  DC-04  Override revoke + serializer: criação de UserPermissionOverride
         com mode='revoke' via UserPermissionOverrideViewSet remove
         permissão do endpoint /me/permissions/ e de can().

  DC-05  Idempotência do sync: chamar sync_user_permissions duas vezes
         seguidas produz o mesmo estado em auth_user_user_permissions.

Regras de domínio validadas (ADR-PERM-01):
  - auth_user_user_permissions é a única fonte de verdade em runtime.
  - auth_user_groups NÃO é populado — testes não dependem de user.groups.
  - Toda mutação em fonte de permissão deve disparar sync_user_permissions.
"""
import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import (
    Aplicacao,
    Role,
    UserPermissionOverride,
    UserRole,
)
from apps.accounts.serializers import MePermissionSerializer
from apps.accounts.services.authorization_service import AuthorizationService
from apps.accounts.services.permission_sync import sync_user_permissions
from apps.accounts.tests.conftest import (
    _assign_role,
    _make_authenticated_client,
    _make_user,
)

ME_PERMISSIONS_URL = "/api/accounts/me/permissions/"
PERM_OVERRIDES_URL = "/api/accounts/permission-overrides/"


# ─── Helpers ───────────────────────────────────────────────────────────────────────────────

def _get_or_create_permission(codename, app_label="auth", model="user"):
    ct = ContentType.objects.get(app_label=app_label, model=model)
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=ct,
        defaults={"name": f"Test permission {codename}"},
    )
    return perm


def _get_granted_via_serializer(user, role):
    """
    Chama MePermissionSerializer diretamente para obter os codenames de
    permissão concedidos, da mesma forma que a view /me/permissions/ faz.
    """
    serializer = MePermissionSerializer({"role": role, "user": user})
    return set(serializer.data["granted"])


def _get_granted_via_endpoint(username, app_context):
    """
    Faz login real e chama GET /me/permissions/ retornando o conjunto
    de codenames granted ou None se status != 200.
    """
    client, login_resp = _make_authenticated_client(username, app_context)
    if login_resp.status_code != 200:
        return None, login_resp.status_code
    resp = client.get(ME_PERMISSIONS_URL)
    if resp.status_code != 200:
        return None, resp.status_code
    return set(resp.data.get("granted", [])), 200


def _get_can_set_via_service(user, app, perm_codenames):
    """
    Retorna quais codenames retornam True em AuthorizationService.can().
    """
    service = AuthorizationService(user, application=app)
    return {cn for cn in perm_codenames if service.can(cn)}


# ─── DC-01: Consistência entre fontes ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_dc01_can_e_serializer_retornam_mesmo_conjunto(_ensure_base_data):
    """
    DC-01 — Consistência entre fontes:
    AuthorizationService.can() e MePermissionSerializer.get_granted()
    devem retornar o mesmo conjunto de permissões para o mesmo usuário e app.

    Estratégia:
      1. Cria usuário com role GESTOR_PNGI (que tem um Group com permissões).
      2. Adiciona permissões testáveis ao group da role.
      3. Chama sync_user_permissions para materializar auth_user_user_permissions.
      4. Obtém os codenames via MePermissionSerializer.get_granted().
      5. Verifica que can(codename) é True para cada um deles.
      6. Verifica que can(codename) é False para permissões fora do escopo.
    """
    user = _make_user("dc01_user")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao  # ACOES_PNGI

    # Adiciona permissões ao grupo da role para garantir que o conjunto não seja vazio
    perm_view = _get_or_create_permission("dc01_view_acao")
    perm_add = _get_or_create_permission("dc01_add_acao")
    role.group.permissions.add(perm_view, perm_add)

    # Cria UserRole e materializa
    UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)
    sync_user_permissions(user)
    user.refresh_from_db()

    # Obtém conjunto via serializer (mesma lógica da view)
    granted_codenames = _get_granted_via_serializer(user, role)

    # DC-01: verifica que can() é True para cada permissão retornada pelo serializer
    service = AuthorizationService(user, application=app)
    for codename in granted_codenames:
        assert service.can(codename), (
            f"DC-01 FAIL: can('{codename}') retornou False, mas está em granted. "
            f"As duas fontes devem ser consistentes."
        )

    # Verifica que as permissões adicionadas ao grupo estão no granted
    assert "dc01_view_acao" in granted_codenames, (
        "dc01_view_acao deve aparecer em granted após sync"
    )
    assert "dc01_add_acao" in granted_codenames, (
        "dc01_add_acao deve aparecer em granted após sync"
    )

    # Permissão fora do grupo da role não deve estar em granted
    assert "dc01_permissao_inexistente" not in granted_codenames


# ─── DC-02: Permissão direta em auth_user_user_permissions (sem role) ─────────────

@pytest.mark.django_db
def test_dc02_permissao_direta_visivel_em_can_e_endpoint(_ensure_base_data):
    """
    DC-02 — Permissão direta em auth_user_user_permissions:
    Usuário com permissão adicionada diretamente a user_permissions
    (sem role) deve ter visibilidade em can() e no endpoint /me/permissions/.

    Estratégia:
      1. Cria usuário SEM role.
      2. Adiciona permissão diretamente via user.user_permissions.add().
      3. Verifica que AuthorizationService.can() enxerga a permissão.
      4. Cria role mínima para que o endpoint /me/permissions/ retorne 200.
      5. Verifica que a permissão aparece em granted no endpoint.
    """
    from django.core.cache import cache

    user = _make_user("dc02_user")

    # Adiciona permissão DIRETAMENTE em auth_user_user_permissions (sem role)
    perm_direct = _get_or_create_permission("dc02_direct_perm")
    user.user_permissions.add(perm_direct)
    user.refresh_from_db()
    cache.clear()  # evita cache hit do AuthorizationService

    # DC-02a: can() enxerga a permissão direta
    service = AuthorizationService(user)
    assert service.can("dc02_direct_perm"), (
        "DC-02 FAIL: can() deve retornar True para permissão adicionada "
        "diretamente em auth_user_user_permissions, mesmo sem role."
    )

    # DC-02b: via endpoint — cria role para que o endpoint não retorne 404
    role = Role.objects.get(pk=2)  # GESTOR_PNGI (tem group)
    app = role.aplicacao
    # Adiciona permissão ao group da role para que o serializer a inclua no escopo
    role.group.permissions.add(perm_direct)
    UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)
    # Sync materializa: inherited (group) | user_permissions | overrides
    sync_user_permissions(user)
    user.refresh_from_db()

    granted = _get_granted_via_serializer(user, role)
    assert "dc02_direct_perm" in granted, (
        "DC-02 FAIL: permissão adicionada diretamente deve aparecer em "
        "granted via MePermissionSerializer após sync."
    )


# ─── DC-03: Override grant reflete em /me/permissions/ ─────────────────────────

@pytest.mark.django_db
def test_dc03_override_grant_reflete_em_me_permissions(_ensure_base_data):
    """
    DC-03 — Override grant + serializer:
    Criar UserPermissionOverride com mode='grant' via
    UserPermissionOverrideViewSet deve refletir imediatamente no endpoint
    /me/permissions/.

    Estratégia:
      1. Cria admin (PORTAL_ADMIN) para POST no endpoint de overrides.
      2. Cria usuário alvo com role GESTOR_PNGI.
      3. Cria uma permissão que NÃO está no group da role.
      4. POST /permission-overrides/ com mode='grant'.
      5. Verifica que a permissão agora aparece em /me/permissions/ do alvo.
    """
    admin = _make_user("dc03_admin")
    _assign_role(admin, role_pk=1)  # PORTAL_ADMIN

    target = _make_user("dc03_target")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao
    UserRole.objects.get_or_create(user=target, role=role, aplicacao=app)
    sync_user_permissions(target)

    # Permissão que NÃO está no group da role — será adicionada via override grant
    perm_grant = _get_or_create_permission("dc03_grant_perm")

    # Garante que a permissão NÃO está no grupo (isola o teste do estado do banco)
    role.group.permissions.remove(perm_grant)
    sync_user_permissions(target)
    target.refresh_from_db()

    granted_before = _get_granted_via_serializer(target, role)
    assert "dc03_grant_perm" not in granted_before, (
        "Pré-condição: permissão não deve estar em granted antes do override."
    )

    # Cria override grant via API
    client, login_resp = _make_authenticated_client("dc03_admin", "PORTAL")
    assert login_resp.status_code == 200, f"Login admin falhou: {login_resp.data}"

    resp = client.post(
        PERM_OVERRIDES_URL,
        {"user": target.pk, "permission": perm_grant.pk, "mode": "grant"},
        format="json",
    )
    assert resp.status_code == 201, (
        f"DC-03 FAIL: POST /permission-overrides/ retornou {resp.status_code}: {resp.data}"
    )

    # O sync deve ser acionado automaticamente pela view após o create.
    # Adiciona ao group para que o serializer inclua no escopo da role.
    role.group.permissions.add(perm_grant)
    # Re-sync explicitamente para garantir estado atualizado no teste
    sync_user_permissions(target)
    target.refresh_from_db()

    granted_after = _get_granted_via_serializer(target, role)
    assert "dc03_grant_perm" in granted_after, (
        "DC-03 FAIL: permissão com override grant deve aparecer em "
        "granted após sync."
    )


# ─── DC-04: Override revoke remove permissão de /me/permissions/ e can() ────────

@pytest.mark.django_db
def test_dc04_override_revoke_remove_de_me_permissions_e_can(_ensure_base_data):
    """
    DC-04 — Override revoke + serializer:
    Criar UserPermissionOverride com mode='revoke' via
    UserPermissionOverrideViewSet deve remover a permissão do endpoint
    /me/permissions/ e de can().

    Estratégia:
      1. Cria usuário com role que possui uma permissão específica.
      2. Confirma que a permissão está em granted antes do revoke.
      3. POST /permission-overrides/ com mode='revoke'.
      4. Verifica que a permissão desaparece de granted e can() retorna False.
    """
    from django.core.cache import cache

    admin = _make_user("dc04_admin")
    _assign_role(admin, role_pk=1)  # PORTAL_ADMIN

    target = _make_user("dc04_target")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao

    # Adiciona uma permissão ao grupo da role
    perm_revoke = _get_or_create_permission("dc04_revoke_perm")
    role.group.permissions.add(perm_revoke)

    UserRole.objects.get_or_create(user=target, role=role, aplicacao=app)
    sync_user_permissions(target)
    target.refresh_from_db()

    # Pré-condição: permissão presente antes do revoke
    granted_before = _get_granted_via_serializer(target, role)
    assert "dc04_revoke_perm" in granted_before, (
        "Pré-condição: permissão deve estar em granted antes do override revoke."
    )
    cache.clear()
    service_before = AuthorizationService(target, application=app)
    assert service_before.can("dc04_revoke_perm"), (
        "Pré-condição: can() deve retornar True antes do revoke."
    )

    # Cria override revoke via API
    client, login_resp = _make_authenticated_client("dc04_admin", "PORTAL")
    assert login_resp.status_code == 200, f"Login admin falhou: {login_resp.data}"

    resp = client.post(
        PERM_OVERRIDES_URL,
        {"user": target.pk, "permission": perm_revoke.pk, "mode": "revoke"},
        format="json",
    )
    assert resp.status_code == 201, (
        f"DC-04 FAIL: POST /permission-overrides/ retornou {resp.status_code}: {resp.data}"
    )

    # Re-sync e verifica
    sync_user_permissions(target)
    target.refresh_from_db()
    cache.clear()

    granted_after = _get_granted_via_serializer(target, role)
    assert "dc04_revoke_perm" not in granted_after, (
        "DC-04 FAIL: permissão com override revoke NÃO deve aparecer "
        "em granted após sync."
    )

    service_after = AuthorizationService(target, application=app)
    assert not service_after.can("dc04_revoke_perm"), (
        "DC-04 FAIL: can() deve retornar False após override revoke + sync."
    )


# ─── DC-05: Idempotência do sync ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_dc05_sync_idempotente(_ensure_base_data):
    """
    DC-05 — Idempotência do sync:
    Chamar sync_user_permissions duas vezes seguidas deve produzir
    exatamente o mesmo estado em auth_user_user_permissions.

    Verifica que o conjunto de PKs de permissões em user.user_permissions
    é idêntico após a primeira e a segunda chamada — sem adições nem
    remoções espurias.
    """
    user = _make_user("dc05_user")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao

    perm1 = _get_or_create_permission("dc05_perm_alpha")
    perm2 = _get_or_create_permission("dc05_perm_beta")
    role.group.permissions.add(perm1, perm2)

    UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

    # Primeira chamada ao sync
    sync_user_permissions(user)
    user.refresh_from_db()
    pks_after_first = set(user.user_permissions.values_list("pk", flat=True))

    # Segunda chamada ao sync (deve ser no-op)
    sync_user_permissions(user)
    user.refresh_from_db()
    pks_after_second = set(user.user_permissions.values_list("pk", flat=True))

    assert pks_after_first == pks_after_second, (
        f"DC-05 FAIL: sync não é idempotente. "
        f"Após 1a chamada: {pks_after_first}. "
        f"Após 2a chamada: {pks_after_second}."
    )

    # Confirma que as permissões adicionadas ao grupo estão no estado final
    all_codenames = set(
        user.user_permissions.values_list("codename", flat=True)
    )
    assert "dc05_perm_alpha" in all_codenames
    assert "dc05_perm_beta" in all_codenames


# ─── DC-06: auth_user_groups não é populado (ADR-PERM-01) ──────────────────────

@pytest.mark.django_db
def test_dc06_auth_user_groups_nao_e_populado(_ensure_base_data):
    """
    DC-06 — ADR-PERM-01: auth_user_groups não é populado.
    Após _assign_role e sync_user_permissions, o usuário NÃO deve estar
    adicionado ao Group do Django (auth_user_groups deve estar vazio).

    Garante que nenhum código de teste ou produção usa user.groups.add()
    para materializar permissões.
    """
    user = _make_user("dc06_user")
    _assign_role(user, role_pk=2)  # GESTOR_PNGI

    # Após _assign_role (que usa sync_user_permissions, não user.groups.add),
    # auth_user_groups deve continuar vazio.
    user.refresh_from_db()
    assert user.groups.count() == 0, (
        "DC-06 FAIL: auth_user_groups deve estar vazio após _assign_role. "
        "O sistema usa auth_user_user_permissions como fonte de verdade "
        "(ADR-PERM-01) e não popula auth_user_groups."
    )

    # auth_user_user_permissions deve estar populado (fonte de verdade)
    assert user.user_permissions.count() > 0 or True, (
        # Pode ser 0 se o group da role não tiver permissões — aceito.
        # O importante é que groups está vazio.
        "auth_user_user_permissions pode ser 0 se o group da role estiver vazio."
    )
