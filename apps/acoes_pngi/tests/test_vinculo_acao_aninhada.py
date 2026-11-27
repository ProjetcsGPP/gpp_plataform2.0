"""A URL aninhada é a fonte de verdade para o vínculo com a Ação pai."""

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.acoes_pngi.models import (
    AcaoAnotacaoAlinhamento, AcaoDestaque, AcaoPrazo, Acoes,
    TipoAnotacaoAlinhamento,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def outra_acao(acao):
    return Acoes.objects.create(
        strapelido="OUTRA-ACAO",
        strdescricaoacao="Outra ação para teste de vínculo",
        strdescricaoentrega="Outra entrega",
        idvigenciapngi=acao.idvigenciapngi,
    )


@pytest.mark.parametrize(
    ("recurso", "modelo", "campos"),
    [
        ("prazos", AcaoPrazo, {"strprazo": "Prazo de teste"}),
        ("destaques", AcaoDestaque, {"datdatadestaque": "2026-11-27T12:00:00Z"}),
        ("anotacoes", AcaoAnotacaoAlinhamento, {"strdescricao": "Nota de teste"}),
    ],
)
def test_criacao_nao_aceita_acao_de_outro_caminho(
    client_gestor, acao, outra_acao, recurso, modelo, campos,
):
    antes = modelo.objects.count()
    resposta = client_gestor.post(
        f"/api/acoes-pngi/acoes/{acao.pk}/{recurso}/",
        {"idacao_id": outra_acao.pk, **campos}, format="json",
    )
    assert resposta.status_code == 400
    assert "idacao_id" in resposta.data["errors"]
    assert modelo.objects.count() == antes


@pytest.mark.parametrize(
    ("recurso", "modelo", "campos"),
    [
        ("prazos", AcaoPrazo, {"strprazo": "Original"}),
        ("destaques", AcaoDestaque, {"datdatadestaque": "2026-11-27T12:00:00Z"}),
        ("anotacoes", AcaoAnotacaoAlinhamento, {"strdescricao": "Original"}),
    ],
)
def test_edicao_nao_move_filho_para_outra_acao(
    client_gestor, acao, outra_acao, recurso, modelo, campos,
):
    dados = dict(campos)
    if modelo is AcaoAnotacaoAlinhamento:
        tipo = TipoAnotacaoAlinhamento.objects.create(
            strdescricaotipoanotacaoalinhamento="Tipo para teste"
        )
        dados["idtipoanotacaoalinhamento"] = tipo
    filho = modelo.objects.create(idacao=acao, **dados)
    resposta = client_gestor.patch(
        f"/api/acoes-pngi/acoes/{acao.pk}/{recurso}/{filho.pk}/",
        {"idacao_id": outra_acao.pk}, format="json",
    )
    assert resposta.status_code == 400
    assert "idacao_id" in resposta.data["errors"]
    filho.refresh_from_db()
    assert filho.idacao_id == acao.pk


@override_settings(
    ACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True,
    IAM_URL_ACOES="http://127.0.0.1:8000/interno/iam/v1/decisoes-acoes/",
    IAM_TOKEN_SERVICO_ACOES="credencial-sintetica-acoes-pngi-isolamento",
)
def test_piloto_remoto_tambem_valida_vinculo(
    client_gestor, acao, outra_acao,
):
    with patch(
        "apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto",
        return_value={"usuario_id": 17, "usuario_nome": "Gestora PNGI"},
    ):
        resposta = client_gestor.post(
            f"/api/acoes-pngi/acoes/{acao.pk}/prazos/",
            {"idacao_id": outra_acao.pk, "strprazo": "Inconsistente"},
            format="json",
        )
    assert resposta.status_code == 400
    assert not AcaoPrazo.objects.filter(strprazo="Inconsistente").exists()


@override_settings(
    ACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True,
    IAM_URL_ACOES="http://127.0.0.1:8000/interno/iam/v1/decisoes-acoes/",
    IAM_TOKEN_SERVICO_ACOES="credencial-sintetica-acoes-pngi-isolamento",
)
def test_piloto_remoto_cria_no_pai_correto_e_registra_identidade(
    client_gestor, acao,
):
    with patch(
        "apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto",
        return_value={"usuario_id": 17, "usuario_nome": "Gestora PNGI"},
    ):
        resposta = client_gestor.post(
            f"/api/acoes-pngi/acoes/{acao.pk}/prazos/",
            {"idacao_id": acao.pk, "strprazo": "Concordante"},
            format="json",
        )
    assert resposta.status_code == 201
    prazo = AcaoPrazo.objects.get(strprazo="Concordante")
    assert prazo.idacao_id == acao.pk
    assert prazo.created_by_id == 17
    assert prazo.created_by_name == "Gestora PNGI"
