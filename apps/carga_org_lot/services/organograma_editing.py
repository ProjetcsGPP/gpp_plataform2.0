"""Operações auxiliares para edição e exportação do organograma."""

from collections import defaultdict, deque
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font

from apps.carga_org_lot.models import ImportacaoPlanilha, ItemOrganograma


ORGANOGRAM_HEADERS = (
    "Numero",
    "Nome",
    "Sigla",
    "Pai_Sigla",
    "Responsavel",
    "Cargo",
)
INITIAL_ORGANS = (
    ("GAB", "Gabinete do Prefeito"),
    ("SEFAZ", "Secretaria Municipal de Fazenda"),
    ("SESA", "Secretaria Municipal de Saúde"),
    ("SEMED", "Secretaria Municipal de Educação"),
)


def get_subtree_descendants(root: ItemOrganograma) -> list[ItemOrganograma]:
    items = list(
        ItemOrganograma.objects.filter(
            idimportacaoplanilha_id=root.idimportacaoplanilha_id
        ).order_by("strnumero", "intlinhaorigem", "iditemorganograma")
    )
    children_by_parent: dict[int, list[ItemOrganograma]] = defaultdict(list)
    for item in items:
        if item.idpai_id is not None:
            children_by_parent[item.idpai_id].append(item)

    descendants = []
    pending = deque(children_by_parent.get(root.pk, []))
    while pending:
        item = pending.popleft()
        descendants.append(item)
        pending.extend(children_by_parent.get(item.pk, []))
    return descendants


def deletion_impact(
    root: ItemOrganograma,
    descendants: list[ItemOrganograma] | None = None,
) -> dict:
    descendants = descendants if descendants is not None else get_subtree_descendants(root)
    return {
        "unidade_raiz": _item_summary(root),
        "total_descendentes": len(descendants),
        "total_excluidos": len(descendants) + 1,
        "unidades": [_item_summary(item) for item in descendants],
    }


def build_updated_organogram_xlsx(importacao: ImportacaoPlanilha) -> bytes:
    items = importacao.itens_organograma.select_related("idpai").order_by(
        "strnumero",
        "intlinhaorigem",
        "iditemorganograma",
    )
    rows = (
        (
            item.strnumero,
            item.strnome,
            item.strsigla,
            item.idpai.strsigla if item.idpai_id else "",
            item.strresponsavel,
            item.strcargo,
        )
        for item in items
    )
    return _build_organogram_xlsx(rows)


def build_initial_organogram_xlsx(
    patriarch_name: str,
    patriarch_acronym: str,
) -> bytes:
    """Gera a estrutura mínima padrão que será validada pelo fluxo de upload."""
    rows = [
        ("1", patriarch_name, patriarch_acronym, "", "", ""),
    ]
    for index, (acronym, name) in enumerate(INITIAL_ORGANS, start=1):
        organ_number = f"1.{index}"
        rows.extend(
            [
                (organ_number, name, acronym, patriarch_acronym, "", ""),
                (f"{organ_number}.1", name, acronym, acronym, "", ""),
            ]
        )
    return _build_organogram_xlsx(rows)


def _build_organogram_xlsx(rows: Iterable[tuple[str, ...]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Organograma"
    worksheet.append(ORGANOGRAM_HEADERS)
    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    for row in rows:
        worksheet.append(row)
        for cell in worksheet[worksheet.max_row]:
            cell.data_type = "s"

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.column_dimensions["A"].width = 18
    worksheet.column_dimensions["B"].width = 60
    worksheet.column_dimensions["C"].width = 24
    worksheet.column_dimensions["D"].width = 24
    worksheet.column_dimensions["E"].width = 40
    worksheet.column_dimensions["F"].width = 40

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _item_summary(item: ItemOrganograma) -> dict:
    return {
        "iditemorganograma": item.pk,
        "strnumero": item.strnumero,
        "strsigla": item.strsigla,
        "strnome": item.strnome,
    }
