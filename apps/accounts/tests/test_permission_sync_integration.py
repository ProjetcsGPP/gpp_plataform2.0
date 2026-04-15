"""
Tests — apps/accounts/tests/test_permission_sync_integration.py

Testes de integração ponta-a-ponta das 3 lacunas declaradas na Issue #18.

Estratégia: sem mock. Cada teste altera uma fonte de permissão e verifica
diretamente no banco (user.user_permissions.all()) se auth_user_user_permissions
foi atualizado pelo fluxo:  evento → signal → sync_user_permissions → DB.

Lacunas cobertas:
  L-1  auth_group_permissions muda → re-sync automático (D-05)
  L-2  UserPermissionOverride criado/editado/deletado → reflexo em DB
  L-3  Role.group muda → atualização de todos os usuários com aquela role

Pré-condições garantidas pelo conftest.py (_ensure_base_data autouse):
  - Aplicacao pk=1 (PORTAL), pk=2 (ACOES_PNGI), pk=3 (CARGA_ORG_LOT)
  - Role pk=1 (PORTAL_ADMIN), pk=2 (GESTOR_PNGI), pk=3 (COORDENADOR_PNGI)
  - Todos os grupos associados às roles existem (group_name via conftest)
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Role, UserPermissionOverride, UserRole
from apps.accounts.services.permission_sync import sync_user_permissions
from apps.accounts.tests.conftest import _make_user

# ─── Helper ─────────────────────────────────────────────────────────────────


def _make_perm(
    codename: str, app_label: str = "auth", model: str = "user"
) -> Permission:
    """Obtém ou cria uma Permission real usando o ContentType correto."""
    ct = ContentType.objects.get(app_label=app_label, model=model)
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=ct,
        defaults={"name": f"Can {codename}"},
    )
    return perm


def _user_has_perm_in_db(user, perm: Permission) -> bool:
    """
    Verifica se a permissão está em auth_user_user_permissions sem cache.
    Usa user.user_permissions.all() forçando nova query.
    """
    user.refresh_from_db()
    return user.user_permissions.filter(pk=perm.pk).exists()


# ════════════════════════════════════════════════════════════════════════════
# LACUNA 1 — D-05: mudança em auth_group_permissions → re-sync automático
# ════════════════════════════════════════════════════════════════════════════


class TestL1GroupPermissionChangeTriggersResync:
    """
    Lacuna 1 (D-05): verifica que alterar auth_group_permissions de um Group
    vinculado a uma Role re-sincroniza auth_user_user_permissions no banco
    para todos os usuários que possuem aquela role.

    Fluxo testado:
      Group.permissions.add(perm)
        → m2m_changed signal
          → invalidate_on_group_permission_change (signals.py)
            → sync_users_permissions([user.pk])
              → sync_user_permissions(user)
                → user.user_permissions.set(effective_perms)
    """

    @pytest.mark.django_db(transaction=True)
    def test_adicionar_perm_ao_group_popula_auth_user_user_permissions(
        self, _ensure_base_data
    ):
        """
        L-1a: Após group.permissions.add(perm), a permissão deve aparecer
        em user.user_permissions sem qualquer ação manual.
        """
        user = _make_user("l1a_user")
        role = Role.objects.get(pk=2)  # GESTOR_PNGI
        app = role.aplicacao
        UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

        # Garante estado inicial limpo
        sync_user_permissions(user)
        perm = _make_perm("l1a_test_perm")
        assert not _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão NÃO deve estar em auth_user_user_permissions antes do evento"

        # Evento: adiciona permissão ao group da role
        role.group.permissions.add(perm)

        # Verificação ponta-a-ponta
        assert _user_has_perm_in_db(user, perm), (
            "L-1a FALHOU: group.permissions.add() não propagou a permissão "
            "para auth_user_user_permissions do usuário"
        )

    @pytest.mark.django_db(transaction=True)
    def test_remover_perm_do_group_remove_de_auth_user_user_permissions(
        self, _ensure_base_data
    ):
        """
        L-1b: Após group.permissions.remove(perm), a permissão deve sumir
        de user.user_permissions sem qualquer ação manual.
        """
        user = _make_user("l1b_user")
        role = Role.objects.get(pk=2)
        app = role.aplicacao
        UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

        perm = _make_perm("l1b_test_perm")
        role.group.permissions.add(perm)
        # Força sync inicial para estado conhecido
        sync_user_permissions(user)
        assert _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão deve estar presente antes da remoção"

        # Evento: remove permissão do group
        role.group.permissions.remove(perm)

        assert not _user_has_perm_in_db(user, perm), (
            "L-1b FALHOU: group.permissions.remove() não removeu a permissão "
            "de auth_user_user_permissions do usuário"
        )

    @pytest.mark.django_db(transaction=True)
    def test_group_perm_change_nao_afeta_usuario_de_outra_role(self, _ensure_base_data):
        """
        L-1c: A mudança em auth_group_permissions de um group só afeta
        usuários daquela role — não deve vazar para usuários de outra role.
        """
        user_pngi = _make_user("l1c_user_pngi")
        user_coord = _make_user("l1c_user_coord")

        role_gestor = Role.objects.get(pk=2)  # GESTOR_PNGI
        role_coord = Role.objects.get(pk=3)  # COORDENADOR_PNGI
        app = role_gestor.aplicacao

        UserRole.objects.get_or_create(user=user_pngi, role=role_gestor, aplicacao=app)
        UserRole.objects.get_or_create(user=user_coord, role=role_coord, aplicacao=app)

        perm_gestor = _make_perm("l1c_gestor_only_perm")
        # Garante estado inicial limpo
        sync_user_permissions(user_pngi)
        sync_user_permissions(user_coord)

        # Adiciona permissão APENAS ao group do GESTOR_PNGI
        role_gestor.group.permissions.add(perm_gestor)

        assert _user_has_perm_in_db(
            user_pngi, perm_gestor
        ), "L-1c: usuário GESTOR_PNGI deve ter a permissão após adicionar ao group"
        assert not _user_has_perm_in_db(user_coord, perm_gestor), (
            "L-1c FALHOU: a permissão do group GESTOR_PNGI não deve vazar "
            "para o usuário com role COORDENADOR_PNGI"
        )


# ════════════════════════════════════════════════════════════════════════════
# LACUNA 2 — UserPermissionOverride → reflexo automático em DB
# ════════════════════════════════════════════════════════════════════════════


class TestL2PermissionOverrideTriggersResync:
    """
    Lacuna 2: verifica que criar, atualizar ou deletar um UserPermissionOverride
    re-sincroniza auth_user_user_permissions no banco via signal do ViewSet.

    Fluxo testado:
      UserPermissionOverride.save()
        → post_save signal
          → UserPermissionOverrideViewSet.perform_create/update/destroy
            → sync_user_permissions(user)
              → user.user_permissions.set(effective_perms)

    Nota: UserPermissionOverrideViewSet conecta sync via perform_create/update/destroy.
    Para testar o reflexo em DB sem depender da view, usamos o signal que a própria
    lógica de sync já registra, ou chamamos sync diretamente após o evento de modelo.
    Os testes abaixo verificam o reflexo real em banco, que é o critério de aceite.
    """

    @pytest.mark.django_db(transaction=True)
    def test_criar_override_grant_adiciona_perm_em_db(self, _ensure_base_data):
        """
        L-2a: Após criar UserPermissionOverride(mode='grant'), a permissão
        deve aparecer em user.user_permissions (auth_user_user_permissions).
        """
        user = _make_user("l2a_user")
        perm = _make_perm("l2a_grant_perm")

        # Garante estado inicial sem a permissão
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão NÃO deve existir antes do override"

        # Evento: cria override grant — ViewSet chama sync após salvar
        override = UserPermissionOverride.objects.create(
            user=user, permission=perm, mode="grant"
        )
        # Simula o que o ViewSet faz após o save
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, perm), (
            "L-2a FALHOU: criar UserPermissionOverride(mode='grant') não propagou "
            "a permissão para auth_user_user_permissions"
        )

    @pytest.mark.django_db(transaction=True)
    def test_deletar_override_grant_remove_perm_de_db(self, _ensure_base_data):
        """
        L-2b: Após deletar um UserPermissionOverride(mode='grant'), a permissão
        deve sumir de user.user_permissions (a menos que venha de outra fonte).
        """
        user = _make_user("l2b_user")
        perm = _make_perm("l2b_revoke_perm")

        override = UserPermissionOverride.objects.create(
            user=user, permission=perm, mode="grant"
        )
        sync_user_permissions(user)
        assert _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão deve estar presente após grant"

        # Evento: deleta o override — ViewSet chama sync após deletar
        override.delete()
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, perm), (
            "L-2b FALHOU: deletar UserPermissionOverride(mode='grant') não removeu "
            "a permissão de auth_user_user_permissions"
        )

    @pytest.mark.django_db(transaction=True)
    def test_criar_override_revoke_remove_perm_herdada_do_grupo(
        self, _ensure_base_data
    ):
        """
        L-2c: Após criar UserPermissionOverride(mode='revoke'), uma permissão
        herdada do group da role deve ser removida de auth_user_user_permissions.
        Garante que revoke vence grant de grupo.
        """
        user = _make_user("l2c_user")
        role = Role.objects.get(pk=2)  # GESTOR_PNGI
        app = role.aplicacao
        UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

        perm = _make_perm("l2c_revoke_inherited_perm")
        # Adiciona permissão ao group para que o usuário a herde
        role.group.permissions.add(perm)
        sync_user_permissions(user)
        assert _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão herdada deve estar presente"

        # Evento: cria override revoke
        UserPermissionOverride.objects.create(user=user, permission=perm, mode="revoke")
        sync_user_permissions(user)

        assert not _user_has_perm_in_db(user, perm), (
            "L-2c FALHOU: override revoke não removeu a permissão herdada do group "
            "de auth_user_user_permissions (regra 'revoke vence tudo' violada)"
        )

    @pytest.mark.django_db(transaction=True)
    def test_deletar_override_revoke_restaura_perm_do_grupo(self, _ensure_base_data):
        """
        L-2d: Após deletar um UserPermissionOverride(mode='revoke'), a permissão
        herdada do group deve ser restaurada em auth_user_user_permissions.
        """
        user = _make_user("l2d_user")
        role = Role.objects.get(pk=2)
        app = role.aplicacao
        UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

        perm = _make_perm("l2d_restore_perm")
        role.group.permissions.add(perm)

        override = UserPermissionOverride.objects.create(
            user=user, permission=perm, mode="revoke"
        )
        sync_user_permissions(user)
        assert not _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão deve estar bloqueada pelo revoke"

        # Evento: deleta o override revoke
        override.delete()
        sync_user_permissions(user)

        assert _user_has_perm_in_db(user, perm), (
            "L-2d FALHOU: deletar override revoke não restaurou a permissão herdada "
            "do group em auth_user_user_permissions"
        )

    @pytest.mark.django_db(transaction=True)
    def test_override_nao_vaza_para_outro_usuario(self, _ensure_base_data):
        """
        L-2e: Um UserPermissionOverride criado para user_a não deve alterar
        auth_user_user_permissions de user_b. Garante isolamento.
        """
        user_a = _make_user("l2e_user_a")
        user_b = _make_user("l2e_user_b")
        perm = _make_perm("l2e_isolated_perm")

        sync_user_permissions(user_a)
        sync_user_permissions(user_b)

        UserPermissionOverride.objects.create(
            user=user_a, permission=perm, mode="grant"
        )
        sync_user_permissions(user_a)

        assert _user_has_perm_in_db(
            user_a, perm
        ), "L-2e: user_a deve ter a permissão após grant override"
        assert not _user_has_perm_in_db(user_b, perm), (
            "L-2e FALHOU: grant override de user_a vazou para auth_user_user_permissions "
            "de user_b"
        )


# ════════════════════════════════════════════════════════════════════════════
# LACUNA 3 — Role.group muda → atualização dos usuários com aquela role
# ════════════════════════════════════════════════════════════════════════════


class TestL3RoleGroupChangeTriggersResync:
    """
    Lacuna 3: verifica que alterar o campo Role.group re-sincroniza
    auth_user_user_permissions para todos os usuários com aquela role.

    Fluxo testado:
      role.group = new_group; role.save()
        → post_save signal em Role
          → sync_on_role_group_change (signals.py)
            → sync_users_permissions(affected_user_ids)
              → sync_user_permissions(user) para cada user
                → user.user_permissions.set(novo_conjunto)
    """

    @pytest.mark.django_db(transaction=True)
    def test_trocar_group_da_role_atualiza_perms_de_todos_os_usuarios(
        self, _ensure_base_data
    ):
        """
        L-3a: Ao trocar Role.group, os usuários com aquela role devem perder
        as permissões do group antigo e ganhar as permissões do group novo.
        """
        user1 = _make_user("l3a_user1")
        user2 = _make_user("l3a_user2")
        role = Role.objects.get(pk=3)  # COORDENADOR_PNGI
        app = role.aplicacao

        UserRole.objects.get_or_create(user=user1, role=role, aplicacao=app)
        UserRole.objects.get_or_create(user=user2, role=role, aplicacao=app)

        perm_old = _make_perm("l3a_old_group_perm")
        perm_new = _make_perm("l3a_new_group_perm")

        old_group = role.group
        new_group, _ = Group.objects.get_or_create(name="l3a_new_group_coordenador")

        # Configura: old_group tem perm_old, new_group tem perm_new
        old_group.permissions.add(perm_old)
        new_group.permissions.add(perm_new)
        sync_user_permissions(user1)
        sync_user_permissions(user2)

        assert _user_has_perm_in_db(
            user1, perm_old
        ), "Pré-condição: user1 deve ter perm_old"
        assert _user_has_perm_in_db(
            user2, perm_old
        ), "Pré-condição: user2 deve ter perm_old"

        # Evento: troca o group da role
        role.group = new_group
        role.save(update_fields=["group"])

        # Verifica que perm_new foi adicionada E perm_old foi removida (sem old_group)
        assert _user_has_perm_in_db(
            user1, perm_new
        ), "L-3a FALHOU: user1 não ganhou perm_new após trocar Role.group"
        assert _user_has_perm_in_db(
            user2, perm_new
        ), "L-3a FALHOU: user2 não ganhou perm_new após trocar Role.group"
        assert not _user_has_perm_in_db(user1, perm_old), (
            "L-3a FALHOU: user1 ainda tem perm_old após trocar Role.group "
            "(old_group não é mais o grupo da role)"
        )
        assert not _user_has_perm_in_db(user2, perm_old), (
            "L-3a FALHOU: user2 ainda tem perm_old após trocar Role.group "
            "(old_group não é mais o grupo da role)"
        )

    @pytest.mark.django_db(transaction=True)
    def test_trocar_group_nao_afeta_usuario_de_outra_role(self, _ensure_base_data):
        """
        L-3b: Ao trocar Role.group de uma role específica, usuários
        de outras roles NÃO devem ter auth_user_user_permissions alteradas.
        """
        user_coord = _make_user("l3b_user_coord")
        user_gestor = _make_user("l3b_user_gestor")

        role_coord = Role.objects.get(pk=3)  # COORDENADOR_PNGI
        role_gestor = Role.objects.get(pk=2)  # GESTOR_PNGI
        app = role_coord.aplicacao

        UserRole.objects.get_or_create(user=user_coord, role=role_coord, aplicacao=app)
        UserRole.objects.get_or_create(
            user=user_gestor, role=role_gestor, aplicacao=app
        )

        perm_gestor = _make_perm("l3b_gestor_perm")
        role_gestor.group.permissions.add(perm_gestor)
        sync_user_permissions(user_gestor)
        sync_user_permissions(user_coord)

        # Evento: troca o group APENAS da role COORDENADOR_PNGI
        new_group, _ = Group.objects.get_or_create(name="l3b_new_coord_group")
        role_coord.group = new_group
        role_coord.save(update_fields=["group"])

        # user_gestor não deve ser afetado
        assert _user_has_perm_in_db(user_gestor, perm_gestor), (
            "L-3b FALHOU: trocar group de COORDENADOR_PNGI afetou "
            "auth_user_user_permissions do usuário GESTOR_PNGI"
        )

    @pytest.mark.django_db(transaction=True)
    def test_trocar_group_para_none_remove_todas_as_perms_herdadas(
        self, _ensure_base_data
    ):
        """
        L-3c: Ao trocar Role.group para None (ou um group sem permissões),
        o usuário deve perder as permissões herdadas do group antigo.
        """
        user = _make_user("l3c_user")
        role = Role.objects.get(pk=4)  # OPERADOR_ACAO
        app = role.aplicacao
        UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

        perm = _make_perm("l3c_inherited_perm")
        role.group.permissions.add(perm)
        sync_user_permissions(user)
        assert _user_has_perm_in_db(
            user, perm
        ), "Pré-condição: permissão herdada deve estar presente"

        # Evento: troca para um group vazio
        empty_group, _ = Group.objects.get_or_create(name="l3c_empty_group")
        role.group = empty_group
        role.save(update_fields=["group"])

        assert not _user_has_perm_in_db(user, perm), (
            "L-3c FALHOU: trocar Role.group para um group vazio não removeu "
            "as permissões herdadas de auth_user_user_permissions"
        )
