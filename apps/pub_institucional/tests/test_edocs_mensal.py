"""Testes da persistência mensal versionada dos relatórios E-Docs."""

import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from uuid import UUID

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.pub_institucional.models import (
    ColetaMensalEdocs,
    CompetenciaEdocs,
    EventoAuditoriaColetaMensalEdocs,
    FonteBrutaColetaMensalEdocs,
    PatriarcaEdocs,
    ResultadoMensalOrganizacaoEdocs,
    ResultadoMensalPatriarcaEdocs,
    SituacaoColetaMensalEdocs,
)
from apps.pub_institucional.serializadores import (
    SerializadorResultadoMensalPatriarcaEdocs,
)
from apps.pub_institucional.services.calculos_edocs import calcular_indicadores_edocs
from apps.pub_institucional.services.edocs_mensal import (
    ErroColetaMensalEdocs,
    executar_coleta_mensal_edocs,
    obter_totais_historicos_edocs,
    reencaminhar_coleta_mensal_edocs,
    solicitar_coleta_mensal_edocs,
)
from apps.pub_institucional.services.patriarcas_edocs import AtorAuditoriaEdocs
from apps.pub_institucional.services.recursos_funcionais import (
    semear_recursos_funcionais_publicacoes,
)
from apps.pub_institucional.tasks import recuperar_coletas_mensais_edocs
from apps.pub_institucional.visoes import (
    VisaoColetaMensalEdocs,
    VisaoEventoAuditoriaColetaMensalEdocs,
    VisaoFonteBrutaColetaMensalEdocs,
    VisaoResultadoMensalOrganizacaoEdocs,
    VisaoResultadoMensalPatriarcaEdocs,
)

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

    assert coleta.situacao == SituacaoColetaMensalEdocs.SUCESSO
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
    assert resultado.versao_calculo == "PLANILHA_MUNICIPIOS_V1"
    assert resultado.economia_papel_kg == Decimal("0.33299")
    assert resultado.gases_poluentes_kg == Decimal("0.2485")
    assert resultado.economia_papel_reais == Decimal("4.26")
    assert resultado.economia_insumos_reais == Decimal("14.40")
    assert resultado.economia_impressao_reais == Decimal("7.10")
    assert resultado.economia_total_reais == Decimal("25.76")
    assert resultado.economia_agua_m3 == Decimal("0.71")
    assert resultado.arvores_salvas == Decimal("0.0071")
    dados_api = SerializadorResultadoMensalPatriarcaEdocs(resultado).data
    assert dados_api["economia_papel_kg"] == "0.33299"
    assert dados_api["gases_poluentes_kg"] == "0.2485"
    assert dados_api["economia_total_reais"] == "25.76"
    organizacao = ResultadoMensalOrganizacaoEdocs.objects.get(coleta=coleta)
    assert organizacao.id_organizacao_externo == ID_ORGANIZACAO
    assert (organizacao.total_processos, organizacao.total_documentos) == (7, 16)
    assert organizacao.total_paginas == 42
    assert set(
        EventoAuditoriaColetaMensalEdocs.objects.filter(coleta=coleta).values_list(
            "tipo_evento", flat=True
        )
    ) == {"SOLICITADA", "EXECUCAO_INICIADA", "SUCESSO"}
    evento_sucesso = EventoAuditoriaColetaMensalEdocs.objects.get(
        coleta=coleta,
        tipo_evento="SUCESSO",
    )
    assert evento_sucesso.metadados["versao_calculo"] == ("PLANILHA_MUNICIPIOS_V1")


def test_recoleta_da_mesma_competencia_cria_nova_revisao(
    patriarca_selecionado,
):
    primeira = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    primeira.situacao = SituacaoColetaMensalEdocs.ERRO
    primeira.save(update_fields=("situacao", "atualizado_em"))

    segunda = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )

    assert segunda.competencia_id == primeira.competencia_id
    assert segunda.revisao == 2
    assert (
        ColetaMensalEdocs.objects.filter(competencia=primeira.competencia).count() == 2
    )


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
        resolve("/api/pub-institucional/resultados-mensais-patriarcas-edocs/").func.cls
        is VisaoResultadoMensalPatriarcaEdocs
    )
    assert (
        resolve(
            "/api/pub-institucional/resultados-mensais-organizacoes-edocs/"
        ).func.cls
        is VisaoResultadoMensalOrganizacaoEdocs
    )
    assert (
        resolve("/api/pub-institucional/fontes-brutas-coletas-mensais-edocs/").func.cls
        is VisaoFonteBrutaColetaMensalEdocs
    )
    assert (
        resolve("/api/pub-institucional/auditoria-coletas-mensais-edocs/").func.cls
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
    assert resposta.data["situacao"] == "SOLICITADA"
    assert resposta.data["acoes_disponiveis"] == ["reencaminhar"]


def test_api_retorna_totais_de_todos_os_municipios_da_coleta(
    patriarca_selecionado,
    gestor_publicacoes_mensal,
):
    coleta = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    coleta = executar_coleta_mensal_edocs(
        coleta.pk,
        cliente=ClienteEdocsMensalSimulado(),
    )
    outro_patriarca = PatriarcaEdocs.objects.create(
        id_externo=UUID("142e5085-4248-4211-80e5-f9e7d0ca4f9e"),
        sigla="PMAB",
        nome="MUNICÍPIO DE ÁGUIA BRANCA",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
        codigo_municipio=3200136,
    )
    indicadores = calcular_indicadores_edocs(
        total_paginas=29,
        total_processos=8,
    )
    ResultadoMensalPatriarcaEdocs.objects.create(
        coleta=coleta,
        patriarca=outro_patriarca,
        id_patriarca_externo=outro_patriarca.id_externo,
        sigla_patriarca=outro_patriarca.sigla,
        nome_patriarca=outro_patriarca.nome,
        codigo_municipio=outro_patriarca.codigo_municipio,
        total_processos=8,
        total_documentos=10,
        total_paginas=29,
        **indicadores.__dict__,
    )
    requisicao = APIRequestFactory().get(
        "/api/pub-institucional/resultados-mensais-patriarcas-edocs/totais/",
        {"coleta_id": str(coleta.pk)},
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_mensal)

    resposta = VisaoResultadoMensalPatriarcaEdocs.as_view({"get": "totais"})(requisicao)

    assert resposta.status_code == 200
    assert resposta.data["coleta_id"] == str(coleta.pk)
    assert resposta.data["quantidade_municipios"] == 2
    assert resposta.data["total_processos"] == 20
    assert resposta.data["total_documentos"] == 35
    assert resposta.data["total_paginas"] == 100
    assert resposta.data["economia_papel_kg"] == "0.46900"
    assert resposta.data["gases_poluentes_kg"] == "0.3500"
    assert resposta.data["economia_total_reais"] == "40.00"
    assert resposta.data["economia_agua_m3"] == "1.00"
    assert resposta.data["arvores_salvas"] == "0.0100"


def test_totais_historicos_atendem_quatro_escopos_com_ultima_revisao(
    patriarca_selecionado,
    gestor_publicacoes_mensal,
):
    outro_patriarca = PatriarcaEdocs.objects.create(
        id_externo=UUID("142e5085-4248-4211-80e5-f9e7d0ca4f9e"),
        sigla="PMAB",
        nome="MUNICÍPIO DE ÁGUIA BRANCA",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
        codigo_municipio=3200136,
    )

    def criar_coleta(ano, revisao):
        competencia, _ = CompetenciaEdocs.objects.get_or_create(ano=ano, mes=9)
        return ColetaMensalEdocs.objects.create(
            competencia=competencia,
            revisao=revisao,
            ambiente="PRD",
            situacao=SituacaoColetaMensalEdocs.SUCESSO,
            concluida_em=timezone.now(),
        )

    def criar_resultado(coleta, patriarca, processos, documentos, paginas):
        indicadores = calcular_indicadores_edocs(
            total_paginas=paginas,
            total_processos=processos,
        )
        ResultadoMensalPatriarcaEdocs.objects.create(
            coleta=coleta,
            patriarca=patriarca,
            id_patriarca_externo=patriarca.id_externo,
            sigla_patriarca=patriarca.sigla,
            nome_patriarca=patriarca.nome,
            codigo_municipio=patriarca.codigo_municipio,
            total_processos=processos,
            total_documentos=documentos,
            total_paginas=paginas,
            **indicadores.__dict__,
        )

    revisao_antiga = criar_coleta(2024, 1)
    criar_resultado(revisao_antiga, patriarca_selecionado, 1, 2, 10)
    criar_resultado(revisao_antiga, outro_patriarca, 3, 6, 30)
    revisao_atual = criar_coleta(2024, 2)
    criar_resultado(revisao_atual, patriarca_selecionado, 2, 4, 20)
    criar_resultado(revisao_atual, outro_patriarca, 4, 8, 40)
    coleta_2025 = criar_coleta(2025, 1)
    criar_resultado(coleta_2025, patriarca_selecionado, 3, 6, 30)

    por_ano = obter_totais_historicos_edocs(ano=2024)
    total_geral = obter_totais_historicos_edocs()
    por_ano_municipio = obter_totais_historicos_edocs(
        ano=2024,
        patriarca_id=patriarca_selecionado.pk,
    )
    total_municipio = obter_totais_historicos_edocs(
        patriarca_id=patriarca_selecionado.pk,
    )

    assert (por_ano["total_paginas"], por_ano["quantidade_municipios"]) == (60, 2)
    assert (total_geral["total_paginas"], total_geral["quantidade_competencias"]) == (
        90,
        2,
    )
    assert por_ano_municipio["total_paginas"] == 20
    assert total_municipio["total_paginas"] == 50

    requisicao = APIRequestFactory().get(
        (
            "/api/pub-institucional/resultados-mensais-patriarcas-edocs/"
            "totais-historicos/"
        ),
        {"ano": 2024, "patriarca_id": patriarca_selecionado.pk},
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_mensal)
    resposta = VisaoResultadoMensalPatriarcaEdocs.as_view({"get": "totais_historicos"})(
        requisicao
    )

    assert resposta.status_code == 200
    assert resposta.data["ano"] == 2024
    assert resposta.data["patriarca_id"] == patriarca_selecionado.pk
    assert resposta.data["total_paginas"] == 20
    assert resposta.data["economia_total_reais"] == "5.60"
    assert resposta.data["quantidade_competencias"] == 1
    assert resposta.data["quantidade_municipios"] == 1


def test_solicitacao_pendente_pode_ser_reencaminhada_sem_nova_revisao(
    patriarca_selecionado,
    monkeypatch,
):
    coleta = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    agendamentos = []
    monkeypatch.setattr(
        "apps.pub_institucional.services.edocs_mensal._agendar_processamento",
        agendamentos.append,
    )

    recuperada = reencaminhar_coleta_mensal_edocs(
        coleta.pk,
        ator=AtorAuditoriaEdocs(usuario_id=7, nome="Gestor"),
    )

    assert recuperada.pk == coleta.pk
    assert recuperada.revisao == 1
    assert recuperada.situacao == SituacaoColetaMensalEdocs.SOLICITADA
    assert agendamentos == [coleta.pk]
    assert recuperada.eventos_auditoria.filter(tipo_evento="REENCAMINHADA").exists()


def test_api_reencaminha_solicitacao_pendente(
    patriarca_selecionado,
    gestor_publicacoes_mensal,
    monkeypatch,
):
    coleta = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    monkeypatch.setattr(
        "apps.pub_institucional.services.edocs_mensal._agendar_processamento",
        lambda coleta_id: None,
    )
    requisicao = APIRequestFactory().post(
        (f"/api/pub-institucional/coletas-mensais-edocs/{coleta.pk}/" "reencaminhar/"),
        {},
        format="json",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_mensal)

    resposta = VisaoColetaMensalEdocs.as_view({"post": "reencaminhar"})(
        requisicao, pk=coleta.pk
    )

    assert resposta.status_code == 202
    assert resposta.data["situacao"] == "SOLICITADA"
    assert resposta.data["acoes_disponiveis"] == ["reencaminhar"]


def test_recuperacao_periodica_reencaminha_solicitacao_antiga(
    patriarca_selecionado,
    monkeypatch,
    settings,
):
    settings.GPP_EDOCS_REQUEST_STALE_SECONDS = 120
    coleta = solicitar_coleta_mensal_edocs(
        ano=2024,
        mes=9,
        agendar=False,
    )
    ColetaMensalEdocs.objects.filter(pk=coleta.pk).update(
        atualizado_em=timezone.now() - timedelta(minutes=3)
    )
    recuperadas = []
    monkeypatch.setattr(
        "apps.pub_institucional.tasks.reencaminhar_coleta_mensal_edocs",
        lambda coleta_id: recuperadas.append(coleta_id),
    )

    resultado = recuperar_coletas_mensais_edocs()

    assert resultado == {"encontradas": 1, "reencaminhadas": 1}
    assert recuperadas == [coleta.pk]


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
