# apps/accounts/tests/test_constraints.py
"""
Testes de constraints de banco e __str__ dos models.
"""
import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import (
    AccountsSession,
    Aplicacao,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserRole,
)

pytestmark = pytest.mark.django_db


# --- Constraints de UniqueConstraint -----------------------------------------


class TestUserRoleConstraints:

    def test_unicidade_user_aplicacao_na_userrole(self, usuario_alvo):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")

        UserRole.objects.create(user=usuario_alvo, aplicacao=app, role=role)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                UserRole.objects.create(user=usuario_alvo, aplicacao=app, role=role)

    def test_unicidade_role_aplicacao_codigoperfil(self):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role = Role.objects.get(codigoperfil="OPERADOR_ACAO")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    aplicacao=app,
                    codigoperfil=role.codigoperfil,
                    nomeperfil="Duplicado",
                )


# --- __str__ dos models de lookup (models.py 24, 28, 32) ---------------------


class TestModelStrMethods:
    """
    Cobre models.py linhas 24, 28, 32 — __str__ de StatusUsuario,
    TipoUsuario e ClassificacaoUsuario.
    Também cobre linha 383–386 — AccountsSession.__str__.
    """

    def test_str_status_usuario(self):
        """models.py linha 24: StatusUsuario.__str__ → strdescricao."""
        obj = StatusUsuario.objects.get(pk=1)
        resultado = str(obj)
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_str_tipo_usuario(self):
        """models.py linha 28: TipoUsuario.__str__ → strdescricao."""
        obj = TipoUsuario.objects.get(pk=1)
        resultado = str(obj)
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_str_classificacao_usuario(self):
        """models.py linha 32: ClassificacaoUsuario.__str__ → strdescricao."""
        obj = ClassificacaoUsuario.objects.get(pk=1)
        resultado = str(obj)
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_str_accounts_session(self, gestor_pngi):
        """
        models.py linhas 383–386: AccountsSession.__str__ deve retornar
        string contendo user_id, session_key e app_context.
        """
        from datetime import timedelta

        from django.utils import timezone

        session = AccountsSession.objects.create(
            user=gestor_pngi,
            session_key="test_session_key_str_123",
            app_context="ACOES_PNGI",
            session_cookie_name="gpp_session_ACOES_PNGI",
            expires_at=timezone.now() + timedelta(hours=1),
            revoked=False,
        )
        resultado = str(session)
        assert isinstance(resultado, str)
        assert len(resultado) > 0
        # __str__ = f"{self.user_id} - {self.session_key} - {self.app_context}"
        assert str(gestor_pngi.pk) in resultado
        assert "test_session_key_str_123" in resultado
        assert "ACOES_PNGI" in resultado
