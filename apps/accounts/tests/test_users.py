# apps/accounts/tests/test_users.py
"""
Testes de criacao de usuarios e gestao de perfis.

Nao usa transaction=True: savepoints sao suficientes para testes HTTP.

Endpoints cobertos:
  POST  /api/accounts/users/
  POST  /api/accounts/users/create-with-role/
  PATCH /api/accounts/profiles/{id}/
"""
import pytest
from django.contrib.auth.models import User

from apps.accounts.models import ClassificacaoUsuario, UserProfile, UserRole

pytestmark = pytest.mark.django_db

USERS_URL       = "/api/accounts/users/"
CREATE_ROLE_URL = "/api/accounts/users/create-with-role/"
PROFILES_URL    = "/api/accounts/profiles/"

def _payload_usuario(suffix):
    return {
        "username": f"novo_user_{suffix}",
        "password": "NovaSenha@2026",
        "name": f"Usuario Teste {suffix}",
        "email": f"novo_user_{suffix}@teste.gov.br",
        "orgao": "ORGAO_TESTE",
    }

# --- UserCreateView ----------------------------------------------------------

class TestUserCreate:

    def test_portal_admin_cria_usuario_retorna_201(self, client_portal_admin):
        resp = client_portal_admin.post(
            USERS_URL, _payload_usuario("a"), format="json"
        )
        assert resp.status_code == 201

    def test_criacao_gera_user_no_banco(self, client_portal_admin):
        client_portal_admin.post(USERS_URL, _payload_usuario("b"), format="json")
        assert User.objects.filter(username="novo_user_b").exists()

    def test_criacao_gera_userprofile(self, client_portal_admin):
        client_portal_admin.post(USERS_URL, _payload_usuario("c"), format="json")
        user = User.objects.get(username="novo_user_c")
        assert UserProfile.objects.filter(user=user).exists()

    def test_username_duplicado_retorna_400(self, client_portal_admin):
        payload = _payload_usuario("dup")
        client_portal_admin.post(USERS_URL, payload, format="json")
        resp = client_portal_admin.post(USERS_URL, payload, format="json")
        assert resp.status_code == 400

    def test_gestor_sem_permissao_criar_retorna_403(self, client_gestor):
        resp = client_gestor.post(
            USERS_URL, _payload_usuario("forbidden"), format="json"
        )
        assert resp.status_code == 403

    def test_nao_autenticado_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.post(
            USERS_URL, _payload_usuario("anon"), format="json"
        )
        assert resp.status_code in (401, 403)


# --- UserCreateWithRoleView --------------------------------------------------

class TestUserCreateWithRole:

    def _payload_com_role(self, suffix):
        from apps.accounts.models import Aplicacao, Role
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        return {
            "username": f"novo_cr_{suffix}",
            "password": "NovaSenha@2026",
            "name": f"Novo CR {suffix}",
            "email": f"novo_cr_{suffix}@teste.gov.br",  # ← adicionar
            "orgao": "ORGAO_TESTE",                      # ← adicionar
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }


    def test_portal_admin_cria_user_com_role_retorna_201(
        self, client_portal_admin
    ):
        resp = client_portal_admin.post(
            CREATE_ROLE_URL, self._payload_com_role("1"), format="json"
        )
        assert resp.status_code == 201

    def test_cria_user_no_banco(self, client_portal_admin):
        client_portal_admin.post(
            CREATE_ROLE_URL, self._payload_com_role("2"), format="json"
        )
        assert User.objects.filter(username="novo_cr_2").exists()

    def test_cria_userrole_no_banco(self, client_portal_admin):
        client_portal_admin.post(
            CREATE_ROLE_URL, self._payload_com_role("3"), format="json"
        )
        assert UserRole.objects.filter(user__username="novo_cr_3").exists()

    def test_resposta_contem_permissions_added(self, client_portal_admin):
        resp = client_portal_admin.post(
            CREATE_ROLE_URL, self._payload_com_role("4"), format="json"
        )
        assert resp.status_code == 201
        assert "permissions_added" in resp.data

    def test_payload_invalido_nao_cria_objeto_parcial(
        self, client_portal_admin
    ):
        resp = client_portal_admin.post(
            CREATE_ROLE_URL,
            {"username": "", "password": "", "name": ""},
            format="json",
        )
        assert resp.status_code == 400
        assert not User.objects.filter(username="").exists()

    def test_app_bloqueada_retorna_400_ou_403(self, client_portal_admin):
        from apps.accounts.models import Aplicacao, Role
        try:
            app_blk = Aplicacao.objects.get(codigointerno="APP_BLOQUEADA")
            role_blk = Role.objects.filter(aplicacao=app_blk).first()
        except Aplicacao.DoesNotExist:
            pytest.skip("APP_BLOQUEADA nao presente nas fixtures")
        if not role_blk:
            pytest.skip("Nenhuma Role para APP_BLOQUEADA nas fixtures")
        resp = client_portal_admin.post(
            CREATE_ROLE_URL,
            {
                "username": "blk_user",
                "password": "NovaSenha@2026",
                "name": "Bloqueada",
                "aplicacao_id": app_blk.pk,
                "role_id": role_blk.pk,
            },
            format="json",
        )
        assert resp.status_code in (400, 403)

    def test_gestor_nao_pode_criar_user_com_role(self, client_gestor):
        resp = client_gestor.post(
            CREATE_ROLE_URL, self._payload_com_role("forbidden"), format="json"
        )
        assert resp.status_code == 403


# --- UserProfileViewSet: partial_update --------------------------------------

class TestUserProfilePatch:

    def test_usuario_edita_proprio_profile(self, client_gestor, gestor_pngi):
        resp = client_gestor.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"name": "Nome Atualizado"},
            format="json",
        )
        assert resp.status_code == 200

    def test_usuario_nao_edita_profile_alheio(
        self, client_operador, gestor_pngi
    ):
        resp = client_operador.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"name": "Invasao"},
            format="json",
        )
        assert resp.status_code in (403, 404)

    def test_usuario_comum_nao_altera_classificacao(
        self, client_gestor, gestor_pngi
    ):
        resp = client_gestor.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"classificacao_usuario": 2},
            format="json",
        )
        assert resp.status_code == 403

    def test_portal_admin_altera_classificacao(
        self, client_portal_admin, gestor_pngi
    ):
        resp = client_portal_admin.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"classificacao_usuario": 2},
            format="json",
        )
        assert resp.status_code == 200

    def test_usuario_comum_nao_altera_status(
        self, client_gestor, gestor_pngi
    ):
        resp = client_gestor.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"status_usuario": 2},
            format="json",
        )
        assert resp.status_code == 403

    def test_portal_admin_altera_status(
        self, client_portal_admin, gestor_pngi
    ):
        resp = client_portal_admin.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"status_usuario": 2},
            format="json",
        )
        assert resp.status_code == 200

    def test_nao_autenticado_retorna_401_ou_403(
        self, client_anonimo, gestor_pngi
    ):
        resp = client_anonimo.patch(
            f"{PROFILES_URL}{gestor_pngi.pk}/",
            {"name": "Anon"},
            format="json",
        )
        assert resp.status_code in (401, 403)
