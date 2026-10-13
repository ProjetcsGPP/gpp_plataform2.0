"""Testes do CRUD e da autorização da API de Eixos."""

from uuid import uuid4

import pytest

from apps.acoes_pngi.models import Eixo

from .conftest import EIXOS_URL

pytestmark = pytest.mark.django_db(transaction=True)


def _alias_unico() -> str:
    return uuid4().hex[:5].upper()


def test_create_eixo_gestor_retorna_201_e_preenche_auditoria(
    client_gestor,
    gestor_pngi,
):
    alias = _alias_unico()
    response = client_gestor.post(
        EIXOS_URL,
        {
            "strdescricaoeixo": "Transformação Digital",
            "stralias": alias,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["strdescricaoeixo"] == "Transformação Digital"
    assert response.data["stralias"] == alias
    assert response.data["created_by_id"] == gestor_pngi.pk
    assert response.data["updated_by_id"] == gestor_pngi.pk


def test_create_eixo_valida_alias_unico(client_gestor, eixo):
    response = client_gestor.post(
        EIXOS_URL,
        {
            "strdescricaoeixo": "Outro eixo",
            "stralias": eixo.stralias,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "stralias" in response.data["errors"]


def test_patch_eixo_gestor_retorna_200_e_atualiza_auditoria(
    client_gestor,
    gestor_pngi,
    eixo,
):
    response = client_gestor.patch(
        f"{EIXOS_URL}{eixo.pk}/",
        {"strdescricaoeixo": "Infraestrutura atualizada"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["strdescricaoeixo"] == "Infraestrutura atualizada"
    assert response.data["updated_by_id"] == gestor_pngi.pk

    eixo.refresh_from_db()
    assert eixo.strdescricaoeixo == "Infraestrutura atualizada"


def test_put_eixo_gestor_retorna_200(client_gestor, eixo):
    alias = _alias_unico()
    response = client_gestor.put(
        f"{EIXOS_URL}{eixo.pk}/",
        {
            "strdescricaoeixo": "Infraestrutura e Conectividade",
            "stralias": alias,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["stralias"] == alias


def test_delete_eixo_gestor_retorna_204(client_gestor):
    eixo = Eixo.objects.create(
        strdescricaoeixo="Eixo descartável",
        stralias="DEL",
    )

    response = client_gestor.delete(f"{EIXOS_URL}{eixo.pk}/")

    assert response.status_code == 204
    assert not Eixo.objects.filter(pk=eixo.pk).exists()


def test_coordenador_pode_consultar_mas_nao_criar_eixo(
    client_coordenador,
    eixo,
):
    assert client_coordenador.get(EIXOS_URL).status_code == 200

    response = client_coordenador.post(
        EIXOS_URL,
        {
            "strdescricaoeixo": "Eixo sem autorização",
            "stralias": "NSA",
        },
        format="json",
    )

    assert response.status_code == 403


def test_operador_nao_pode_atualizar_eixo(client_operador, eixo):
    response = client_operador.patch(
        f"{EIXOS_URL}{eixo.pk}/",
        {"strdescricaoeixo": "Alteração indevida"},
        format="json",
    )

    assert response.status_code == 403
