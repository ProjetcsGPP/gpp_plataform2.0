"""API de consumo de capabilities e navegação funcional."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Capability, Menu, Role, RoleCapability
from apps.accounts.serializers import RoleCapabilitySerializer


pytestmark = pytest.mark.django_db


@pytest.fixture
def functional_resources():
    app_pngi = Aplicacao.objects.get(codigointerno="ACOES_PNGI")
    app_carga = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")

    capability_acoes = Capability.objects.create(
        aplicacao=app_pngi,
        codigo="ACOES",
        nome="Ações",
    )
    capability_config = Capability.objects.create(
        aplicacao=app_pngi,
        codigo="CONFIGURACOES",
        nome="Configurações",
    )
    capability_inativa = Capability.objects.create(
        aplicacao=app_pngi,
        codigo="INATIVA",
        nome="Inativa",
        ativo=False,
    )
    capability_carga = Capability.objects.create(
        aplicacao=app_carga,
        codigo="CARGAS",
        nome="Cargas",
    )

    gestor = Role.objects.get(codigoperfil="GESTOR_PNGI")
    coordenador = Role.objects.get(codigoperfil="COORDENADOR_PNGI")
    operador = Role.objects.get(codigoperfil="OPERADOR_ACAO")

    for role, capability in [
        (gestor, capability_acoes),
        (gestor, capability_config),
        (gestor, capability_inativa),
        (coordenador, capability_acoes),
        (operador, capability_acoes),
    ]:
        RoleCapability.objects.create(
            aplicacao=app_pngi,
            role=role,
            capability=capability,
        )

    dashboard = Menu.objects.create(
        aplicacao=app_pngi,
        codigo="DASHBOARD",
        nome="Dashboard",
        rota="/acoes-pngi",
        icone="dashboard",
        ordem=10,
    )
    menu_acoes = Menu.objects.create(
        aplicacao=app_pngi,
        codigo="ACOES",
        nome="Ações",
        rota="/acoes-pngi/acoes",
        icone="assignment",
        ordem=20,
        capability=capability_acoes,
    )
    menu_config = Menu.objects.create(
        aplicacao=app_pngi,
        codigo="CONFIGURACOES",
        nome="Configurações",
        icone="settings",
        ordem=30,
        capability=capability_config,
    )
    menu_eixos = Menu.objects.create(
        aplicacao=app_pngi,
        codigo="EIXOS",
        nome="Eixos",
        rota="/acoes-pngi/configuracoes/eixos",
        icone="account_tree",
        ordem=10,
        parent=menu_config,
    )
    menu_vigencias = Menu.objects.create(
        aplicacao=app_pngi,
        codigo="VIGENCIAS",
        nome="Vigências",
        rota="/acoes-pngi/configuracoes/vigencias",
        icone="event",
        ordem=20,
        parent=menu_config,
    )
    Menu.objects.create(
        aplicacao=app_pngi,
        codigo="MENU_INATIVO",
        nome="Menu inativo",
        ativo=False,
    )
    Menu.objects.create(
        aplicacao=app_carga,
        codigo="CARGAS",
        nome="Cargas",
        capability=capability_carga,
    )

    return {
        "app_pngi": app_pngi,
        "capability_acoes": capability_acoes,
        "gestor": gestor,
        "dashboard": dashboard,
        "menu_acoes": menu_acoes,
        "menu_config": menu_config,
        "menu_eixos": menu_eixos,
        "menu_vigencias": menu_vigencias,
    }


def test_capabilities_exigem_autenticacao(functional_resources):
    response = APIClient().get("/api/accounts/capabilities/")

    assert response.status_code == 401


def test_gestor_recebe_capabilities_distribuidas_ativas(
    client_gestor,
    functional_resources,
):
    response = client_gestor.get("/api/accounts/capabilities/")

    assert response.status_code == 200
    assert [item["codigo"] for item in response.data] == [
        "ACOES",
        "CONFIGURACOES",
    ]
    assert {item["aplicacao_codigo"] for item in response.data} == {"ACOES_PNGI"}


def test_coordenador_recebe_somente_capability_acoes(
    client_coordenador,
    functional_resources,
):
    response = client_coordenador.get("/api/accounts/capabilities/")

    assert response.status_code == 200
    assert [item["codigo"] for item in response.data] == ["ACOES"]


def test_filtro_por_query_nao_troca_app_context(
    client_gestor,
    functional_resources,
):
    response = client_gestor.get(
        "/api/accounts/capabilities/?aplicacao=CARGA_ORG_LOT"
    )

    assert response.status_code == 200
    assert {item["aplicacao_codigo"] for item in response.data} == {"ACOES_PNGI"}


def test_capabilities_sao_somente_leitura(client_gestor, functional_resources):
    response = client_gestor.post(
        "/api/accounts/capabilities/",
        {"codigo": "NOVA", "nome": "Nova"},
        format="json",
    )

    assert response.status_code == 405


def test_menu_gestor_retorna_arvore_hierarquica(
    client_gestor,
    functional_resources,
):
    response = client_gestor.get("/api/accounts/menus/")

    assert response.status_code == 200
    assert response.data["app_context"] == "ACOES_PNGI"
    assert [item["codigo"] for item in response.data["items"]] == [
        "DASHBOARD",
        "ACOES",
        "CONFIGURACOES",
    ]

    configuracoes = response.data["items"][2]
    assert configuracoes["capability"] == "CONFIGURACOES"
    assert configuracoes["rota"] == ""
    assert [item["codigo"] for item in configuracoes["children"]] == [
        "EIXOS",
        "VIGENCIAS",
    ]
    assert configuracoes["children"][0]["parent"] == configuracoes["id"]


def test_menu_coordenador_nao_expoe_configuracoes_nem_filhos_orfaos(
    client_coordenador,
    functional_resources,
):
    response = client_coordenador.get("/api/accounts/menus/")

    assert response.status_code == 200
    serialized = str(response.data)
    assert [item["codigo"] for item in response.data["items"]] == [
        "DASHBOARD",
        "ACOES",
    ]
    assert "CONFIGURACOES" not in serialized
    assert "EIXOS" not in serialized
    assert "VIGENCIAS" not in serialized


def test_menu_nao_vaza_recursos_de_outra_aplicacao(
    client_gestor,
    functional_resources,
):
    response = client_gestor.get("/api/accounts/menus/")

    assert response.status_code == 200
    assert "CARGAS" not in str(response.data)


def test_menu_e_somente_leitura(client_gestor, functional_resources):
    response = client_gestor.post(
        "/api/accounts/menus/",
        {"codigo": "NOVO", "nome": "Novo"},
        format="json",
    )

    assert response.status_code == 405


def test_role_capability_nao_possui_endpoint_publico(
    client_gestor,
    functional_resources,
):
    response = client_gestor.get("/api/accounts/role-capabilities/")

    assert response.status_code == 404


def test_role_capability_serializer_representa_distribuicao(functional_resources):
    relation = RoleCapability.objects.get(
        role=functional_resources["gestor"],
        capability=functional_resources["capability_acoes"],
    )

    assert RoleCapabilitySerializer(relation).data == {
        "id": relation.pk,
        "aplicacao": functional_resources["app_pngi"].pk,
        "aplicacao_codigo": "ACOES_PNGI",
        "role": functional_resources["gestor"].pk,
        "role_codigo": "GESTOR_PNGI",
        "capability": functional_resources["capability_acoes"].pk,
        "capability_codigo": "ACOES",
    }
