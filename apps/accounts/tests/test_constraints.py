# apps/accounts/tests/test_constraints.py
"""
Testes de constraints de banco de dados da app accounts.

MANTEM transaction=True: IntegrityError real exige commit no banco.
O conftest.py usa get_or_create nos helpers, entao StatusUsuario etc.
 sao criados se nao existirem -- sem depender de fixtures pre-carregadas.
"""
import pytest
from django.db import IntegrityError

from apps.accounts.models import Aplicacao, Role, UserRole

pytestmark = pytest.mark.django_db(transaction=True)


# --- Role: unicidade codigoperfil por aplicacao ------------------------------

class TestRoleConstraints:

    def test_codigoperfil_duplicado_mesma_app_gera_integrity_error(self, db):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        with pytest.raises(IntegrityError):
            Role.objects.create(
                codigoperfil="GESTOR_PNGI",
                nomeperfil="Gestor Duplicado",
                aplicacao=app,
            )

    def test_mesmo_codigoperfil_em_apps_diferentes_e_permitido(self, db):
        app_pngi = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        r1 = Role.objects.create(
            codigoperfil="ROLE_CROSS_APP_TEST",
            nomeperfil="Cross App Role PNGI",
            aplicacao=app_pngi,
        )
        r2 = Role.objects.create(
            codigoperfil="ROLE_CROSS_APP_TEST",
            nomeperfil="Cross App Role CARGA",
            aplicacao=app_carga,
        )
        assert r1.pk != r2.pk


# --- UserRole: unicidade user por aplicacao ----------------------------------

class TestUserRoleConstraints:

    def test_usuario_com_dois_roles_mesma_app_gera_integrity_error(
        self, db, operador_acao
    ):
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        role_gestor = Role.objects.get(codigoperfil="GESTOR_PNGI")
        with pytest.raises(IntegrityError):
            UserRole.objects.create(
                user=operador_acao,
                role=role_gestor,
                aplicacao=app,
            )

    def test_usuario_pode_ter_roles_em_apps_diferentes(
        self, db, gestor_pngi
    ):
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        role_carga = Role.objects.get(codigoperfil="GESTOR_CARGA")
        ur = UserRole.objects.create(
            user=gestor_pngi,
            role=role_carga,
            aplicacao=app_carga,
        )
        assert ur.pk is not None
        assert UserRole.objects.filter(user=gestor_pngi).count() == 2


# --- Attribute: unicidade user+app+key (se model existir) -------------------

class TestAttributeConstraints:

    def test_atributo_duplicado_gera_integrity_error(self, db, gestor_pngi):
        try:
            from apps.accounts.models import Attribute
        except ImportError:
            pytest.skip("Model Attribute nao existe nesta versao")
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        Attribute.objects.create(
            user=gestor_pngi, aplicacao=app, key="orgao", value="SPU"
        )
        with pytest.raises(IntegrityError):
            Attribute.objects.create(
                user=gestor_pngi, aplicacao=app, key="orgao", value="OUTRO"
            )

    def test_mesma_key_em_app_diferente_e_permitido(self, db, gestor_pngi):
        try:
            from apps.accounts.models import Attribute
        except ImportError:
            pytest.skip("Model Attribute nao existe nesta versao")
        app_pngi = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
        Attribute.objects.create(
            user=gestor_pngi, aplicacao=app_pngi, key="orgao", value="SPU"
        )
        attr2 = Attribute.objects.create(
            user=gestor_pngi, aplicacao=app_carga, key="orgao", value="SPU"
        )
        assert attr2.pk is not None

    def test_key_diferente_mesma_app_e_permitido(self, db, gestor_pngi):
        try:
            from apps.accounts.models import Attribute
        except ImportError:
            pytest.skip("Model Attribute nao existe nesta versao")
        app = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
        Attribute.objects.create(
            user=gestor_pngi, aplicacao=app, key="orgao", value="SPU"
        )
        attr2 = Attribute.objects.create(
            user=gestor_pngi, aplicacao=app, key="setor", value="TI"
        )
        assert attr2.pk is not None
