"""
Testes das entidades funcionais de distribuição e navegação:

    Capability
    RoleCapability
    Menu

Regras fundamentais:
- Todas as entidades são vinculadas a uma Aplicacao.
- Capability organiza/distribui recursos funcionais.
- RoleCapability distribui Capability para Role.
- Nenhuma dessas entidades concede permissões Django.
- Não são permitidas associações entre aplicações diferentes.
- Menu organiza a navegação e pode ou não estar associado a uma Capability.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.models import Aplicacao, Capability, Menu, Role, RoleCapability

pytestmark = pytest.mark.django_db


# ============================================================================
# HELPERS
# ============================================================================


def _app(codigointerno):
    return Aplicacao.objects.get(codigointerno=codigointerno)


def _make_capability(aplicacao, codigo="ACOES", nome="Ações"):
    return Capability.objects.create(
        aplicacao=aplicacao,
        codigo=codigo,
        nome=nome,
    )


# ============================================================================
# CAPABILITY
# ============================================================================


class TestCapability:

    def test_cria_capability_vinculada_a_aplicacao(self):
        app = _app("ACOES_PNGI")

        capability = _make_capability(app)

        assert capability.pk is not None
        assert capability.aplicacao == app
        assert capability.codigo == "ACOES"
        assert capability.nome == "Ações"
        assert capability.ativo is True

    def test_codigo_deve_ser_unico_dentro_da_aplicacao(self):
        app = _app("ACOES_PNGI")

        _make_capability(app, codigo="ACOES")

        with pytest.raises(IntegrityError):
            _make_capability(
                app,
                codigo="ACOES",
                nome="Outra definição",
            )

    def test_mesmo_codigo_pode_existir_em_aplicacoes_diferentes(self):
        app_pngi = _app("ACOES_PNGI")
        app_carga = _app("CARGA_ORG_LOT")

        capability_pngi = _make_capability(
            app_pngi,
            codigo="GERENCIAR",
        )
        capability_carga = _make_capability(
            app_carga,
            codigo="GERENCIAR",
        )

        assert capability_pngi.pk != capability_carga.pk
        assert capability_pngi.codigo == capability_carga.codigo
        assert capability_pngi.aplicacao_id != capability_carga.aplicacao_id

    def test_descricao_e_ativo_possuem_valores_padrao(self):
        app = _app("ACOES_PNGI")

        capability = Capability.objects.create(
            aplicacao=app,
            codigo="TESTE",
            nome="Teste",
        )

        assert capability.descricao == ""
        assert capability.ativo is True


# ============================================================================
# ROLE CAPABILITY
# ============================================================================


class TestRoleCapability:

    def test_associa_role_e_capability_da_mesma_aplicacao(self):
        app = _app("ACOES_PNGI")
        role = Role.objects.get(codigoperfil="GESTOR_PNGI")
        capability = _make_capability(app)

        role_capability = RoleCapability.objects.create(
            aplicacao=app,
            role=role,
            capability=capability,
        )

        assert role_capability.pk is not None
        assert role_capability.aplicacao == app
        assert role_capability.role == role
        assert role_capability.capability == capability

    def test_nao_permite_role_de_outra_aplicacao(self):
        app_pngi = _app("ACOES_PNGI")
        app_carga = _app("CARGA_ORG_LOT")

        role_pngi = Role.objects.get(codigoperfil="GESTOR_PNGI")
        capability = _make_capability(app_pngi)

        with pytest.raises(ValidationError):
            RoleCapability.objects.create(
                aplicacao=app_carga,
                role=role_pngi,
                capability=capability,
            )

    def test_nao_permite_capability_de_outra_aplicacao(self):
        app_pngi = _app("ACOES_PNGI")
        app_carga = _app("CARGA_ORG_LOT")

        role = Role.objects.get(codigoperfil="GESTOR_PNGI")
        capability_carga = _make_capability(
            app_carga,
            codigo="GERENCIAR",
        )

        with pytest.raises(ValidationError):
            RoleCapability.objects.create(
                aplicacao=app_pngi,
                role=role,
                capability=capability_carga,
            )

    def test_nao_permite_duplicidade_da_mesma_associacao(self):
        app = _app("ACOES_PNGI")
        role = Role.objects.get(codigoperfil="GESTOR_PNGI")
        capability = _make_capability(app)

        RoleCapability.objects.create(
            aplicacao=app,
            role=role,
            capability=capability,
        )

        with pytest.raises(ValidationError):
            RoleCapability.objects.create(
                aplicacao=app,
                role=role,
                capability=capability,
            )

    def test_role_pode_receber_varias_capabilities(self):
        app = _app("ACOES_PNGI")
        role = Role.objects.get(codigoperfil="GESTOR_PNGI")

        capability_acoes = _make_capability(
            app,
            codigo="ACOES",
            nome="Ações",
        )
        capability_config = _make_capability(
            app,
            codigo="CONFIGURACOES",
            nome="Configurações",
        )

        RoleCapability.objects.create(
            aplicacao=app,
            role=role,
            capability=capability_acoes,
        )
        RoleCapability.objects.create(
            aplicacao=app,
            role=role,
            capability=capability_config,
        )

        assert role.role_capabilities.count() == 2

    def test_capability_pode_ser_distribuida_para_varias_roles(self):
        app = _app("ACOES_PNGI")

        role_gestor = Role.objects.get(codigoperfil="GESTOR_PNGI")
        role_coordenador = Role.objects.get(codigoperfil="COORDENADOR_PNGI")

        capability = _make_capability(app)

        RoleCapability.objects.create(
            aplicacao=app,
            role=role_gestor,
            capability=capability,
        )
        RoleCapability.objects.create(
            aplicacao=app,
            role=role_coordenador,
            capability=capability,
        )

        assert capability.role_capabilities.count() == 2


# ============================================================================
# MENU
# ============================================================================


class TestMenu:

    def test_cria_menu_raiz(self):
        app = _app("ACOES_PNGI")

        menu = Menu.objects.create(
            aplicacao=app,
            codigo="DASHBOARD",
            nome="Dashboard",
            rota="/acoes-pngi",
        )

        assert menu.pk is not None
        assert menu.aplicacao == app
        assert menu.parent is None
        assert menu.capability is None

    def test_cria_menu_com_capability(self):
        app = _app("ACOES_PNGI")
        capability = _make_capability(app)

        menu = Menu.objects.create(
            aplicacao=app,
            codigo="ACOES",
            nome="Ações",
            rota="/acoes-pngi/acoes",
            capability=capability,
        )

        assert menu.capability == capability

    def test_cria_menu_filho(self):
        app = _app("ACOES_PNGI")

        parent = Menu.objects.create(
            aplicacao=app,
            codigo="CONFIGURACOES",
            nome="Configurações",
        )

        child = Menu.objects.create(
            aplicacao=app,
            codigo="EIXOS",
            nome="Eixos",
            parent=parent,
        )

        assert child.parent == parent
        assert list(parent.children.all()) == [child]

    def test_nao_permite_menu_pai_de_outra_aplicacao(self):
        app_pngi = _app("ACOES_PNGI")
        app_carga = _app("CARGA_ORG_LOT")

        parent = Menu.objects.create(
            aplicacao=app_carga,
            codigo="CONFIGURACOES",
            nome="Configurações",
        )

        with pytest.raises(ValidationError):
            Menu.objects.create(
                aplicacao=app_pngi,
                codigo="EIXOS",
                nome="Eixos",
                parent=parent,
            )

    def test_nao_permite_capability_de_outra_aplicacao(self):
        app_pngi = _app("ACOES_PNGI")
        app_carga = _app("CARGA_ORG_LOT")

        capability = _make_capability(
            app_carga,
            codigo="GERENCIAR",
        )

        with pytest.raises(ValidationError):
            Menu.objects.create(
                aplicacao=app_pngi,
                codigo="ACOES",
                nome="Ações",
                capability=capability,
            )

    def test_nao_permite_menu_ser_pai_de_si_mesmo(self):
        app = _app("ACOES_PNGI")

        menu = Menu.objects.create(
            aplicacao=app,
            codigo="CONFIGURACOES",
            nome="Configurações",
        )

        menu.parent = menu

        with pytest.raises(ValidationError):
            menu.save()

    def test_codigo_deve_ser_unico_dentro_da_aplicacao(self):
        app = _app("ACOES_PNGI")

        Menu.objects.create(
            aplicacao=app,
            codigo="ACOES",
            nome="Ações",
        )

        with pytest.raises(ValidationError):
            Menu.objects.create(
                aplicacao=app,
                codigo="ACOES",
                nome="Outra definição",
            )

    def test_mesmo_codigo_pode_existir_em_aplicacoes_diferentes(self):
        app_pngi = _app("ACOES_PNGI")
        app_carga = _app("CARGA_ORG_LOT")

        menu_pngi = Menu.objects.create(
            aplicacao=app_pngi,
            codigo="DASHBOARD",
            nome="Dashboard",
        )
        menu_carga = Menu.objects.create(
            aplicacao=app_carga,
            codigo="DASHBOARD",
            nome="Dashboard",
        )

        assert menu_pngi.pk != menu_carga.pk
        assert menu_pngi.codigo == menu_carga.codigo

    def test_valores_padrao(self):
        app = _app("ACOES_PNGI")

        menu = Menu.objects.create(
            aplicacao=app,
            codigo="TESTE",
            nome="Teste",
        )

        assert menu.descricao == ""
        assert menu.rota == ""
        assert menu.icone == ""
        assert menu.ordem == 0
        assert menu.ativo is True
        assert menu.parent is None
        assert menu.capability is None
