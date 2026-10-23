"""Revisão auditável e incorporação dos itens de lotação importados."""

from __future__ import annotations

import re
import unicodedata

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from validate_docbr import CPF

from apps.carga_org_lot.models import (
    AcaoResolucaoValidacao,
    AlternativaResolucaoValidacao,
    CasoValidacaoImportacao,
    ImportacaoPlanilha,
    ItemLotacao,
    ItemLotacaoImportado,
    ItemOrganograma,
    ResolucaoValidacao,
    StatusCasoValidacao,
    StatusImportacaoLocal,
    StatusItemLotacaoImportado,
)
from apps.carga_org_lot.services.lotacao import normalize_cpf
from apps.carga_org_lot.services.cargos import learn_position_resolution
from apps.carga_org_lot.services.lotacao_sets import sync_lotation_set
from apps.carga_org_lot.services.workflow import AuditActor, register_lotation_import


EDITABLE_FIELDS = {
    "idorgaoorganograma_id",
    "idunidadeorganograma_id",
    "strsiglaorgao",
    "strnomeorgao",
    "strnomeservidor",
    "strcpf",
    "strcargooriginal",
    "strcargonormalizado",
    "strsiglaunidade",
    "strnomeunidade",
}
CPF_VALIDATOR = CPF()


def _valid_cpf(value) -> bool:
    cpf = normalize_cpf(value)
    return len(cpf) == 11 and CPF_VALIDATOR.validate(cpf)


def _comparison_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def _snapshot(items) -> list[dict]:
    return [
        {
            "iditemlotacaoimportado": item.pk,
            **{field: getattr(item, field) for field in sorted(EDITABLE_FIELDS)},
            "strsituacao": item.strsituacao,
        }
        for item in items
    ]


def _belongs_to_organ(organ_id: int, unit: ItemOrganograma) -> bool:
    if unit.pk == organ_id:
        return True
    current = unit
    visited = set()
    while current.idpai_id is not None and current.pk not in visited:
        if current.idpai_id == organ_id:
            return True
        visited.add(current.pk)
        current = ItemOrganograma.objects.only("iditemorganograma", "idpai_id").get(
            pk=current.idpai_id
        )
    return False


def _validate_organogram_references(importacao, item):
    if item.idorgaoorganograma_id is None or item.idunidadeorganograma_id is None:
        return False
    organ = item.idorgaoorganograma
    unit = item.idunidadeorganograma
    reference_id = importacao.idimportacaoorganograma_id
    if (
        organ.idimportacaoplanilha_id != reference_id
        or unit.idimportacaoplanilha_id != reference_id
    ):
        return False
    if organ.idpai_id is None:
        return False
    organ_parent = ItemOrganograma.objects.only("idpai_id").get(pk=organ.idpai_id)
    if organ_parent.idpai_id is not None:
        return False
    return _belongs_to_organ(organ.pk, unit)


def _validate_case_resolution(case, items):
    importacao = case.idrelatoriovalidacao.idimportacaoplanilha
    if case.strcodigo == "cpf_duplicado_planilha":
        cpfs = [normalize_cpf(item.strcpf) for item in items]
        if not all(_valid_cpf(cpf) for cpf in cpfs) or len(cpfs) != len(set(cpfs)):
            raise serializers.ValidationError(
                {
                    "alteracoes": (
                        "A correção deve manter CPFs válidos e eliminar a repetição "
                        "entre as linhas deste caso. Para manter as lotações, use "
                        "a ação de aceitar o aviso."
                    )
                }
            )
        return
    validators = {
        "cpf_digitos_verificadores_invalidos": lambda item: _valid_cpf(item.strcpf),
        "cpf_invalido": lambda item: _valid_cpf(item.strcpf),
        "cpf_ausente": lambda item: _valid_cpf(item.strcpf),
        "nome_servidor_ausente": lambda item: bool(item.strnomeservidor.strip()),
        "cargo_ausente": lambda item: bool(item.strcargonormalizado.strip()),
        "orgao_ausente": lambda item: _validate_organogram_references(
            importacao, item
        ),
        "orgao_invalido": lambda item: _validate_organogram_references(
            importacao, item
        ),
        "unidade_ausente": lambda item: _validate_organogram_references(
            importacao, item
        ),
        "unidade_invalida": lambda item: _validate_organogram_references(
            importacao, item
        ),
        "unidade_ambigua": lambda item: _validate_organogram_references(
            importacao, item
        ),
        "nome_orgao_divergente": lambda item: (
            item.idorgaoorganograma_id is not None
            and _comparison_key(item.strnomeorgao)
            == _comparison_key(item.idorgaoorganograma.strnome)
        ),
        "nome_unidade_divergente": lambda item: (
            item.idunidadeorganograma_id is not None
            and _comparison_key(item.strnomeunidade)
            == _comparison_key(item.idunidadeorganograma.strnome)
        ),
        "sigla_orgao_muito_longa": lambda item: len(item.strsiglaorgao) <= 20,
        "sigla_unidade_muito_longa": lambda item: len(item.strsiglaunidade) <= 25,
        "cargo_muito_longo": lambda item: len(item.strcargonormalizado) <= 100,
        "nome_orgao_muito_longo": lambda item: len(item.strnomeorgao) <= 500,
        "nome_servidor_muito_longo": lambda item: len(item.strnomeservidor) <= 255,
        "nome_unidade_muito_longo": lambda item: len(item.strnomeunidade) <= 500,
    }
    validator = validators.get(case.strcodigo)
    if validator is not None and not all(validator(item) for item in items):
        raise serializers.ValidationError(
            {"alteracoes": "A correção informada ainda não resolve esta crítica."}
        )


def _sync_organogram_references(item, changed_fields):
    try:
        if "idorgaoorganograma_id" in changed_fields:
            organ = ItemOrganograma.objects.get(pk=item.idorgaoorganograma_id)
            item.idorgaoorganograma = organ
            item.strsiglaorgao = organ.strsigla
            item.strnomeorgao = organ.strnome
        if "idunidadeorganograma_id" in changed_fields:
            unit = ItemOrganograma.objects.get(pk=item.idunidadeorganograma_id)
            item.idunidadeorganograma = unit
            item.strsiglaunidade = unit.strsigla
            item.strnomeunidade = unit.strnome
    except ItemOrganograma.DoesNotExist as exc:
        raise serializers.ValidationError(
            {"alteracoes": "O órgão ou a unidade informada não existe."}
        ) from exc


def _close_cases_for_discarded_items(case, actor, justification):
    importacao = case.idrelatoriovalidacao.idimportacaoplanilha
    related_case_ids = list(
        CasoValidacaoImportacao.objects.filter(
            idrelatoriovalidacao__idimportacaoplanilha=importacao,
            strstatus=StatusCasoValidacao.PENDENTE,
            itens__strsituacao=StatusItemLotacaoImportado.DESCARTADO,
        )
        .exclude(pk=case.pk)
        .values_list("pk", flat=True)
        .distinct()
    )
    related_cases = CasoValidacaoImportacao.objects.select_for_update().filter(
        pk__in=related_case_ids
    )
    for related in related_cases:
        related_items = list(related.itens.all())
        if any(
            item.strsituacao != StatusItemLotacaoImportado.DESCARTADO
            for item in related_items
        ):
            continue
        snapshot = _snapshot(related_items)
        related.strstatus = StatusCasoValidacao.LINHAS_DESCARTADAS
        related.datresolucao = timezone.now()
        related.updated_by_id = actor.user_id
        related.updated_by_name = actor.user_name
        related.save()
        ResolucaoValidacao.objects.create(
            idcasovalidacao=related,
            stracao=AcaoResolucaoValidacao.DESCARTAR_LINHAS,
            strjustificativa=(
                justification
                or "Linha descartada durante a resolução de outra crítica."
            ),
            jsonantes=snapshot,
            jsondepois=snapshot,
            created_by_id=actor.user_id,
            created_by_name=actor.user_name,
            updated_by_id=actor.user_id,
            updated_by_name=actor.user_name,
        )


def _update_item_states(importacao):
    items = importacao.itens_lotacao_importados.all()
    for item in items:
        if item.strsituacao == StatusItemLotacaoImportado.DESCARTADO:
            continue
        pending = item.casos_validacao.filter(
            strstatus=StatusCasoValidacao.PENDENTE
        )
        if pending.filter(strseveridade="ERRO").exists():
            status = StatusItemLotacaoImportado.COM_ERROS
        elif pending.filter(strseveridade="AVISO").exists():
            status = StatusItemLotacaoImportado.COM_AVISOS
        else:
            status = StatusItemLotacaoImportado.CORRIGIDO
        if item.strsituacao != status:
            item.strsituacao = status
            item.save(update_fields=["strsituacao", "updated_at"])

    pending_cases = importacao.relatorio_validacao.casos.filter(
        strstatus=StatusCasoValidacao.PENDENTE
    )
    if pending_cases.exists():
        importacao.strstatusimportacao = (
            StatusImportacaoLocal.AGUARDANDO_REVISAO_CARGOS
            if not pending_cases.exclude(
                strcodigo="cargo_correspondencia_sugerida"
            ).exists()
            else StatusImportacaoLocal.AGUARDANDO_REVISAO
        )
    elif importacao.itens_lotacao_importados.exclude(
        strsituacao=StatusItemLotacaoImportado.DESCARTADO
    ).exists():
        importacao.strstatusimportacao = StatusImportacaoLocal.PRONTA_PARA_INCORPORAR
    else:
        importacao.strstatusimportacao = StatusImportacaoLocal.SEM_REGISTROS_VALIDOS
    importacao.save(update_fields=["strstatusimportacao", "updated_at"])


@transaction.atomic
def resolve_validation_case(
    case: CasoValidacaoImportacao,
    *,
    action: str,
    actor: AuditActor,
    justification: str = "",
    alternative: AlternativaResolucaoValidacao | None = None,
    changes: list[dict] | None = None,
    position_scope: str = "GLOBAL",
    remember_position: bool = False,
) -> CasoValidacaoImportacao:
    case = CasoValidacaoImportacao.objects.select_for_update().get(pk=case.pk)
    if case.strstatus != StatusCasoValidacao.PENDENTE:
        raise serializers.ValidationError("Este caso já foi resolvido.")
    items = list(
        case.itens.select_related(
            "idorgaoorganograma",
            "idunidadeorganograma",
        ).all()
    )
    before = _snapshot(items)

    if action == AcaoResolucaoValidacao.ACEITAR_COMO_INFORMADO:
        if case.strseveridade != "AVISO":
            raise serializers.ValidationError(
                "Somente avisos podem ser aceitos sem correção."
            )
        new_status = StatusCasoValidacao.ACEITO_COMO_INFORMADO
    elif action == AcaoResolucaoValidacao.DESCARTAR_LINHAS:
        for item in items:
            item.strsituacao = StatusItemLotacaoImportado.DESCARTADO
            item.updated_by_id = actor.user_id
            item.updated_by_name = actor.user_name
            item.save()
        new_status = StatusCasoValidacao.LINHAS_DESCARTADAS
    else:
        if action == AcaoResolucaoValidacao.APLICAR_SUGESTAO:
            if alternative is None or alternative.idcasovalidacao_id != case.pk:
                raise serializers.ValidationError(
                    {"alternativa_id": "A alternativa não pertence a este caso."}
                )
            if alternative.stracao != AcaoResolucaoValidacao.APLICAR_SUGESTAO:
                raise serializers.ValidationError(
                    {"alternativa_id": "A alternativa não é uma sugestão aplicável."}
                )
            changes = [
                {"iditemlotacaoimportado": item.pk, "campos": alternative.jsonpayload}
                for item in items
            ]
            new_status = StatusCasoValidacao.SUGESTAO_APLICADA
        else:
            new_status = StatusCasoValidacao.CORRIGIDO
            if not changes:
                raise serializers.ValidationError(
                    {"alteracoes": "Informe ao menos uma correção manual."}
                )
        valid_item_ids = {item.pk for item in items}
        informed_ids = [
            entry["iditemlotacaoimportado"] for entry in (changes or [])
        ]
        invalid_ids = set(informed_ids) - valid_item_ids
        if invalid_ids:
            raise serializers.ValidationError(
                {
                    "alteracoes": (
                        "Há linhas que não pertencem a este caso: "
                        f"{', '.join(str(value) for value in sorted(invalid_ids))}."
                    )
                }
            )
        if len(informed_ids) != len(set(informed_ids)):
            raise serializers.ValidationError(
                {"alteracoes": "Cada linha deve aparecer somente uma vez."}
            )
        change_map = {
            entry["iditemlotacaoimportado"]: entry.get("campos", {})
            for entry in (changes or [])
        }
        for item in items:
            fields = dict(change_map.get(item.pk, {}))
            unknown = set(fields) - EDITABLE_FIELDS
            if unknown:
                field_names = ", ".join(sorted(unknown))
                raise serializers.ValidationError(
                    {"alteracoes": f"Campos não permitidos: {field_names}."}
                )
            if "strcpf" in fields:
                fields["strcpf"] = normalize_cpf(fields["strcpf"])
            for field, value in fields.items():
                setattr(item, field, value)
            _sync_organogram_references(item, fields)
            item.updated_by_id = actor.user_id
            item.updated_by_name = actor.user_name
            item.save()
        items = list(
            case.itens.select_related(
                "idorgaoorganograma",
                "idunidadeorganograma",
            ).all()
        )
        _validate_case_resolution(case, items)

    learn_position_resolution(
        case,
        items,
        action=action,
        alternative=alternative,
        actor=actor,
        scope=position_scope,
        remember=remember_position,
    )
    items = list(case.itens.all())
    case.strstatus = new_status
    case.datresolucao = timezone.now()
    case.updated_by_id = actor.user_id
    case.updated_by_name = actor.user_name
    case.save()
    ResolucaoValidacao.objects.create(
        idcasovalidacao=case,
        idalternativaresolucao=alternative,
        stracao=action,
        strjustificativa=justification,
        jsonantes=before,
        jsondepois=_snapshot(items),
        created_by_id=actor.user_id,
        created_by_name=actor.user_name,
        updated_by_id=actor.user_id,
        updated_by_name=actor.user_name,
    )
    if action == AcaoResolucaoValidacao.DESCARTAR_LINHAS:
        _close_cases_for_discarded_items(case, actor, justification)
    importacao = case.idrelatoriovalidacao.idimportacaoplanilha
    _update_item_states(importacao)
    if importacao.idconjuntolotacao_id:
        sync_lotation_set(importacao.idconjuntolotacao, actor=actor)
    return case


@transaction.atomic
def incorporate_lotation(importacao: ImportacaoPlanilha, actor: AuditActor) -> int:
    importacao = ImportacaoPlanilha.objects.select_for_update().get(pk=importacao.pk)
    if importacao.strstatusimportacao != StatusImportacaoLocal.PRONTA_PARA_INCORPORAR:
        raise serializers.ValidationError(
            "A importação ainda não está pronta para incorporação."
        )
    source_items = list(
        importacao.itens_lotacao_importados.exclude(
            strsituacao=StatusItemLotacaoImportado.DESCARTADO
        ).select_related("idorgaoorganograma", "idunidadeorganograma")
    )
    if not source_items:
        raise serializers.ValidationError(
            "Não existem registros aceitos para incorporar."
        )
    for item in source_items:
        normalized_cpf = normalize_cpf(item.strcpf)
        if item.strcpf != normalized_cpf:
            item.strcpf = normalized_cpf
            item.updated_by_id = actor.user_id
            item.updated_by_name = actor.user_name
            item.save(
                update_fields=[
                    "strcpf",
                    "updated_by_id",
                    "updated_by_name",
                    "updated_at",
                ]
            )
        if not all(
            (
                item.idorgaoorganograma_id,
                item.idunidadeorganograma_id,
                item.strnomeservidor.strip(),
                _valid_cpf(item.strcpf),
                item.strcargonormalizado.strip(),
            )
        ):
            raise serializers.ValidationError(
                "Existem linhas que ainda não possuem os dados obrigatórios válidos."
            )
        if not _validate_organogram_references(importacao, item):
            raise serializers.ValidationError(
                "Existem linhas vinculadas a órgão ou unidade incompatível com "
                "o organograma de referência."
            )

    importacao.strstatusimportacao = StatusImportacaoLocal.INCORPORANDO
    importacao.save(update_fields=["strstatusimportacao", "updated_at"])
    candidates = [
        ItemLotacao(
            iditemlotacaoimportado=item,
            idimportacaoplanilha=importacao,
            idorgaoorganograma=item.idorgaoorganograma,
            idunidadeorganograma=item.idunidadeorganograma,
            idcargoreferencia=item.idcargoreferencia,
            strsiglaorgao=item.strsiglaorgao,
            strnomeorgao=item.strnomeorgao,
            strnomeservidor=item.strnomeservidor,
            strcpf=item.strcpf,
            strcargooriginal=item.strcargooriginal,
            strcargonormalizado=item.strcargonormalizado,
            strsiglaunidade=item.strsiglaunidade,
            strnomeunidade=item.strnomeunidade,
            strabaorigem=item.strabaorigem,
            intlinhaorigem=item.intlinhaorigem,
            created_by_id=actor.user_id,
            created_by_name=actor.user_name,
            updated_by_id=actor.user_id,
            updated_by_name=actor.user_name,
        )
        for item in source_items
    ]
    for source, candidate in zip(source_items, candidates, strict=True):
        try:
            candidate.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {
                    "itens_lotacao": {
                        "iditemlotacaoimportado": source.pk,
                        "aba": source.strabaorigem,
                        "linha": source.intlinhaorigem,
                        "campos": exc.message_dict,
                    }
                }
            ) from exc
    created = ItemLotacao.objects.bulk_create(candidates)
    ItemLotacaoImportado.objects.filter(
        pk__in=[item.pk for item in source_items]
    ).update(strsituacao=StatusItemLotacaoImportado.INCORPORADO)
    importacao.strstatusimportacao = StatusImportacaoLocal.INCORPORADA
    importacao.save(update_fields=["strstatusimportacao", "updated_at"])
    if importacao.idprocessocargainicial_id:
        register_lotation_import(
            importacao.idprocessocargainicial,
            valid=True,
            actor=actor,
        )
    if importacao.idconjuntolotacao_id:
        sync_lotation_set(importacao.idconjuntolotacao, actor=actor)
    return len(created)
