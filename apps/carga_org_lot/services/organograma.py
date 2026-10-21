"""Leitura e validação integral de planilhas de organograma."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO
import re
import unicodedata

import pandas as pd


ORGANOGRAMA_TYPE_ID = 3
ORGAN_NAME_MAX_LENGTH = 100
ORGAN_ACRONYM_MAX_LENGTH = 20
UNIT_NAME_MAX_LENGTH = 100
UNIT_ACRONYM_MAX_LENGTH = 25


def _key(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _header_key(value) -> str:
    text = unicodedata.normalize("NFKD", _key(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text).strip().lower()


def _number(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().rstrip(".")


@dataclass(frozen=True)
class OrganogramaIssue:
    codigo: str
    mensagem: str
    aba: str | None = None
    linha: int | None = None
    campo: str | None = None

    def as_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "codigo": self.codigo,
                "mensagem": self.mensagem,
                "aba": self.aba,
                "linha": self.linha,
                "campo": self.campo,
            }.items()
            if value is not None
        }


@dataclass
class OrganogramaValidationReport:
    issues: list[OrganogramaIssue] = field(default_factory=list)
    items: list["OrganogramaRow"] = field(default_factory=list)
    available_sheets: list[dict] = field(default_factory=list)
    selected_sheet: str = ""
    requires_sheet_selection: bool = False
    total_abas_lidas: int = 0
    total_linhas_lidas: int = 0
    leitura_completa: bool = True
    criar_unidades_espelho: bool = False
    total_unidades_espelho_criadas: int = 0

    @property
    def valid(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict:
        if self.requires_sheet_selection:
            return {
                "codigo": "selecao_aba_obrigatoria",
                "mensagem": (
                    "A planilha de organograma possui mais de uma aba com "
                    "dados. Selecione a aba que deve ser importada."
                ),
                "abas": self.available_sheets,
            }
        return {
            "codigo": "planilha_invalida",
            "mensagem": (
                "A importação foi rejeitada porque a planilha contém erros."
            ),
            "leitura_completa": self.leitura_completa,
            "total_abas_lidas": self.total_abas_lidas,
            "total_linhas_lidas": self.total_linhas_lidas,
            "total_erros": len(self.issues),
            "criar_unidades_espelho": self.criar_unidades_espelho,
            "total_unidades_espelho_criadas": (
                self.total_unidades_espelho_criadas
            ),
            "erros": [issue.as_dict() for issue in self.issues],
        }


@dataclass
class OrganogramaRow:
    line: int
    name: str
    acronym: str
    parent: str
    number: str
    responsible: str = ""
    position: str = ""
    resolved_parent: str = ""
    resolved_parent_line: int | None = None
    generated_automatically: bool = False


NAME_HEADERS = {
    "nome",
    "nome do orgao",
    "nome do orgao unidade",
    "nome da unidade",
    "estrutura organizacional",
    "estrutura organizacional do municipio",
}
ACRONYM_HEADERS = {
    "sigla",
    "sigla atual",
    "siglas atuais",
    "sigla do orgao",
    "sigla da unidade",
}
PARENT_HEADERS = {
    "pai",
    "pai sigla",
    "sigla pai",
    "orgao pai",
    "unidade pai",
    "parent",
    "parent sigla",
}
NUMBER_HEADERS = {
    "numero",
    "numeracao",
    "item",
    "hierarquia",
    "nivel hierarquico",
    "codigo hierarquico",
}
RESPONSIBLE_HEADERS = {
    "responsavel",
    "nome do responsavel",
    "responsavel pela unidade",
    "responsavel pelo orgao",
    "titular",
}
POSITION_HEADERS = {
    "cargo",
    "cargo do responsavel",
    "funcao",
    "funcao do responsavel",
    "cargo funcao",
}
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)*")


def validate_organogram_spreadsheet(
    content: bytes,
    extension: str,
    expected_root_acronym: str,
    selected_sheet: str = "",
    criar_unidades_espelho: bool = False,
) -> OrganogramaValidationReport:
    """Seleciona e valida integralmente uma aba de organograma."""
    report = OrganogramaValidationReport(
        criar_unidades_espelho=criar_unidades_espelho
    )
    try:
        sheets = pd.read_excel(
            BytesIO(content),
            sheet_name=None,
            header=None,
            dtype=object,
            engine=_engine_for(extension),
        )
    except Exception:  # bibliotecas de planilha lançam exceções não uniformes
        report.leitura_completa = False
        report.issues.append(
            OrganogramaIssue(
                codigo="arquivo_ilegivel",
                mensagem=(
                    "Não foi possível abrir ou ler a estrutura da planilha. "
                    "Verifique se o arquivo não está corrompido."
                ),
            )
        )
        return report

    nonempty_sheets = {
        sheet_name: dataframe.dropna(axis=1, how="all")
        for sheet_name, dataframe in sheets.items()
        if not dataframe.dropna(how="all").dropna(axis=1, how="all").empty
    }
    report.available_sheets = [
        {
            "nome": name,
            "ordem": order,
            "linhas_preenchidas": int(len(dataframe.dropna(how="all"))),
        }
        for order, (name, dataframe) in enumerate(nonempty_sheets.items(), start=1)
    ]

    if not nonempty_sheets:
        report.issues.append(
            OrganogramaIssue(
                codigo="planilha_vazia",
                mensagem="A planilha não possui nenhuma aba com dados.",
            )
        )
        return report

    selected_sheet = selected_sheet.strip()
    if not selected_sheet and len(nonempty_sheets) > 1:
        report.requires_sheet_selection = True
        return report
    if selected_sheet and selected_sheet not in nonempty_sheets:
        report.issues.append(
            OrganogramaIssue(
                codigo="aba_nao_encontrada",
                mensagem="A aba selecionada não existe ou não possui dados.",
                aba=selected_sheet,
            )
        )
        return report

    report.selected_sheet = selected_sheet or next(iter(nonempty_sheets))
    report.total_abas_lidas = 1
    report.items = _validate_sheet(
        report.selected_sheet,
        nonempty_sheets[report.selected_sheet],
        _key(expected_root_acronym),
        report,
    )
    return report


def _engine_for(extension: str) -> str:
    engines = {".xlsx": "openpyxl", ".xls": "xlrd", ".ods": "odf"}
    return engines[extension.lower()]


def _find_header(dataframe: pd.DataFrame):
    for header_position in range(min(len(dataframe), 25)):
        values = {
            column: _header_key(dataframe.iloc[header_position, column])
            for column in range(len(dataframe.columns))
        }
        name = next((col for col, value in values.items() if value in NAME_HEADERS), None)
        acronym = next(
            (col for col, value in values.items() if value in ACRONYM_HEADERS),
            None,
        )
        if name is None or acronym is None:
            continue
        parent = next(
            (col for col, value in values.items() if value in PARENT_HEADERS),
            None,
        )
        number = next(
            (col for col, value in values.items() if value in NUMBER_HEADERS),
            None,
        )
        responsible = next(
            (col for col, value in values.items() if value in RESPONSIBLE_HEADERS),
            None,
        )
        position_col = next(
            (col for col, value in values.items() if value in POSITION_HEADERS),
            None,
        )
        if number is None:
            number = _infer_number_column(
                dataframe,
                header_position,
                {name, acronym, parent, responsible, position_col},
            )
        return (
            header_position,
            name,
            acronym,
            parent,
            number,
            responsible,
            position_col,
        )
    return None


def _infer_number_column(dataframe, header_position, excluded) -> int | None:
    for column in range(len(dataframe.columns)):
        if column in excluded:
            continue
        values = [
            _number(value)
            for value in dataframe.iloc[header_position + 1 :, column].tolist()
            if _key(value)
        ]
        if values and sum(bool(NUMBER_PATTERN.fullmatch(v)) for v in values) / len(
            values
        ) >= 0.8:
            return column
    return None


def _validate_sheet(sheet, dataframe, expected_root, report):
    header = _find_header(dataframe)
    if header is None:
        report.issues.append(
            OrganogramaIssue(
                codigo="cabecalho_nao_identificado",
                mensagem=(
                    "Não foi possível identificar as colunas de nome e sigla "
                    "nesta aba."
                ),
                aba=sheet,
            )
        )
        return []

    (
        header_position,
        name_col,
        acronym_col,
        parent_col,
        number_col,
        responsible_col,
        position_col,
    ) = header
    if parent_col is None and number_col is None:
        report.issues.append(
            OrganogramaIssue(
                codigo="hierarquia_nao_identificada",
                mensagem=(
                    "Informe uma coluna de pai ou uma coluna de numeração "
                    "hierárquica."
                ),
                aba=sheet,
            )
        )
        return []

    rows = _extract_rows(
        dataframe,
        header_position,
        name_col,
        acronym_col,
        parent_col,
        number_col,
        responsible_col,
        position_col,
    )
    report.total_linhas_lidas += len(rows)
    if not rows:
        report.issues.append(
            OrganogramaIssue(
                codigo="aba_sem_dados",
                mensagem="A aba possui cabeçalho, mas não contém registros.",
                aba=sheet,
            )
        )
        return []

    _validate_required_fields(sheet, rows, report)
    has_composed_number = any("." in row.number for row in rows if row.number)
    if number_col is not None:
        _validate_numbers(sheet, rows, report)
    if number_col is not None and (parent_col is None or has_composed_number):
        _validate_number_hierarchy(sheet, rows, report)
    if parent_col is not None and not has_composed_number:
        _validate_explicit_parents(sheet, rows, report)
    elif parent_col is not None:
        _validate_number_parent_agreement(sheet, rows, report)
    _validate_cycles(sheet, rows, report)
    _validate_root(sheet, rows, expected_root, report)
    _validate_prodest_limits(sheet, rows, report)
    if report.criar_unidades_espelho:
        _ensure_mirror_units(sheet, rows, report)
    _validate_scoped_duplicates(sheet, rows, report)
    return rows


def _extract_rows(
    dataframe,
    header,
    name_col,
    acronym_col,
    parent_col,
    number_col,
    responsible_col,
    position_col,
):
    rows = []
    relevant = {name_col, acronym_col, parent_col, number_col} - {None}
    for position in range(header + 1, len(dataframe)):
        values = dataframe.iloc[position]
        if not any(_key(values.iloc[column]) for column in relevant):
            continue
        rows.append(
            OrganogramaRow(
                line=position + 1,
                name=_key(values.iloc[name_col]),
                acronym=_key(values.iloc[acronym_col]),
                parent=_key(values.iloc[parent_col]) if parent_col is not None else "",
                number=_number(values.iloc[number_col]) if number_col is not None else "",
                responsible=(
                    _key(values.iloc[responsible_col])
                    if responsible_col is not None
                    else ""
                ),
                position=(
                    _key(values.iloc[position_col])
                    if position_col is not None
                    else ""
                ),
            )
        )
    return rows


def _validate_required_fields(sheet, rows, report):
    for row in rows:
        if not row.name:
            _add(report, "nome_obrigatorio", "O nome é obrigatório.", sheet, row, "nome")
        if not row.acronym:
            _add(report, "sigla_obrigatoria", "A sigla é obrigatória.", sheet, row, "sigla")
        elif " " in row.acronym:
            _add(
                report,
                "sigla_com_espaco",
                "A sigla não pode conter espaços.",
                sheet,
                row,
                "sigla",
            )


def _validate_numbers(sheet, rows, report):
    for row in rows:
        if row.number and not NUMBER_PATTERN.fullmatch(row.number):
            _add(
                report,
                "numero_invalido",
                "Use somente números separados por pontos, como 1.2.3.",
                sheet,
                row,
                "numero",
            )
    counts = Counter(row.number for row in rows if row.number)
    for row in rows:
        if row.number and counts[row.number] > 1:
            _add(
                report,
                "numero_duplicado",
                "A numeração informada está duplicada.",
                sheet,
                row,
                "numero",
            )


def _validate_explicit_parents(sheet, rows, report):
    for row in rows:
        if not row.parent:
            continue
        candidates = [
            candidate
            for candidate in rows
            if candidate.line != row.line
            and row.parent in {candidate.acronym, candidate.name}
        ]
        if not candidates:
            _add(
                report,
                "pai_inexistente",
                "O pai informado não corresponde a uma sigla ou nome único.",
                sheet,
                row,
                "pai",
            )
            continue
        if len(candidates) > 1:
            _add(
                report,
                "pai_ambiguo",
                (
                    "O pai informado corresponde a mais de uma unidade. "
                    "Use numeração hierárquica para diferenciá-las."
                ),
                sheet,
                row,
                "pai",
            )
            continue
        parent = candidates[0]
        row.resolved_parent = parent.acronym
        row.resolved_parent_line = parent.line


def _validate_cycles(sheet, rows, report):
    by_line = {row.line: row for row in rows}
    reported = set()
    for row in rows:
        current = row
        visited = set()
        while current is not None:
            if current.line in visited:
                if row.line not in reported:
                    _add(
                        report,
                        "ciclo_hierarquico",
                        "Foi encontrado um ciclo na relação entre pais e filhos.",
                        sheet,
                        row,
                        "pai",
                    )
                    reported.add(row.line)
                break
            visited.add(current.line)
            current = by_line.get(current.resolved_parent_line)


def _validate_number_hierarchy(sheet, rows, report):
    valid_rows = [row for row in rows if NUMBER_PATTERN.fullmatch(row.number)]
    blank_numbers = [row for row in rows if not row.number]
    by_number = {row.number: row for row in valid_rows}

    if blank_numbers:
        if len(blank_numbers) != 1:
            for row in blank_numbers:
                _add(
                    report,
                    "numero_obrigatorio",
                    "Somente a raiz pode ficar sem numeração hierárquica.",
                    sheet,
                    row,
                    "numero",
                )
        root = blank_numbers[0] if len(blank_numbers) == 1 else None
        for row in valid_rows:
            if "." not in row.number:
                row.resolved_parent = root.acronym if root else ""
                row.resolved_parent_line = root.line if root else None
                continue
            parent_number = row.number.rsplit(".", 1)[0]
            parent = by_number.get(parent_number)
            if parent is None:
                _missing_number_parent(sheet, row, report)
            else:
                row.resolved_parent = parent.acronym
                row.resolved_parent_line = parent.line
        return

    top_level = [row for row in valid_rows if "." not in row.number]
    if len(top_level) == 1:
        root = top_level[0]
        for row in valid_rows:
            if row is root:
                continue
            parent_number = row.number.rsplit(".", 1)[0] if "." in row.number else ""
            parent = by_number.get(parent_number)
            if parent is None:
                _missing_number_parent(sheet, row, report)
            else:
                row.resolved_parent = parent.acronym
                row.resolved_parent_line = parent.line
    else:
        for row in top_level:
            _add(
                report,
                "raiz_ambigua",
                "Há mais de uma raiz e não existe uma coluna de pai para diferenciá-las.",
                sheet,
                row,
                "numero",
            )


def _missing_number_parent(sheet, row, report):
    _add(
        report,
        "numero_pai_inexistente",
        "O nível imediatamente superior da numeração não existe.",
        sheet,
        row,
        "numero",
    )


def _validate_number_parent_agreement(sheet, rows, report):
    by_line = {row.line: row for row in rows}
    for row in rows:
        numbered_parent = by_line.get(row.resolved_parent_line)
        if not row.parent and numbered_parent is None:
            continue
        if numbered_parent is None or row.parent not in {
            numbered_parent.acronym,
            numbered_parent.name,
        }:
            _add(
                report,
                "pai_divergente_da_numeracao",
                "A coluna de pai diverge da hierarquia indicada pela numeração.",
                sheet,
                row,
                "pai",
            )


def _validate_root(sheet, rows, expected_root, report):
    roots = [row for row in rows if row.resolved_parent_line is None]
    if len(roots) != 1:
        report.issues.append(
            OrganogramaIssue(
                codigo="quantidade_raizes_invalida",
                mensagem="O organograma deve possuir exatamente uma raiz.",
                aba=sheet,
                campo="pai",
            )
        )
        return
    if roots[0].acronym and roots[0].acronym != expected_root:
        _add(
            report,
            "raiz_diferente_do_patriarca",
            "A sigla da raiz não corresponde ao patriarca selecionado.",
            sheet,
            roots[0],
            "sigla",
        )


def _validate_scoped_duplicates(sheet, rows, report):
    by_line = {row.line: row for row in rows}
    roots = [row for row in rows if row.resolved_parent_line is None]
    root_line = roots[0].line if len(roots) == 1 else None
    sibling_groups = {}
    for row in rows:
        sibling_groups.setdefault(row.resolved_parent_line, []).append(row)

    for parent_line, siblings in sibling_groups.items():
        parent = by_line.get(parent_line)
        if parent is not None and parent.resolved_parent_line is None:
            _report_sibling_duplicates(
                sheet,
                siblings,
                "acronym",
                "sigla_duplicada_entre_irmaos",
                "sigla",
                report,
            )
        _report_sibling_duplicates(
            sheet,
            siblings,
            "name",
            "nome_duplicado_entre_irmaos",
            "nome",
            report,
        )

    units_by_organ = {}
    if root_line is not None:
        for row in rows:
            organ_line = _owning_organ_line(row, by_line, root_line)
            if organ_line is not None:
                units_by_organ.setdefault(organ_line, []).append(row)
    for units in units_by_organ.values():
        counts = Counter(row.acronym for row in units if row.acronym)
        for row in units:
            if row.acronym and counts[row.acronym] > 1:
                _add(
                    report,
                    "sigla_duplicada_no_orgao",
                    "A sigla da unidade deve ser única dentro do órgão.",
                    sheet,
                    row,
                    "sigla",
                )

    for row in rows:
        parent = by_line.get(row.resolved_parent_line)
        if parent is None or parent.resolved_parent_line is not None:
            continue
        if row.acronym and row.acronym == parent.acronym:
            _add(
                report,
                "sigla_igual_ao_pai_no_nivel_2",
                "Um órgão do nível 2 não pode repetir a sigla do Patriarca.",
                sheet,
                row,
                "sigla",
            )


def _validate_prodest_limits(sheet, rows, report):
    by_line = {row.line: row for row in rows}
    roots = [row for row in rows if row.resolved_parent_line is None]
    if len(roots) != 1:
        return

    root_line = roots[0].line
    for row in rows:
        if row.line == root_line:
            continue
        is_organ = row.resolved_parent_line == root_line
        if is_organ:
            limits = (
                ("name", ORGAN_NAME_MAX_LENGTH, "nome_orgao_muito_longo", "nome"),
                (
                    "acronym",
                    ORGAN_ACRONYM_MAX_LENGTH,
                    "sigla_orgao_muito_longa",
                    "sigla",
                ),
            )
            entity = "órgão"
        elif _owning_organ_line(row, by_line, root_line) is not None:
            limits = (
                (
                    "name",
                    UNIT_NAME_MAX_LENGTH,
                    "nome_unidade_muito_longo",
                    "nome",
                ),
                (
                    "acronym",
                    UNIT_ACRONYM_MAX_LENGTH,
                    "sigla_unidade_muito_longa",
                    "sigla",
                ),
            )
            entity = "unidade"
        else:
            continue

        for attribute, maximum, code, field_name in limits:
            if len(getattr(row, attribute)) > maximum:
                _add(
                    report,
                    code,
                    (
                        f"O {field_name} do {entity} deve ter no máximo "
                        f"{maximum} caracteres."
                    ),
                    sheet,
                    row,
                    field_name,
                )


def _owning_organ_line(row, by_line, root_line):
    """Retorna o órgão que contém a unidade; órgãos e raiz retornam None."""
    parent = by_line.get(row.resolved_parent_line)
    visited = set()
    while parent is not None and parent.line not in visited:
        if parent.resolved_parent_line == root_line:
            return parent.line
        if parent.line == root_line:
            return None
        visited.add(parent.line)
        parent = by_line.get(parent.resolved_parent_line)
    return None


def _ensure_mirror_units(sheet, rows, report):
    roots = [row for row in rows if row.resolved_parent_line is None]
    if len(roots) != 1:
        return

    root = roots[0]
    organs = [row for row in rows if row.resolved_parent_line == root.line]
    original_has_composed_number = any("." in row.number for row in rows if row.number)
    root_without_number = not root.number
    next_synthetic_line = max((row.line for row in rows), default=0) + 1

    for organ in organs:
        children = [row for row in rows if row.resolved_parent_line == organ.line]
        if any(
            child.name == organ.name and child.acronym == organ.acronym
            for child in children
        ):
            continue

        conflicting_child = next(
            (
                child
                for child in children
                if child.name == organ.name or child.acronym == organ.acronym
            ),
            None,
        )
        if conflicting_child is not None:
            _add(
                report,
                "conflito_unidade_espelho",
                (
                    "Não foi possível criar automaticamente a unidade do órgão: "
                    "já existe uma unidade filha com o mesmo nome ou a mesma sigla."
                ),
                sheet,
                conflicting_child,
                "sigla",
            )
            continue

        number = ""
        if organ.number and (original_has_composed_number or root_without_number):
            number = _next_child_number(organ, children)
        rows.append(
            OrganogramaRow(
                line=next_synthetic_line,
                name=organ.name,
                acronym=organ.acronym,
                parent=organ.acronym,
                number=number,
                resolved_parent=organ.acronym,
                resolved_parent_line=organ.line,
                generated_automatically=True,
            )
        )
        next_synthetic_line += 1
        report.total_unidades_espelho_criadas += 1


def _next_child_number(organ, children) -> str:
    prefix = f"{organ.number}."
    used_suffixes = []
    for child in children:
        if not child.number.startswith(prefix):
            continue
        suffix = child.number[len(prefix) :]
        if suffix.isdecimal() and "." not in suffix:
            used_suffixes.append(int(suffix))
    return f"{prefix}{max(used_suffixes, default=0) + 1}"


def _report_sibling_duplicates(
    sheet,
    rows,
    attribute,
    code,
    field_name,
    report,
):
    counts = Counter(getattr(row, attribute) for row in rows if getattr(row, attribute))
    for row in rows:
        value = getattr(row, attribute)
        if value and counts[value] > 1:
            _add(
                report,
                code,
                f'O valor informado em "{field_name}" está repetido entre irmãos.',
                sheet,
                row,
                field_name,
            )


def _add(report, code, message, sheet, row, field_name):
    report.issues.append(
        OrganogramaIssue(
            codigo=code,
            mensagem=message,
            aba=sheet,
            linha=row.line,
            campo=field_name,
        )
    )
