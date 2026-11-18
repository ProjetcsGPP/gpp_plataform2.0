"""Seed idempotente dos recursos funcionais de Publicações Institucionais."""

from dataclasses import dataclass

from django.contrib.auth.models import Group, Permission
from django.db import transaction

from apps.accounts.models import (Aplicacao, Capability, Menu, Role,
                                  RoleCapability)
from apps.pub_institucional.models import (
    ConfiguracaoVisaoPublicacao, EscopoVisaoPublicacao,
    FonteVisaoPublicacao, PerfilCalculoEflow)


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
    codigo_capability: str | None = None
    codigo_parent: str | None = None


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
    DefinicaoCapability(
        codigo="COLETA_DADOS",
        nome="Coleta de Dados",
        descricao="Importa e consulta as fontes utilizadas nas publicações.",
    ),
    DefinicaoCapability(
        codigo="PUBLICACOES",
        nome="Publicações",
        descricao="Prepara, valida, publica e preserva versões institucionais.",
    ),
)

MENUS_PUBLICACOES = (
    DefinicaoMenu(
        codigo="PATRIARCAS",
        nome="Patriarcas",
        rota="",
        icone="other_houses",
        ordem=100,
    ),
    DefinicaoMenu(
        codigo="PATRIARCAS_EDOCS",
        nome="Catálogo",
        rota="/publicacoes/patriarcas",
        icone="other_houses",
        ordem=100,
        codigo_capability="CATALOGO_EDOCS",
        codigo_parent="PATRIARCAS",
    ),
    DefinicaoMenu(
        codigo="COLETAS_EDOCS",
        nome="Coletas",
        rota="/publicacoes/coletas",
        icone="sync",
        ordem=200,
        codigo_capability="COLETAS_EDOCS",
        codigo_parent="PATRIARCAS",
    ),
    DefinicaoMenu(
        codigo="DIVERGENCIAS_EDOCS",
        nome="Divergências",
        rota="/publicacoes/divergencias",
        icone="rule",
        ordem=300,
        codigo_capability="DIVERGENCIAS_EDOCS",
        codigo_parent="PATRIARCAS",
    ),
    DefinicaoMenu(
        codigo="AUDITORIA_EDOCS",
        nome="Auditoria",
        rota="/publicacoes/auditoria",
        icone="history",
        ordem=400,
        codigo_capability="AUDITORIA_EDOCS",
        codigo_parent="PATRIARCAS",
    ),
    DefinicaoMenu(
        codigo="COLETA_DADOS",
        nome="Coleta de Dados",
        rota="",
        icone="database",
        ordem=200,
    ),
    DefinicaoMenu(
        codigo="COLETA_EDOCS_MENSAL",
        nome="E-Docs",
        rota="/publicacoes/coleta-dados/edocs",
        icone="cloud_download",
        ordem=100,
        codigo_capability="COLETA_DADOS",
        codigo_parent="COLETA_DADOS",
    ),
    DefinicaoMenu(
        codigo="COLETA_EFLOW",
        nome="E-Flow",
        rota="/publicacoes/coleta-dados/eflow",
        icone="upload_file",
        ordem=200,
        codigo_capability="COLETA_DADOS",
        codigo_parent="COLETA_DADOS",
    ),
    DefinicaoMenu(
        codigo="PUBLICACOES",
        nome="Publicações",
        rota="",
        icone="publish",
        ordem=300,
    ),
    DefinicaoMenu(
        codigo="GESTAO_PUBLICACOES",
        nome="Gestão",
        rota="/publicacoes/gestao",
        icone="edit_document",
        ordem=100,
        codigo_capability="PUBLICACOES",
        codigo_parent="PUBLICACOES",
    ),
    DefinicaoMenu(
        codigo="VISOES_PUBLICACAO",
        nome="Visões",
        rota="/publicacoes/visoes",
        icone="filter_alt",
        ordem=200,
        codigo_capability="PUBLICACOES",
        codigo_parent="PUBLICACOES",
    ),
    DefinicaoMenu(
        codigo="HISTORICO_PUBLICACOES",
        nome="Histórico",
        rota="/publicacoes/historico",
        icone="history",
        ordem=300,
        codigo_capability="PUBLICACOES",
        codigo_parent="PUBLICACOES",
    ),
)

PERMISSOES_GESTOR_PUBLICACOES = (
    "add_municipioedocs",
    "alterar_indicador_municipio_sem_edocs",
    "alterar_indicadores_municipais_edocs",
    "alterar_situacao_municipio_edocs",
    "alterar_preferencia_exibicao_eflow",
    "consultar_patriarcas_edocs",
    "add_publicacao",
    "calcular_publicacao",
    "change_publicacao",
    "change_municipioedocs",
    "configurar_visao_publicacao",
    "importar_coleta_eflow",
    "revisar_patriarcas_edocs",
    "selecionar_patriarcas_coleta",
    "solicitar_coleta_patriarcas_edocs",
    "solicitar_coleta_mensal_edocs",
    "substituir_publicacao",
    "publicar_publicacao",
    "revogar_publicacao",
    "validar_publicacao",
    "view_coletapatriarcasedocs",
    "view_coletaeflow",
    "view_coletamensaledocs",
    "view_definicaofluxoeflow",
    "view_divergenciapatriarcaedocs",
    "view_eventoauditoriapatriarcaedocs",
    "view_eventoauditoriaeflow",
    "view_eventoauditoriamunicipioedocs",
    "view_eventoauditoriapreferenciaeflow",
    "view_eventoauditoriacoletamensaledocs",
    "view_configuracaovisaopublicacao",
    "view_historicopublicacao",
    "view_implantacaopatriarcaedocs",
    "view_municipioedocs",
    "view_fontebrutacoletamensaledocs",
    "view_observacaopatriarcaedocs",
    "view_patriarcaedocs",
    "view_preferenciaexibicaoeflow",
    "view_publicacao",
    "view_resultadocalculoeflow",
    "view_resultadomensalorganizacaoedocs",
    "view_resultadomensalpatriarcaedocs",
    "visualizar_coletas_patriarcas",
    "visualizar_previa_publicacao",
)


VISOES_INICIAIS_PUBLICACAO = (
    {
        "codigo": "MUNICIPIOS_EDOCS",
        "nome": "Municípios E-Docs",
        "descricao": "Patriarcas municipais com código IBGE na competência.",
        "fonte": FonteVisaoPublicacao.EDOCS,
        "escopo": EscopoVisaoPublicacao.MUNICIPIOS,
        "perfil_calculo_eflow": "",
    },
    {
        "codigo": "GERAL_EFLOW",
        "nome": "E-Flow Geral",
        "descricao": "Todas as definições do snapshot E-Flow vigente.",
        "fonte": FonteVisaoPublicacao.EFLOW,
        "escopo": EscopoVisaoPublicacao.TODOS,
        "perfil_calculo_eflow": PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO,
    },
    {
        "codigo": "MUNICIPIOS_EFLOW",
        "nome": "Municípios E-Flow",
        "descricao": "Definições dos patriarcas com código IBGE.",
        "fonte": FonteVisaoPublicacao.EFLOW,
        "escopo": EscopoVisaoPublicacao.MUNICIPIOS,
        "perfil_calculo_eflow": PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO,
    },
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

    menus = {}
    for item in MENUS_PUBLICACOES:
        parent = menus.get(item.codigo_parent)
        if item.codigo_parent and parent is None:
            raise RuntimeError(
                f"Menu pai não definido antes do filho: {item.codigo_parent}"
            )
        menu, _ = Menu.objects.update_or_create(
            aplicacao=aplicacao,
            codigo=item.codigo,
            defaults={
                "nome": item.nome,
                "descricao": "",
                "rota": item.rota,
                "icone": item.icone,
                "ordem": item.ordem,
                "ativo": True,
                "parent": parent,
                "capability": capabilities.get(item.codigo_capability),
            },
        )
        menus[item.codigo] = menu

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

    for definicao in VISOES_INICIAIS_PUBLICACAO:
        ConfiguracaoVisaoPublicacao.objects.update_or_create(
            codigo=definicao["codigo"],
            defaults={**definicao, "ativa": True},
        )

    return {
        "aplicacao_criada": int(criada),
        "capabilities": len(CAPABILITIES_PUBLICACOES),
        "associacoes": len(CAPABILITIES_PUBLICACOES),
        "menus": len(MENUS_PUBLICACOES),
        "permissoes": len(PERMISSOES_GESTOR_PUBLICACOES),
        "visoes_publicacao": len(VISOES_INICIAIS_PUBLICACAO),
    }
