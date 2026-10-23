"""Testes do catálogo global e do tratamento de cargos importados."""

from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook

from apps.carga_org_lot.models import (
    CargoReferenciaGlobal,
    ConjuntoLotacao,
    ImportacaoPlanilha,
    ItemLotacao,
    ItemLotacaoImportado,
    OcorrenciaCargoImportacao,
    Patriarca,
    SituacaoConjuntoLotacao,
    StatusImportacaoLocal,
    StatusProgresso,
    TipoCarga,
    VariacaoCargoGlobal,
)
from apps.carga_org_lot.services.cargos import cargo_key
from apps.carga_org_lot.services.lotacao_sets import sync_lotation_set
from apps.carga_org_lot.services.workflow import AuditActor


BASE_URL = "/api/carga-org-lot"


def _xlsx(name, header, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = name
    worksheet.append(header)
    for row in rows:
        worksheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _file(name, content):
    return SimpleUploadedFile(
        name,
        content,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


def _organogram_file(patriarch):
    return _file(
        "organograma.xlsx",
        _xlsx(
            "Organograma",
            ("Numero", "Nome", "Sigla"),
            [
                (1, patriarch.strnome, patriarch.strsiglapatriarca),
                ("1.1", "Secretaria de Administração", "SEMAD"),
                ("1.1.1", "Secretaria de Administração", "SEMAD"),
            ],
        ),
    )


def _lotation_file(position):
    return _file(
        "lotacao.xlsx",
        _xlsx(
            "ADMINISTRACAO",
            (
                "Sigla",
                "Secretaria/Órgão",
                "Nome do Servidor",
                "CPF",
                "Ocupação/Cargo",
                "Sigla Setor",
                "Setor de Lotação",
            ),
            [
                (
                    "SEMAD",
                    "Secretaria de Administração",
                    "Maria da Silva",
                    "903.961.004-57",
                    position,
                    "SEMAD",
                    "Secretaria de Administração",
                )
            ],
        ),
    )


@pytest.fixture
def cargo_context(db):
    status = StatusProgresso.objects.create(idstatusprogresso=1, strdescricao="Novo")
    organogram_type = TipoCarga.objects.create(
        idtipocarga=3,
        strdescricao="Organograma",
    )
    lotation_type = TipoCarga.objects.create(
        idtipocarga=4,
        strdescricao="Lotações",
    )
    patriarch = Patriarca.objects.create(
        idexternopatriarca=uuid4(),
        strsiglapatriarca="PMVV",
        strnome="Prefeitura Municipal de Vila Velha",
        datcriacao=timezone.now(),
        idstatusprogresso=status,
    )
    return patriarch, organogram_type, lotation_type


def _upload_organogram(client, patriarch, organogram_type):
    response = client.post(
        f"{BASE_URL}/importacoes/upload/",
        {
            "idpatriarca_id": patriarch.pk,
            "idtipocarga_id": organogram_type.pk,
            "arquivo": _organogram_file(patriarch),
        },
        format="multipart",
    )
    assert response.status_code == 201
    return response.data["idimportacaoplanilha"]


def _upload_lotation(client, patriarch, lotation_type, organogram_id, position):
    return client.post(
        f"{BASE_URL}/importacoes/upload/",
        {
            "idpatriarca_id": patriarch.pk,
            "idtipocarga_id": lotation_type.pk,
            "idimportacaoorganograma_id": organogram_id,
            "arquivo": _lotation_file(position),
        },
        format="multipart",
    )


def _add_lotation_to_set(client, set_id, lotation_type, position):
    return client.post(
        f"{BASE_URL}/conjuntos-lotacao/{set_id}/importacoes/",
        {
            "idtipocarga_id": lotation_type.pk,
            "arquivo": _lotation_file(position),
        },
        format="multipart",
    )


@pytest.mark.django_db(transaction=True)
def test_catalogo_global_e_alimentado_por_toda_leitura(
    client_gestor_carga_lot,
    cargo_context,
):
    patriarch, organogram_type, lotation_type = cargo_context
    organogram_id = _upload_organogram(
        client_gestor_carga_lot,
        patriarch,
        organogram_type,
    )

    response = _upload_lotation(
        client_gestor_carga_lot,
        patriarch,
        lotation_type,
        organogram_id,
        "Auxiliar Administrativo",
    )

    assert response.status_code == 201
    reference = CargoReferenciaGlobal.objects.get(
        strchave="AUXILIAR ADMINISTRATIVO"
    )
    variation = VariacaoCargoGlobal.objects.get(
        strchave="AUXILIAR ADMINISTRATIVO"
    )
    occurrence = OcorrenciaCargoImportacao.objects.get(
        idimportacaoplanilha_id=response.data["idimportacaoplanilha"]
    )
    assert reference.strstatus == "NOVO"
    assert variation.idcargoreferencia == reference
    assert variation.inttotalocorrencias == 1
    assert variation.inttotalimportacoes == 1
    assert variation.inttotalpatriarcas == 1
    assert occurrence.intquantidade == 1
    assert occurrence.jsonlocalizacoes == [{"aba": "ADMINISTRACAO", "linha": 2}]


@pytest.mark.parametrize(
    ("import_status", "expected_set_status"),
    [
        (
            StatusImportacaoLocal.ANALISANDO_CARGOS,
            SituacaoConjuntoLotacao.EM_VALIDACAO,
        ),
        (
            StatusImportacaoLocal.AGUARDANDO_REVISAO_CARGOS,
            SituacaoConjuntoLotacao.COM_PENDENCIAS,
        ),
    ],
)
@pytest.mark.django_db(transaction=True)
def test_conjunto_bloqueia_homologacao_durante_tratamento_de_cargos(
    client_gestor_carga_lot,
    cargo_context,
    import_status,
    expected_set_status,
):
    patriarch, organogram_type, lotation_type = cargo_context
    organogram_id = _upload_organogram(
        client_gestor_carga_lot,
        patriarch,
        organogram_type,
    )
    imported = _upload_lotation(
        client_gestor_carga_lot,
        patriarch,
        lotation_type,
        organogram_id,
        "Auxiliar Administrativo",
    )
    assert imported.status_code == 201
    importation = ImportacaoPlanilha.objects.get(
        pk=imported.data["idimportacaoplanilha"]
    )
    conjunto = ConjuntoLotacao.objects.get(
        pk=imported.data["idconjuntolotacao_id"]
    )
    assert ItemLotacao.objects.filter(idimportacaoplanilha=importation).exists()

    importation.strstatusimportacao = import_status
    importation.save(update_fields=["strstatusimportacao", "updated_at"])
    sync_lotation_set(conjunto, actor=AuditActor(user_name="teste"))

    conjunto.refresh_from_db()
    assert conjunto.strsituacao == expected_set_status
    response = client_gestor_carga_lot.post(
        f"{BASE_URL}/conjuntos-lotacao/{conjunto.pk}/homologar/",
        {"justificativa": "Ainda existem cargos em tratamento."},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_sugestao_agrupada_e_resolucao_ensina_catalogo_global(
    client_gestor_carga_lot,
    cargo_context,
):
    patriarch, organogram_type, lotation_type = cargo_context
    organogram_id = _upload_organogram(
        client_gestor_carga_lot,
        patriarch,
        organogram_type,
    )
    initial = _upload_lotation(
        client_gestor_carga_lot,
        patriarch,
        lotation_type,
        organogram_id,
        "Auxiliar Administrativo",
    )
    reference = CargoReferenciaGlobal.objects.get(
        strchave="AUXILIAR ADMINISTRATIVO"
    )
    confirmation = client_gestor_carga_lot.patch(
        f"{BASE_URL}/cargos-referencia/{reference.pk}/",
        {"strstatus": "CONFIRMADO"},
        format="json",
    )
    assert confirmation.status_code == 200

    set_id = initial.data["idconjuntolotacao_id"]
    suggested = _add_lotation_to_set(
        client_gestor_carga_lot,
        set_id,
        lotation_type,
        "Aux. Adm.",
    )

    assert suggested.status_code == 201
    assert suggested.data["strstatusimportacao"] == "AGUARDANDO_REVISAO_CARGOS"
    assert suggested.data["total_itens_lotacao"] == 0
    conjunto = ConjuntoLotacao.objects.get(pk=set_id)
    assert conjunto.strsituacao == SituacaoConjuntoLotacao.COM_PENDENCIAS
    premature_homologation = client_gestor_carga_lot.post(
        f"{BASE_URL}/conjuntos-lotacao/{set_id}/homologar/",
        {"justificativa": "Ainda existem cargos pendentes."},
        format="json",
    )
    assert premature_homologation.status_code == 400
    report = suggested.data["relatorio_validacao"]
    assert report["jsonresumo"]["cargos"]["total_descricoes_em_analise"] == 1
    cargo_cases = [
        case
        for case in report["casos"]
        if case["strcodigo"] == "cargo_correspondencia_sugerida"
    ]
    assert len(cargo_cases) == 1
    alternative = next(
        entry
        for entry in cargo_cases[0]["alternativas"]
        if entry["idcargoreferencia_id"] == reference.pk
    )
    assert float(alternative["decconfianca"]) == 100.0

    resolution = client_gestor_carga_lot.post(
        (
            f"{BASE_URL}/casos-validacao-importacao/"
            f"{cargo_cases[0]['idcasovalidacao']}/resolver/"
        ),
        {
            "acao": "APLICAR_SUGESTAO",
            "alternativa_id": alternative["idalternativaresolucao"],
            "escopo_cargo": "GLOBAL",
        },
        format="json",
    )
    assert resolution.status_code == 200
    variation = VariacaoCargoGlobal.objects.get(strchave="AUX ADM")
    assert variation.strstatus == "CONFIRMADA"
    assert variation.idcargoreferencia == reference
    staged = ItemLotacaoImportado.objects.get(
        idimportacaoplanilha_id=suggested.data["idimportacaoplanilha"]
    )
    assert staged.idcargoreferencia == reference
    assert staged.strcargonormalizado == "Auxiliar Administrativo"
    importation = ImportacaoPlanilha.objects.get(
        pk=suggested.data["idimportacaoplanilha"]
    )
    assert importation.strstatusimportacao == "PRONTA_PARA_INCORPORAR"
    conjunto.refresh_from_db()
    assert conjunto.strsituacao == SituacaoConjuntoLotacao.EM_VALIDACAO

    incorporated = client_gestor_carga_lot.post(
        f"{BASE_URL}/importacoes/{importation.pk}/incorporar-lotacao/",
        {},
        format="json",
    )
    assert incorporated.status_code == 200
    assert ItemLotacao.objects.get(
        idimportacaoplanilha=importation
    ).idcargoreferencia == reference
    conjunto.refresh_from_db()
    assert (
        conjunto.strsituacao
        == SituacaoConjuntoLotacao.PRONTO_PARA_HOMOLOGACAO
    )
    assert initial.status_code == 201

    other_patriarch = Patriarca.objects.create(
        idexternopatriarca=uuid4(),
        strsiglapatriarca="PMBG",
        strnome="Prefeitura Municipal de Baixo Guandu",
        datcriacao=timezone.now(),
        idstatusprogresso=patriarch.idstatusprogresso,
    )
    other_organogram_id = _upload_organogram(
        client_gestor_carga_lot,
        other_patriarch,
        organogram_type,
    )
    reused = _upload_lotation(
        client_gestor_carga_lot,
        other_patriarch,
        lotation_type,
        other_organogram_id,
        "Aux. Adm.",
    )
    assert reused.status_code == 201
    assert reused.data["strstatusimportacao"] == "INCORPORADA"
    reused_item = ItemLotacao.objects.get(
        idimportacaoplanilha_id=reused.data["idimportacaoplanilha"]
    )
    assert reused_item.idcargoreferencia == reference
    assert reused_item.strcargonormalizado == "Auxiliar Administrativo"


def test_chave_de_cargo_normaliza_acentos_pontuacao_e_limite():
    assert cargo_key("  Téc. de Enfermagem ") == "TEC DE ENFERMAGEM"
    assert len(cargo_key("Cargo " * 100)) <= 255


def test_endpoints_do_catalogo_preservam_vinculo_confirmado(
    client_gestor_carga_lot,
    cargo_context,
):
    response = client_gestor_carga_lot.post(
        f"{BASE_URL}/cargos-referencia/",
        {
            "strnome": "Técnico de Enfermagem",
            "strstatus": "CONFIRMADO",
        },
        format="json",
    )
    assert response.status_code == 201
    reference_id = response.data["idcargoreferencia"]

    response = client_gestor_carga_lot.post(
        f"{BASE_URL}/variacoes-cargo/",
        {
            "strdescricao": "Téc. Enfermagem",
            "idcargoreferencia_id": reference_id,
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["strstatus"] == "CONFIRMADA"
    variation_id = response.data["idvariacaocargo"]

    response = client_gestor_carga_lot.patch(
        f"{BASE_URL}/variacoes-cargo/{variation_id}/",
        {"idcargoreferencia_id": None},
        format="json",
    )
    assert response.status_code == 400
    assert "strstatus" in response.data["errors"]

    response = client_gestor_carga_lot.get(
        f"{BASE_URL}/variacoes-cargo/?cargo_referencia=invalido"
    )
    assert response.status_code == 400
