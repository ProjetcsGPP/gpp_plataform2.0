"""
test_signals_coverage.py
=========================

Testes de cobertura para as linhas não-cobertas de signals.py.

Linhas alvo:
  - 133-139: invalidate_on_userrole_change — branch User.DoesNotExist
             e branch de exceção genérica
  - 186: sync_on_role_group_change — branch early-return quando
         nenhum usuário com a role afetada

Meta: cobertura de signals.py de 94% → >= 97%
"""
import pytest
from unittest.mock import patch

from apps.accounts.tests.factories import (
    make_role,
    make_user,
    make_user_role,
)


@pytest.mark.django_db
class TestInvalidateOnUserroleChangeEdgeCases:
    """
    Cobre as linhas 133-139 de signals.py:

    branch ``User.DoesNotExist`` (linhas 133-136) e
    branch genérico de exceção (linhas 137-139).

    Estes branches são disparados dentro do handler do signal
    invalidate_on_userrole_change quando o user não é encontrado
    ou quando sync_user_permissions lança uma excecao inesperada.
    """

    def test_userrole_delete_com_user_inexistente_nao_falha(self):
        """
        Linhas 133-136 (User.DoesNotExist):
        Quando o user_id referenciado pelo UserRole já não existe
        no banco no momento do signal, o handler deve logar e continuar
        sem propagar a exceção.
        """
        from apps.accounts.models import UserRole
        from django.contrib.auth.models import User

        ur = make_user_role()
        user_id = ur.user.pk

        # Simulamos um cenario onde o user foi deletado antes do signal
        # de delete do UserRole ser processado, forçando User.DoesNotExist
        with patch(
            "apps.accounts.signals.sync_user_permissions",
            side_effect=User.DoesNotExist("user not found"),
        ):
            # Trigger do signal via delete
            UserRole.objects.filter(user_id=user_id).delete()
            # Se chegou aqui sem excecao, o branch foi coberto corretamente

    def test_userrole_save_com_excecao_generica_nao_falha(self):
        """
        Linhas 137-139 (Exception genérico):
        Quando sync_user_permissions lança uma excecao inesperada,
        o handler deve logar e não propagar.
        """
        from apps.accounts.models import UserRole

        user = make_user()
        role = make_role()

        with patch(
            "apps.accounts.signals.sync_user_permissions",
            side_effect=RuntimeError("Erro inesperado simulado"),
        ):
            # Trigger do signal via save do UserRole
            UserRole.objects.get_or_create(
                user=user,
                aplicacao=role.aplicacao,
                defaults={"role": role},
            )
            # Nao deve propagar a excecao


@pytest.mark.django_db
class TestSyncOnRoleGroupChangeEdgeCases:
    """
    Cobre a linha 186 de signals.py:
    branch early-return quando nenhum usuário tem a role afetada.
    """

    def test_role_sem_users_nao_dispara_sync(self):
        """
        Linha 186: quando affected_user_ids estiver vazio, o signal
        deve retornar sem chamar sync_users_permissions.
        """
        from django.contrib.auth.models import Group

        role = make_role()
        # Garante que nenhum user tem essa role
        from apps.accounts.models import UserRole
        UserRole.objects.filter(role=role).delete()

        new_group, _ = Group.objects.get_or_create(name=f"new_group_for_{role.codigoperfil}")

        with patch(
            "apps.accounts.signals.sync_users_permissions"
        ) as mock_sync:
            # Muda o group da role — dispara sync_on_role_group_change
            role.group = new_group
            role.save()

            # Como nao ha users, nao deve chamar sync_users_permissions
            mock_sync.assert_not_called()

    def test_role_com_users_dispara_sync(self):
        """
        Valida o caminho oposto: quando há usuarios afetados,
        sync_users_permissions é chamado com os user_ids corretos.
        """
        from django.contrib.auth.models import Group

        ur = make_user_role()
        new_group, _ = Group.objects.get_or_create(
            name=f"new_group_signal_{ur.role.codigoperfil}"
        )

        with patch(
            "apps.accounts.signals.sync_users_permissions"
        ) as mock_sync:
            ur.role.group = new_group
            ur.role.save()

            mock_sync.assert_called_once()
            called_ids = mock_sync.call_args[0][0]
            assert ur.user.pk in called_ids
