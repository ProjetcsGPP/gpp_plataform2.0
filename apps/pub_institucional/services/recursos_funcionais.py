"""Seed idempotente dos recursos funcionais de Publicações Institucionais."""

from dataclasses import dataclass

from django.contrib.auth.models import Group, Permission
from django.db import transaction

from apps.accounts.models import (
    Aplicacao,
    Capability,
    Menu,
    Role,
    RoleCapability,
)


@dataclass(frozen=True)
class DefinicaoCapability:
    codigo: str
    nome: str
    descricao: str


@dataclass(frozen=True)
class DefinicaoMenu:
    codigo: str
    nome: str
    rota: str
    icone: str
    ordem: int
    codigo_capability: str


CAPABILITIES_PUBLICACOES = (
    DefinicaoCapability(
        codigo="CATALOGO_EDOCS",
        nome="Catálogo E-Docs",
        descricao="Consulta e seleção dos patriarcas utilizados nas coletas.",
    ),
    DefinicaoCapability(
        codigo="COLETAS_EDOCS",
        nome="Coletas E-Docs",
        descricao="Solicita e acompanha consultas ao catálogo de patriarcas.",
    ),
    DefinicaoCapability(
        codigo="DIVERGENCIAS_EDOCS",
        nome="Divergências E-Docs",
        descricao="Analisa e decide divergências observadas no catálogo.",
    ),
    DefinicaoCapability(
        codigo="AUDITORIA_EDOCS",
        nome="Auditoria E-Docs",
        descricao="Consulta os eventos de auditoria do catálogo E-Docs.",
    ),
)

MENUS_PUBLICACOES = (
    DefinicaoMenu(
        codigo="PATRIARCAS_EDOCS",
        nome="Patriarcas",
        rota="/publicacoes/patriarcas",
        icone="other_houses",
        ordem=100,
        codigo_capability="CATALOGO_EDOCS",
    ),
    DefinicaoMenu(
        codigo="COLETAS_EDOCS",
        nome="Coletas",
        rota="/publicacoes/coletas",
        icone="sync",
        ordem=200,
        codigo_capability="COLETAS_EDOCS",
    ),
    DefinicaoMenu(
        codigo="DIVERGENCIAS_EDOCS",
        nome="Divergências",
        rota="/publicacoes/divergencias",
        icone="rule",
        ordem=300,
        codigo_capability="DIVERGENCIAS_EDOCS",
    ),
    DefinicaoMenu(
        codigo="AUDITORIA_EDOCS",
        nome="Auditoria",
        rota="/publicacoes/auditoria",
        icone="history",
        ordem=400,
        codigo_capability="AUDITORIA_EDOCS",
    ),
)

PERMISSOES_GESTOR_PUBLICACOES = (
    "consultar_patriarcas_edocs",
    "revisar_patriarcas_edocs",
    "selecionar_patriarcas_coleta",
    "solicitar_coleta_patriarcas_edocs",
    "view_coletapatriarcasedocs",
    "view_divergenciapatriarcaedocs",
    "view_eventoauditoriapatriarcaedocs",
    "view_observacaopatriarcaedocs",
    "view_patriarcaedocs",
    "visualizar_coletas_patriarcas",
)


@transaction.atomic
def semear_recursos_funcionais_publicacoes() -> dict[str, int]:
    """Cria ou reconcilia o contrato IAM inicial sem ativar produção."""

    aplicacao, criada = Aplicacao.objects.get_or_create(
        codigointerno="PUB_INSTITUCIONAL",
        defaults={
            "nomeaplicacao": "Publicações Institucionais",
            "base_url": None,
            "isshowinportal": True,
            "isappbloqueada": False,
            "isappproductionready": False,
        },
    )
    campos_aplicacao = []
    if aplicacao.nomeaplicacao != "Publicações Institucionais":
        aplicacao.nomeaplicacao = "Publicações Institucionais"
        campos_aplicacao.append("nomeaplicacao")
    if not aplicacao.isshowinportal:
        aplicacao.isshowinportal = True
        campos_aplicacao.append("isshowinportal")
    if campos_aplicacao:
        aplicacao.save(update_fields=campos_aplicacao)

    perfil, _ = Role.objects.update_or_create(
        aplicacao=aplicacao,
        codigoperfil="GESTOR_PUBLICACOES",
        defaults={"nomeperfil": "Gestor de Publicações"},
    )
    perfil.refresh_from_db()
    if perfil.group_id is None:
        grupo, _ = Group.objects.get_or_create(
            name="PUB_INSTITUCIONAL_GESTOR_PUBLICACOES"
        )
        perfil.group = grupo
        perfil.save(update_fields=["group"])

    capabilities = {}
    for item in CAPABILITIES_PUBLICACOES:
        capability, _ = Capability.objects.update_or_create(
            aplicacao=aplicacao,
            codigo=item.codigo,
            defaults={
                "nome": item.nome,
                "descricao": item.descricao,
                "ativo": True,
            },
        )
        capabilities[item.codigo] = capability
        RoleCapability.objects.get_or_create(
            aplicacao=aplicacao,
            role=perfil,
            capability=capability,
        )

    for item in MENUS_PUBLICACOES:
        Menu.objects.update_or_create(
            aplicacao=aplicacao,
            codigo=item.codigo,
            defaults={
                "nome": item.nome,
                "descricao": "",
                "rota": item.rota,
                "icone": item.icone,
                "ordem": item.ordem,
                "ativo": True,
                "parent": None,
                "capability": capabilities[item.codigo_capability],
            },
        )

    permissoes = Permission.objects.filter(
        content_type__app_label="pub_institucional",
        codename__in=PERMISSOES_GESTOR_PUBLICACOES,
    )
    codigos_encontrados = set(permissoes.values_list("codename", flat=True))
    codigos_ausentes = set(PERMISSOES_GESTOR_PUBLICACOES) - codigos_encontrados
    if codigos_ausentes:
        raise RuntimeError(
            "Permissões técnicas ausentes: " + ", ".join(sorted(codigos_ausentes))
        )
    permissoes_existentes = set(
        perfil.group.permissions.filter(
            content_type__app_label="pub_institucional",
            codename__in=PERMISSOES_GESTOR_PUBLICACOES,
        ).values_list("pk", flat=True)
    )
    permissoes_novas = [
        permissao
        for permissao in permissoes
        if permissao.pk not in permissoes_existentes
    ]
    if permissoes_novas:
        perfil.group.permissions.add(*permissoes_novas)

    return {
        "aplicacao_criada": int(criada),
        "capabilities": len(CAPABILITIES_PUBLICACOES),
        "associacoes": len(CAPABILITIES_PUBLICACOES),
        "menus": len(MENUS_PUBLICACOES),
        "permissoes": len(PERMISSOES_GESTOR_PUBLICACOES),
    }
