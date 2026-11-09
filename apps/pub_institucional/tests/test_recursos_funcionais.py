"""Testes do seed funcional de Publicações Institucionais."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import (
    Aplicacao,
    Capability,
    Menu,
    Role,
    RoleCapability,
)
from apps.pub_institucional.services.recursos_funcionais import (
    PERMISSOES_GESTOR_PUBLICACOES,
)

pytestmark = pytest.mark.django_db


def test_seed_publicacoes_reconcilia_contrato_funcional_sem_ativar_operacao():
    aplicacao, _ = Aplicacao.objects.update_or_create(
        codigointerno="PUB_INSTITUCIONAL",
        defaults={
            "nomeaplicacao": "Nome anterior",
            "base_url": "https://publicacoes.exemplo.local/",
            "isshowinportal": False,
            "isappbloqueada": True,
            "isappproductionready": True,
        },
    )

    call_command("semear_publicacoes", stdout=StringIO())
    call_command("semear_publicacoes", stdout=StringIO())

    aplicacao.refresh_from_db()
    assert aplicacao.nomeaplicacao == "Publicações Institucionais"
    assert aplicacao.base_url == "https://publicacoes.exemplo.local/"
    assert aplicacao.isshowinportal is True
    assert aplicacao.isappbloqueada is True
    assert aplicacao.isappproductionready is True

    perfil = Role.objects.get(
        aplicacao=aplicacao,
        codigoperfil="GESTOR_PUBLICACOES",
    )
    assert perfil.nomeperfil == "Gestor de Publicações"
    assert perfil.group.name == "PUB_INSTITUCIONAL_GESTOR_PUBLICACOES"
    assert set(
        perfil.group.permissions.filter(
            content_type__app_label="pub_institucional"
        ).values_list("codename", flat=True)
    ) >= set(PERMISSOES_GESTOR_PUBLICACOES)

    assert set(
        Capability.objects.filter(aplicacao=aplicacao).values_list(
            "codigo", flat=True
        )
    ) >= {
        "CATALOGO_EDOCS",
        "COLETAS_EDOCS",
        "DIVERGENCIAS_EDOCS",
        "AUDITORIA_EDOCS",
    }
    assert set(
        RoleCapability.objects.filter(
            aplicacao=aplicacao,
            role=perfil,
        ).values_list("capability__codigo", flat=True)
    ) >= {
        "CATALOGO_EDOCS",
        "COLETAS_EDOCS",
        "DIVERGENCIAS_EDOCS",
        "AUDITORIA_EDOCS",
    }

    menus = list(
        Menu.objects.filter(
            aplicacao=aplicacao,
            codigo__in={
                "PATRIARCAS_EDOCS",
                "COLETAS_EDOCS",
                "DIVERGENCIAS_EDOCS",
                "AUDITORIA_EDOCS",
            },
        )
        .order_by("ordem")
        .values_list("codigo", "rota", "capability__codigo")
    )
    assert menus == [
        (
            "PATRIARCAS_EDOCS",
            "/publicacoes/patriarcas",
            "CATALOGO_EDOCS",
        ),
        ("COLETAS_EDOCS", "/publicacoes/coletas", "COLETAS_EDOCS"),
        (
            "DIVERGENCIAS_EDOCS",
            "/publicacoes/divergencias",
            "DIVERGENCIAS_EDOCS",
        ),
        ("AUDITORIA_EDOCS", "/publicacoes/auditoria", "AUDITORIA_EDOCS"),
    ]
