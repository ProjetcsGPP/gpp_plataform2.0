"""Testes da apresentação de detalhes da integração."""

from django.test import override_settings

from apps.carga_org_lot.services.integration_event_presentation import (
    build_display_details,
)


@override_settings(TIME_ZONE="America/Sao_Paulo")
def test_converte_data_utc_para_horario_local_sem_alterar_origem():
    source = {
        "limite_segundos": 1800,
        "ultima_atualizacao_prodest": "2026-10-29T13:44:03.0413547",
    }

    result = build_display_details(source)

    assert source["ultima_atualizacao_prodest"] == (
        "2026-10-29T13:44:03.0413547"
    )
    assert result == {
        "limite_segundos": 1800,
        "ultima_atualizacao_prodest": "29/10/2026 10:44:03",
    }


def test_preserva_data_invalida_para_nao_ocultar_detalhe_tecnico():
    source = {"ultima_atualizacao_prodest": "valor-invalido"}

    assert build_display_details(source) == source
