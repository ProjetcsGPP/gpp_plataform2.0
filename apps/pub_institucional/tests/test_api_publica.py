"""Contrato e isolamento da API pública de Publicações Institucionais."""

from datetime import timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from django.core.cache import cache
from django.db import DatabaseError
from django.test import override_settings
from django.urls import resolve
from django.utils import timezone
from django.utils.http import http_date
from rest_framework.test import APIClient

from apps.pub_institucional.models import (ColetaMensalEdocs, CompetenciaEdocs,
                                           ConfiguracaoVisaoPublicacao,
                                           EscopoVisaoPublicacao,
                                           FonteVisaoPublicacao,
                                           PatriarcaEdocs, Publicacao,
                                           SecaoPublicacao,
                                           SituacaoColetaMensalEdocs,
                                           SituacaoPublicacao)
from apps.pub_institucional.publico.visoes import (
    VisaoDetalhePublicacaoPublica, VisaoHistoricoPublico,
    VisaoPublicacaoVigente, VisaoSeriesPublicacaoPublica)

pytestmark = pytest.mark.django_db


def _publicacao(*, mes=1, situacao=SituacaoPublicacao.PUBLICADA):
    patriarca, _ = PatriarcaEdocs.objects.get_or_create(
        id_externo=UUID("00000000-0000-0000-0000-000000000001"),
        defaults={
            "sigla": "PMTESTE",
            "nome": "Município de Teste",
            "tipo_agente": 5,
            "descricao_tipo_agente": "Organizacao",
            "codigo_municipio": 3200001,
        },
    )
    competencia, _ = CompetenciaEdocs.objects.get_or_create(ano=2024, mes=mes)
    coleta = ColetaMensalEdocs.objects.create(
        competencia=competencia,
        revisao=1,
        ambiente="PRD",
        situacao=SituacaoColetaMensalEdocs.SUCESSO,
    )
    visao, _ = ConfiguracaoVisaoPublicacao.objects.get_or_create(
        codigo="MUNICIPIOS_EDOCS_PUBLICO",
        defaults={
            "nome": "Municípios E-Docs",
            "fonte": FonteVisaoPublicacao.EDOCS,
            "escopo": EscopoVisaoPublicacao.MUNICIPIOS,
        },
    )
    publicada_em = timezone.now() + timedelta(minutes=mes)
    publicacao = Publicacao.objects.create(
        titulo=f"Publicação {mes}",
        ano_referencia=2024,
        mes_referencia=mes,
        situacao=situacao,
        publicada_em=publicada_em,
        publicada_por_id=99,
        publicada_por_nome="Gestor sigiloso",
        justificativa_publicacao="Justificativa administrativa sigilosa",
        hash_conteudo=f"{mes:064d}",
    )
    SecaoPublicacao.objects.create(
        publicacao=publicacao,
        ordem=1,
        titulo="E-Docs",
        fonte=FonteVisaoPublicacao.EDOCS,
        configuracao_visao=visao,
        coleta_edocs=coleta,
        perfil_calculo="PLANILHA_MUNICIPIOS_V1",
        configuracao_congelada={
            "codigo": visao.codigo,
            "fonte": FonteVisaoPublicacao.EDOCS,
            "segredo_interno": "não expor",
        },
        resultado={
            "quantidade_patriarcas": 1,
            "totais": {
                "total_paginas": 10,
                "campo_novo_nao_autorizado": "não expor",
            },
            "patriarcas": [
                {
                    "patriarca_id": patriarca.pk,
                    "id_patriarca_externo": str(patriarca.id_externo),
                    "codigo_municipio": patriarca.codigo_municipio,
                    "nome_municipio": "Município de Teste",
                    "sigla_patriarca": patriarca.sigla,
                    "nome_patriarca": patriarca.nome,
                    "total_paginas": 10,
                }
            ],
            "series_historicas": [
                {
                    "codigo": "TOTAL_PAGINAS",
                    "titulo": "Páginas",
                    "periodicidade": "MENSAL",
                    "natureza": "FLUXO_MENSAL",
                    "unidade": "páginas",
                    "precisao": 0,
                    "serie_completa": True,
                    "pontos": [
                        {
                            "competencia": f"2024-{mes:02d}",
                            "valor": "10",
                            "valor_acumulado": "10",
                            "proveniencia": {
                                "tipo": "PUBLICACAO",
                                "coleta_id": str(coleta.pk),
                                "publicacao_id": str(publicacao.pk),
                            },
                        }
                    ],
                }
            ],
            "consolidados_historicos_patriarcas": [
                {
                    "posicao": 1,
                    "patriarca_id": patriarca.pk,
                    "codigo_municipio": patriarca.codigo_municipio,
                    "nome_municipio": "Município de Teste",
                    "sigla_patriarca": patriarca.sigla,
                    "nome_patriarca": patriarca.nome,
                    "competencias_consideradas": 1,
                    "economia_total_reais": "100.00",
                }
            ],
            "mapas": [
                {
                    "schema_version": "1.1",
                    "tipo": "MAPA_MUNICIPAL",
                    "indicador": "IMPLANTACAO_EDOCS",
                    "titulo": "Implantação E-Docs nos municípios",
                    "competencia": f"2024-{mes:02d}",
                    "codigo_uf": 32,
                    "quantidade_municipios": 1,
                    "referencia_temporal": "COMPETENCIA",
                    "modo": "CATEGORICO",
                    "unidade de valor": "R$",
                    "precisao": None,
                    "texto_sem_dados": "Sem dados disponíveis",
                    "legenda": [
                        {
                            "codigo": "SEM_DADOS",
                            "rotulo": "Sem dados disponíveis",
                            "cor": "#d1d5db",
                            "ordem": 99,
                        }
                    ],
                    "municipios": [
                        {
                            "codigo_ibge": "3200001",
                            "nome": "Município de Teste",
                            "categoria": "SEM_DADOS",
                            "edocs": {
                                "mes": {"total_paginas": "10", "segredo_interno": "oculto"},
                                "acumulado": {
                                    "total_paginas": "30",
                                    "competencias_consideradas": 2,
                                },
                            },
                            "eflow": {
                                "quantidade_fluxos": 1,
                                "segredo_interno": "oculto",
                                "orgaos_maior_quantidade_fluxos": [],
                                "distribuicao_publico_alvo": [],
                            },
                            "texto_alternativo": (
                                "Município de Teste: sem dados disponíveis"
                            ),
                        }
                    ],
                    "proveniencia": {
                        "fonte_uso": "API oficial E-Docs",
                        "fonte_situacao_manual": (
                            "Cadastro municipal administrativo"
                        ),
                        "fonte_catalogo_municipal": (
                            "API de Localidades do IBGE"
                        ),
                        "regra": "IMPLANTACAO_EDOCS_V2",
                        "coleta_edocs_id": str(coleta.pk),
                    },
                }
            ],
        },
        hash_resultado=f"{mes + 10:064d}",
        calculada_em=publicada_em,
    )
    return publicacao


def test_rotas_publicas_usam_views_proprias():
    base = "/api/public/v1/publicacoes-institucionais"
    identificador = "00000000-0000-0000-0000-000000000001"
    assert resolve(f"{base}/vigente/").func.view_class is VisaoPublicacaoVigente
    assert resolve(f"{base}/").func.view_class is VisaoHistoricoPublico
    assert (
        resolve(f"{base}/{identificador}/").func.view_class
        is VisaoDetalhePublicacaoPublica
    )
    assert (
        resolve(f"{base}/{identificador}/series/").func.view_class
        is VisaoSeriesPublicacaoPublica
    )


def test_vigente_sem_publicacao_retorna_erro_estavel():
    resposta = APIClient().get(
        "/api/public/v1/publicacoes-institucionais/vigente/"
    )

    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "PUBLICACAO_NAO_DISPONIVEL"
    assert resposta["Cache-Control"] == "no-store"


def test_detalhe_publico_aplica_allowlist_e_nao_varia_por_cookie():
    publicacao = _publicacao()
    cliente = APIClient()
    cliente.cookies["gpp_session_PUB_INSTITUCIONAL"] = "sessao-inexistente"

    resposta = cliente.get(
        f"/api/public/v1/publicacoes-institucionais/{publicacao.pk}/"
    )
    conteudo = resposta.json()
    texto = resposta.content.decode("utf-8")

    assert resposta.status_code == 200
    assert resposta["ETag"] == f'"{publicacao.hash_conteudo}"'
    assert "Cookie" not in resposta.get("Vary", "")
    assert conteudo["competencia"] == "2024-01"
    assert conteudo["secoes"][0]["codigo"] == "MUNICIPIOS_EDOCS_PUBLICO"
    assert conteudo["secoes"][0]["conteudo"]["totais"] == {
        "total_paginas": 10
    }
    assert "patriarca_id" not in texto
    assert "id_patriarca_externo" not in texto
    assert "coleta_id" not in texto
    assert "publicada_por" not in texto
    assert "justificativa" not in texto
    assert "segredo_interno" not in texto
    assert "campo_novo_nao_autorizado" not in texto
    ranking = conteudo["secoes"][0]["conteudo"][
        "consolidados_historicos_patriarcas"
    ]
    assert ranking[0]["economia_total_reais"] == "100.00"
    assert ranking[0]["nome_municipio"] == "Município de Teste"
    assert "patriarca_id" not in ranking[0]
    mapa = conteudo["secoes"][0]["conteudo"]["mapas"][0]
    assert mapa["codigo_uf"] == 32
    assert mapa["unidade de valor"] == "R$"
    assert "unidade" not in mapa
    assert mapa["quantidade_municipios"] == 1
    assert mapa["municipios"] == [
        {
            "codigo_ibge": "3200001",
            "nome": "Município de Teste",
            "categoria": "SEM_DADOS",
            "edocs": {
                "mes": {"total_paginas": "10"},
                "acumulado": {
                    "total_paginas": "30",
                    "competencias_consideradas": 2,
                },
            },
            "eflow": {
                "quantidade_fluxos": 1,
                "orgaos_maior_quantidade_fluxos": [],
                "distribuicao_publico_alvo": [],
            },
            "texto_alternativo": (
                "Município de Teste: sem dados disponíveis"
            ),
        }
    ]
    assert mapa["proveniencia"]["fonte_catalogo_municipal"] == (
        "API de Localidades do IBGE"
    )
    assert "coleta_edocs_id" not in mapa["proveniencia"]


def test_etag_retorna_304_e_series_possuem_projecao_propria():
    publicacao = _publicacao()
    cliente = APIClient()
    rota = f"/api/public/v1/publicacoes-institucionais/{publicacao.pk}/series/"

    primeira = cliente.get(rota)
    segunda = cliente.get(rota, HTTP_IF_NONE_MATCH=primeira["ETag"])

    assert primeira.status_code == 200
    assert primeira.json()["secoes"][0]["series_historicas"][0][
        "codigo"
    ] == "TOTAL_PAGINAS"
    assert segunda.status_code == 304
    assert segunda.content == b""


def test_revogacao_nao_recua_ponteiro_e_retorna_410_no_detalhe():
    _publicacao(mes=1)
    revogada = _publicacao(mes=2, situacao=SituacaoPublicacao.REVOGADA)
    cliente = APIClient()

    vigente = cliente.get(
        "/api/public/v1/publicacoes-institucionais/vigente/"
    )
    detalhe = cliente.get(
        f"/api/public/v1/publicacoes-institucionais/{revogada.pk}/"
    )

    assert vigente.status_code == 404
    assert vigente.json()["codigo"] == "PUBLICACAO_NAO_DISPONIVEL"
    assert detalhe.status_code == 410
    assert detalhe.json()["codigo"] == "PUBLICACAO_REVOGADA"


def test_historico_exclui_revogada_e_rascunho():
    publicada = _publicacao(mes=1)
    _publicacao(mes=2, situacao=SituacaoPublicacao.REVOGADA)
    Publicacao.objects.create(
        titulo="Rascunho",
        ano_referencia=2024,
        mes_referencia=3,
    )

    resposta = APIClient().get(
        "/api/public/v1/publicacoes-institucionais/"
    )

    assert resposta.status_code == 200
    assert resposta.json()["quantidade"] == 1
    assert resposta.json()["resultados"][0]["id"] == str(publicada.pk)
    assert resposta["Last-Modified"] == http_date(
        publicada.publicada_em.timestamp()
    )

    nao_modificada = APIClient().get(
        "/api/public/v1/publicacoes-institucionais/",
        HTTP_IF_NONE_MATCH=resposta["ETag"],
    )

    assert nao_modificada.status_code == 304
    assert nao_modificada["Last-Modified"] == resposta["Last-Modified"]


def test_historico_vazio_nao_inventa_last_modified():
    resposta = APIClient().get(
        "/api/public/v1/publicacoes-institucionais/"
    )

    assert resposta.status_code == 200
    assert resposta.json()["quantidade"] == 0
    assert "Last-Modified" not in resposta


def test_falha_de_banco_retorna_503_sem_detalhe_interno():
    with patch(
        "apps.pub_institucional.publico.visoes._publicacao_vigente",
        side_effect=DatabaseError("senha=segredo-interno"),
    ):
        resposta = APIClient().get(
            "/api/public/v1/publicacoes-institucionais/vigente/"
        )

    assert resposta.status_code == 503
    assert resposta.json()["codigo"] == (
        "PUBLICACAO_TEMPORARIAMENTE_INDISPONIVEL"
    )
    assert "segredo-interno" not in resposta.content.decode("utf-8")


@override_settings(PUBLICACOES_PUBLIC_THROTTLE_RATE="1/min")
def test_throttle_publico_retorna_429_estavel_e_retry_after():
    cache.clear()
    cliente = APIClient()
    rota = "/api/public/v1/publicacoes-institucionais/vigente/"

    primeira = cliente.get(rota)
    segunda = cliente.get(rota)

    assert primeira.status_code == 404
    assert segunda.status_code == 429
    assert segunda.json()["codigo"] == "LIMITE_PUBLICO_EXCEDIDO"
    assert int(segunda["Retry-After"]) >= 1
