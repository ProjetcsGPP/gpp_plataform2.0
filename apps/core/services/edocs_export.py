"""Coleta mensal E-Docs com evidência JSON e planilha operacional."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.core.services.edocs import EdocsClient


class EdocsExportError(RuntimeError):
    """Configuração ou transformação inválida da coleta mensal."""


@dataclass(frozen=True)
class PatriarchSelection:
    id: str
    name: str
    municipality_code: int | None


@dataclass(frozen=True)
class EdocsExportResult:
    workbook_path: Path
    raw_directory: Path
    catalog_path: Path
    selection_path: Path
    selected_patriarchs: int


MUNICIPALITY_COLUMNS = (
    "COD_MUNIC",
    "idPatriarca",
    "nomePatriarca",
    "totalProcessos",
    "totalDocumentos",
    "totalPaginas",
    "mes",
    "ano",
)
ORGANIZATION_COLUMNS = (
    "COD_MUNIC",
    "idPatriarca",
    "nomePatriarca",
    "idOrganizacao",
    "nomeOrganizacao",
    "totalProcessos",
    "totalDocumentos",
    "totalPaginas",
    "mes",
    "ano",
)


def load_patriarch_selection(path):
    """Lê IDs, nomes e códigos municipais da seleção versionável."""
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EdocsExportError(
            "Não foi possível ler o JSON de patriarcas selecionados."
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise EdocsExportError(
            "O JSON de patriarcas deve ser uma lista não vazia."
        )

    result = []
    seen = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict) or not {"id", "nome"} <= set(item):
            raise EdocsExportError(
                f"O item {index} deve conter id e nome."
            )
        if set(item) - {"id", "nome", "COD_MUNIC"}:
            raise EdocsExportError(
                f"O item {index} contém campos não permitidos."
            )
        try:
            patriarch_id = str(UUID(str(item["id"])))
        except (TypeError, ValueError, AttributeError) as exc:
            raise EdocsExportError(
                f"O item {index} possui um id inválido."
            ) from exc
        name = str(item["nome"]).strip()
        if not name:
            raise EdocsExportError(f"O item {index} possui nome vazio.")
        if patriarch_id in seen:
            raise EdocsExportError(
                f"O patriarca {patriarch_id} aparece mais de uma vez."
            )
        seen.add(patriarch_id)
        municipality_code = item.get("COD_MUNIC")
        if municipality_code is not None and (
            isinstance(municipality_code, bool)
            or not isinstance(municipality_code, int)
            or not 1_000_000 <= municipality_code <= 9_999_999
        ):
            raise EdocsExportError(
                f"O item {index} possui COD_MUNIC inválido."
            )
        result.append(
            PatriarchSelection(patriarch_id, name, municipality_code)
        )
    return result


def export_monthly_edocs(
    *,
    month,
    year,
    selection_path,
    output_directory,
    client=None,
):
    """Executa os cinco métodos aprovados e produz JSONs e XLSX."""
    month = _valid_month(month)
    year = _valid_year(year)
    selections = load_patriarch_selection(selection_path)
    selection_path = Path(selection_path)
    api = client or EdocsClient()
    month_path = f"{month:02d}"

    available_raw = api.list_patriarchs()
    available = _normalize_available_patriarchs(available_raw)
    available_by_id = {item["id"]: item for item in available}
    missing = [item.id for item in selections if item.id not in available_by_id]
    if missing:
        raise EdocsExportError(
            "Patriarcas selecionados não estão habilitados no E-Docs: "
            + ", ".join(missing)
        )

    process_global = api.process_report(month_path, year)
    document_global = api.document_report(month_path, year)
    process_by_org = []
    document_by_org = []
    raw_by_patriarch = {}
    for selection in selections:
        process_rows = api.process_report_by_patriarch(
            selection.id,
            month_path,
            year,
        )
        document_rows = api.document_report_by_patriarch(
            selection.id,
            month_path,
            year,
        )
        process_by_org.extend(
            _with_selection_name(process_rows, selection.name)
        )
        document_by_org.extend(
            _with_selection_name(document_rows, selection.name)
        )
        raw_by_patriarch[selection.id] = {
            "processos": process_rows,
            "documentos": document_rows,
        }

    selected_ids = {selection.id for selection in selections}
    codes_by_id = {
        selection.id: selection.municipality_code for selection in selections
    }
    municipality_rows = _merge_reports(
        process_global,
        document_global,
        key_fields=("idPatriarca",),
        selected_ids=selected_ids,
        month=month,
        year=year,
        codes_by_id=codes_by_id,
    )
    names_by_id = {selection.id: selection.name for selection in selections}
    organization_rows = _merge_reports(
        process_by_org,
        document_by_org,
        key_fields=("idPatriarca", "idOrganizacao"),
        selected_ids=selected_ids,
        month=month,
        year=year,
        names_by_id=names_by_id,
        codes_by_id=codes_by_id,
    )

    output_root = Path(output_directory)
    period_directory = output_root / f"{year}-{month:02d}"
    raw_directory = period_directory / "json"
    output_root.mkdir(parents=True, exist_ok=True)
    period_directory.mkdir(mode=0o700, exist_ok=True)
    raw_directory.mkdir(mode=0o700, exist_ok=True)
    period_directory.chmod(0o700)
    raw_directory.chmod(0o700)
    catalog_path = period_directory / "patriarcas_catalogo_edocs.json"

    _write_json_atomic(catalog_path, available)
    _write_json_atomic(raw_directory / "edoc-05-patriarcas.json", available_raw)
    _write_json_atomic(
        raw_directory / "edoc-01-processos-geral.json",
        process_global,
    )
    _write_json_atomic(
        raw_directory / "edoc-03-documentos-geral.json",
        document_global,
    )
    for selection in selections:
        raw = raw_by_patriarch[selection.id]
        _write_json_atomic(
            raw_directory / f"edoc-02-processos-{selection.id}.json",
            raw["processos"],
        )
        _write_json_atomic(
            raw_directory / f"edoc-04-documentos-{selection.id}.json",
            raw["documentos"],
        )

    workbook_path = period_directory / f"edocs_{year}_{month:02d}.xlsx"
    _write_workbook_atomic(
        workbook_path,
        environment=api.environment,
        month=month,
        year=year,
        selections=selections,
        available_by_id=available_by_id,
        municipality_rows=municipality_rows,
        organization_rows=organization_rows,
    )
    return EdocsExportResult(
        workbook_path=workbook_path,
        raw_directory=raw_directory,
        catalog_path=catalog_path,
        selection_path=selection_path,
        selected_patriarchs=len(selections),
    )


def _valid_month(value):
    try:
        month = int(value)
    except (TypeError, ValueError) as exc:
        raise EdocsExportError("O mês deve ser um número entre 1 e 12.") from exc
    if not 1 <= month <= 12:
        raise EdocsExportError("O mês deve ser um número entre 1 e 12.")
    return month


def _valid_year(value):
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise EdocsExportError("O ano deve ser um número válido.") from exc
    if not 1 <= year <= 9999:
        raise EdocsExportError("O ano deve ser um número válido.")
    return year


def _normalize_available_patriarchs(rows):
    result = []
    seen = set()
    for item in rows:
        try:
            patriarch_id = str(UUID(str(item["id"])))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise EdocsExportError(
                "A lista de patriarcas retornou um identificador inválido."
            ) from exc
        name = str(item.get("nome") or "").strip()
        if not name:
            raise EdocsExportError(
                "A lista de patriarcas retornou um nome vazio."
            )
        if patriarch_id in seen:
            raise EdocsExportError(
                "A lista de patriarcas retornou identificadores duplicados."
            )
        seen.add(patriarch_id)
        result.append({"id": patriarch_id, "nome": name})
    return sorted(result, key=lambda item: (item["nome"].casefold(), item["id"]))


def _with_selection_name(rows, name):
    return [
        {**row, "nomePatriarcaConsulta": name}
        for row in rows
    ]


def _merge_reports(
    process_rows,
    document_rows,
    *,
    key_fields,
    selected_ids,
    month,
    year,
    names_by_id=None,
    codes_by_id=None,
):
    merged = {}
    for source_name, source_rows in (
        ("processos", process_rows),
        ("documentos", document_rows),
    ):
        source_keys = set()
        for row in source_rows:
            patriarch_id = str(row.get("idPatriarca") or "")
            if patriarch_id not in selected_ids:
                continue
            key = tuple(str(row.get(field) or "") for field in key_fields)
            if not all(key):
                raise EdocsExportError(
                    "Um relatório E-Docs retornou identificador obrigatório vazio."
                )
            if key in source_keys:
                raise EdocsExportError(
                    "O relatório E-Docs de "
                    f"{source_name} retornou identificadores duplicados."
                )
            source_keys.add(key)
            target = merged.setdefault(key, {})
            target.update(row)
    result = []
    for key in sorted(merged):
        row = merged[key]
        patriarch_id = str(row["idPatriarca"])
        if names_by_id:
            row["nomePatriarca"] = names_by_id[patriarch_id]
            row.pop("nomePatriarcaConsulta", None)
        if codes_by_id is not None:
            row["COD_MUNIC"] = codes_by_id[patriarch_id]
        row["mes"] = month
        row["ano"] = year
        result.append(row)
    return result


def _write_json_atomic(path, payload):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _write_workbook_atomic(
    path,
    *,
    environment,
    month,
    year,
    selections,
    available_by_id,
    municipality_rows,
    organization_rows,
):
    workbook = Workbook()
    workbook.remove(workbook.active)
    collected_at = datetime.now(UTC).isoformat()
    _add_sheet(
        workbook,
        "Parâmetros",
        [
            {"campo": "ambiente", "valor": environment},
            {"campo": "mês", "valor": month},
            {"campo": "ano", "valor": year},
            {"campo": "coletado_em_utc", "valor": collected_at},
        ],
        ("campo", "valor"),
    )
    selected_rows = [
        {
            "COD_MUNIC": item.municipality_code,
            "id": item.id,
            "nomeConfigurado": item.name,
            "nomeEdocs": available_by_id[item.id]["nome"],
        }
        for item in selections
    ]
    _add_sheet(
        workbook,
        "Patriarcas",
        selected_rows,
        ("COD_MUNIC", "id", "nomeConfigurado", "nomeEdocs"),
    )
    _add_sheet(
        workbook,
        "Municípios",
        municipality_rows,
        MUNICIPALITY_COLUMNS,
    )
    _add_sheet(
        workbook,
        "Organizações",
        organization_rows,
        ORGANIZATION_COLUMNS,
    )
    _add_sheet(
        workbook,
        "Fontes",
        _source_rows(month, year, environment),
        ("codigo", "metodo", "endpoint", "ambiente", "mes", "ano"),
    )

    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        workbook.save(temporary)
        os.replace(temporary, path)
    finally:
        workbook.close()
        if temporary and temporary.exists():
            temporary.unlink()


def _add_sheet(workbook, title, rows, preferred_columns):
    worksheet = workbook.create_sheet(title=title)
    columns = list(preferred_columns)
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    worksheet.append(columns)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in worksheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
    for row in rows:
        worksheet.append([_cell_value(row.get(column)) for column in columns])
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for index, column in enumerate(columns, start=1):
        values = [str(column)] + [
            str(_cell_value(row.get(column)) or "") for row in rows
        ]
        width = min(max(len(value) for value in values) + 2, 60)
        worksheet.column_dimensions[get_column_letter(index)].width = width


def _cell_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _source_rows(month, year, environment):
    month_path = f"{month:02d}"
    return [
        {
            "codigo": "IBGE-01",
            "metodo": "REFERÊNCIA",
            "endpoint": (
                "https://servicodados.ibge.gov.br/api/v1/localidades/"
                "estados/32/municipios"
            ),
            "ambiente": "EXTERNO",
            "mes": None,
            "ano": None,
        },
        {
            "codigo": "EDOC-05",
            "metodo": "GET",
            "endpoint": "/v2/agente/patriarcas",
            "ambiente": environment,
            "mes": month,
            "ano": year,
        },
        {
            "codigo": "EDOC-01",
            "metodo": "GET",
            "endpoint": (
                "/v2/processos/relatorio-quantitativos/"
                f"mes/{month_path}/ano/{year}"
            ),
            "ambiente": environment,
            "mes": month,
            "ano": year,
        },
        {
            "codigo": "EDOC-02",
            "metodo": "GET",
            "endpoint": (
                "/v2/processos/relatorio-quantitativos/{idPatriarca}/"
                f"mes/{month_path}/ano/{year}"
            ),
            "ambiente": environment,
            "mes": month,
            "ano": year,
        },
        {
            "codigo": "EDOC-03",
            "metodo": "GET",
            "endpoint": (
                "/v2/documentos/relatorio-quantitativos/"
                f"mes/{month_path}/ano/{year}"
            ),
            "ambiente": environment,
            "mes": month,
            "ano": year,
        },
        {
            "codigo": "EDOC-04",
            "metodo": "GET",
            "endpoint": (
                "/v2/documentos/relatorio-quantitativos/{idPatriarca}/"
                f"mes/{month_path}/ano/{year}"
            ),
            "ambiente": environment,
            "mes": month,
            "ano": year,
        },
    ]
