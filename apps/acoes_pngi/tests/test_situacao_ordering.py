"""Testes da ordenação segura, composta e paginada de Situações."""

from uuid import uuid4

import pytest

from apps.acoes_pngi.models import SituacaoAcao

from .conftest import SITUACOES_URL


pytestmark = pytest.mark.django_db(transaction=True)


def _ids(response) -> list[int]:
    assert response.status_code == 200
    return [item["idsituacaoacao"] for item in response.data["results"]]


def _criar_situacoes(quantidade: int = 4, *, descricao: str | None = None):
    prefixo = uuid4().hex[:8]
    return [
        SituacaoAcao.objects.create(
            strdescricaosituacao=descricao or f"Situação {prefixo} {indice}",
        )
        for indice in range(quantidade)
    ]


def test_ordering_ascendente_por_descricao(client_gestor):
    _criar_situacoes()
    expected = list(
        SituacaoAcao.objects.order_by(
            "strdescricaosituacao",
            "idsituacaoacao",
        ).values_list("idsituacaoacao", flat=True)[:100]
    )

    response = client_gestor.get(
        SITUACOES_URL,
        {"ordering": "strdescricaosituacao", "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_descendente_por_data_de_atualizacao(client_gestor):
    _criar_situacoes()
    expected = list(
        SituacaoAcao.objects.order_by(
            "-updated_at",
            "idsituacaoacao",
        ).values_list("idsituacaoacao", flat=True)[:100]
    )

    response = client_gestor.get(
        SITUACOES_URL,
        {"ordering": "-updated_at", "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_composta(client_gestor):
    _criar_situacoes()
    ordering = ["strdescricaosituacao", "-updated_at", "idsituacaoacao"]
    expected = list(
        SituacaoAcao.objects.order_by(*ordering).values_list(
            "idsituacaoacao",
            flat=True,
        )[:100]
    )

    response = client_gestor.get(
        SITUACOES_URL,
        {"ordering": ",".join(ordering), "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_invalida_e_sanitizada_para_padrao(client_gestor):
    _criar_situacoes()
    expected = list(
        SituacaoAcao.objects.order_by(
            "strdescricaosituacao",
            "idsituacaoacao",
        ).values_list("idsituacaoacao", flat=True)[:100]
    )

    response = client_gestor.get(
        SITUACOES_URL,
        {"ordering": "campo_inexistente", "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_mista_descarta_apenas_campo_invalido(client_gestor):
    _criar_situacoes()
    expected = list(
        SituacaoAcao.objects.order_by(
            "-strdescricaosituacao",
            "idsituacaoacao",
        ).values_list("idsituacaoacao", flat=True)[:100]
    )

    response = client_gestor.get(
        SITUACOES_URL,
        {
            "ordering": "campo_inexistente,-strdescricaosituacao",
            "page_size": 100,
        },
    )

    assert _ids(response) == expected


def test_ordering_acrescenta_id_como_desempate(client_gestor):
    prefixo = uuid4().hex[:8]
    autor = f"ZZZZZ autor {prefixo}"
    descricoes = [f"Mesmo autor {prefixo} {indice}" for indice in range(4)]
    situacoes = [
        SituacaoAcao.objects.create(
            strdescricaosituacao=descricao,
            updated_by_name=autor,
        )
        for descricao in descricoes
    ]

    response = client_gestor.get(
        SITUACOES_URL,
        {"ordering": "-updated_by_name", "page_size": 100},
    )

    ids_criados = {situacao.pk for situacao in situacoes}
    ids_no_resultado = [
        item["idsituacaoacao"]
        for item in response.data["results"]
        if item["idsituacaoacao"] in ids_criados
    ]
    assert ids_no_resultado == sorted(ids_criados)


def test_ordering_deterministica_entre_paginas(client_gestor):
    _criar_situacoes(5)
    expected = list(
        SituacaoAcao.objects.order_by(
            "updated_by_name",
            "idsituacaoacao",
        ).values_list("idsituacaoacao", flat=True)[:4]
    )

    first_page = client_gestor.get(
        SITUACOES_URL,
        {"ordering": "updated_by_name", "page_size": 2, "page": 1},
    )
    second_page = client_gestor.get(
        SITUACOES_URL,
        {"ordering": "updated_by_name", "page_size": 2, "page": 2},
    )

    assert _ids(first_page) + _ids(second_page) == expected
    assert set(_ids(first_page)).isdisjoint(_ids(second_page))
