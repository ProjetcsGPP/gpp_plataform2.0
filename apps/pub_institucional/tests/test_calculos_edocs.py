"""Testes das formulas derivadas da planilha de referencia do E-Docs."""

from decimal import Decimal

from apps.pub_institucional.services.calculos_edocs import \
    calcular_indicadores_edocs


def test_calculos_reproduzem_formulas_da_aba_municipios():
    resultado = calcular_indicadores_edocs(
        total_paginas=22299,
        total_processos=340,
    )

    assert resultado.versao_calculo == "PLANILHA_MUNICIPIOS_V1"
    assert resultado.economia_papel_kg == Decimal("104.58231")
    assert resultado.gases_poluentes_kg == Decimal("78.0465")
    assert resultado.economia_papel_reais == Decimal("1337.94")
    assert resultado.economia_insumos_reais == Decimal("408.00")
    assert resultado.economia_impressao_reais == Decimal("2229.90")
    assert resultado.economia_total_reais == Decimal("3975.84")
    assert resultado.economia_agua_m3 == Decimal("222.99")
    assert resultado.arvores_salvas == Decimal("2.2299")


def test_totais_ausentes_geram_indicadores_derivados_zerados():
    resultado = calcular_indicadores_edocs(
        total_paginas=None,
        total_processos=None,
    )

    assert resultado.economia_papel_kg == Decimal("0.00000")
    assert resultado.gases_poluentes_kg == Decimal("0.0000")
    assert resultado.economia_total_reais == Decimal("0.00")
    assert resultado.economia_agua_m3 == Decimal("0.00")
    assert resultado.arvores_salvas == Decimal("0.0000")
