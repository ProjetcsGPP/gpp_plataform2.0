"""Funções compartilhadas pelos scripts de limpeza de dados de teste."""

from __future__ import annotations

import os
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")


def setup_django() -> None:
    import django

    django.setup()


def scope_description(patriarch_id: int | None) -> str:
    return "todos os patriarcas" if patriarch_id is None else f"patriarca {patriarch_id}"


def require_confirmation(*, description: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    print()
    print(f"ATENÇÃO: serão excluídos dados de teste de {description}.")
    answer = input('Digite EXCLUIR para continuar: ').strip()
    if answer != "EXCLUIR":
        print("Operação cancelada. Nenhum dado foi excluído.")
        raise SystemExit(1)


def lotation_preview(*, patriarch_id=None, organogram_ids=None) -> dict:
    from apps.carga_org_lot.models import (
        CasoValidacaoImportacao,
        ConjuntoLotacao,
        ImportacaoPlanilha,
        ItemLotacao,
        ItemLotacaoImportado,
        ResolucaoValidacao,
    )

    imports = ImportacaoPlanilha.objects.filter(idtipocarga_id__in=(4, 5))
    sets = ConjuntoLotacao.objects.all()
    if patriarch_id is not None:
        imports = imports.filter(idpatriarca_id=patriarch_id)
        sets = sets.filter(idpatriarca_id=patriarch_id)
    if organogram_ids is not None:
        imports = imports.filter(idimportacaoorganograma_id__in=organogram_ids)
        sets = sets.filter(idimportacaoorganograma_id__in=organogram_ids)
    cases = CasoValidacaoImportacao.objects.filter(
        idrelatoriovalidacao__idimportacaoplanilha__in=imports
    )
    return {
        "importacoes_lotacao": imports.count(),
        "conjuntos_lotacao": sets.count(),
        "itens_importados": ItemLotacaoImportado.objects.filter(
            idimportacaoplanilha__in=imports
        ).count(),
        "itens_incorporados": ItemLotacao.objects.filter(
            idimportacaoplanilha__in=imports
        ).count(),
        "casos_validacao": cases.count(),
        "resolucoes": ResolucaoValidacao.objects.filter(
            idcasovalidacao__in=cases
        ).count(),
    }


def delete_lotation_data(*, patriarch_id=None, organogram_ids=None) -> dict:
    from apps.carga_org_lot.models import (
        CasoValidacaoImportacao,
        ConjuntoLotacao,
        ImportacaoPlanilha,
        ItemLotacao,
        ResolucaoValidacao,
    )

    imports = ImportacaoPlanilha.objects.filter(idtipocarga_id__in=(4, 5))
    sets = ConjuntoLotacao.objects.all()
    if patriarch_id is not None:
        imports = imports.filter(idpatriarca_id=patriarch_id)
        sets = sets.filter(idpatriarca_id=patriarch_id)
    if organogram_ids is not None:
        imports = imports.filter(idimportacaoorganograma_id__in=organogram_ids)
        sets = sets.filter(idimportacaoorganograma_id__in=organogram_ids)

    import_ids = list(imports.values_list("pk", flat=True))
    set_ids = list(sets.values_list("pk", flat=True))
    cases = CasoValidacaoImportacao.objects.filter(
        idrelatoriovalidacao__idimportacaoplanilha_id__in=import_ids
    )
    result = {}
    result["resolucoes"] = ResolucaoValidacao.objects.filter(
        idcasovalidacao__in=cases
    ).delete()[0]
    result["itens_incorporados"] = ItemLotacao.objects.filter(
        idimportacaoplanilha_id__in=import_ids
    ).delete()[0]
    result["importacoes_e_dependencias"] = ImportacaoPlanilha.objects.filter(
        pk__in=import_ids
    ).delete()[0]

    ConjuntoLotacao.objects.filter(
        idconjuntoanterior_id__in=set_ids
    ).update(idconjuntoanterior=None)
    ConjuntoLotacao.objects.filter(pk__in=set_ids).update(idconjuntoanterior=None)
    result["conjuntos_e_historicos"] = ConjuntoLotacao.objects.filter(
        pk__in=set_ids
    ).delete()[0]
    return result


def reset_global_position_catalog() -> dict:
    from apps.carga_org_lot.models import (
        CargoReferenciaGlobal,
        MapeamentoCargoPatriarca,
        OcorrenciaCargoImportacao,
        VariacaoCargoGlobal,
    )

    return {
        "ocorrencias_cargo": OcorrenciaCargoImportacao.objects.all().delete()[0],
        "mapeamentos_cargo": MapeamentoCargoPatriarca.objects.all().delete()[0],
        "variacoes_cargo": VariacaoCargoGlobal.objects.all().delete()[0],
        "cargos_referencia": CargoReferenciaGlobal.objects.all().delete()[0],
    }


def print_counts(title: str, values: dict) -> None:
    print(title)
    for key, value in values.items():
        print(f"  {key}: {value}")
