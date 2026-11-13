"""Allowlist explícita da representação pública de publicações congeladas."""

from apps.pub_institucional.models import FonteVisaoPublicacao

CAMPOS_INDICADORES_EDOCS = (
    "total_processos",
    "total_documentos",
    "total_paginas",
    "economia_papel_kg",
    "gases_poluentes_kg",
    "economia_papel_reais",
    "economia_insumos_reais",
    "economia_impressao_reais",
    "economia_total_reais",
    "economia_agua_m3",
    "arvores_salvas",
)

CAMPOS_INDICADORES_EFLOW = (
    "quantidade_fluxos",
    "quantidade_orgaos_participantes",
    "quantidade_setores_ativos",
)


def _selecionar(dados, campos):
    return {campo: dados.get(campo) for campo in campos if campo in dados}


def _projetar_proveniencia(proveniencia):
    campos = ("tipo", "versao", "vigencia_inicio")
    return _selecionar(proveniencia or {}, campos)


def _projetar_series(series):
    resultado = []
    for serie in series or []:
        resultado.append(
            {
                "codigo": serie.get("codigo"),
                "titulo": serie.get("titulo"),
                "periodicidade": serie.get("periodicidade"),
                "natureza": serie.get("natureza"),
                "unidade": serie.get("unidade"),
                "precisao": serie.get("precisao"),
                "serie_completa": serie.get("serie_completa"),
                "pontos": [
                    {
                        "competencia": ponto.get("competencia"),
                        "valor": ponto.get("valor"),
                        "valor_acumulado": ponto.get("valor_acumulado"),
                        "proveniencia": _projetar_proveniencia(
                            ponto.get("proveniencia")
                        ),
                    }
                    for ponto in serie.get("pontos", [])
                ],
            }
        )
    return resultado


def _projetar_mapas(mapas):
    resultado = []
    for mapa in mapas or []:
        resultado.append(
            {
                "schema_version": mapa.get("schema_version"),
                "tipo": mapa.get("tipo"),
                "indicador": mapa.get("indicador"),
                "titulo": mapa.get("titulo"),
                "competencia": mapa.get("competencia"),
                "codigo_uf": mapa.get("codigo_uf"),
                "quantidade_municipios": mapa.get("quantidade_municipios"),
                "referencia_temporal": mapa.get("referencia_temporal"),
                "modo": mapa.get("modo"),
                "unidade": mapa.get("unidade"),
                "precisao": mapa.get("precisao"),
                "texto_sem_dados": mapa.get("texto_sem_dados"),
                "legenda": [
                    _selecionar(item, ("codigo", "rotulo", "cor", "ordem"))
                    for item in mapa.get("legenda", [])
                ],
                "municipios": [
                    _selecionar(
                        item,
                        (
                            "codigo_ibge",
                            "nome",
                            "categoria",
                            "valor",
                            "texto_alternativo",
                        ),
                    )
                    for item in mapa.get("municipios", [])
                ],
                "proveniencia": _selecionar(
                    mapa.get("proveniencia", {}),
                    (
                        "fonte_uso",
                        "fonte_situacao_manual",
                        "fonte_catalogo_municipal",
                        "regra",
                    ),
                ),
            }
        )
    return resultado


def _projetar_resultado_edocs(resultado):
    patriarcas = []
    for item in resultado.get("patriarcas", []):
        patriarcas.append(
            {
                **_selecionar(
                    item,
                    (
                        "codigo_municipio",
                        "nome_municipio",
                        "sigla_patriarca",
                        "nome_patriarca",
                        "versao_calculo",
                    ),
                ),
                **_selecionar(item, CAMPOS_INDICADORES_EDOCS),
            }
        )
    consolidados = [
        {
            **_selecionar(
                item,
                (
                    "posicao",
                    "codigo_municipio",
                    "nome_municipio",
                    "sigla_patriarca",
                    "nome_patriarca",
                    "competencias_consideradas",
                ),
            ),
            **_selecionar(item, CAMPOS_INDICADORES_EDOCS),
        }
        for item in resultado.get("consolidados_historicos_patriarcas", [])
    ]
    return {
        "quantidade_patriarcas": resultado.get("quantidade_patriarcas", 0),
        "totais": _selecionar(
            resultado.get("totais", {}),
            CAMPOS_INDICADORES_EDOCS,
        ),
        "patriarcas": patriarcas,
        "mapas": _projetar_mapas(resultado.get("mapas", [])),
        "series_historicas": _projetar_series(
            resultado.get("series_historicas", [])
        ),
        "consolidados_historicos_patriarcas": consolidados,
    }


def _projetar_resultado_eflow(resultado):
    return {
        **_selecionar(resultado, CAMPOS_INDICADORES_EFLOW),
        "orgaos_maior_quantidade_fluxos": [
            _selecionar(
                item,
                (
                    "patriarca",
                    "orgao",
                    "quantidade_fluxos",
                    "percentual",
                ),
            )
            for item in resultado.get("orgaos_maior_quantidade_fluxos", [])
        ],
        "distribuicao_publico_alvo": [
            _selecionar(
                item,
                ("publico_alvo", "quantidade_fluxos", "percentual"),
            )
            for item in resultado.get("distribuicao_publico_alvo", [])
        ],
        "series_historicas": _projetar_series(
            resultado.get("series_historicas", [])
        ),
    }


def projetar_secao_publica(secao):
    congelada = secao.configuracao_congelada or {}
    resultado = secao.resultado or {}
    if secao.fonte == FonteVisaoPublicacao.EDOCS:
        conteudo = _projetar_resultado_edocs(resultado)
    else:
        conteudo = _projetar_resultado_eflow(resultado)
    return {
        "ordem": secao.ordem,
        "codigo": congelada.get("codigo"),
        "titulo": secao.titulo,
        "fonte": secao.fonte,
        "perfil_calculo": secao.perfil_calculo,
        "conteudo": conteudo,
    }


def projetar_resumo_publicacao(publicacao):
    return {
        "id": str(publicacao.pk),
        "versao": publicacao.versao,
        "titulo": publicacao.titulo,
        "competencia": (
            f"{publicacao.ano_referencia:04d}-{publicacao.mes_referencia:02d}"
        ),
        "publicada_em": publicacao.publicada_em,
    }


def projetar_publicacao(publicacao):
    return {
        "schema_version": "1.0",
        **projetar_resumo_publicacao(publicacao),
        "secoes": [
            projetar_secao_publica(secao)
            for secao in publicacao.secoes.all()
        ],
    }


def projetar_series_publicacao(publicacao):
    return {
        "schema_version": "1.0",
        **projetar_resumo_publicacao(publicacao),
        "secoes": [
            {
                "ordem": secao.ordem,
                "codigo": (secao.configuracao_congelada or {}).get("codigo"),
                "titulo": secao.titulo,
                "fonte": secao.fonte,
                "series_historicas": _projetar_series(
                    (secao.resultado or {}).get("series_historicas", [])
                ),
            }
            for secao in publicacao.secoes.all()
        ],
    }
