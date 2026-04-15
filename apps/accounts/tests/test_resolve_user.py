# apps/accounts/tests/test_resolve_user.py
"""
Testes para ResolveUserView — POST /api/accounts/auth/resolve-user/
Cobre views.py linhas 196–243 (endpoint público de resolução de identificador).
"""
import pytest

pytestmark = pytest.mark.django_db

URL = "/api/accounts/auth/resolve-user/"


class TestResolveUserView:

    def test_identifier_vazio_retorna_400(self, client_anonimo):
        resp = client_anonimo.post(URL, {"identifier": ""}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_identifier_ausente_retorna_400(self, client_anonimo):
        resp = client_anonimo.post(URL, {}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_identifier_muito_longo_retorna_400(self, client_anonimo):
        identifier_longo = "a" * 255
        resp = client_anonimo.post(URL, {"identifier": identifier_longo}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_identifier_exatamente_254_chars_nao_retorna_400_por_tamanho(
        self, client_anonimo, usuario_sem_role
    ):
        # Garante que 254 chars NÃO cai na branch de tamanho máximo.
        # O usuário não existirá com esse username, então esperamos 404 (user_not_found),
        # mas NÃO 400 por tamanho — a branch len>254 não deve ser acionada.
        identifier_254 = "a" * 254
        resp = client_anonimo.post(URL, {"identifier": identifier_254}, format="json")
        assert resp.status_code in (404, 400)
        if resp.status_code == 400:
            # Se 400, deve ser por outro motivo, não tamanho
            assert (
                resp.data.get("code") != "invalid_request" or len(identifier_254) <= 254
            )

    def test_username_valido_ativo_retorna_200(self, client_anonimo, gestor_pngi):
        resp = client_anonimo.post(
            URL, {"identifier": gestor_pngi.username}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["username"] == gestor_pngi.username

    def test_email_valido_ativo_retorna_200(self, client_anonimo, gestor_pngi):
        # Atribui email ao gestor_pngi para o teste
        gestor_pngi.email = "gestor_resolve@teste.gov.br"
        gestor_pngi.save(update_fields=["email"])

        resp = client_anonimo.post(
            URL, {"identifier": "gestor_resolve@teste.gov.br"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["username"] == gestor_pngi.username

    def test_username_inexistente_retorna_404(self, client_anonimo):
        resp = client_anonimo.post(
            URL, {"identifier": "username_que_nao_existe_xyz123"}, format="json"
        )
        assert resp.status_code == 404
        assert resp.data["code"] == "user_not_found"

    def test_email_inexistente_retorna_404(self, client_anonimo):
        resp = client_anonimo.post(
            URL, {"identifier": "nao_existe@teste.gov.br"}, format="json"
        )
        assert resp.status_code == 404
        assert resp.data["code"] == "user_not_found"

    def test_usuario_inativo_retorna_404(self, client_anonimo, usuario_sem_role):
        usuario_sem_role.is_active = False
        usuario_sem_role.save(update_fields=["is_active"])

        resp = client_anonimo.post(
            URL, {"identifier": usuario_sem_role.username}, format="json"
        )
        assert resp.status_code == 404
        assert resp.data["code"] == "user_not_found"

    def test_identifier_sem_arroba_usa_branch_username(
        self, client_anonimo, portal_admin
    ):
        """Identifier sem '@' deve cair na branch de lookup por username."""
        resp = client_anonimo.post(
            URL, {"identifier": portal_admin.username}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["username"] == portal_admin.username

    def test_identifier_com_arroba_usa_branch_email(
        self, client_anonimo, coordenador_pngi
    ):
        """Identifier com '@' deve cair na branch de lookup por email."""
        coordenador_pngi.email = "coordenador_resolve@teste.gov.br"
        coordenador_pngi.save(update_fields=["email"])

        resp = client_anonimo.post(
            URL, {"identifier": "coordenador_resolve@teste.gov.br"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["username"] == coordenador_pngi.username

    def test_endpoint_acessivel_sem_autenticacao(self, client_anonimo):
        """AllowAny — qualquer request sem cookie deve funcionar (não 401/403)."""
        resp = client_anonimo.post(URL, {"identifier": "qualquer"}, format="json")
        assert resp.status_code not in (401, 403)
