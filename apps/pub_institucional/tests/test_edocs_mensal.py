"""Testes da persistência mensal versionada dos relatórios E-Docs."""

import json
from io import StringIO
from uuid import UUID

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import resolve
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.pub_institucional.models import (ColetaMensalEdocs,
                                           EventoAuditoriaColetaMensalEdocs,
                                           FonteBrutaColetaMensalEdocs,
                                           PatriarcaEdocs,
                                           ResultadoMensalOrganizacaoEdocs,
                                           ResultadoMensalPatriarcaEdocs,
                                           SituacaoColetaMensalEdocs)
from apps.pub_institucional.services.edocs_mensal import (
    ErroColetaMensalEdocs, executar_coleta_mensal_edocs,
    solicitar_coleta_mensal_edocs)
from apps.pub_institucional.services.patriarcas_edocs import AtorAuditoriaEdocs
from apps.pub_institucional.services.recursos_funcionais import \
    semear_recursos_funcionais_publicacoes
from apps.pub_institucional.visoes import (
    VisaoColetaMensalEdocs, VisaoEventoAuditoriaColetaMensalEdocs,
    VisaoFonteBrutaColetaMensalEdocs, VisaoResultadoMensalOrganizacaoEdocs,
    VisaoResultadoMensalPatriarcaEdocs)

pytestmark = pytest.mark.django_db

ID_PATRIARCA = UUID("b817315b-63ea-417e-b191-6ecbc42e56e4")
ID_ORGANIZACAO = UUID("8dff4a03-d25d-42d6-8bc3-376e0e7ead53")


class ClienteEdocsMensalSimulado:
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

    def relatorio_processos(self, mes, ano):
        assert (mes, ano) == ("09", 2024)
        return [
            {
                "idPatriarca": str(ID_PATRIARCA),
                "nomePatriarca": "PMBJN - MUNICÍPIO DE BOM JESUS DO NORTE",
                "totalProcessos": 12,
            }
        ]

    def relatorio_documentos(self, mes, ano):
        assert (mes, ano) == ("09", 2024)
        return [
            {
                "idPatriarca": str(ID_PATRIARCA),
                "nomePatriarca": "PMBJN - MUNICÍPIO DE BOM JESUS DO NORTE",
                "totalDocumentos": 25,
                "totalPaginas": 71,
            }
        ]

    def relatorio_processos_por_patriarca(self, id_patriarca, mes, ano):
        assert UUID(str(id_patriarca)) == ID_PATRIARCA
        return [
            {
                "idPatriarca": str(ID_PATRIARCA),
                "idOrganizacao": str(ID_ORGANIZACAO),
                "nomeOrganizacao": "SEMPLAF",
                "totalProcessos": 7,
            }
        ]

    def relatorio_documentos_por_patriarca(self, id_patriarca, mes, ano):
        assert UUID(str(id_patriarca)) == ID_PATRIARCA
        return [
            {
                "idPatriarca": str(ID_PATRIARCA),
                "idOrganizacao": str(ID_ORGANIZACAO),
                "nomeOrganizacao": "SEMPLAF",
                "totalDocumentos": 16,
                "totalPaginas": 42,
            }
        ]


@pytest.fixture
def patriarca_selecionado():
    return PatriarcaEdocs.objects.create(
        id_externo=ID_PATRIARCA,
        sigla="PMBJN",
        nome="MUNICÍPIO DE BOM JESUS DO NORTE",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
        coletar_detalhes=True,
        codigo_municipio=3201100,
    )


@pytest.fixture
def gestor_publicacoes_mensal():
    semear_recursos_funcionais_publicacoes()
    aplicacao = Aplicacao.objects.get(codigointerno="PUB_INSTITUCIONAL")
    perfil = Role.objects.get(
        aplicacao=aplicacao,
        codigoperfil="GESTOR_PUBLICACOES",
    )
    usuario = User.objects.create_user(username="gestor_publicacoes_mensal")
    UserRole.objects.create(user=usuario, aplicacao=aplicacao, role=perfil)
    return usuario


def test_coleta_mensal_preserva_fontes_e_normaliza_resultados(
    patriarca_selecionado,
):
    ator = AtorAuditoriaEdocs(usuario_id=7, nome="Gestor")
    coleta = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        ator=ator,
        agendar=False,
    )

    coleta = executar_coleta_mensal_edocs(
        coleta.pk,
        cliente=ClienteEdocsMensalSimulado(),
    )

    assert coleta.situacao == SituacaoColetaMensalEdocs.CONCLUIDA
    assert coleta.revisao == 1
    assert coleta.quantidade_patriarcas == 1
    assert coleta.quantidade_organizacoes == 1
    assert coleta.quantidade_fontes_brutas == 5
    assert FonteBrutaColetaMensalEdocs.objects.filter(coleta=coleta).count() == 5
    resultado = ResultadoMensalPatriarcaEdocs.objects.get(coleta=coleta)
    assert resultado.patriarca == patriarca_selecionado
    assert resultado.codigo_municipio == 3201100
    assert (resultado.total_processos, resultado.total_documentos) == (12, 25)
    assert resultado.total_paginas == 71
    organizacao = ResultadoMensalOrganizacaoEdocs.objects.get(coleta=coleta)
    assert organizacao.id_organizacao_externo == ID_ORGANIZACAO
    assert (organizacao.total_processos, organizacao.total_documentos) == (7, 16)
    assert organizacao.total_paginas == 42
    assert set(
        EventoAuditoriaColetaMensalEdocs.objects.filter(
            coleta=coleta
        ).values_list("tipo_evento", flat=True)
    ) == {"SOLICITADA", "INICIADA", "CONCLUIDA"}


def test_recoleta_da_mesma_competencia_cria_nova_revisao(
    patriarca_selecionado,
):
    primeira = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    primeira.situacao = SituacaoColetaMensalEdocs.FALHOU
    primeira.save(update_fields=("situacao", "atualizado_em"))

    segunda = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )

    assert segunda.competencia_id == primeira.competencia_id
    assert segunda.revisao == 2
    assert ColetaMensalEdocs.objects.filter(
        competencia=primeira.competencia
    ).count() == 2


def test_nao_permite_duas_coletas_ativas_na_mesma_competencia(
    patriarca_selecionado,
):
    solicitar_coleta_mensal_edocs(ano=2024, mes=9, agendar=False)

    with pytest.raises(ErroColetaMensalEdocs, match="coleta ativa"):
        solicitar_coleta_mensal_edocs(ano=2024, mes=9, agendar=False)


def test_selecao_fica_congelada_quando_coleta_e_solicitada(
    patriarca_selecionado,
):
    coleta = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    patriarca_selecionado.coletar_detalhes = False
    patriarca_selecionado.save(update_fields=("coletar_detalhes", "atualizado_em"))

    assert coleta.patriarcas_solicitados == [
        {
            "id": patriarca_selecionado.pk,
            "id_externo": str(ID_PATRIARCA),
            "sigla": "PMBJN",
            "nome": "MUNICÍPIO DE BOM JESUS DO NORTE",
        }
    ]


def test_rotas_mensais_expoem_coleta_resultados_fontes_e_auditoria():
    assert (
        resolve("/api/pub-institucional/coletas-mensais-edocs/").func.cls
        is VisaoColetaMensalEdocs
    )
    assert (
        resolve(
            "/api/pub-institucional/resultados-mensais-patriarcas-edocs/"
        ).func.cls
        is VisaoResultadoMensalPatriarcaEdocs
    )
    assert (
        resolve(
            "/api/pub-institucional/resultados-mensais-organizacoes-edocs/"
        ).func.cls
        is VisaoResultadoMensalOrganizacaoEdocs
    )
    assert (
        resolve(
            "/api/pub-institucional/fontes-brutas-coletas-mensais-edocs/"
        ).func.cls
        is VisaoFonteBrutaColetaMensalEdocs
    )
    assert (
        resolve(
            "/api/pub-institucional/auditoria-coletas-mensais-edocs/"
        ).func.cls
        is VisaoEventoAuditoriaColetaMensalEdocs
    )


def test_api_solicita_coleta_assincrona(
    patriarca_selecionado,
    gestor_publicacoes_mensal,
    monkeypatch,
):
    def solicitar_sem_agendar(**argumentos):
        return solicitar_coleta_mensal_edocs(**argumentos, agendar=False)

    monkeypatch.setattr(
        "apps.pub_institucional.visoes.solicitar_coleta_mensal_edocs",
        solicitar_sem_agendar,
    )
    requisicao = APIRequestFactory().post(
        "/api/pub-institucional/coletas-mensais-edocs/",
        {"ano": 2024, "mes": 9},
        format="json",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_mensal)

    resposta = VisaoColetaMensalEdocs.as_view({"post": "create"})(requisicao)

    assert resposta.status_code == 202
    assert resposta.data["ano"] == 2024
    assert resposta.data["mes"] == 9
    assert resposta.data["revisao"] == 1
    assert resposta.data["situacao"] == "AGENDADA"


def test_comando_importa_codigo_municipal_com_auditoria(
    patriarca_selecionado,
    tmp_path,
):
    patriarca_selecionado.codigo_municipio = None
    patriarca_selecionado.save(update_fields=("codigo_municipio", "atualizado_em"))
    caminho = tmp_path / "patriarcas.json"
    caminho.write_text(
        json.dumps(
            [
                {
                    "id": str(ID_PATRIARCA),
                    "nome": patriarca_selecionado.nome,
                    "COD_MUNIC": 3201100,
                }
            ]
        ),
        encoding="utf-8",
    )

    call_command(
        "importar_codigos_municipios_edocs",
        arquivo=caminho,
        stdout=StringIO(),
    )

    patriarca_selecionado.refresh_from_db()
    assert patriarca_selecionado.codigo_municipio == 3201100
    assert patriarca_selecionado.eventos_auditoria.filter(
        tipo_evento="INDICADORES_MUNICIPAIS_ALTERADOS"
    ).exists()
