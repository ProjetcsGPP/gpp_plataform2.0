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

from apps.pub_institucional.services.cliente_edocs import ClienteEdocs


class ErroExportacaoEdocs(RuntimeError):
    """Configuração ou transformação inválida da coleta mensal."""


@dataclass(frozen=True)
class SelecaoPatriarca:
    id: str
    nome: str
    codigo_municipio: int | None


@dataclass(frozen=True)
class ResultadoExportacaoEdocs:
    caminho_planilha: Path
    diretorio_dados_brutos: Path
    caminho_catalogo: Path
    caminho_selecao: Path
    quantidade_patriarcas_selecionados: int


COLUNAS_MUNICIPIO = (
    "COD_MUNIC",
    "idPatriarca",
    "nomePatriarca",
    "totalProcessos",
    "totalDocumentos",
    "totalPaginas",
    "mes",
    "ano",
)
COLUNAS_ORGANIZACAO = (
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


def carregar_selecao_patriarcas(caminho):
    """Lê IDs, nomes e códigos municipais da seleção versionável."""
    config_path = Path(caminho)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErroExportacaoEdocs(
            "Não foi possível ler o JSON de patriarcas selecionados."
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise ErroExportacaoEdocs(
            "O JSON de patriarcas deve ser uma lista não vazia."
        )

    result = []
    seen = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict) or not {"id", "nome"} <= set(item):
            raise ErroExportacaoEdocs(
                f"O item {index} deve conter id e nome."
            )
        if set(item) - {"id", "nome", "COD_MUNIC"}:
            raise ErroExportacaoEdocs(
                f"O item {index} contém campos não permitidos."
            )
        try:
            id_patriarca = str(UUID(str(item["id"])))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ErroExportacaoEdocs(
                f"O item {index} possui um id inválido."
            ) from exc
        name = str(item["nome"]).strip()
        if not name:
            raise ErroExportacaoEdocs(f"O item {index} possui nome vazio.")
        if id_patriarca in seen:
            raise ErroExportacaoEdocs(
                f"O patriarca {id_patriarca} aparece mais de uma vez."
            )
        seen.add(id_patriarca)
        municipality_code = item.get("COD_MUNIC")
        if municipality_code is not None and (
            isinstance(municipality_code, bool)
            or not isinstance(municipality_code, int)
            or not 1_000_000 <= municipality_code <= 9_999_999
        ):
            raise ErroExportacaoEdocs(
                f"O item {index} possui COD_MUNIC inválido."
            )
        result.append(
            SelecaoPatriarca(id_patriarca, name, municipality_code)
        )
    return result


def exportar_edocs_mensal(  # pylint: disable=too-many-locals
    *,
    mes,
    ano,
    caminho_selecao,
    diretorio_saida,
    cliente=None,
):
    """Executa os cinco métodos aprovados e produz JSONs e XLSX."""
    mes = _validar_mes(mes)
    ano = _validar_ano(ano)
    selections = carregar_selecao_patriarcas(caminho_selecao)
    caminho_selecao = Path(caminho_selecao)
    api = cliente or ClienteEdocs()
    month_path = f"{mes:02d}"

    available_raw = api.listar_patriarcas()
    available = _normalizar_patriarcas_disponiveis(available_raw)
    available_by_id = {item["id"]: item for item in available}
    missing = [item.id for item in selections if item.id not in available_by_id]
    if missing:
        raise ErroExportacaoEdocs(
            "Patriarcas selecionados não estão habilitados no E-Docs: "
            + ", ".join(missing)
        )

    process_global = api.relatorio_processos(month_path, ano)
    document_global = api.relatorio_documentos(month_path, ano)
    process_by_org = []
    document_by_org = []
    raw_by_patriarch = {}
    for selection in selections:
        process_rows = api.relatorio_processos_por_patriarca(
            selection.id,
            month_path,
            ano,
        )
        document_rows = api.relatorio_documentos_por_patriarca(
            selection.id,
            month_path,
            ano,
        )
        process_by_org.extend(
            _adicionar_nome_selecao(process_rows, selection.nome)
        )
        document_by_org.extend(
            _adicionar_nome_selecao(document_rows, selection.nome)
        )
        raw_by_patriarch[selection.id] = {
            "processos": process_rows,
            "documentos": document_rows,
        }

    selected_ids = {selection.id for selection in selections}
    codes_by_id = {
        selection.id: selection.codigo_municipio for selection in selections
    }
    municipality_rows = _consolidar_relatorios(
        process_global,
        document_global,
        campos_chave=("idPatriarca",),
        ids_selecionados=selected_ids,
        mes=mes,
        ano=ano,
        codigos_por_id=codes_by_id,
    )
    names_by_id = {selection.id: selection.nome for selection in selections}
    organization_rows = _consolidar_relatorios(
        process_by_org,
        document_by_org,
        campos_chave=("idPatriarca", "idOrganizacao"),
        ids_selecionados=selected_ids,
        mes=mes,
        ano=ano,
        nomes_por_id=names_by_id,
        codigos_por_id=codes_by_id,
    )

    output_root = Path(diretorio_saida)
    period_directory = output_root / f"{ano}-{mes:02d}"
    raw_directory = period_directory / "json"
    output_root.mkdir(parents=True, exist_ok=True)
    period_directory.mkdir(mode=0o700, exist_ok=True)
    raw_directory.mkdir(mode=0o700, exist_ok=True)
    period_directory.chmod(0o700)
    raw_directory.chmod(0o700)
    catalog_path = period_directory / "patriarcas_catalogo_edocs.json"

    _gravar_json_atomico(catalog_path, available)
    _gravar_json_atomico(raw_directory / "edoc-05-patriarcas.json", available_raw)
    _gravar_json_atomico(
        raw_directory / "edoc-01-processos-geral.json",
        process_global,
    )
    _gravar_json_atomico(
        raw_directory / "edoc-03-documentos-geral.json",
        document_global,
    )
    for selection in selections:
        raw = raw_by_patriarch[selection.id]
        _gravar_json_atomico(
            raw_directory / f"edoc-02-processos-{selection.id}.json",
            raw["processos"],
        )
        _gravar_json_atomico(
            raw_directory / f"edoc-04-documentos-{selection.id}.json",
            raw["documentos"],
        )

    workbook_path = period_directory / f"edocs_{ano}_{mes:02d}.xlsx"
    _gravar_planilha_atomica(
        workbook_path,
        environment=api.ambiente,
        mes=mes,
        ano=ano,
        selections=selections,
        available_by_id=available_by_id,
        municipality_rows=municipality_rows,
        organization_rows=organization_rows,
    )
    return ResultadoExportacaoEdocs(
        caminho_planilha=workbook_path,
        diretorio_dados_brutos=raw_directory,
        caminho_catalogo=catalog_path,
        caminho_selecao=caminho_selecao,
        quantidade_patriarcas_selecionados=len(selections),
    )


def _validar_mes(value):
    try:
        mes = int(value)
    except (TypeError, ValueError) as exc:
        raise ErroExportacaoEdocs("O mês deve ser um número entre 1 e 12.") from exc
    if not 1 <= mes <= 12:
        raise ErroExportacaoEdocs("O mês deve ser um número entre 1 e 12.")
    return mes


def _validar_ano(value):
    try:
        ano = int(value)
    except (TypeError, ValueError) as exc:
        raise ErroExportacaoEdocs("O ano deve ser um número válido.") from exc
    if not 1 <= ano <= 9999:
        raise ErroExportacaoEdocs("O ano deve ser um número válido.")
    return ano


def _normalizar_patriarcas_disponiveis(linhas):
    result = []
    seen = set()
    for item in linhas:
        try:
            id_patriarca = str(UUID(str(item["id"])))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ErroExportacaoEdocs(
                "A lista de patriarcas retornou um identificador inválido."
            ) from exc
        name = str(item.get("nome") or "").strip()
        if not name:
            raise ErroExportacaoEdocs(
                "A lista de patriarcas retornou um nome vazio."
            )
        if id_patriarca in seen:
            raise ErroExportacaoEdocs(
                "A lista de patriarcas retornou identificadores duplicados."
            )
        seen.add(id_patriarca)
        result.append({"id": id_patriarca, "nome": name})
    return sorted(result, key=lambda item: (item["nome"].casefold(), item["id"]))


def _adicionar_nome_selecao(linhas, nome):
    return [
        {**linha, "nomePatriarcaConsulta": nome}
        for linha in linhas
    ]


def _consolidar_relatorios(
    linhas_processos,
    linhas_documentos,
    *,
    campos_chave,
    ids_selecionados,
    mes,
    ano,
    nomes_por_id=None,
    codigos_por_id=None,
):
    merged = {}
    for source_name, source_rows in (
        ("processos", linhas_processos),
        ("documentos", linhas_documentos),
    ):
        source_keys = set()
        for row in source_rows:
            id_patriarca = str(row.get("idPatriarca") or "")
            if id_patriarca not in ids_selecionados:
                continue
            key = tuple(str(row.get(field) or "") for field in campos_chave)
            if not all(key):
                raise ErroExportacaoEdocs(
                    "Um relatório E-Docs retornou identificador obrigatório vazio."
                )
            if key in source_keys:
                raise ErroExportacaoEdocs(
                    "O relatório E-Docs de "
                    f"{source_name} retornou identificadores duplicados."
                )
            source_keys.add(key)
            target = merged.setdefault(key, {})
            target.update(row)
    result = []
    for key in sorted(merged):
        row = merged[key]
        id_patriarca = str(row["idPatriarca"])
        if nomes_por_id:
            row["nomePatriarca"] = nomes_por_id[id_patriarca]
            row.pop("nomePatriarcaConsulta", None)
        if codigos_por_id is not None:
            row["COD_MUNIC"] = codigos_por_id[id_patriarca]
        row["mes"] = mes
        row["ano"] = ano
        result.append(row)
    return result


def _gravar_json_atomico(caminho, conteudo):
    caminho = Path(caminho)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=caminho.parent,
            prefix=f".{caminho.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(conteudo, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, caminho)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _gravar_planilha_atomica(
    caminho,
    *,
    environment,
    mes,
    ano,
    selections,
    available_by_id,
    municipality_rows,
    organization_rows,
):
    workbook = Workbook()
    workbook.remove(workbook.active)
    collected_at = datetime.now(UTC).isoformat()
    _adicionar_aba(
        workbook,
        "Parâmetros",
        [
            {"campo": "ambiente", "valor": environment},
            {"campo": "mês", "valor": mes},
            {"campo": "ano", "valor": ano},
            {"campo": "coletado_em_utc", "valor": collected_at},
        ],
        ("campo", "valor"),
    )
    selected_rows = [
        {
            "COD_MUNIC": item.codigo_municipio,
            "id": item.id,
            "nomeConfigurado": item.nome,
            "nomeEdocs": available_by_id[item.id]["nome"],
        }
        for item in selections
    ]
    _adicionar_aba(
        workbook,
        "Patriarcas",
        selected_rows,
        ("COD_MUNIC", "id", "nomeConfigurado", "nomeEdocs"),
    )
    _adicionar_aba(
        workbook,
        "Municípios",
        municipality_rows,
        COLUNAS_MUNICIPIO,
    )
    _adicionar_aba(
        workbook,
        "Organizações",
        organization_rows,
        COLUNAS_ORGANIZACAO,
    )
    _adicionar_aba(
        workbook,
        "Fontes",
        _linhas_fontes(mes, ano, environment),
        ("codigo", "metodo", "endpoint", "ambiente", "mes", "ano"),
    )

    caminho = Path(caminho)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=caminho.parent,
            prefix=f".{caminho.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        workbook.save(temporary)
        os.replace(temporary, caminho)
    finally:
        workbook.close()
        if temporary and temporary.exists():
            temporary.unlink()


def _adicionar_aba(workbook, title, rows, preferred_columns):
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
        worksheet.append([_valor_celula(row.get(column)) for column in columns])
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for index, column in enumerate(columns, start=1):
        values = [str(column)] + [
            str(_valor_celula(row.get(column)) or "") for row in rows
        ]
        width = min(max(len(value) for value in values) + 2, 60)
        worksheet.column_dimensions[get_column_letter(index)].width = width


def _valor_celula(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _linhas_fontes(mes, ano, environment):
    month_path = f"{mes:02d}"
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
            "mes": mes,
            "ano": ano,
        },
        {
            "codigo": "EDOC-01",
            "metodo": "GET",
            "endpoint": (
                "/v2/processos/relatorio-quantitativos/"
                f"mes/{month_path}/ano/{ano}"
            ),
            "ambiente": environment,
            "mes": mes,
            "ano": ano,
        },
        {
            "codigo": "EDOC-02",
            "metodo": "GET",
            "endpoint": (
                "/v2/processos/relatorio-quantitativos/{idPatriarca}/"
                f"mes/{month_path}/ano/{ano}"
            ),
            "ambiente": environment,
            "mes": mes,
            "ano": ano,
        },
        {
            "codigo": "EDOC-03",
            "metodo": "GET",
            "endpoint": (
                "/v2/documentos/relatorio-quantitativos/"
                f"mes/{month_path}/ano/{ano}"
            ),
            "ambiente": environment,
            "mes": mes,
            "ano": ano,
        },
        {
            "codigo": "EDOC-04",
            "metodo": "GET",
            "endpoint": (
                "/v2/documentos/relatorio-quantitativos/{idPatriarca}/"
                f"mes/{month_path}/ano/{ano}"
            ),
            "ambiente": environment,
            "mes": mes,
            "ano": ano,
        },
    ]
