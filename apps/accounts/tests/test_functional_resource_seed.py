"""Testes da carga idempotente de recursos funcionais."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import Aplicacao, Capability, Menu, RoleCapability

pytestmark = pytest.mark.django_db


def test_seed_carga_org_lot_cria_contrato_funcional_idempotente():
    application = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
    Menu.objects.filter(aplicacao=application).delete()
    RoleCapability.objects.filter(aplicacao=application).delete()
    Capability.objects.filter(aplicacao=application).delete()

    call_command("seed_functional_resources", stdout=StringIO())
    call_command("seed_functional_resources", stdout=StringIO())

    assert list(
        Capability.objects.filter(aplicacao=application).values_list(
            "codigo", flat=True
        )
    ) == ["LOTACAO", "ORGANOGRAMA", "PATRIARCA"]
    assert set(
        RoleCapability.objects.filter(aplicacao=application).values_list(
            "role__codigoperfil",
            "capability__codigo",
        )
    ) == {
        ("GESTOR_CARGA", "PATRIARCA"),
        ("GESTOR_CARGA", "ORGANOGRAMA"),
        ("GESTOR_CARGA", "LOTACAO"),
    }

    menus = list(
        Menu.objects.filter(aplicacao=application)
        .order_by("ordem")
        .values(
            "codigo",
            "nome",
            "rota",
            "icone",
            "ordem",
            "parent_id",
            "capability__codigo",
        )
    )
    assert menus == [
        {
            "codigo": "DASHBOARD",
            "nome": "Dashboard",
            "rota": "/carga-org-lot/dashboard",
            "icone": "dashboard",
            "ordem": 100,
            "parent_id": None,
            "capability__codigo": None,
        },
        {
            "codigo": "PATRIARCA",
            "nome": "Patriarcas",
            "rota": "/carga-org-lot/patriarcas",
            "icone": "other_houses",
            "ordem": 200,
            "parent_id": None,
            "capability__codigo": "PATRIARCA",
        },
        {
            "codigo": "ORGANOGRAMA",
            "nome": "Organogramas",
            "rota": "/carga-org-lot/organogramas",
            "icone": "account_tree",
            "ordem": 300,
            "parent_id": None,
            "capability__codigo": "ORGANOGRAMA",
        },
        {
            "codigo": "LOTACAO",
            "nome": "Lotações",
            "rota": "/carga-org-lot/lotacoes",
            "icone": "group_add",
            "ordem": 400,
            "parent_id": None,
            "capability__codigo": "LOTACAO",
        },
    ]


def test_seed_corrige_codigo_legado_do_menu():
    application = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
    Menu.objects.filter(aplicacao=application, codigo="PATRIARCA").delete()
    Menu.objects.update_or_create(
        aplicacao=application,
        codigo="PATRIACA",
        defaults={"nome": "Patriarca"},
    )

    call_command("seed_functional_resources", stdout=StringIO())

    assert not Menu.objects.filter(
        aplicacao=application,
        codigo="PATRIACA",
    ).exists()
    assert Menu.objects.filter(
        aplicacao=application,
        codigo="PATRIARCA",
        nome="Patriarcas",
    ).exists()
