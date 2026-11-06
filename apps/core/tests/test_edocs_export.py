"""Testes da planilha mensal E-Docs com dados inteiramente sintéticos."""

import json
import stat

import pytest
from openpyxl import load_workbook

from apps.core.services.edocs_export import (EdocsExportError, _merge_reports,
                                             export_monthly_edocs,
                                             load_patriarch_selection)

SELECTED_ID = "b817315b-63ea-417e-b191-6ecbc42e56e4"
OTHER_ID = "49f6865b-cc2c-49ec-8d8e-00a829f2a893"
ORG_ID = "8dff4a03-d25d-42d6-8bc3-376e0e7ead53"


class FakeEdocsClient:
    environment = "HML"

    def list_patriarchs(self):
        return [
            {"id": OTHER_ID, "nome": "OUTRO MUNICÍPIO", "sigla": "OUTRO"},
            {"id": SELECTED_ID, "nome": "MUNICÍPIO TESTE", "sigla": "PMT"},
        ]

    def process_report(self, month, year):
        assert (month, year) == ("10", 2025)
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

    def document_report(self, month, year):
        assert (month, year) == ("10", 2025)
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

    def process_report_by_patriarch(self, patriarch_id, month, year):
        assert (patriarch_id, month, year) == (SELECTED_ID, "10", 2025)
        return [
            {
                "idPatriarca": SELECTED_ID,
                "idOrganizacao": ORG_ID,
                "nomeOrganizacao": "ORGANIZAÇÃO TESTE",
                "totalProcessos": 20,
            }
        ]

    def document_report_by_patriarch(self, patriarch_id, month, year):
        assert (patriarch_id, month, year) == (SELECTED_ID, "10", 2025)
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

    result = export_monthly_edocs(
        month=10,
        year=2025,
        selection_path=selection_path,
        output_directory=tmp_path / "output",
        client=FakeEdocsClient(),
    )

    assert result.workbook_path.exists()
    assert result.raw_directory.is_dir()
    assert stat.S_IMODE(result.raw_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(result.workbook_path.parent.stat().st_mode) == 0o700
    assert result.selected_patriarchs == 1
    assert result.catalog_path.name == "patriarcas_catalogo_edocs.json"
    assert result.catalog_path.exists()
    assert result.selection_path == selection_path
    assert selection_path.read_bytes() == original_selection
    assert (result.raw_directory / "edoc-05-patriarcas.json").exists()
    assert (
        result.raw_directory / f"edoc-02-processos-{SELECTED_ID}.json"
    ).exists()

    workbook = load_workbook(result.workbook_path, data_only=False)
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
    class MultiplePatriarchsClient(FakeEdocsClient):
        def process_report_by_patriarch(self, patriarch_id, month, year):
            assert (month, year) == ("10", 2025)
            total = 20 if patriarch_id == SELECTED_ID else 99
            return [
                {
                    "idPatriarca": patriarch_id,
                    "idOrganizacao": ORG_ID,
                    "nomeOrganizacao": "ORGANIZAÇÃO TESTE",
                    "totalProcessos": total,
                }
            ]

        def document_report_by_patriarch(self, patriarch_id, month, year):
            assert (month, year) == ("10", 2025)
            total = 40 if patriarch_id == SELECTED_ID else 100
            return [
                {
                    "idPatriarca": patriarch_id,
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

    result = export_monthly_edocs(
        month=10,
        year=2025,
        selection_path=selection_path,
        output_directory=tmp_path / "output",
        client=MultiplePatriarchsClient(),
    )

    workbook = load_workbook(result.workbook_path, read_only=True)
    municipality_ids = {
        row[1].value for row in list(workbook["Municípios"].iter_rows())[1:]
    }
    organization_ids = {
        row[1].value for row in list(workbook["Organizações"].iter_rows())[1:]
    }
    assert result.selected_patriarchs == 2
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

    with pytest.raises(EdocsExportError, match="campos não permitidos"):
        load_patriarch_selection(path)


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

    with pytest.raises(EdocsExportError, match="COD_MUNIC inválido"):
        load_patriarch_selection(path)


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

    with pytest.raises(EdocsExportError, match="não estão habilitados"):
        export_monthly_edocs(
            month=10,
            year=2025,
            selection_path=selection_path,
            output_directory=tmp_path / "output",
            client=FakeEdocsClient(),
        )


def test_merge_rejects_duplicate_identifiers_in_same_report():
    duplicate = {
        "idPatriarca": SELECTED_ID,
        "nomePatriarca": "MUNICÍPIO TESTE",
        "totalProcessos": 20,
    }

    with pytest.raises(EdocsExportError, match="identificadores duplicados"):
        _merge_reports(
            [duplicate, duplicate.copy()],
            [],
            key_fields=("idPatriarca",),
            selected_ids={SELECTED_ID},
            month=10,
            year=2025,
        )
