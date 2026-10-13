"""Testes do CRUD e da autorização da API de Situações."""

from uuid import uuid4

import pytest

from apps.acoes_pngi.models import SituacaoAcao

from .conftest import SITUACOES_URL


pytestmark = pytest.mark.django_db(transaction=True)


def _descricao_unica(prefixo: str = "Situação") -> str:
    return f"{prefixo} {uuid4().hex[:8]}"


def test_create_situacao_gestor_retorna_201_e_preenche_auditoria(
    client_gestor,
    gestor_pngi,
):
    descricao = _descricao_unica()
    response = client_gestor.post(
        SITUACOES_URL,
        {"strdescricaosituacao": descricao},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["strdescricaosituacao"] == descricao
    assert response.data["created_by_id"] == gestor_pngi.pk
    assert response.data["updated_by_id"] == gestor_pngi.pk


def test_create_situacao_valida_descricao_unica(client_gestor, situacao):
    response = client_gestor.post(
        SITUACOES_URL,
        {"strdescricaosituacao": situacao.strdescricaosituacao},
        format="json",
    )

    assert response.status_code == 400
    assert "strdescricaosituacao" in response.data["errors"]


def test_patch_situacao_gestor_retorna_200_e_atualiza_auditoria(
    client_gestor,
    gestor_pngi,
    situacao,
):
    descricao = _descricao_unica("Atualizada")
    response = client_gestor.patch(
        f"{SITUACOES_URL}{situacao.pk}/",
        {"strdescricaosituacao": descricao},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["strdescricaosituacao"] == descricao
    assert response.data["updated_by_id"] == gestor_pngi.pk

    situacao.refresh_from_db()
    assert situacao.strdescricaosituacao == descricao


def test_put_situacao_gestor_retorna_200(client_gestor, situacao):
    descricao = _descricao_unica("Substituída")
    response = client_gestor.put(
        f"{SITUACOES_URL}{situacao.pk}/",
        {"strdescricaosituacao": descricao},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["strdescricaosituacao"] == descricao


def test_delete_situacao_gestor_retorna_204(client_gestor):
    situacao = SituacaoAcao.objects.create(
        strdescricaosituacao=_descricao_unica("Descartável"),
    )

    response = client_gestor.delete(f"{SITUACOES_URL}{situacao.pk}/")

    assert response.status_code == 204
    assert not SituacaoAcao.objects.filter(pk=situacao.pk).exists()


def test_coordenador_pode_consultar_mas_nao_criar_situacao(
    client_coordenador,
    situacao,
):
    assert client_coordenador.get(SITUACOES_URL).status_code == 200

    response = client_coordenador.post(
        SITUACOES_URL,
        {"strdescricaosituacao": _descricao_unica("Negada")},
        format="json",
    )

    assert response.status_code == 403


def test_operador_nao_pode_atualizar_situacao(client_operador, situacao):
    response = client_operador.patch(
        f"{SITUACOES_URL}{situacao.pk}/",
        {"strdescricaosituacao": _descricao_unica("Indevida")},
        format="json",
    )

    assert response.status_code == 403
