"""Calculos derivados dos quantitativos mensais do E-Docs."""

from dataclasses import dataclass
from decimal import Decimal


VERSAO_CALCULO_EDOCS = "PLANILHA_MUNICIPIOS_V1"

MASSA_PAPEL_POR_PAGINA_KG = Decimal("0.00469")
GASES_POLUENTES_POR_PAGINA_KG = Decimal("0.0035")
CUSTO_PAPEL_POR_PAGINA_REAIS = Decimal("0.06")
CUSTO_INSUMOS_POR_PROCESSO_REAIS = Decimal("1.20")
CUSTO_IMPRESSAO_POR_PAGINA_REAIS = Decimal("0.10")
AGUA_POR_PAGINA_M3 = Decimal("0.01")
ARVORES_POR_PAGINA = Decimal("0.0001")


@dataclass(frozen=True)
class IndicadoresCalculadosEdocs:
    """Valores derivados de uma linha mensal da planilha de referencia."""

    versao_calculo: str
    economia_papel_kg: Decimal
    gases_poluentes_kg: Decimal
    economia_papel_reais: Decimal
    economia_insumos_reais: Decimal
    economia_impressao_reais: Decimal
    economia_total_reais: Decimal
    economia_agua_m3: Decimal
    arvores_salvas: Decimal


def calcular_indicadores_edocs(
    *,
    total_paginas: int | None,
    total_processos: int | None,
) -> IndicadoresCalculadosEdocs:
    """Reproduz as formulas da aba Municipios para uma competencia."""

    paginas = Decimal(total_paginas or 0)
    processos = Decimal(total_processos or 0)
    economia_papel_reais = paginas * CUSTO_PAPEL_POR_PAGINA_REAIS
    economia_insumos_reais = processos * CUSTO_INSUMOS_POR_PROCESSO_REAIS
    economia_impressao_reais = paginas * CUSTO_IMPRESSAO_POR_PAGINA_REAIS

    return IndicadoresCalculadosEdocs(
        versao_calculo=VERSAO_CALCULO_EDOCS,
        economia_papel_kg=paginas * MASSA_PAPEL_POR_PAGINA_KG,
        gases_poluentes_kg=paginas * GASES_POLUENTES_POR_PAGINA_KG,
        economia_papel_reais=economia_papel_reais,
        economia_insumos_reais=economia_insumos_reais,
        economia_impressao_reais=economia_impressao_reais,
        economia_total_reais=(
            economia_papel_reais
            + economia_insumos_reais
            + economia_impressao_reais
        ),
        economia_agua_m3=paginas * AGUA_POR_PAGINA_M3,
        arvores_salvas=paginas * ARVORES_POR_PAGINA,
    )
