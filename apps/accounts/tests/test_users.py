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
from unittest.mock import patch

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


# --- UserCreateView — edge cases de coverage --------------------------------

class TestUserCreateViewEdgeCases:

    def test_nao_portal_admin_sem_permissao_na_app_retorna_403(
        self, client_gestor, gestor_pngi
    ):
        """
        views.py 348→358: gestor_pngi (não-portal-admin) tenta criar usuário
        numa aplicação para a qual não tem permissão de gestão → 403.
        """
        resp = client_gestor.post(
            USERS_URL, _payload_usuario("edge_np"), format="json"
        )
        assert resp.status_code == 403

    def test_database_error_no_save_retorna_500(self, client_portal_admin):
        """
        views.py 360–367: simular DatabaseError no serializer.save() →
        500 com detail='Erro interno ao criar usuário. Tente novamente.'
        """
        from django.db import DatabaseError

        with patch(
            "apps.accounts.serializers.UserCreateSerializer.create",
            side_effect=DatabaseError("simulated db error"),
        ):
            resp = client_portal_admin.post(
                USERS_URL, _payload_usuario("dberr"), format="json"
            )
        assert resp.status_code == 500
        assert "Erro interno ao criar usuário" in str(resp.data.get("detail", ""))


# --- UserCreateWithRoleView —  edge cases de coverage -----------------------

class TestUserCreateWithRoleEdgeCases:

    def _payload_com_role(self, suffix):
        from apps.accounts.models import Aplicacao, Role
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        return {
            "username": f"novo_cr_{suffix}",
            "password": "NovaSenha@2026",
            "name": f"Novo CR {suffix}",
            "email": f"novo_cr_{suffix}@teste.gov.br",
            "orgao": "ORGAO_TESTE",
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }

    def test_nao_admin_nao_superuser_retorna_403(self, client_gestor):
        """
        views.py 407→421: gestor_pngi não é portal_admin nem superuser
        → 403 na verificação inicial do endpoint.
        """
        resp = client_gestor.post(
            CREATE_ROLE_URL, self._payload_com_role("notadmin"), format="json"
        )
        assert resp.status_code == 403

    def test_portal_admin_sem_escopo_na_app_retorna_403(
        self, client_portal_admin
    ):
        """
        views.py 411–417: portal_admin tenta criar em app onde a policy
        retorna False para user_can_create_user_in_application.
        Mocka o service para simular escopo negado.
        """
        with patch(
            "apps.accounts.services.authorization_service.AuthorizationService"
            ".user_can_create_user_in_application",
            return_value=False,
        ):
            resp = client_portal_admin.post(
                CREATE_ROLE_URL, self._payload_com_role("noscope"), format="json"
            )
        assert resp.status_code == 403

    def test_database_error_no_save_retorna_500(self, client_portal_admin):
        """
        views.py 423–430: DatabaseError no serializer.save() →
        500 com detail='Erro interno ao criar usuário com role. Tente novamente.'
        """
        from django.db import DatabaseError

        with patch(
            "apps.accounts.serializers.UserCreateWithRoleSerializer.create",
            side_effect=DatabaseError("simulated db error"),
        ):
            resp = client_portal_admin.post(
                CREATE_ROLE_URL, self._payload_com_role("dberr_cr"), format="json"
            )
        assert resp.status_code == 500
        assert "Erro interno ao criar usuário com role" in str(
            resp.data.get("detail", "")
        )


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


# --- Validações do UserCreateSerializer (serializers.py) --------------------

class TestUserCreateSerializerValidations:

    def test_validate_email_duplicado_retorna_400(self, client_portal_admin):
        """
        serializers.py 157–158: validate_email com email já existente → 400.
        """
        payload = _payload_usuario("email_dup")
        # Cria o primeiro usuário com sucesso
        r1 = client_portal_admin.post(USERS_URL, payload, format="json")
        assert r1.status_code == 201

        # Tenta criar outro com mesmo email mas username diferente
        payload2 = _payload_usuario("email_dup2")
        payload2["email"] = payload["email"]  # mesmo email
        r2 = client_portal_admin.post(USERS_URL, payload2, format="json")
        assert r2.status_code == 400

    def test_validate_password_fraca_retorna_400(self, client_portal_admin):
        """
        serializers.py 169: validate_password com senha fraca → 400.
        """
        payload = _payload_usuario("weakpwd")
        payload["password"] = "123"
        resp = client_portal_admin.post(USERS_URL, payload, format="json")
        assert resp.status_code == 400

    def test_get_fk_or_400_pk_inexistente_retorna_400(self, client_portal_admin):
        """
        serializers.py 52: _get_fk_or_400 com pk inexistente → ValidationError 400.
        Disparado via UserCreateWithRoleSerializer com status_usuario=9999.
        """
        from apps.accounts.models import Aplicacao, Role
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")

        payload = {
            "username": "fk_test_user",
            "password": "NovaSenha@2026",
            "name": "FK Test",
            "email": "fk_test@teste.gov.br",
            "orgao": "ORGAO_TESTE",
            "aplicacao_id": app.pk,
            "role_id": role.pk,
            # status_usuario 9999 não existe no banco
            "status_usuario": 9999,
        }
        resp = client_portal_admin.post(CREATE_ROLE_URL, payload, format="json")
        assert resp.status_code == 400


# --- Validações do UserCreateWithRoleSerializer (serializers.py) ------------

class TestUserCreateWithRoleSerializerValidations:

    def _base_payload(self, suffix):
        from apps.accounts.models import Aplicacao, Role
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")
        return {
            "username": f"wcr_val_{suffix}",
            "password": "NovaSenha@2026",
            "name": f"WCR Val {suffix}",
            "email": f"wcr_val_{suffix}@teste.gov.br",
            "orgao": "ORGAO_TESTE",
            "aplicacao_id": app.pk,
            "role_id": role.pk,
        }

    def test_serializers_317_username_duplicado_retorna_400(
        self, client_portal_admin
    ):
        """
        serializers.py 317: validate_username duplicado → 400.
        """
        payload = self._base_payload("udup")
        client_portal_admin.post(CREATE_ROLE_URL, payload, format="json")
        # Mesmo username, email diferente
        payload2 = self._base_payload("udup_b")
        payload2["username"] = payload["username"]
        resp = client_portal_admin.post(CREATE_ROLE_URL, payload2, format="json")
        assert resp.status_code == 400

    def test_serializers_322_email_duplicado_retorna_400(
        self, client_portal_admin
    ):
        """
        serializers.py 322: validate_email duplicado → 400.
        """
        payload = self._base_payload("edup")
        client_portal_admin.post(CREATE_ROLE_URL, payload, format="json")
        # Mesmo email, username diferente
        payload2 = self._base_payload("edup_b")
        payload2["email"] = payload["email"]
        resp = client_portal_admin.post(CREATE_ROLE_URL, payload2, format="json")
        assert resp.status_code == 400

    def test_serializers_328_329_password_fraca_retorna_400(
        self, client_portal_admin
    ):
        """
        serializers.py 328–329: validate_password fraca → 400.
        """
        payload = self._base_payload("weakpwd_cr")
        payload["password"] = "123"
        resp = client_portal_admin.post(CREATE_ROLE_URL, payload, format="json")
        assert resp.status_code == 400

    def test_serializers_337_role_nao_pertence_a_app_retorna_400(
        self, client_portal_admin
    ):
        """
        serializers.py 337: role não pertence à aplicacao → 400 com 'role_id'.
        """
        from apps.accounts.models import Aplicacao, Role
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        role_pngi = Role.objects.get(codigoperfil="GESTOR_PNGI")

        payload = self._base_payload("roleneq")
        payload["aplicacao_id"] = app_carga.pk
        payload["role_id"] = role_pngi.pk  # role de ACOES_PNGI, não CARGA_ORG_LOT
        resp = client_portal_admin.post(CREATE_ROLE_URL, payload, format="json")
        assert resp.status_code == 400
        assert "role_id" in str(resp.data)

    def test_serializers_341_348_fk_fallback_sem_status_tipo_classif(
        self, client_portal_admin
    ):
        """
        serializers.py 341→348: status_usuario/tipo_usuario/classificacao_usuario
        omitidos → _get_fk_or_400 é chamado com pk=1 (deve existir);
        a criação deve ser bem-sucedida (pk=1 existe no conftest).
        """
        from apps.accounts.models import Aplicacao, Role
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")

        payload = {
            "username": "wcr_no_fk",
            "password": "NovaSenha@2026",
            "name": "WCR No FK",
            "email": "wcr_no_fk@teste.gov.br",
            "orgao": "ORGAO_TESTE",
            "aplicacao_id": app.pk,
            "role_id": role.pk,
            # status_usuario, tipo_usuario, classificacao_usuario OMITIDOS
        }
        resp = client_portal_admin.post(CREATE_ROLE_URL, payload, format="json")
        assert resp.status_code == 201


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
            {"status_usuario": 2},  # ← referencia idstatususuario=2
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
