"""
test_permission_sync_coverage.py
================================

Testes de cobertura para linhas críticas de permission_sync.py
not previously covered (Fase 10 — Issue #23).

Linhas alvo:
  - 236, 242-243: sync_user_permissions — branch de erro/exceção
  - 296-300: sync_users_permissions — tratamento de excecao por user
  - 314-318: sync_all_users_permissions — log start/done + dispatch

Meta: cobertura de permission_sync.py de 88% → >= 95%
"""
import pytest
from unittest.mock import patch

from apps.accounts.services.permission_sync import (
    sync_all_users_permissions,
    sync_user_permissions,
    sync_users_permissions,
)
from apps.accounts.tests.factories import (
    make_permission,
    make_role,
    make_user,
    make_user_role,
)


@pytest.mark.django_db
class TestSyncUserPermissionsEdgeCases:
    """
    Cobre as linhas 236 e 242-243 de permission_sync.py.

    Linha 236: caminho feliz onde current_pks == new_pks (NOOP).
    Linhas 242-243: ramo de diff com added/removed.
    """

    def test_sync_noop_quando_ja_em_sync(self):
        """
        Linha 236: sync_user_permissions retorna sem alterar o banco
        quando current_pks == new_pks.
        """
        perm = make_permission(codename="noop_sync_perm")
        role = make_role()
        role.group.permissions.add(perm)
        ur = make_user_role(role=role)
        user = ur.user

        # Primeira sync já foi chamada pelo helper.
        # Segunda chamada deve ser NOOP (sem alteração de estado).
        perms_antes = set(user.user_permissions.values_list("pk", flat=True))
        sync_user_permissions(user)
        perms_depois = set(user.user_permissions.values_list("pk", flat=True))

        assert perms_antes == perms_depois

    def test_sync_detecta_e_registra_diff(self):
        """
        Linhas 242-243: quando added e removed são calculados.
        Verifica que added = new - current e removed = current - new.
        """
        perm_inicial = make_permission(codename="perm_antes_sync")
        perm_nova = make_permission(codename="perm_depois_sync")

        role = make_role()
        role.group.permissions.add(perm_inicial)

        ur = make_user_role(role=role)
        user = ur.user

        # Troca as permissões do grupo
        role.group.permissions.set([perm_nova])

        # Chama sync — added={perm_nova}, removed={perm_inicial}
        sync_user_permissions(user)

        codes = list(user.user_permissions.values_list("codename", flat=True))
        assert "perm_depois_sync" in codes
        assert "perm_antes_sync" not in codes

    def test_sync_usuario_sem_role_zera_permissions(self):
        """
        Se o usuário tinha permissões e a role foi removida,
        sync deve zerar auth_user_user_permissions.
        """
        from apps.accounts.models import UserRole

        perm = make_permission(codename="perm_a_remover_sync")
        role = make_role()
        role.group.permissions.add(perm)

        ur = make_user_role(role=role)
        user = ur.user
        assert user.user_permissions.count() > 0

        # Remove a role sem disparar o signal (para testar sync direto)
        UserRole.objects.filter(user=user).delete()
        sync_user_permissions(user)

        user.refresh_from_db()
        assert user.user_permissions.count() == 0


@pytest.mark.django_db
class TestSyncUsersPermissionsEdgeCases:
    """
    Cobre linhas 296-300 de permission_sync.py:
    tratamento de exceção por user dentro do batch.
    """

    def test_batch_vazio_retorna_sem_erro(self):
        """sync_users_permissions([]) deve retornar silenciosamente."""
        sync_users_permissions([])  # Nao deve levantar excecao

    def test_batch_ignora_user_id_invalido(self):
        """IDs inexistentes no batch são silenciosamente ignorados."""
        sync_users_permissions([999999, 999998])  # IDs inexistentes

    def test_batch_captura_excecao_por_user(self):
        """
        Linhas 296-300: quando sync_user_permissions lanca excecao para
        um usuário, o batch continua e não propaga o erro.
        """
        user1 = make_user()
        user2 = make_user()

        call_count = {"count": 0}

        original_sync = sync_user_permissions

        def sync_side_effect(user):
            call_count["count"] += 1
            if user.pk == user1.pk:
                raise RuntimeError("Erro simulado no sync")
            return original_sync(user)

        with patch(
            "apps.accounts.services.permission_sync.sync_user_permissions",
            side_effect=sync_side_effect,
        ):
            # Nao deve propagar a excecao
            sync_users_permissions([user1.pk, user2.pk])

        # Ambos os users foram processados (mesmo o que gerou excecao)
        assert call_count["count"] == 2

    def test_batch_processa_multiplos_users(self):
        ur1 = make_user_role()
        ur2 = make_user_role()

        perm = make_permission(codename="batch_perm_multi")
        ur1.role.group.permissions.add(perm)
        ur2.role.group.permissions.add(perm)

        sync_users_permissions([ur1.user.pk, ur2.user.pk])

        for ur in [ur1, ur2]:
            ur.user.refresh_from_db()
            assert ur.user.user_permissions.filter(codename="batch_perm_multi").exists()


@pytest.mark.django_db
class TestSyncAllUsersPermissions:
    """
    Cobre linhas 314-318 de permission_sync.py:
    sync_all_users_permissions dispara para todos com roles ativas.
    """

    def test_sync_all_materializa_permissions(self):
        """
        Linhas 314-318: sync_all chama sync_users_permissions para
        todos os user_ids com UserRole.
        """
        perm = make_permission(codename="all_sync_perm")
        ur = make_user_role()
        ur.role.group.permissions.add(perm)

        # Remove as permissões manualmente para forçar re-sync
        ur.user.user_permissions.clear()
        assert ur.user.user_permissions.count() == 0

        sync_all_users_permissions()

        ur.user.refresh_from_db()
        assert ur.user.user_permissions.filter(codename="all_sync_perm").exists()

    def test_sync_all_nao_afeta_users_sem_role(self):
        """Usuários sem role não devem ter permissões após sync_all."""
        user_sem_role = make_user()
        sync_all_users_permissions()
        assert user_sem_role.user_permissions.count() == 0

    def test_sync_all_com_banco_vazio_nao_falha(self):
        """Linhas 314/318: deve executar mesmo sem roles no banco."""
        from apps.accounts.models import UserRole
        UserRole.objects.all().delete()
        sync_all_users_permissions()  # Nao deve levantar excecao
