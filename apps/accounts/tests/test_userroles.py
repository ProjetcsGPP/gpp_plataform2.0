# apps/accounts/tests/test_userroles.py
"""
Testes do UserRoleViewSet.

Nao usa transaction=True: savepoints sao suficientes para testes HTTP.

Endpoints cobertos:
  POST   /api/accounts/user-roles/
  DELETE /api/accounts/user-roles/{id}/
  GET    /api/accounts/user-roles/

Dados base: initial_data.json
  Aplicacao pk=2 -> ACOES_PNGI
  Role pk=2  -> GESTOR_PNGI
  Role pk=3  -> COORDENADOR_PNGI
  Role pk=4  -> OPERADOR_ACAO
"""
import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Aplicacao, Role, UserRole

pytestmark = pytest.mark.django_db

URL = "/api/accounts/user-roles/"


def _get_or_create_test_perm(codename):
    ct = ContentType.objects.first()
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=ct,
        defaults={"name": f"Test permission {codename}"},
    )
    return perm


# --- Atribuicao (POST) -------------------------------------------------------

class TestUserRoleAssign:

    def test_portal_admin_atribui_role_retorna_201(
        self, client_portal_admin, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="GESTOR_PNGI")
        resp = client_portal_admin.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        assert resp.status_code == 201

    def test_assign_cria_userrole_no_banco(
        self, client_portal_admin, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="COORDENADOR_PNGI")
        client_portal_admin.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        assert UserRole.objects.filter(
            user=usuario_alvo, role=role, aplicacao=app
        ).exists()

    def test_assign_sincroniza_permissoes_do_group(
        self, client_portal_admin, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        perm = _get_or_create_test_perm("test_sync_userrole")
        role.group.permissions.add(perm)

        client_portal_admin.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        usuario_alvo.refresh_from_db()
        assert usuario_alvo.user_permissions.filter(
            codename="test_sync_userrole"
        ).exists()

    def test_assign_duplicado_retorna_400_ou_409(
        self, client_portal_admin, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        data = {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk}
        client_portal_admin.post(URL, data, format="json")
        resp = client_portal_admin.post(URL, data, format="json")
        assert resp.status_code in (400, 409)

    def test_assign_role_de_app_diferente_retorna_400(
        self, client_portal_admin, usuario_alvo
    ):
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        role_pngi = Role.objects.get(codigoperfil="GESTOR_PNGI")
        resp = client_portal_admin.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app_carga.pk, "role": role_pngi.pk},
            format="json",
        )
        assert resp.status_code == 400


# --- Acesso negado (POST) ----------------------------------------------------

class TestUserRoleAssignAcessoNegado:

    def test_gestor_nao_pode_atribuir_role(
        self, client_gestor, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        resp = client_gestor.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        assert resp.status_code == 403

    def test_coordenador_nao_pode_atribuir_role(
        self, client_coordenador, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        resp = client_coordenador.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        assert resp.status_code == 403

    def test_operador_nao_pode_atribuir_role(
        self, client_operador, usuario_alvo
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        resp = client_operador.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        assert resp.status_code == 403

    def test_anonimo_nao_pode_atribuir_role(self, client_anonimo, usuario_alvo):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        resp = client_anonimo.post(
            URL,
            {"user": usuario_alvo.pk, "aplicacao": app.pk, "role": role.pk},
            format="json",
        )
        assert resp.status_code in (401, 403)


# --- Revogacao (DELETE) -------------------------------------------------------

class TestUserRoleRevoke:

    def test_portal_admin_revoga_role_retorna_204(
        self, client_portal_admin, operador_acao
    ):
        userrole = UserRole.objects.get(user=operador_acao)
        resp = client_portal_admin.delete(f"{URL}{userrole.pk}/")
        assert resp.status_code == 204

    def test_revoke_remove_userrole_do_banco(
        self, client_portal_admin, operador_acao
    ):
        userrole = UserRole.objects.get(user=operador_acao)
        pk = userrole.pk
        client_portal_admin.delete(f"{URL}{pk}/")
        assert not UserRole.objects.filter(pk=pk).exists()

    def test_revoke_remove_permissoes_exclusivas_do_group(
        self, client_portal_admin, operador_acao
    ):
        userrole = UserRole.objects.get(user=operador_acao)
        perm = _get_or_create_test_perm("test_revoke_userrole")
        userrole.role.group.permissions.add(perm)
        operador_acao.user_permissions.add(perm)

        client_portal_admin.delete(f"{URL}{userrole.pk}/")
        operador_acao.refresh_from_db()
        assert not operador_acao.user_permissions.filter(
            codename="test_revoke_userrole"
        ).exists()

    def test_gestor_nao_pode_revogar_role(
        self, client_gestor, operador_acao
    ):
        userrole = UserRole.objects.get(user=operador_acao)
        resp = client_gestor.delete(f"{URL}{userrole.pk}/")
        assert resp.status_code == 403

    def test_coordenador_nao_pode_revogar_role(
        self, client_coordenador, operador_acao
    ):
        userrole = UserRole.objects.get(user=operador_acao)
        resp = client_coordenador.delete(f"{URL}{userrole.pk}/")
        assert resp.status_code == 403

    def test_anonimo_nao_pode_revogar_role(self, client_anonimo, operador_acao):
        userrole = UserRole.objects.get(user=operador_acao)
        resp = client_anonimo.delete(f"{URL}{userrole.pk}/")
        assert resp.status_code in (401, 403)


# --- Edge Cases de Destroy e Serializer (novos — cobrindo gaps) --------------

class TestUserRoleDestroyEdgeCases:

    def test_destroy_com_role_group_none_nao_lanca_attribute_error(
        self, client_portal_admin, usuario_alvo
    ):
        """
        views.py 545–549: deletar UserRole onde role.group=None →
        log deve conter 'None' sem lançar AttributeError.
        """
        from apps.accounts.models import Aplicacao, Role

        # Cria uma Role sem group
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role_sem_group, _ = Role.objects.get_or_create(
            codigoperfil="ROLE_SEM_GROUP_TEST",
            aplicacao=app,
            defaults={"nomeperfil": "Role Sem Group", "group": None},
        )
        # Força group=None mesmo que já existisse
        role_sem_group.group = None
        role_sem_group.save(update_fields=["group"])

        # Atribui a role ao usuário alvo diretamente
        userrole = UserRole.objects.create(
            user=usuario_alvo,
            aplicacao=app,
            role=role_sem_group,
        )

        resp = client_portal_admin.delete(f"{URL}{userrole.pk}/")
        # Deve retornar 204 sem AttributeError
        assert resp.status_code == 204

    def test_serializer_role_nao_pertence_a_app_retorna_400(
        self, client_portal_admin, usuario_alvo
    ):
        """
        serializers.py 260: tentar criar UserRole com role que não pertence
        à app → 400 com 'role': 'A role selecionada não pertence à aplicação informada.'
        """
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        role_pngi = Role.objects.get(codigoperfil="GESTOR_PNGI")
        resp = client_portal_admin.post(
            URL,
            {
                "user": usuario_alvo.pk,
                "aplicacao": app_carga.pk,
                "role": role_pngi.pk,
            },
            format="json",
        )
        assert resp.status_code == 400
        resp_str = str(resp.data)
        assert "role" in resp_str
        assert "não pertence" in resp_str
