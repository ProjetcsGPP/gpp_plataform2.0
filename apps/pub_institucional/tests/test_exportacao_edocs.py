"""Testes da planilha mensal E-Docs com dados inteiramente sintéticos."""

import json
import stat

import pytest
from openpyxl import load_workbook

from apps.pub_institucional.services.exportacao_edocs import (
    ErroExportacaoEdocs, _consolidar_relatorios, carregar_selecao_patriarcas,
    exportar_edocs_mensal)

SELECTED_ID = "b817315b-63ea-417e-b191-6ecbc42e56e4"
OTHER_ID = "49f6865b-cc2c-49ec-8d8e-00a829f2a893"
ORG_ID = "8dff4a03-d25d-42d6-8bc3-376e0e7ead53"


class ClienteEdocsSimulado:
    ambiente = "HML"

    def listar_patriarcas(self):
        return [
            {"id": OTHER_ID, "nome": "OUTRO MUNICÍPIO", "sigla": "OUTRO"},
            {"id": SELECTED_ID, "nome": "MUNICÍPIO TESTE", "sigla": "PMT"},
        ]

    def relatorio_processos(self, mes, ano):
        assert (mes, ano) == ("10", 2025)
        return [
            {
                "idPatriarca": SELECTED_ID,
                "nomePatriarca": "MUNICÍPIO TESTE",
                "totalProcessos": 20,
            },
            {
                "idPatriarca": OTHER_ID,
                "nomePatriarca": "OUTRO MUNICÍPIO",
                "totalProcessos": 99,
            },
        ]

    def relatorio_documentos(self, mes, ano):
        assert (mes, ano) == ("10", 2025)
        return [
            {
                "idPatriarca": SELECTED_ID,
                "nomePatriarca": "MUNICÍPIO TESTE",
                "totalDocumentos": 40,
                "totalPaginas": 80,
            },
            {
                "idPatriarca": OTHER_ID,
                "nomePatriarca": "OUTRO MUNICÍPIO",
                "totalDocumentos": 100,
                "totalPaginas": 200,
            },
        ]

    def relatorio_processos_por_patriarca(self, id_patriarca, mes, ano):
        assert (id_patriarca, mes, ano) == (SELECTED_ID, "10", 2025)
        return [
            {
                "idPatriarca": SELECTED_ID,
                "idOrganizacao": ORG_ID,
                "nomeOrganizacao": "ORGANIZAÇÃO TESTE",
                "totalProcessos": 20,
            }
        ]

    def relatorio_documentos_por_patriarca(self, id_patriarca, mes, ano):
        assert (id_patriarca, mes, ano) == (SELECTED_ID, "10", 2025)
        return [
            {
                "idPatriarca": SELECTED_ID,
                "idOrganizacao": ORG_ID,
                "nomeOrganizacao": "ORGANIZAÇÃO TESTE",
                "totalDocumentos": 40,
                "totalPaginas": 80,
            }
        ]


def _write_selection(path):
    path.write_text(
        json.dumps(
            [
                {
                    "id": SELECTED_ID,
                    "nome": "NOME PARA VISUALIZAÇÃO",
                    "COD_MUNIC": 3201100,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_export_creates_new_workbook_and_raw_evidence(tmp_path):
    selection_path = tmp_path / "patriarcas.json"
    _write_selection(selection_path)
    original_selection = selection_path.read_bytes()

    result = exportar_edocs_mensal(
        mes=10,
        ano=2025,
        caminho_selecao=selection_path,
        diretorio_saida=tmp_path / "output",
        cliente=ClienteEdocsSimulado(),
    )

    assert result.caminho_planilha.exists()
    assert result.diretorio_dados_brutos.is_dir()
    assert stat.S_IMODE(result.diretorio_dados_brutos.stat().st_mode) == 0o700
    assert stat.S_IMODE(result.caminho_planilha.parent.stat().st_mode) == 0o700
    assert result.quantidade_patriarcas_selecionados == 1
    assert result.caminho_catalogo.name == "patriarcas_catalogo_edocs.json"
    assert result.caminho_catalogo.exists()
    assert result.caminho_selecao == selection_path
    assert selection_path.read_bytes() == original_selection
    assert (result.diretorio_dados_brutos / "edoc-05-patriarcas.json").exists()
    assert (
        result.diretorio_dados_brutos / f"edoc-02-processos-{SELECTED_ID}.json"
    ).exists()

    workbook = load_workbook(result.caminho_planilha, data_only=False)
    assert workbook.sheetnames == [
        "Parâmetros",
        "Patriarcas",
        "Municípios",
        "Organizações",
        "Fontes",
    ]
    municipality = workbook["Municípios"]
    headers = [cell.value for cell in municipality[1]]
    values = [cell.value for cell in municipality[2]]
    row = dict(zip(headers, values, strict=True))
    assert row == {
        "COD_MUNIC": 3201100,
        "idPatriarca": SELECTED_ID,
        "nomePatriarca": "MUNICÍPIO TESTE",
        "totalProcessos": 20,
        "totalDocumentos": 40,
        "totalPaginas": 80,
        "mes": 10,
        "ano": 2025,
    }
    assert municipality.max_row == 2
    assert "LATITUDE" not in headers
    assert all(
        cell.data_type != "f"
        for worksheet in workbook.worksheets
        for row_cells in worksheet.iter_rows()
        for cell in row_cells
    )
    workbook.close()


def test_export_consolidates_all_selected_patriarchs_in_same_workbook(
    tmp_path,
):
    class ClienteMultiplosPatriarcas(ClienteEdocsSimulado):
        def relatorio_processos_por_patriarca(self, id_patriarca, mes, ano):
            assert (mes, ano) == ("10", 2025)
            total = 20 if id_patriarca == SELECTED_ID else 99
            return [
                {
                    "idPatriarca": id_patriarca,
                    "idOrganizacao": ORG_ID,
                    "nomeOrganizacao": "ORGANIZAÇÃO TESTE",
                    "totalProcessos": total,
                }
            ]

        def relatorio_documentos_por_patriarca(self, id_patriarca, mes, ano):
            assert (mes, ano) == ("10", 2025)
            total = 40 if id_patriarca == SELECTED_ID else 100
            return [
                {
                    "idPatriarca": id_patriarca,
                    "idOrganizacao": ORG_ID,
                    "nomeOrganizacao": "ORGANIZAÇÃO TESTE",
                    "totalDocumentos": total,
                    "totalPaginas": total * 2,
                }
            ]

    selection_path = tmp_path / "patriarcas_disponiveis.json"
    selection_path.write_text(
        json.dumps(
            [
                {
                    "id": SELECTED_ID,
                    "nome": "MUNICÍPIO TESTE",
                    "COD_MUNIC": 3201100,
                },
                {
                    "id": OTHER_ID,
                    "nome": "OUTRO MUNICÍPIO",
                    "COD_MUNIC": 3203320,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = exportar_edocs_mensal(
        mes=10,
        ano=2025,
        caminho_selecao=selection_path,
        diretorio_saida=tmp_path / "output",
        cliente=ClienteMultiplosPatriarcas(),
    )

    workbook = load_workbook(result.caminho_planilha, read_only=True)
    municipality_ids = {
        row[1].value for row in list(workbook["Municípios"].iter_rows())[1:]
    }
    organization_ids = {
        row[1].value for row in list(workbook["Organizações"].iter_rows())[1:]
    }
    assert result.quantidade_patriarcas_selecionados == 2
    assert municipality_ids == {SELECTED_ID, OTHER_ID}
    assert organization_ids == {SELECTED_ID, OTHER_ID}
    workbook.close()


def test_selection_rejects_extra_fields(tmp_path):
    path = tmp_path / "patriarcas.json"
    path.write_text(
        json.dumps(
            [{"id": SELECTED_ID, "nome": "Teste", "segredo": "não"}]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ErroExportacaoEdocs, match="campos não permitidos"):
        carregar_selecao_patriarcas(path)


def test_selection_rejects_invalid_municipality_code(tmp_path):
    path = tmp_path / "patriarcas.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": SELECTED_ID,
                    "nome": "Teste",
                    "COD_MUNIC": "3201100",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ErroExportacaoEdocs, match="COD_MUNIC inválido"):
        carregar_selecao_patriarcas(path)


def test_export_rejects_selected_patriarch_absent_from_catalog(tmp_path):
    selection_path = tmp_path / "patriarcas.json"
    selection_path.write_text(
        json.dumps(
            [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "nome": "Ausente",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ErroExportacaoEdocs, match="não estão habilitados"):
        exportar_edocs_mensal(
            mes=10,
            ano=2025,
            caminho_selecao=selection_path,
            diretorio_saida=tmp_path / "output",
            cliente=ClienteEdocsSimulado(),
        )


def test_merge_rejects_duplicate_identifiers_in_same_report():
    duplicate = {
        "idPatriarca": SELECTED_ID,
        "nomePatriarca": "MUNICÍPIO TESTE",
        "totalProcessos": 20,
    }

    with pytest.raises(ErroExportacaoEdocs, match="identificadores duplicados"):
        _consolidar_relatorios(
            [duplicate, duplicate.copy()],
            [],
            campos_chave=("idPatriarca",),
            ids_selecionados={SELECTED_ID},
            mes=10,
            ano=2025,
        )
