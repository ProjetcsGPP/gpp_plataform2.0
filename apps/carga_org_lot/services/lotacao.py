"""Leitura e validação integral de planilhas de lotação."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from numbers import Integral, Real
import re
import unicodedata

import pandas as pd
from validate_docbr import CPF


LOTACAO_TYPE_IDS = {4, 5}
ORGAN_ACRONYM_MAX_LENGTH = 20
UNIT_ACRONYM_MAX_LENGTH = 25
CARGO_MAX_LENGTH = 100
PERSON_NAME_MAX_LENGTH = 255
SOURCE_NAME_MAX_LENGTH = 500
RULES_VERSION = "lotacao-v4"

CPF_VALIDATOR = CPF()


def _text(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _key(value) -> str:
    return _text(value).upper()


def _cpf_text(value) -> str:
    """Preserva o zero inicial perdido quando o CPF é uma célula numérica."""
    if pd.isna(value):
        return ""
    if isinstance(value, Integral) and not isinstance(value, bool):
        return str(value).zfill(11)
    if isinstance(value, Real) and float(value).is_integer():
        return str(int(value)).zfill(11)
    return _text(value)


def normalize_cpf(value) -> str:
    """Converte CPF textual ou numérico para sua representação canônica."""
    return re.sub(r"\D", "", _cpf_text(value))


def _header_key(value) -> str:
    text = unicodedata.normalize("NFKD", _key(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text).strip().lower()


def _engine_for(extension: str) -> str:
    engines = {".xlsx": "openpyxl", ".xls": "xlrd", ".ods": "odf"}
    return engines[extension.lower()]


@dataclass(frozen=True)
class LotacaoIssue:
    codigo: str
    mensagem: str
    severidade: str = "ERRO"
    aba: str | None = None
    linha: int | None = None
    campo: str | None = None
    valor_original: str = ""
    valor_normalizado: str = ""
    regra_aplicada: str = ""
    sugestoes: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "codigo": self.codigo,
                "mensagem": self.mensagem,
                "severidade": self.severidade,
                "aba": self.aba,
                "linha": self.linha,
                "campo": self.campo,
                "valor_original": self.valor_original,
                "valor_normalizado": self.valor_normalizado,
                "regra_aplicada": self.regra_aplicada,
                "sugestoes": list(self.sugestoes),
            }.items()
            if value not in (None, "")
        }


@dataclass
class LotacaoRow:
    sheet: str
    line: int
    organ_id: int | None
    unit_id: int | None
    organ_acronym: str
    original_organ_acronym: str
    organ_name: str
    person_name: str
    cpf: str
    original_cpf: str
    original_position: str
    normalized_position: str
    unit_acronym: str
    original_unit_acronym: str
    unit_name: str


@dataclass
class LotacaoValidationReport:
    issues: list[LotacaoIssue] = field(default_factory=list)
    items: list[LotacaoRow] = field(default_factory=list)
    processed_sheets: list[str] = field(default_factory=list)
    total_abas_lidas: int = 0
    total_linhas_lidas: int = 0
    total_linhas_validas: int = 0
    leitura_completa: bool = True
    cargo_summary: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[LotacaoIssue]:
        return [issue for issue in self.issues if issue.severidade == "ERRO"]

    @property
    def warnings(self) -> list[LotacaoIssue]:
        return [issue for issue in self.issues if issue.severidade == "AVISO"]

    @property
    def normalizations(self) -> list[LotacaoIssue]:
        return [
            issue for issue in self.issues if issue.severidade == "NORMALIZACAO"
        ]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "codigo": "planilha_valida" if self.valid else "planilha_invalida",
            "mensagem": (
                "A planilha de lotação foi validada e incorporada."
                if self.valid
                else "A importação foi rejeitada porque a planilha contém erros."
            ),
            "versao_regras": RULES_VERSION,
            "leitura_completa": self.leitura_completa,
            "abas_processadas": self.processed_sheets,
            "total_abas_lidas": self.total_abas_lidas,
            "total_linhas_lidas": self.total_linhas_lidas,
            "total_linhas_validas": self.total_linhas_validas,
            "total_erros": len(self.errors),
            "total_avisos": len(self.warnings),
            "total_normalizacoes": len(self.normalizations),
            "cargos": self.cargo_summary,
            "erros": [issue.as_dict() for issue in self.errors],
            "avisos": [issue.as_dict() for issue in self.warnings],
            "normalizacoes": [
                issue.as_dict() for issue in self.normalizations
            ],
        }


HEADER_ALIASES = {
    "organ_acronym": {
        "sigla",
        "sigla orgao",
        "sigla secretaria",
        "orgao sigla",
        "orgao do servidor",
    },
    "organ_name": {
        "secretaria orgao",
        "orgao secretaria",
        "nome do orgao",
        "nome da secretaria",
    },
    "person_name": {
        "nome do servidor",
        "servidor",
        "nome",
    },
    "cpf": {"cpf", "cpf do servidor"},
    "position": {
        "ocupacao cargo",
        "cargo ocupacao",
        "cargo",
        "ocupacao",
    },
    "unit_acronym": {
        "sigla setor",
        "sigla unidade",
        "unidade sigla",
        "setor unidade de lotacao",
    },
    "unit_name": {
        "setor de lotacao",
        "unidade de lotacao",
        "nome do setor",
        "nome da unidade",
    },
}


def validate_lotation_spreadsheet(
    content: bytes,
    extension: str,
    organogram_items,
) -> LotacaoValidationReport:
    """Lê todas as abas e valida a lotação contra um organograma persistido."""
    report = LotacaoValidationReport()
    try:
        sheets = pd.read_excel(
            BytesIO(content),
            sheet_name=None,
            header=None,
            dtype=object,
            engine=_engine_for(extension),
        )
    except Exception:
        report.leitura_completa = False
        report.issues.append(
            LotacaoIssue(
                codigo="arquivo_ilegivel",
                mensagem=(
                    "Não foi possível abrir ou ler a estrutura da planilha. "
                    "Verifique se o arquivo não está corrompido."
                ),
            )
        )
        return report

    nonempty_sheets = {
        name: dataframe.dropna(axis=1, how="all")
        for name, dataframe in sheets.items()
        if not dataframe.dropna(how="all").dropna(axis=1, how="all").empty
    }
    if not nonempty_sheets:
        report.issues.append(
            LotacaoIssue(
                codigo="planilha_vazia",
                mensagem="A planilha não possui nenhuma aba com dados.",
            )
        )
        return report

    hierarchy = _build_hierarchy(organogram_items, report)
    for sheet_name, dataframe in nonempty_sheets.items():
        report.total_abas_lidas += 1
        report.processed_sheets.append(sheet_name)
        header = _find_header(dataframe)
        if header is None:
            report.issues.append(
                LotacaoIssue(
                    codigo="cabecalho_lotacao_nao_encontrado",
                    mensagem=(
                        "Não foi encontrado um cabeçalho de lotação com as "
                        "sete colunas obrigatórias."
                    ),
                    aba=sheet_name,
                )
            )
            continue
        header_position, columns = header
        _validate_sheet(
            sheet_name,
            dataframe,
            header_position,
            columns,
            hierarchy,
            report,
        )
    _report_duplicate_cpfs(report)
    if report.total_linhas_lidas == 0:
        report.issues.append(
            LotacaoIssue(
                codigo="planilha_sem_lotacoes",
                mensagem="A planilha não possui nenhuma linha de lotação.",
            )
        )
    return report


def _find_header(dataframe: pd.DataFrame):
    for position in range(min(len(dataframe), 25)):
        values = {
            column: _header_key(dataframe.iloc[position, column])
            for column in range(len(dataframe.columns))
        }
        columns = {}
        for field_name, aliases in HEADER_ALIASES.items():
            column = next(
                (column for column, value in values.items() if value in aliases),
                None,
            )
            if column is None:
                break
            columns[field_name] = column
        if len(columns) == len(HEADER_ALIASES):
            return position, columns
    return None


def _build_hierarchy(items, report: LotacaoValidationReport) -> dict:
    items = list(items)
    roots = [item for item in items if item.idpai_id is None]
    if len(roots) != 1:
        report.issues.append(
            LotacaoIssue(
                codigo="organograma_referencia_sem_raiz_unica",
                mensagem=(
                    "O organograma de referência deve possuir exatamente "
                    "um patriarca na raiz."
                ),
            )
        )
        return {"organs": {}, "units": {}}

    root = roots[0]
    organs = {
        _key(item.strsigla): item
        for item in items
        if item.idpai_id == root.pk
    }
    by_id = {item.pk: item for item in items}
    units: dict[tuple[int, str], list] = {}
    for item in items:
        organ = _owning_organ(item, root.pk, by_id)
        if organ is None:
            continue
        units.setdefault((organ.pk, _key(item.strsigla)), []).append(item)
    return {"organs": organs, "units": units}


def _owning_organ(item, root_id: int, by_id: dict):
    if item.idpai_id == root_id:
        return item
    current = item
    visited = set()
    while current.idpai_id is not None and current.pk not in visited:
        visited.add(current.pk)
        parent = by_id.get(current.idpai_id)
        if parent is None:
            return None
        if parent.idpai_id == root_id:
            return parent
        current = parent
    return None


def _validate_sheet(
    sheet_name,
    dataframe,
    header_position,
    columns,
    hierarchy,
    report,
):
    for position in range(header_position + 1, len(dataframe)):
        raw = {
            field_name: _text(dataframe.iloc[position, column])
            for field_name, column in columns.items()
        }
        raw["cpf"] = _cpf_text(dataframe.iloc[position, columns["cpf"]])
        if not any(raw.values()):
            continue

        line = position + 1
        report.total_linhas_lidas += 1
        issue_count = len(report.errors)
        organ_acronym = _key(raw["organ_acronym"])
        unit_acronym = _key(raw["unit_acronym"])
        cpf = normalize_cpf(raw["cpf"])
        normalized_position = _key(raw["position"])

        _record_normalization(
            report,
            sheet_name,
            line,
            "strsiglaorgao",
            raw["organ_acronym"],
            organ_acronym,
        )
        _record_normalization(
            report,
            sheet_name,
            line,
            "strsiglaunidade",
            raw["unit_acronym"],
            unit_acronym,
        )
        _record_normalization(report, sheet_name, line, "strcpf", raw["cpf"], cpf)
        _record_normalization(
            report,
            sheet_name,
            line,
            "strcargonormalizado",
            raw["position"],
            normalized_position,
        )

        organ = _validate_organ(
            report, hierarchy, organ_acronym, raw, sheet_name, line
        )
        unit = _validate_unit(
            report,
            hierarchy,
            organ,
            organ_acronym,
            unit_acronym,
            raw,
            sheet_name,
            line,
        )
        _validate_person_data(
            report,
            raw,
            cpf,
            normalized_position,
            sheet_name,
            line,
        )
        _validate_source_lengths(report, raw, sheet_name, line)

        row = LotacaoRow(
            sheet=sheet_name,
            line=line,
            organ_id=organ.pk if organ is not None else None,
            unit_id=unit.pk if unit is not None else None,
            organ_acronym=organ_acronym,
            original_organ_acronym=raw["organ_acronym"],
            organ_name=_text(raw["organ_name"]),
            person_name=_text(raw["person_name"]),
            cpf=cpf,
            original_cpf=raw["cpf"],
            original_position=_text(raw["position"]),
            normalized_position=normalized_position,
            unit_acronym=unit_acronym,
            original_unit_acronym=raw["unit_acronym"],
            unit_name=_text(raw["unit_name"]),
        )
        report.items.append(row)
        if len(report.errors) == issue_count:
            report.total_linhas_validas += 1


def _validate_organ(report, hierarchy, acronym, raw, sheet, line):
    organ = hierarchy["organs"].get(acronym)
    if not acronym:
        _error(
            report,
            "orgao_ausente",
            "A sigla do órgão é obrigatória.",
            sheet,
            line,
            "strsiglaorgao",
        )
    elif len(acronym) > ORGAN_ACRONYM_MAX_LENGTH:
        _error(
            report,
            "sigla_orgao_muito_longa",
            "A sigla do órgão deve ter no máximo "
            f"{ORGAN_ACRONYM_MAX_LENGTH} caracteres.",
            sheet,
            line,
            "strsiglaorgao",
            raw["organ_acronym"],
        )
    elif organ is None:
        _error(
            report,
            "orgao_invalido",
            f'O órgão "{acronym}" não existe no nível 2 do organograma '
            "selecionado.",
            sheet,
            line,
            "strsiglaorgao",
            raw["organ_acronym"],
        )
    return organ


def _validate_unit(
    report,
    hierarchy,
    organ,
    organ_acronym,
    unit_acronym,
    raw,
    sheet,
    line,
):
    if not unit_acronym:
        _error(
            report,
            "unidade_ausente",
            "A sigla da unidade de lotação é obrigatória.",
            sheet,
            line,
            "strsiglaunidade",
        )
        return None
    if len(unit_acronym) > UNIT_ACRONYM_MAX_LENGTH:
        _error(
            report,
            "sigla_unidade_muito_longa",
            "A sigla da unidade deve ter no máximo "
            f"{UNIT_ACRONYM_MAX_LENGTH} caracteres.",
            sheet,
            line,
            "strsiglaunidade",
            raw["unit_acronym"],
        )
        return None
    if organ is None:
        return None

    candidates = hierarchy["units"].get((organ.pk, unit_acronym), [])
    descendants = [candidate for candidate in candidates if candidate.pk != organ.pk]
    if len(descendants) == 1:
        return descendants[0]
    if not descendants and unit_acronym == _key(organ.strsigla):
        return organ
    if not candidates:
        code = "unidade_invalida"
        message = (
            f'A unidade "{unit_acronym}" não existe na hierarquia do órgão '
            f'"{organ_acronym}".'
        )
    else:
        code = "unidade_ambigua"
        message = (
            f'A sigla "{unit_acronym}" identifica mais de uma unidade no '
            f'órgão "{organ_acronym}".'
        )
    _error(
        report,
        code,
        message,
        sheet,
        line,
        "strsiglaunidade",
        raw["unit_acronym"],
    )
    return None


def _validate_person_data(report, raw, cpf, position, sheet, line):
    if not raw["cpf"]:
        _error(report, "cpf_ausente", "O CPF é obrigatório.", sheet, line, "strcpf")
    elif len(cpf) != 11:
        _error(
            report,
            "cpf_invalido",
            "O CPF deve possuir exatamente 11 dígitos numéricos.",
            sheet,
            line,
            "strcpf",
            raw["cpf"],
        )
    elif not CPF_VALIDATOR.validate(cpf):
        _error(
            report,
            "cpf_digitos_verificadores_invalidos",
            "O CPF possui 11 dígitos, mas os dígitos verificadores são inválidos.",
            sheet,
            line,
            "strcpf",
            raw["cpf"],
        )
    if not raw["person_name"]:
        _error(
            report,
            "nome_servidor_ausente",
            "O nome do servidor é obrigatório.",
            sheet,
            line,
            "strnomeservidor",
        )
    if not position:
        _error(
            report,
            "cargo_ausente",
            "O cargo ou ocupação é obrigatório.",
            sheet,
            line,
            "strcargooriginal",
        )
    elif len(position) > CARGO_MAX_LENGTH:
        _error(
            report,
            "cargo_muito_longo",
            "O cargo ou ocupação deve ter no máximo "
            f"{CARGO_MAX_LENGTH} caracteres.",
            sheet,
            line,
            "strcargooriginal",
            raw["position"],
        )


def _report_duplicate_cpfs(report: LotacaoValidationReport):
    rows_by_assignment: dict[tuple, list[LotacaoRow]] = {}
    for row in report.items:
        if row.cpf:
            organ_key = (
                ("id", row.organ_id)
                if row.organ_id is not None
                else ("sigla", row.organ_acronym)
            )
            unit_key = (
                ("id", row.unit_id)
                if row.unit_id is not None
                else ("sigla", row.unit_acronym)
            )
            key = (row.cpf, organ_key, unit_key)
            rows_by_assignment.setdefault(key, []).append(row)

    for (cpf, _organ_key, _unit_key), rows in rows_by_assignment.items():
        if len(rows) < 2:
            continue
        locations = ", ".join(f'{row.sheet}, linha {row.line}' for row in rows)
        for row in rows:
            report.issues.append(
                LotacaoIssue(
                    codigo="cpf_duplicado_planilha",
                    mensagem=(
                        "O CPF aparece mais de uma vez no mesmo órgão e "
                        "na mesma unidade: "
                        f"{locations}. Verifique se as lotações são intencionais."
                    ),
                    severidade="AVISO",
                    aba=row.sheet,
                    linha=row.line,
                    campo="strcpf",
                    valor_original=cpf,
                    regra_aplicada=(
                        "detecção de CPF repetido no mesmo órgão e unidade, "
                        "entre linhas e abas"
                    ),
                )
            )


def _validate_source_lengths(report, raw, sheet, line):
    length_rules = (
        (
            "organ_name",
            SOURCE_NAME_MAX_LENGTH,
            "nome_orgao_muito_longo",
            "strnomeorgao",
        ),
        (
            "person_name",
            PERSON_NAME_MAX_LENGTH,
            "nome_servidor_muito_longo",
            "strnomeservidor",
        ),
        (
            "unit_name",
            SOURCE_NAME_MAX_LENGTH,
            "nome_unidade_muito_longo",
            "strnomeunidade",
        ),
    )
    for source_field, maximum, code, model_field in length_rules:
        if len(raw[source_field]) > maximum:
            _error(
                report,
                code,
                f"O campo deve ter no máximo {maximum} caracteres.",
                sheet,
                line,
                model_field,
                raw[source_field],
            )


def _record_normalization(report, sheet, line, field_name, original, normalized):
    if original and original != normalized:
        report.issues.append(
            LotacaoIssue(
                codigo="valor_normalizado",
                mensagem="O valor foi normalizado sem perda da informação original.",
                severidade="NORMALIZACAO",
                aba=sheet,
                linha=line,
                campo=field_name,
                valor_original=original,
                valor_normalizado=normalized,
                regra_aplicada="remoção de espaços excedentes e padronização",
            )
        )


def _error(
    report,
    code,
    message,
    sheet,
    line,
    field_name,
    original="",
    suggestions=(),
):
    report.issues.append(
        LotacaoIssue(
            codigo=code,
            mensagem=message,
            aba=sheet,
            linha=line,
            campo=field_name,
            valor_original=original,
            sugestoes=tuple(suggestions),
        )
    )
