"""Testes do recorte editorial, vigências e implantação observada."""

from uuid import UUID

import pytest
from django.urls import resolve

from apps.pub_institucional.models import (
    ColetaMensalEdocs,
    CompetenciaEdocs,
    ConfiguracaoVisaoPublicacao,
    EscopoVisaoPublicacao,
    FonteVisaoPublicacao,
    ImplantacaoPatriarcaEdocs,
    PatriarcaEdocs,
    Publicacao,
    ResultadoMensalPatriarcaEdocs,
    SituacaoColetaMensalEdocs,
    SituacaoPublicacao,
)
from apps.pub_institucional.serializadores import SerializadorPublicacao
from apps.pub_institucional.services.implantacao_edocs import (
    registrar_implantacoes_observadas,
)
from apps.pub_institucional.services.patriarcas_edocs import AtorAuditoriaEdocs
from apps.pub_institucional.services.publicacoes import (
    AtorAuditoriaPublicacao,
    ErroPublicacao,
    adicionar_secao,
    criar_publicacao,
    publicar_publicacao,
    recalcular_publicacao,
)
from apps.pub_institucional.visoes import (
    VisaoConfiguracaoVisaoPublicacao,
    VisaoHistoricoPublicacao,
    VisaoPublicacao,
)

pytestmark = pytest.mark.django_db


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

    registrar_implantacoes_observadas(coleta, [resultado], ator=ator)
    implantacao = ImplantacaoPatriarcaEdocs.objects.get(patriarca=patriarca)

    assert (implantacao.ano, implantacao.mes) == (2024, 6)
    assert implantacao.coleta_evidencia == coleta
    assert implantacao.eventos_auditoria.count() == 1

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
