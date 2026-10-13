"""Testes da ordenação segura, composta e paginada de Eixos."""

from uuid import uuid4

import pytest

from apps.acoes_pngi.models import Eixo

from .conftest import EIXOS_URL


pytestmark = pytest.mark.django_db(transaction=True)


def _ids(response) -> list[int]:
    assert response.status_code == 200
    return [item["ideixo"] for item in response.data["results"]]


def _criar_eixos(quantidade: int = 4, *, descricao: str | None = None):
    prefixo = uuid4().hex[:8].upper()
    return [
        Eixo.objects.create(
            strdescricaoeixo=descricao or f"Eixo {prefixo} {indice}",
            stralias=uuid4().hex[:5].upper(),
        )
        for indice in range(quantidade)
    ]


def test_ordering_ascendente_por_alias(client_gestor):
    _criar_eixos()
    expected = list(
        Eixo.objects.order_by("stralias", "ideixo").values_list(
            "ideixo",
            flat=True,
        )[:100]
    )

    response = client_gestor.get(
        EIXOS_URL,
        {"ordering": "stralias", "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_descendente_por_data_de_atualizacao(client_gestor):
    _criar_eixos()
    expected = list(
        Eixo.objects.order_by("-updated_at", "ideixo").values_list(
            "ideixo",
            flat=True,
        )[:100]
    )

    response = client_gestor.get(
        EIXOS_URL,
        {"ordering": "-updated_at", "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_composta(client_gestor):
    _criar_eixos(descricao=f"Descrição {uuid4().hex}")
    ordering = ["strdescricaoeixo", "-updated_at", "ideixo"]
    expected = list(
        Eixo.objects.order_by(*ordering).values_list("ideixo", flat=True)[:100]
    )

    response = client_gestor.get(
        EIXOS_URL,
        {"ordering": ",".join(ordering), "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_invalida_e_sanitizada_para_padrao(client_gestor):
    _criar_eixos()
    expected = list(
        Eixo.objects.order_by("stralias", "ideixo").values_list(
            "ideixo",
            flat=True,
        )[:100]
    )

    response = client_gestor.get(
        EIXOS_URL,
        {"ordering": "campo_inexistente", "page_size": 100},
    )

    assert _ids(response) == expected


def test_ordering_mista_descarta_apenas_campo_invalido(client_gestor):
    _criar_eixos()
    expected = list(
        Eixo.objects.order_by("-stralias", "ideixo").values_list(
            "ideixo",
            flat=True,
        )[:100]
    )

    response = client_gestor.get(
        EIXOS_URL,
        {
            "ordering": "campo_inexistente,-stralias",
            "page_size": 100,
        },
    )

    assert _ids(response) == expected


def test_ordering_acrescenta_ideixo_como_desempate(client_gestor):
    descricao = f"ZZZZZ Mesmo valor {uuid4().hex}"
    eixos = _criar_eixos(descricao=descricao)

    response = client_gestor.get(
        EIXOS_URL,
        {"ordering": "-strdescricaoeixo", "page_size": 100},
    )

    ids_do_grupo = [
        item["ideixo"]
        for item in response.data["results"]
        if item["strdescricaoeixo"] == descricao
    ]
    assert ids_do_grupo == sorted(eixo.pk for eixo in eixos)


def test_ordering_deterministica_entre_paginas(client_gestor):
    _criar_eixos(5, descricao=f"Paginação {uuid4().hex}")
    expected = list(
        Eixo.objects.order_by("strdescricaoeixo", "ideixo").values_list(
            "ideixo",
            flat=True,
        )[:4]
    )

    first_page = client_gestor.get(
        EIXOS_URL,
        {"ordering": "strdescricaoeixo", "page_size": 2, "page": 1},
    )
    second_page = client_gestor.get(
        EIXOS_URL,
        {"ordering": "strdescricaoeixo", "page_size": 2, "page": 2},
    )

    assert _ids(first_page) + _ids(second_page) == expected
    assert set(_ids(first_page)).isdisjoint(_ids(second_page))
