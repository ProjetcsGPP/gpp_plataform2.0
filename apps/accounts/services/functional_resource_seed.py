"""Carga idempotente de capabilities, role capabilities e menus."""

from dataclasses import dataclass

from django.db import transaction

from apps.accounts.models import Aplicacao, Capability, Menu, Role, RoleCapability


@dataclass(frozen=True)
class CapabilitySeed:
    codigo: str
    nome: str
    descricao: str


@dataclass(frozen=True)
class MenuSeed:
    codigo: str
    nome: str
    rota: str
    icone: str
    ordem: int
    capability_codigo: str | None = None


CARGA_ORG_LOT_CAPABILITIES = (
    CapabilitySeed(
        codigo="PATRIARCA",
        nome="Patriarcas",
        descricao=(
            "Cadastro e acompanhamento das instituições utilizadas nas cargas."
        ),
    ),
    CapabilitySeed(
        codigo="ORGANOGRAMA",
        nome="Organogramas",
        descricao="Importação, validação e acompanhamento de organogramas.",
    ),
    CapabilitySeed(
        codigo="LOTACAO",
        nome="Lotações",
        descricao="Importação, validação e acompanhamento de lotações.",
    ),
)

CARGA_ORG_LOT_MENUS = (
    MenuSeed(
        codigo="DASHBOARD",
        nome="Dashboard",
        rota="/carga-org-lot/dashboard",
        icone="dashboard",
        ordem=100,
    ),
    MenuSeed(
        codigo="PATRIARCA",
        nome="Patriarcas",
        rota="/carga-org-lot/patriarcas",
        icone="other_houses",
        ordem=200,
        capability_codigo="PATRIARCA",
    ),
    MenuSeed(
        codigo="ORGANOGRAMA",
        nome="Organogramas",
        rota="/carga-org-lot/organogramas",
        icone="account_tree",
        ordem=300,
        capability_codigo="ORGANOGRAMA",
    ),
    MenuSeed(
        codigo="LOTACAO",
        nome="Lotações",
        rota="/carga-org-lot/lotacoes",
        icone="group_add",
        ordem=400,
        capability_codigo="LOTACAO",
    ),
)


@transaction.atomic
def seed_carga_org_lot_functional_resources() -> dict[str, int]:
    """Cria ou atualiza os recursos funcionais da aplicação Carga Org/Lot."""
    application = Aplicacao.objects.get(codigointerno="CARGA_ORG_LOT")
    role = Role.objects.get(
        aplicacao=application,
        codigoperfil="GESTOR_CARGA",
    )

    _normalize_legacy_menu_code(application)

    capabilities = {}
    for item in CARGA_ORG_LOT_CAPABILITIES:
        capability, _ = Capability.objects.update_or_create(
            aplicacao=application,
            codigo=item.codigo,
            defaults={
                "nome": item.nome,
                "descricao": item.descricao,
                "ativo": True,
            },
        )
        capabilities[item.codigo] = capability
        RoleCapability.objects.get_or_create(
            aplicacao=application,
            role=role,
            capability=capability,
        )

    for item in CARGA_ORG_LOT_MENUS:
        Menu.objects.update_or_create(
            aplicacao=application,
            codigo=item.codigo,
            defaults={
                "nome": item.nome,
                "descricao": "",
                "rota": item.rota,
                "icone": item.icone,
                "ordem": item.ordem,
                "ativo": True,
                "parent": None,
                "capability": capabilities.get(item.capability_codigo),
            },
        )

    return {
        "capabilities": len(CARGA_ORG_LOT_CAPABILITIES),
        "role_capabilities": len(CARGA_ORG_LOT_CAPABILITIES),
        "menus": len(CARGA_ORG_LOT_MENUS),
    }


def _normalize_legacy_menu_code(application: Aplicacao) -> None:
    legacy = Menu.objects.filter(
        aplicacao=application,
        codigo="PATRIACA",
    ).first()
    if legacy is None:
        return

    canonical = Menu.objects.filter(
        aplicacao=application,
        codigo="PATRIARCA",
    ).first()
    if canonical is None:
        legacy.codigo = "PATRIARCA"
        legacy.save(update_fields=["codigo"])
        return

    legacy.delete()

