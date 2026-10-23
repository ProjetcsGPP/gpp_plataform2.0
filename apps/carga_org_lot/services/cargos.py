"""Catálogo global e sugestões explicáveis para cargos de lotação."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import re
import unicodedata

from django.db.models import Count, Sum
from rapidfuzz import fuzz

from apps.carga_org_lot.models import (
    AcaoResolucaoValidacao,
    CargoReferenciaGlobal,
    EscopoMapeamentoCargo,
    ItemLotacaoImportado,
    MapeamentoCargoPatriarca,
    OcorrenciaCargoImportacao,
    StatusCargoReferencia,
    StatusItemLotacaoImportado,
    StatusVariacaoCargo,
    VariacaoCargoGlobal,
)
from apps.carga_org_lot.services.lotacao import LotacaoIssue


CARGO_RULES_VERSION = "cargos-v1"
MINIMUM_SUGGESTION_SCORE = 80
MAX_SUGGESTIONS = 5

ABBREVIATIONS = {
    "ADM": "ADMINISTRATIVO",
    "ADMIN": "ADMINISTRATIVO",
    "ASSIST": "ASSISTENTE",
    "AUX": "AUXILIAR",
    "COORD": "COORDENADOR",
    "DIR": "DIRETOR",
    "EDUC": "EDUCACAO",
    "ENF": "ENFERMEIRO",
    "PROF": "PROFESSOR",
    "TEC": "TECNICO",
}


def cargo_key(value: str) -> str:
    """Chave estável de pesquisa; o texto original continua preservado."""
    text = unicodedata.normalize("NFKD", (value or "").strip().upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    key = re.sub(r"[^A-Z0-9]+", " ", text).strip()
    if len(key) <= 255:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"{key[:230].rstrip()} {digest}"


def _expanded_key(value: str) -> str:
    return " ".join(ABBREVIATIONS.get(token, token) for token in cargo_key(value).split())


def _score(source: str, candidate: str) -> float:
    expanded_source = _expanded_key(source)
    expanded_candidate = _expanded_key(candidate)
    return round(
        max(
            fuzz.WRatio(expanded_source, expanded_candidate),
            fuzz.token_set_ratio(expanded_source, expanded_candidate),
        ),
        2,
    )


def _audit_fields(audit_data: dict) -> dict:
    return {
        key: audit_data.get(key)
        for key in (
            "created_by_id",
            "created_by_name",
            "updated_by_id",
            "updated_by_name",
        )
    }


def _refresh_variation_statistics(variation: VariacaoCargoGlobal) -> None:
    statistics = variation.ocorrencias.aggregate(
        total=Sum("intquantidade"),
        imports=Count("idimportacaoplanilha", distinct=True),
        patriarchs=Count("idpatriarca", distinct=True),
    )
    variation.inttotalocorrencias = statistics["total"] or 0
    variation.inttotalimportacoes = statistics["imports"] or 0
    variation.inttotalpatriarcas = statistics["patriarchs"] or 0
    variation.save(
        update_fields=[
            "inttotalocorrencias",
            "inttotalimportacoes",
            "inttotalpatriarcas",
            "datultimaocorrencia",
            "updated_at",
        ]
    )


def _resolved_reference(importacao, variation):
    local = (
        MapeamentoCargoPatriarca.objects.select_related("idcargoreferencia")
        .filter(
            idpatriarca=importacao.idpatriarca,
            idvariacaocargo=variation,
            flgativo=True,
            idcargoreferencia__flgativo=True,
            idcargoreferencia__strstatus=StatusCargoReferencia.CONFIRMADO,
        )
        .first()
    )
    if local is not None:
        return local.idcargoreferencia
    if (
        variation.idcargoreferencia_id
        and variation.idcargoreferencia.flgativo
        and variation.idcargoreferencia.strstatus
        == StatusCargoReferencia.CONFIRMADO
    ):
        return variation.idcargoreferencia
    return None


def _candidate_suggestions(key: str, references) -> list[dict]:
    candidates = []
    for reference in references:
        score = _score(key, reference.strchave)
        if score < MINIMUM_SUGGESTION_SCORE:
            continue
        candidates.append(
            {
                "cargo_referencia_id": reference.pk,
                "descricao": f"Usar o cargo {reference.strnome}.",
                "alteracoes": {"strcargonormalizado": reference.strnome},
                "confianca": score,
            }
        )
    return sorted(
        candidates,
        key=lambda entry: (-entry["confianca"], entry["descricao"]),
    )[:MAX_SUGGESTIONS]


def _register_observation(importacao, key, items, fields):
    representative = items[0].strcargooriginal.strip()[:255]
    variation, _ = VariacaoCargoGlobal.objects.get_or_create(
        strchave=key,
        defaults={"strdescricao": representative, **fields},
    )
    locations = [
        {"aba": item.strabaorigem, "linha": item.intlinhaorigem}
        for item in items
    ]
    occurrence, occurrence_created = OcorrenciaCargoImportacao.objects.get_or_create(
        idvariacaocargo=variation,
        idimportacaoplanilha=importacao,
        defaults={
            "idpatriarca": importacao.idpatriarca,
            "intquantidade": len(items),
            "jsonlocalizacoes": locations,
            **fields,
        },
    )
    if not occurrence_created:
        occurrence.intquantidade = len(items)
        occurrence.jsonlocalizacoes = locations
        occurrence.updated_by_id = fields["updated_by_id"]
        occurrence.updated_by_name = fields["updated_by_name"]
        occurrence.save()
    _refresh_variation_statistics(variation)

    exact_reference = CargoReferenciaGlobal.objects.filter(
        strchave=key,
        strstatus=StatusCargoReferencia.CONFIRMADO,
        flgativo=True,
    ).first()
    if exact_reference and variation.idcargoreferencia_id is None:
        variation.idcargoreferencia = exact_reference
        variation.strstatus = StatusVariacaoCargo.CONFIRMADA
        variation.updated_by_id = fields["updated_by_id"]
        variation.updated_by_name = fields["updated_by_name"]
        variation.save()

    if variation.idcargoreferencia_id is None and len(representative) <= 100:
        observed_reference, _ = CargoReferenciaGlobal.objects.get_or_create(
            strchave=key,
            defaults={
                "strnome": representative,
                "strstatus": StatusCargoReferencia.NOVO,
                "strorigem": "IMPORTACAO",
                **fields,
            },
        )
        variation.idcargoreferencia = observed_reference
        variation.updated_by_id = fields["updated_by_id"]
        variation.updated_by_name = fields["updated_by_name"]
        variation.save()
    return variation, representative


def _apply_reference(items, variation, reference):
    for item in items:
        item.idvariacaocargo = variation
        item.idcargoreferencia = reference
        item.strcargonormalizado = reference.strnome
    ItemLotacaoImportado.objects.bulk_update(
        items,
        ["idvariacaocargo", "idcargoreferencia", "strcargonormalizado"],
    )


def _append_suggestion_issues(report, items, key, representative, suggestions):
    message = (
        f'O cargo "{representative}" é semelhante a cargo(s) já '
        "confirmado(s). Escolha a correspondência correta ou mantenha o "
        "valor informado."
    )
    status_updates = []
    for item in items:
        if item.strsituacao == StatusItemLotacaoImportado.ACEITO:
            item.strsituacao = StatusItemLotacaoImportado.COM_AVISOS
            status_updates.append(item)
        report.issues.append(
            LotacaoIssue(
                codigo="cargo_correspondencia_sugerida",
                mensagem=message,
                severidade="AVISO",
                aba=item.strabaorigem,
                linha=item.intlinhaorigem,
                campo="strcargonormalizado",
                valor_original=item.strcargooriginal,
                valor_normalizado=key,
                regra_aplicada=(
                    f"{CARGO_RULES_VERSION}: similaridade lexical e expansão "
                    "de abreviações"
                ),
                sugestoes=tuple(suggestions),
            )
        )
    if status_updates:
        ItemLotacaoImportado.objects.bulk_update(status_updates, ["strsituacao"])


def analyze_imported_positions(importacao, report, staged_items, audit_data) -> dict:
    """Registra todos os cargos e inclui críticas somente quando há decisão real."""
    fields = _audit_fields(audit_data)
    confirmed_references = list(
        CargoReferenciaGlobal.objects.filter(
            strstatus=StatusCargoReferencia.CONFIRMADO,
            flgativo=True,
        )
    )
    grouped = defaultdict(list)
    for item in staged_items.values():
        key = cargo_key(item.strcargooriginal)
        if key:
            grouped[key].append(item)

    summary = {
        "versao_regras": CARGO_RULES_VERSION,
        "total_descricoes_distintas": len(grouped),
        "total_correspondencias_confirmadas": 0,
        "total_descricoes_novas": 0,
        "total_descricoes_em_analise": 0,
    }
    for key, items in grouped.items():
        variation, representative = _register_observation(
            importacao,
            key,
            items,
            fields,
        )

        reference = _resolved_reference(importacao, variation)
        if reference is not None:
            summary["total_correspondencias_confirmadas"] += 1
            if (
                variation.idcargoreferencia_id == reference.pk
                and variation.strstatus != StatusVariacaoCargo.CONFIRMADA
            ):
                variation.strstatus = StatusVariacaoCargo.CONFIRMADA
                variation.updated_by_id = fields["updated_by_id"]
                variation.updated_by_name = fields["updated_by_name"]
                variation.save()
            _apply_reference(items, variation, reference)
            continue

        suggestions = _candidate_suggestions(key, confirmed_references)
        variation.strstatus = (
            StatusVariacaoCargo.EM_ANALISE
            if suggestions
            else StatusVariacaoCargo.NOVA
        )
        variation.updated_by_id = fields["updated_by_id"]
        variation.updated_by_name = fields["updated_by_name"]
        variation.save()
        for item in items:
            item.idvariacaocargo = variation
        ItemLotacaoImportado.objects.bulk_update(items, ["idvariacaocargo"])

        if not suggestions:
            summary["total_descricoes_novas"] += 1
            continue

        summary["total_descricoes_em_analise"] += 1
        _append_suggestion_issues(
            report,
            items,
            key,
            representative,
            suggestions,
        )
    report.cargo_summary = summary
    return summary


def learn_position_resolution(
    case,
    items,
    *,
    action,
    alternative,
    actor,
    scope=EscopoMapeamentoCargo.GLOBAL,
    remember=False,
) -> None:
    """Aplica o vínculo canônico e aprende apenas após decisão humana."""
    if case.strcodigo != "cargo_correspondencia_sugerida" or not items:
        return
    if action == AcaoResolucaoValidacao.APLICAR_SUGESTAO:
        reference = getattr(alternative, "idcargoreferencia", None)
        should_remember = reference is not None
    elif action in {
        AcaoResolucaoValidacao.ACEITAR_COMO_INFORMADO,
        AcaoResolucaoValidacao.CORRIGIR_MANUALMENTE,
    }:
        reference = None
        should_remember = remember
    else:
        return
    if reference is None and should_remember:
        normalized_name = items[0].strcargonormalizado.strip()
        key = cargo_key(normalized_name)
        if not key:
            return
        reference, _ = CargoReferenciaGlobal.objects.get_or_create(
            strchave=key,
            defaults={
                "strnome": normalized_name[:100],
                "strstatus": StatusCargoReferencia.CONFIRMADO,
                "strorigem": "REVISAO_IMPORTACAO",
                "created_by_id": actor.user_id,
                "created_by_name": actor.user_name,
                "updated_by_id": actor.user_id,
                "updated_by_name": actor.user_name,
            },
        )
    if reference is None:
        return
    if reference.strstatus != StatusCargoReferencia.CONFIRMADO:
        reference.strstatus = StatusCargoReferencia.CONFIRMADO
        reference.updated_by_id = actor.user_id
        reference.updated_by_name = actor.user_name
        reference.save()

    variations = {
        item.idvariacaocargo
        for item in items
        if item.idvariacaocargo_id is not None
    }
    for variation in variations:
        if scope == EscopoMapeamentoCargo.GLOBAL:
            variation.idcargoreferencia = reference
            variation.strstatus = StatusVariacaoCargo.CONFIRMADA
            variation.updated_by_id = actor.user_id
            variation.updated_by_name = actor.user_name
            variation.save()
        elif scope == EscopoMapeamentoCargo.PATRIARCA:
            mapping, mapping_created = MapeamentoCargoPatriarca.objects.get_or_create(
                idpatriarca=case.idrelatoriovalidacao.idimportacaoplanilha.idpatriarca,
                idvariacaocargo=variation,
                defaults={
                    "idcargoreferencia": reference,
                    "flgativo": True,
                    "updated_by_id": actor.user_id,
                    "updated_by_name": actor.user_name,
                    "created_by_id": actor.user_id,
                    "created_by_name": actor.user_name,
                },
            )
            if not mapping_created:
                mapping.idcargoreferencia = reference
                mapping.flgativo = True
                mapping.updated_by_id = actor.user_id
                mapping.updated_by_name = actor.user_name
                mapping.save()
        for item in items:
            if item.idvariacaocargo_id != variation.pk:
                continue
            item.idcargoreferencia = reference
            item.strcargonormalizado = reference.strnome
            item.updated_by_id = actor.user_id
            item.updated_by_name = actor.user_name
            item.save(
                update_fields=[
                    "idcargoreferencia",
                    "strcargonormalizado",
                    "updated_by_id",
                    "updated_by_name",
                    "updated_at",
                ]
            )
