"""Testes do contrato HTTP administrativo do catálogo E-Docs."""

from datetime import timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from django.contrib.auth.models import Permission, User
from django.test import override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import (APIClient, APIRequestFactory,
                                 force_authenticate)

from apps.accounts.middleware import AppContextMiddleware
from apps.accounts.models import AccountsSession, Aplicacao, Role, UserRole
from apps.core.middleware.application_context import URL_PREFIX_MAP
from apps.pub_institucional.models import (ColetaPatriarcasEdocs,
                                           DivergenciaPatriarcaEdocs,
                                           EventoAuditoriaPatriarcaEdocs,
                                           MunicipioEdocs, PatriarcaEdocs)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, sincronizar_patriarcas_edocs)
from apps.pub_institucional.services.recursos_funcionais import \
    semear_recursos_funcionais_publicacoes
from apps.pub_institucional.visoes import (VisaoColetaPatriarcasEdocs,
                                           VisaoConfiguracaoIbge,
                                           VisaoDivergenciaPatriarcaEdocs,
                                           VisaoEstadosIbge,
                                           VisaoEventoAuditoriaPatriarcaEdocs,
                                           VisaoMunicipioEdocs,
                                           VisaoMunicipiosIbge,
                                           VisaoMunicipiosUfPadraoIbge,
                                           VisaoPatriarcaEdocs)

pytestmark = pytest.mark.django_db

ID_PATRIARCA = UUID("b817315b-63ea-417e-b191-6ecbc42e56e4")


class ClienteEdocsSimulado:
    def listar_patriarcas(self):
        return [
            {
                "id": str(ID_PATRIARCA),
                "sigla": "PMBJN",
                "nome": "MUNICÍPIO DE BOM JESUS DO NORTE",
                "tipoAgente": 5,
                "descricaoTipoAgente": "Organizacao",
            }
        ]


@pytest.fixture
def gestor_publicacoes():
    semear_recursos_funcionais_publicacoes()
    aplicacao = Aplicacao.objects.get(codigointerno="PUB_INSTITUCIONAL")
    perfil = Role.objects.get(
        aplicacao=aplicacao,
        codigoperfil="GESTOR_PUBLICACOES",
    )
    usuario = User.objects.create_user(username="gestor_publicacoes_api")
    UserRole.objects.create(user=usuario, aplicacao=aplicacao, role=perfil)
    usuario.refresh_from_db()
    return usuario


def _requisicao(metodo, caminho, usuario, dados=None):
    fabrica = APIRequestFactory()
    construtor = getattr(fabrica, metodo)
    requisicao = construtor(
        caminho,
        data=dados,
        format="json",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=usuario)
    return requisicao


def test_rotas_resolvem_as_quatro_areas_administrativas():
    assert (
        resolve("/api/pub-institucional/municipios-edocs/").func.cls
        is VisaoMunicipioEdocs
    )
    assert resolve("/api/pub-institucional/patriarcas/").func.cls is VisaoPatriarcaEdocs
    assert resolve("/api/pub-institucional/coletas/").func.cls is VisaoColetaPatriarcasEdocs
    assert (
        resolve("/api/pub-institucional/divergencias/").func.cls
        is VisaoDivergenciaPatriarcaEdocs
    )


def test_rotas_ibge_resolvem_na_api_administrativa_de_publicacoes():
    assert (
        resolve("/api/pub-institucional/ibge/configuracao/").func.view_class
        is VisaoConfiguracaoIbge
    )
    assert (
        resolve("/api/pub-institucional/ibge/estados/").func.view_class
        is VisaoEstadosIbge
    )
    assert (
        resolve(
            "/api/pub-institucional/ibge/estados/32/municipios/"
        ).func.view_class
        is VisaoMunicipiosIbge
    )
    assert (
        resolve("/api/pub-institucional/ibge/municipios/").func.view_class
        is VisaoMunicipiosUfPadraoIbge
    )


@override_settings(IBGE_UF_PADRAO=32)
@patch("apps.pub_institucional.visoes.listar_municipios_ibge")
def test_api_ibge_uf_padrao_retorna_apenas_municipios_nao_cadastrados(
    listar_municipios,
    gestor_publicacoes,
):
    listar_municipios.return_value = [
        {"id": 3200102, "nome": "Afonso Cláudio", "codigo_uf": 32},
        {"id": 3200201, "nome": "Alegre", "codigo_uf": 32},
        {"id": 3200300, "nome": "Alfredo Chaves", "codigo_uf": 32},
    ]
    MunicipioEdocs.objects.create(codigo_ibge=3200201, nome="Alegre")
    resposta = VisaoMunicipiosUfPadraoIbge.as_view()(
        _requisicao(
            "get",
            "/api/pub-institucional/ibge/municipios/",
            gestor_publicacoes,
        )
    )

    assert resposta.status_code == 200
    assert resposta.data == [
        {"nome": "Afonso Cláudio", "codigo_ibge": 3200102},
        {"nome": "Alfredo Chaves", "codigo_ibge": 3200300},
    ]
    assert list(resposta.data[0]) == ["nome", "codigo_ibge"]
    listar_municipios.assert_called_once_with(32)


def test_municipio_sem_patriarca_pode_ser_cadastrado_e_mudar_situacao(
    gestor_publicacoes,
):
    criar = VisaoMunicipioEdocs.as_view({"post": "create"})
    resposta = criar(
        _requisicao(
            "post",
            "/api/pub-institucional/municipios-edocs/",
            gestor_publicacoes,
            {
                "codigo_ibge": 3200102,
                "nome": "Município sem patriarca",
                "situacao": "MANIFESTOU_INTERESSE",
                "ano_inicio": 2024,
                "mes_inicio": 6,
                "justificativa": "Manifestação formal recebida.",
            },
        )
    )

    assert resposta.status_code == 201
    assert resposta.data["patriarca_edocs"] is None
    assert not PatriarcaEdocs.objects.filter(codigo_municipio=3200102).exists()
    municipio = MunicipioEdocs.objects.get(codigo_ibge=3200102)

    alterar = VisaoMunicipioEdocs.as_view({"patch": "situacao"})
    resposta = alterar(
        _requisicao(
            "patch",
            f"/api/pub-institucional/municipios-edocs/{municipio.pk}/situacao/",
            gestor_publicacoes,
            {
                "situacao": "EM_IMPLANTACAO",
                "ano_inicio": 2024,
                "mes_inicio": 8,
                "versao": municipio.versao,
                "justificativa": "Implantação iniciada.",
            },
        ),
        pk=municipio.pk,
    )

    assert resposta.status_code == 200
    assert resposta.data["situacao_atual"]["situacao"] == "EM_IMPLANTACAO"
    vigencias = municipio.vigencias_situacao.order_by("ano_inicio", "mes_inicio")
    assert [(item.situacao, item.mes_inicio, item.mes_fim) for item in vigencias] == [
        ("MANIFESTOU_INTERESSE", 6, 7),
        ("EM_IMPLANTACAO", 8, None),
    ]


def test_middlewares_reconhecem_o_contexto_da_aplicacao():
    assert (
        AppContextMiddleware.APP_COOKIE_MAP["pub-institucional"]
        == "PUB_INSTITUCIONAL"
    )
    assert URL_PREFIX_MAP["pub-institucional"] == "PUB_INSTITUCIONAL"


def test_requisicao_http_usa_cookie_dedicado_da_aplicacao(gestor_publicacoes):
    chave = "pubinst-api-0000000000000000000000000000"
    AccountsSession.objects.create(
        user=gestor_publicacoes,
        session_key=chave,
        session_cookie_name="gpp_session_PUB_INSTITUCIONAL",
        app_context="PUB_INSTITUCIONAL",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    cliente = APIClient()
    cliente.cookies["gpp_session_PUB_INSTITUCIONAL"] = chave

    resposta = cliente.get("/api/pub-institucional/patriarcas/")

    assert resposta.status_code == 200
    assert resposta.data["results"] == []
    assert (
        resolve("/api/pub-institucional/auditoria/").func.cls
        is VisaoEventoAuditoriaPatriarcaEdocs
    )


def test_mapas_de_permissao_nao_dependem_do_nome_da_role():
    assert VisaoPatriarcaEdocs.mapa_permissoes == {
        "list": "view_patriarcaedocs",
        "retrieve": "view_patriarcaedocs",
        "selecao_coleta": "selecionar_patriarcas_coleta",
        "indicador_municipio_sem_edocs": (
            "alterar_indicador_municipio_sem_edocs"
        ),
        "indicadores_municipais": "alterar_indicadores_municipais_edocs",
    }
    assert VisaoColetaPatriarcasEdocs.mapa_permissoes == {
        "list": "view_coletapatriarcasedocs",
        "retrieve": "view_coletapatriarcasedocs",
        "create": "solicitar_coleta_patriarcas_edocs",
    }
    assert VisaoDivergenciaPatriarcaEdocs.mapa_permissoes["decidir"] == (
        "revisar_patriarcas_edocs"
    )
    assert VisaoEventoAuditoriaPatriarcaEdocs.mapa_permissoes["list"] == (
        "view_eventoauditoriapatriarcaedocs"
    )


def test_lista_patriarcas_e_altera_selecao_com_auditoria(gestor_publicacoes):
    patriarca = PatriarcaEdocs.objects.create(
        id_externo=ID_PATRIARCA,
        sigla="PMBJN",
        nome="MUNICÍPIO DE BOM JESUS DO NORTE",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
    )
    listar = VisaoPatriarcaEdocs.as_view({"get": "list"})
    resposta = listar(
        _requisicao(
            "get",
            "/api/pub-institucional/patriarcas/?ativo=true",
            gestor_publicacoes,
        )
    )
    assert resposta.status_code == 200
    assert resposta.data["results"][0]["id"] == patriarca.pk
    assert resposta.data["results"][0]["acoes_disponiveis"] == [
        "alterar_selecao_coleta",
        "alterar_indicador_municipio_sem_edocs",
        "alterar_indicadores_municipais",
    ]
    assert (
        resposta.data["results"][0]["municipio_implantado_sem_uso_edocs"]
        is False
    )

    selecionar = VisaoPatriarcaEdocs.as_view({"patch": "selecao_coleta"})
    resposta = selecionar(
        _requisicao(
            "patch",
            f"/api/pub-institucional/patriarcas/{patriarca.pk}/selecao-coleta/",
            gestor_publicacoes,
            {
                "coletar_detalhes": True,
                "justificativa": "Incluído na coleta mensal.",
            },
        ),
        pk=patriarca.pk,
    )
    assert resposta.status_code == 200
    patriarca.refresh_from_db()
    assert patriarca.coletar_detalhes is True
    assert EventoAuditoriaPatriarcaEdocs.objects.filter(
        patriarca=patriarca,
        tipo_evento="SELECAO_COLETA_ALTERADA",
    ).exists()

    alterar_indicador = VisaoPatriarcaEdocs.as_view(
        {"patch": "indicador_municipio_sem_edocs"}
    )
    resposta = alterar_indicador(
        _requisicao(
            "patch",
            (
                f"/api/pub-institucional/patriarcas/{patriarca.pk}/"
                "indicador-municipio-sem-edocs/"
            ),
            gestor_publicacoes,
            {
                "municipio_implantado_sem_uso_edocs": True,
                "ano_inicio": 2024,
                "mes_inicio": 6,
                "justificativa": "Implantação confirmada manualmente.",
            },
        ),
        pk=patriarca.pk,
    )
    assert resposta.status_code == 200
    assert resposta.data["municipio_implantado_sem_uso_edocs"] is True
    assert resposta.data["ano_inicio_implantacao_sem_uso_edocs"] == 2024
    assert resposta.data["mes_inicio_implantacao_sem_uso_edocs"] == 6
    assert EventoAuditoriaPatriarcaEdocs.objects.filter(
        patriarca=patriarca,
        tipo_evento="INDICADOR_SEM_EDOCS_ALTERADO",
    ).exists()

    alterar_indicadores = VisaoPatriarcaEdocs.as_view(
        {"patch": "indicadores_municipais"}
    )
    resposta = alterar_indicadores(
        _requisicao(
            "patch",
            (
                f"/api/pub-institucional/patriarcas/{patriarca.pk}/"
                "indicadores-municipais/"
            ),
            gestor_publicacoes,
            {
                "codigo_municipio": 3201100,
                "municipio_implantado": True,
                "municipio_em_implantacao": False,
                "municipio_manifestou_interesse": True,
                "justificativa": "Situação municipal validada pelo gestor.",
            },
        ),
        pk=patriarca.pk,
    )
    assert resposta.status_code == 200
    assert resposta.data["codigo_municipio"] == 3201100
    assert resposta.data["municipio_implantado"] is True
    assert resposta.data["municipio_manifestou_interesse"] is True
    assert EventoAuditoriaPatriarcaEdocs.objects.filter(
        patriarca=patriarca,
        tipo_evento="INDICADORES_MUNICIPAIS_ALTERADOS",
    ).exists()


def test_lista_patriarcas_nega_usuario_sem_permissao_tecnica(gestor_publicacoes):
    permissao = Permission.objects.get(
        content_type__app_label="pub_institucional",
        codename="view_patriarcaedocs",
    )
    gestor_publicacoes.user_permissions.remove(permissao)
    gestor_publicacoes = User.objects.get(pk=gestor_publicacoes.pk)

    listar = VisaoPatriarcaEdocs.as_view({"get": "list"})
    resposta = listar(
        _requisicao(
            "get",
            "/api/pub-institucional/patriarcas/",
            gestor_publicacoes,
        )
    )
    assert resposta.status_code == 403


def test_filtro_invalido_retorna_erro_de_contrato(gestor_publicacoes):
    listar = VisaoDivergenciaPatriarcaEdocs.as_view({"get": "list"})
    resposta = listar(
        _requisicao(
            "get",
            "/api/pub-institucional/divergencias/?coleta_id=invalido",
            gestor_publicacoes,
        )
    )
    assert resposta.status_code == 400


def test_solicita_coleta_e_retorna_recurso_persistido(gestor_publicacoes):
    coleta = ColetaPatriarcasEdocs.objects.create(
        ambiente="PRD",
        situacao="CONCLUIDA",
        iniciada_em=timezone.now(),
        concluida_em=timezone.now(),
    )
    with patch(
        "apps.pub_institucional.visoes.sincronizar_patriarcas_edocs",
        return_value=coleta,
    ):
        criar = VisaoColetaPatriarcasEdocs.as_view({"post": "create"})
        resposta = criar(
            _requisicao(
                "post",
                "/api/pub-institucional/coletas/",
                gestor_publicacoes,
                {},
            )
        )
    assert resposta.status_code == 201
    assert resposta.data["id"] == str(coleta.pk)


def test_decisao_de_divergencia_atualiza_catalogo_definitivo(gestor_publicacoes):
    coleta = sincronizar_patriarcas_edocs(
        ator=AtorAuditoriaEdocs(
            usuario_id=gestor_publicacoes.pk,
            nome=gestor_publicacoes.username,
        ),
        cliente=ClienteEdocsSimulado(),
    )
    divergencia = DivergenciaPatriarcaEdocs.objects.get(coleta=coleta)
    decidir = VisaoDivergenciaPatriarcaEdocs.as_view({"post": "decidir"})
    resposta = decidir(
        _requisicao(
            "post",
            f"/api/pub-institucional/divergencias/{divergencia.pk}/decidir/",
            gestor_publicacoes,
            {
                "decisao": "ADICIONAR",
                "justificativa": "Cadastro validado junto à PRODEST.",
                "coletar_detalhes": True,
            },
        ),
        pk=divergencia.pk,
    )
    assert resposta.status_code == 200
    assert resposta.data["situacao"] == "APLICADA"
    assert resposta.data["acoes_disponiveis"] == []
    assert PatriarcaEdocs.objects.get(id_externo=ID_PATRIARCA).coletar_detalhes

    resposta_repetida = decidir(
        _requisicao(
            "post",
            f"/api/pub-institucional/divergencias/{divergencia.pk}/decidir/",
            gestor_publicacoes,
            {
                "decisao": "ADICIONAR",
                "justificativa": "Tentativa repetida.",
            },
        ),
        pk=divergencia.pk,
    )
    assert resposta_repetida.status_code == 409
    assert resposta_repetida.data["errors"]["codigo"] == (
        "conflito_catalogo_edocs"
    )
