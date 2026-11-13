"""Testes do recorte editorial, vigências e implantação observada."""

from uuid import UUID

import pytest
from django.core.cache import cache
from django.urls import resolve
from django.utils import timezone

from apps.pub_institucional.models import (ColetaEflow, ColetaMensalEdocs,
                                           CompetenciaEdocs,
                                           ConfiguracaoVisaoPublicacao,
                                           DefinicaoFluxoEflow,
                                           EscopoVisaoPublicacao,
                                           EventoAuditoriaMunicipioEdocs,
                                           FonteVisaoPublicacao,
                                           ImplantacaoPatriarcaEdocs,
                                           MunicipioEdocs, PatriarcaEdocs,
                                           PerfilCalculoEflow, Publicacao,
                                           ResultadoMensalPatriarcaEdocs,
                                           SituacaoColetaEflow,
                                           SituacaoColetaMensalEdocs,
                                           SituacaoPublicacao)
from apps.pub_institucional.serializadores import SerializadorPublicacao
from apps.pub_institucional.services.implantacao_edocs import \
    registrar_implantacoes_observadas
from apps.pub_institucional.services.municipios_edocs import \
    cadastrar_municipio_edocs
from apps.pub_institucional.services.patriarcas_edocs import AtorAuditoriaEdocs
from apps.pub_institucional.services.publicacoes import (
    AtorAuditoriaPublicacao, ErroPublicacao, adicionar_secao, criar_publicacao,
    publicar_publicacao, recalcular_publicacao)
from apps.pub_institucional.visoes import (VisaoConfiguracaoVisaoPublicacao,
                                           VisaoHistoricoPublicacao,
                                           VisaoPublicacao)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalogo_municipal_ibge_em_cache():
    chave = "common:ibge:localidades:municipios:32:v1"
    cache.set(
        chave,
        [
            {"id": 3200001, "nome": "Município IBGE 1", "codigo_uf": 32},
            {"id": 3200002, "nome": "Município IBGE 2", "codigo_uf": 32},
            {"id": 3200003, "nome": "Município IBGE 3", "codigo_uf": 32},
            {"id": 3200004, "nome": "Município IBGE 4", "codigo_uf": 32},
        ],
        timeout=None,
    )
    yield
    cache.delete(chave)


def test_rotas_editoriais_sao_expostas():
    assert (
        resolve("/api/pub-institucional/publicacoes/").func.cls
        is VisaoPublicacao
    )
    assert (
        resolve("/api/pub-institucional/visoes-publicacao/").func.cls
        is VisaoConfiguracaoVisaoPublicacao
    )
    assert (
        resolve("/api/pub-institucional/historico-publicacoes/").func.cls
        is VisaoHistoricoPublicacao
    )


def _patriarca(sufixo, *, codigo_municipio=None):
    return PatriarcaEdocs.objects.create(
        id_externo=UUID(f"00000000-0000-0000-0000-{sufixo:012d}"),
        sigla=f"P{sufixo}",
        nome=f"Patriarca {sufixo}",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
        codigo_municipio=codigo_municipio,
    )


def _coleta(ano=2024, mes=1):
    competencia = CompetenciaEdocs.objects.create(ano=ano, mes=mes)
    return ColetaMensalEdocs.objects.create(
        competencia=competencia,
        revisao=1,
        ambiente="PRD",
        situacao=SituacaoColetaMensalEdocs.SUCESSO,
    )


def _resultado(coleta, patriarca, *, processos=1, documentos=2, paginas=3):
    return ResultadoMensalPatriarcaEdocs.objects.create(
        coleta=coleta,
        patriarca=patriarca,
        id_patriarca_externo=patriarca.id_externo,
        sigla_patriarca=patriarca.sigla,
        nome_patriarca=patriarca.nome,
        codigo_municipio=patriarca.codigo_municipio,
        total_processos=processos,
        total_documentos=documentos,
        total_paginas=paginas,
    )


def test_implantacao_guarda_primeira_competencia_positiva_sem_sobrescrever():
    patriarca = _patriarca(1, codigo_municipio=3200001)
    coleta = _coleta(2024, 6)
    resultado = _resultado(coleta, patriarca)
    ator = AtorAuditoriaEdocs(usuario_id=7, nome="Gestor")
    municipio = cadastrar_municipio_edocs(
        codigo_ibge=3200001,
        nome="Município em implantação",
        situacao="EM_IMPLANTACAO",
        ano_inicio=2024,
        mes_inicio=1,
        justificativa="Implantação acompanhada pelo gestor.",
        ator=ator,
    )

    registrar_implantacoes_observadas(coleta, [resultado], ator=ator)
    implantacao = ImplantacaoPatriarcaEdocs.objects.get(patriarca=patriarca)

    assert (implantacao.ano, implantacao.mes) == (2024, 6)
    assert implantacao.coleta_evidencia == coleta
    assert implantacao.eventos_auditoria.count() == 1
    municipio.refresh_from_db()
    vigencia_manual = municipio.vigencias_situacao.get()
    assert (vigencia_manual.ano_fim, vigencia_manual.mes_fim) == (2024, 5)
    assert EventoAuditoriaMunicipioEdocs.objects.filter(
        municipio=municipio,
        tipo_evento="IMPLANTACAO_COM_USO_OBSERVADA",
    ).exists()
    assert MunicipioEdocs.objects.filter(codigo_ibge=3200001).count() == 1

    patriarca_novo = _patriarca(2, codigo_municipio=3200002)
    resultado_novo = _resultado(coleta, patriarca_novo)
    registrar_implantacoes_observadas(coleta, [resultado_novo], ator=ator)
    municipio_novo = MunicipioEdocs.objects.get(codigo_ibge=3200002)
    assert municipio_novo.nome == patriarca_novo.nome
    assert municipio_novo.eventos_auditoria.filter(
        tipo_evento="IMPLANTACAO_COM_USO_OBSERVADA"
    ).exists()

    coleta_anterior = _coleta(2024, 1)
    resultado_anterior = _resultado(coleta_anterior, patriarca)
    registrar_implantacoes_observadas(
        coleta_anterior,
        [resultado_anterior],
        ator=ator,
    )
    implantacao.refresh_from_db()
    assert (implantacao.ano, implantacao.mes) == (2024, 6)
    assert implantacao.eventos_auditoria.count() == 1


def test_publicacao_municipal_congela_competencia_fontes_e_resultado():
    municipio = _patriarca(1, codigo_municipio=3200001)
    governo = _patriarca(2)
    coleta = _coleta(2024, 1)
    _resultado(coleta, municipio, paginas=10)
    _resultado(coleta, governo, paginas=100)
    visao = ConfiguracaoVisaoPublicacao.objects.create(
        codigo="MUNICIPIOS_EDOCS",
        nome="Municípios E-Docs",
        fonte=FonteVisaoPublicacao.EDOCS,
        escopo=EscopoVisaoPublicacao.MUNICIPIOS,
    )
    ator = AtorAuditoriaPublicacao(usuario_id=7, nome="Gestor")
    publicacao = criar_publicacao(
        titulo="Resultados de janeiro",
        ano=2024,
        mes=1,
        ator=ator,
    )
    adicionar_secao(
        publicacao=publicacao,
        configuracao=visao,
        titulo="E-Docs nos municípios",
        ordem=1,
        ator=ator,
    )

    publicacao = recalcular_publicacao(publicacao, ator=ator)
    secao = publicacao.secoes.get()

    assert publicacao.situacao == SituacaoPublicacao.AGUARDANDO_PUBLICACAO
    assert secao.coleta_edocs == coleta
    assert secao.resultado["quantidade_patriarcas"] == 1
    assert secao.resultado["patriarcas"][0]["patriarca_id"] == municipio.pk
    assert secao.configuracao_congelada["patriarcas_ids"] == [municipio.pk]

    publicacao = publicar_publicacao(
        publicacao,
        justificativa="Publicação mensal conferida.",
        versao_registro=publicacao.versao_registro,
        ator=ator,
    )
    assert publicacao.situacao == SituacaoPublicacao.PUBLICADA
    assert publicacao.hash_conteudo
    assert publicacao.historico.filter(tipo_evento="PUBLICADA").exists()

    contrato = SerializadorPublicacao(publicacao).data
    assert contrato["ano_referencia"] == 2024
    assert contrato["mes_referencia"] == 1
    assert contrato["competencia"] == "2024-01"

    with pytest.raises(ErroPublicacao, match="não permite recalcular"):
        recalcular_publicacao(publicacao, ator=ator)


def test_serie_historica_prioriza_publicacao_e_identifica_coleta_substituta():
    municipio = _patriarca(1, codigo_municipio=3200001)
    visao = ConfiguracaoVisaoPublicacao.objects.create(
        codigo="MUNICIPIOS_EDOCS_SERIE",
        nome="Municípios E-Docs",
        fonte=FonteVisaoPublicacao.EDOCS,
        escopo=EscopoVisaoPublicacao.MUNICIPIOS,
    )
    ator = AtorAuditoriaPublicacao(usuario_id=7, nome="Gestor")

    coleta_janeiro = _coleta(2024, 1)
    _resultado(coleta_janeiro, municipio, paginas=10)

    coleta_fevereiro = _coleta(2024, 2)
    _resultado(coleta_fevereiro, municipio, paginas=20)
    publicada = criar_publicacao(
        titulo="Resultados de fevereiro",
        ano=2024,
        mes=2,
        ator=ator,
    )
    adicionar_secao(
        publicacao=publicada,
        configuracao=visao,
        titulo="E-Docs nos municípios",
        ordem=1,
        ator=ator,
    )
    publicada = recalcular_publicacao(publicada, ator=ator)
    publicada = publicar_publicacao(
        publicada,
        justificativa="Competência conferida.",
        versao_registro=publicada.versao_registro,
        ator=ator,
    )

    coleta_marco = _coleta(2024, 3)
    _resultado(coleta_marco, municipio, paginas=30)
    candidata = criar_publicacao(
        titulo="Resultados de março",
        ano=2024,
        mes=3,
        ator=ator,
    )
    adicionar_secao(
        publicacao=candidata,
        configuracao=visao,
        titulo="E-Docs nos municípios",
        ordem=1,
        ator=ator,
    )

    candidata = recalcular_publicacao(candidata, ator=ator)
    series = candidata.secoes.get().resultado["series_historicas"]
    paginas = next(serie for serie in series if serie["codigo"] == "TOTAL_PAGINAS")

    assert [ponto["valor"] for ponto in paginas["pontos"]] == ["10", "20", "30"]
    assert [
        ponto["valor_acumulado"] for ponto in paginas["pontos"]
    ] == ["10", "30", "60"]
    assert [
        ponto["proveniencia"]["tipo"] for ponto in paginas["pontos"]
    ] == [
        "ULTIMA_COLETA_COM_SUCESSO",
        "PUBLICACAO",
        "SECAO_PUBLICACAO_ATUAL",
    ]
    assert paginas["natureza"] == "FLUXO_MENSAL"
    assert paginas["serie_completa"] is True
    consolidado = candidata.secoes.get().resultado[
        "consolidados_historicos_patriarcas"
    ][0]
    assert consolidado["codigo_municipio"] == municipio.codigo_municipio
    assert consolidado["nome_municipio"] == "Município IBGE 1"
    assert consolidado["total_paginas"] == "60"
    assert consolidado["competencias_consideradas"] == 3


def test_serie_historica_eflow_repete_snapshot_vigente_sem_acumular():
    patriarca = _patriarca(1, codigo_municipio=3200001)

    def criar_snapshot(sufixo, ano, mes, quantidade):
        coleta = ColetaEflow.objects.create(
            situacao=SituacaoColetaEflow.CONCLUIDA,
            arquivo_nome=f"eflow-{sufixo}.csv",
            arquivo_hash_sha256=f"{sufixo:064d}",
            arquivo_tamanho_bytes=1,
            arquivo_conteudo=b"x",
            iniciada_em=timezone.now(),
            concluida_em=timezone.now(),
            ano_vigencia_inicio=ano,
            mes_vigencia_inicio=mes,
            vigencia_retroativa=(ano, mes) == (2024, 1),
        )
        for indice in range(quantidade):
            DefinicaoFluxoEflow.objects.create(
                coleta=coleta,
                id_externo=UUID(
                    f"00000000-0000-0000-{sufixo:04d}-{indice + 1:012d}"
                ),
                nome=f"Fluxo {sufixo}-{indice}",
                versao_origem=1,
                publico_alvo="Cidadão",
                patriarca=patriarca,
                patriarca_texto=patriarca.sigla,
                orgao="Órgão",
                setor=f"Setor {indice}",
            )
        return coleta

    criar_snapshot(1, 2024, 1, 1)
    coleta_marco = criar_snapshot(2, 2024, 3, 2)
    visao = ConfiguracaoVisaoPublicacao.objects.create(
        codigo="GERAL_EFLOW_SERIE",
        nome="Geral E-Flow",
        fonte=FonteVisaoPublicacao.EFLOW,
        escopo=EscopoVisaoPublicacao.TODOS,
        perfil_calculo_eflow=PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO,
    )
    ator = AtorAuditoriaPublicacao(usuario_id=7, nome="Gestor")
    publicacao = criar_publicacao(
        titulo="Resultados E-Flow de março",
        ano=2024,
        mes=3,
        ator=ator,
    )
    adicionar_secao(
        publicacao=publicacao,
        configuracao=visao,
        titulo="E-Flow",
        ordem=1,
        coleta_id=coleta_marco.pk,
        ator=ator,
    )

    publicacao = recalcular_publicacao(publicacao, ator=ator)
    series = publicacao.secoes.get().resultado["series_historicas"]
    fluxos = next(
        serie for serie in series if serie["codigo"] == "QUANTIDADE_FLUXOS"
    )

    assert [ponto["valor"] for ponto in fluxos["pontos"]] == ["1", "1", "2"]
    assert all(
        ponto["valor_acumulado"] is None for ponto in fluxos["pontos"]
    )
    assert fluxos["natureza"] == "ESTOQUE_VIGENTE"
    assert [
        ponto["proveniencia"]["tipo"] for ponto in fluxos["pontos"]
    ] == [
        "SNAPSHOT_VIGENTE",
        "SNAPSHOT_VIGENTE",
        "SECAO_PUBLICACAO_ATUAL",
    ]


def test_resultado_zerado_nao_inere_implantacao():
    patriarca = _patriarca(1, codigo_municipio=3200001)
    coleta = _coleta(2024, 1)
    resultado = _resultado(
        coleta,
        patriarca,
        processos=0,
        documentos=0,
        paginas=0,
    )

    registrar_implantacoes_observadas(
        coleta,
        [resultado],
        ator=AtorAuditoriaEdocs(nome="sistema"),
    )

    assert not ImplantacaoPatriarcaEdocs.objects.filter(
        patriarca=patriarca
    ).exists()
    assert not Publicacao.objects.exists()


def test_publicacao_congela_mapa_municipal_por_competencia_com_api_prevalente():
    com_uso = _patriarca(1, codigo_municipio=3200001)
    sem_uso = _patriarca(2, codigo_municipio=3200002)
    futuro = _patriarca(3, codigo_municipio=3200003)
    ator_municipio = AtorAuditoriaEdocs(usuario_id=7, nome="Gestor")
    for patriarca, situacao, mes_inicio in (
        (com_uso, "IMPLANTADO_SEM_USO_EDOCS", 6),
        (sem_uso, "IMPLANTADO_SEM_USO_EDOCS", 6),
        (futuro, "EM_IMPLANTACAO", 7),
    ):
        cadastrar_municipio_edocs(
            codigo_ibge=patriarca.codigo_municipio,
            nome=patriarca.nome,
            situacao=situacao,
            ano_inicio=2024,
            mes_inicio=mes_inicio,
            justificativa="Carga histórica validada.",
            ator=ator_municipio,
        )
    cadastrar_municipio_edocs(
        codigo_ibge=3200004,
        nome="Município ainda sem patriarca",
        situacao="EM_IMPLANTACAO",
        ano_inicio=2024,
        mes_inicio=6,
        justificativa="Implantação informada pelo gestor.",
        ator=ator_municipio,
    )

    coleta = _coleta(2024, 6)
    resultado_com_uso = _resultado(coleta, com_uso)
    _resultado(coleta, sem_uso, processos=0, documentos=0, paginas=0)
    registrar_implantacoes_observadas(
        coleta,
        [resultado_com_uso],
        ator=AtorAuditoriaEdocs(nome="sistema"),
    )
    visao = ConfiguracaoVisaoPublicacao.objects.create(
        codigo="MUNICIPIOS_EDOCS_MAPA",
        nome="Municípios E-Docs",
        fonte=FonteVisaoPublicacao.EDOCS,
        escopo=EscopoVisaoPublicacao.MUNICIPIOS,
    )
    ator = AtorAuditoriaPublicacao(usuario_id=7, nome="Gestor")
    publicacao = criar_publicacao(
        titulo="Resultados de junho",
        ano=2024,
        mes=6,
        ator=ator,
    )
    adicionar_secao(
        publicacao=publicacao,
        configuracao=visao,
        titulo="E-Docs nos municípios",
        ordem=1,
        ator=ator,
    )

    publicacao = recalcular_publicacao(publicacao, ator=ator)
    mapa = publicacao.secoes.get().resultado["mapas"][0]
    categorias = {
        item["codigo_ibge"]: item["categoria"]
        for item in mapa["municipios"]
    }

    assert mapa["competencia"] == "2024-06"
    assert mapa["codigo_uf"] == 32
    assert mapa["quantidade_municipios"] == 4
    assert [item["nome"] for item in mapa["municipios"]] == [
        "Município IBGE 1",
        "Município IBGE 2",
        "Município IBGE 3",
        "Município IBGE 4",
    ]
    assert categorias == {
        "3200001": "IMPLANTADO_COM_USO_EDOCS",
        "3200002": "IMPLANTADO_SEM_USO_EDOCS",
        "3200003": "SEM_DADOS",
        "3200004": "EM_IMPLANTACAO",
    }
    assert mapa["proveniencia"]["regra"] == "IMPLANTACAO_EDOCS_V2"
    assert mapa["proveniencia"]["fonte_catalogo_municipal"] == (
        "API de Localidades do IBGE"
    )
