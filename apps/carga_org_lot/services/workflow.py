"""Transições do processo local de preparação da carga inicial."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.carga_org_lot.models import (
    EnvioOrganogramaProdest,
    FaseProcessoCargaInicial,
    HistoricoProcessoCargaInicial,
    ImportacaoPlanilha,
    ProcessoCargaInicial,
    StatusLotacaoProcesso,
    StatusImportacaoLocal,
    StatusOrganogramaProcesso,
)


@dataclass(frozen=True)
class AuditActor:
    user_id: int | None = None
    user_name: str = ""

    @classmethod
    def from_validated_data(cls, data: dict) -> "AuditActor":
        return cls(
            user_id=data.get("created_by_id") or data.get("updated_by_id"),
            user_name=data.get("created_by_name") or data.get("updated_by_name", ""),
        )


def get_or_create_active_process(patriarca, actor: AuditActor) -> ProcessoCargaInicial:
    process, created = ProcessoCargaInicial.objects.get_or_create(
        idpatriarca=patriarca,
        flgativo=True,
        defaults={
            "created_by_id": actor.user_id,
            "created_by_name": actor.user_name,
            "updated_by_id": actor.user_id,
            "updated_by_name": actor.user_name,
        },
    )
    if created:
        _record_history(
            process,
            actor,
            action="PROCESSO_CRIADO",
            previous=("", "", ""),
            message="Processo de carga inicial criado com o Patriarca.",
        )
    return process


@transaction.atomic
def register_organogram_import(
    process: ProcessoCargaInicial,
    *,
    valid: bool,
    actor: AuditActor,
    message: str = "",
) -> ProcessoCargaInicial:
    process = ProcessoCargaInicial.objects.select_for_update().get(pk=process.pk)
    previous = _snapshot(process)
    had_lotation = process.strstatuslotacao not in {
        StatusLotacaoProcesso.BLOQUEADA,
        StatusLotacaoProcesso.NAO_INICIADA,
    }
    process.strfaseatual = FaseProcessoCargaInicial.PREPARANDO_ORGANOGRAMA
    process.strstatusorganograma = (
        StatusOrganogramaProcesso.EM_PREPARACAO
        if valid
        else StatusOrganogramaProcesso.COM_PENDENCIAS
    )
    if had_lotation:
        process.strstatuslotacao = StatusLotacaoProcesso.DESATUALIZADA
    process.updated_by_id = actor.user_id
    process.updated_by_name = actor.user_name
    process.save()
    _record_history(
        process,
        actor,
        action=("ORGANOGRAMA_IMPORTADO" if valid else "ORGANOGRAMA_REJEITADO"),
        previous=previous,
        message=message,
    )
    return process


@transaction.atomic
def register_lotation_import(
    process: ProcessoCargaInicial,
    *,
    valid: bool,
    actor: AuditActor,
    pending_review: bool = False,
) -> ProcessoCargaInicial:
    process = ProcessoCargaInicial.objects.select_for_update().get(pk=process.pk)
    previous = _snapshot(process)
    process.strfaseatual = FaseProcessoCargaInicial.PREPARANDO_LOTACOES
    process.strstatusorganograma = StatusOrganogramaProcesso.PRONTO
    process.strstatuslotacao = (
        StatusLotacaoProcesso.EM_PREPARACAO
        if valid
        else StatusLotacaoProcesso.COM_PENDENCIAS
    )
    process.updated_by_id = actor.user_id
    process.updated_by_name = actor.user_name
    process.save()
    _record_history(
        process,
        actor,
        action=(
            "LOTACAO_IMPORTADA"
            if valid
            else (
                "LOTACAO_AGUARDANDO_REVISAO"
                if pending_review
                else "LOTACAO_REJEITADA"
            )
        ),
        previous=previous,
        message=(
            "Importação de lotação incorporada ao processo em preparação."
            if valid
            else (
                "Importação de lotação aguardando revisão das críticas."
                if pending_review
                else "Importação de lotação rejeitada pela validação."
            )
        ),
    )
    return process


@transaction.atomic
def register_organogram_item_change(
    importacao: ImportacaoPlanilha,
    *,
    actor: AuditActor,
    action: str,
    message: str,
    details: dict,
) -> ProcessoCargaInicial:
    importacao = ImportacaoPlanilha.objects.select_for_update().get(pk=importacao.pk)
    process = (
        ProcessoCargaInicial.objects.get(pk=importacao.idprocessocargainicial_id)
        if importacao.idprocessocargainicial_id is not None
        else None
    )
    if process is None:
        process = get_or_create_active_process(importacao.idpatriarca, actor)
        importacao.idprocessocargainicial = process

    now = timezone.now()
    if importacao.datprimeiraalteracao is None:
        importacao.datprimeiraalteracao = now
    importacao.datultimaalteracao = now
    importacao.flgpossuialteracoes = True
    importacao.strstatusimportacao = StatusImportacaoLocal.ALTERADA
    importacao.updated_by_id = actor.user_id
    importacao.updated_by_name = actor.user_name
    importacao.save()

    process = ProcessoCargaInicial.objects.select_for_update().get(pk=process.pk)
    previous = _snapshot(process)
    process.strfaseatual = FaseProcessoCargaInicial.PREPARANDO_ORGANOGRAMA
    process.strstatusorganograma = StatusOrganogramaProcesso.EM_PREPARACAO
    possui_lotacao = importacao.importacoes_lotacao.exists() or (
        process.strstatuslotacao
        not in {
            StatusLotacaoProcesso.BLOQUEADA,
            StatusLotacaoProcesso.NAO_INICIADA,
        }
    )
    if possui_lotacao:
        process.strstatuslotacao = StatusLotacaoProcesso.DESATUALIZADA
    process.updated_by_id = actor.user_id
    process.updated_by_name = actor.user_name
    process.save()
    _record_history(
        process,
        actor,
        action=action,
        previous=previous,
        message=message,
        details=details,
    )
    latest_completed = (
        EnvioOrganogramaProdest.objects.filter(
            idimportacaoplanilha=importacao,
            strstatus="CONCLUIDO",
        )
        .order_by("-datsolicitacao", "-pk")
        .first()
    )
    if latest_completed:
        latest_completed.strstatus = "CONCLUIDO_DESATUALIZADO"
        latest_completed.save(update_fields=["strstatus", "updated_at"])
        from .integration_events import record_operational_event

        record_operational_event(
            latest_completed,
            code="ORIGEM_LOCAL_DESATUALIZADA",
            phase="CONCLUSAO",
            status="AVISO",
            title="Organograma local alterado",
            message=(
                "O organograma foi alterado depois do envio. "
                "Será necessária uma nova tentativa para atualizar a PRODEST."
            ),
            actor=actor,
            details=details,
        )
    return process


@transaction.atomic
def register_organogram_submission(
    envio: EnvioOrganogramaProdest,
    *,
    actor: AuditActor,
) -> ProcessoCargaInicial:
    process = ProcessoCargaInicial.objects.select_for_update().get(
        pk=envio.idprocessocargainicial_id
    )
    previous = _snapshot(process)
    process.strfaseatual = (
        FaseProcessoCargaInicial.SIMULANDO
        if envio.flgdryrun
        else FaseProcessoCargaInicial.ENVIANDO
    )
    process.strstatusorganograma = StatusOrganogramaProcesso.PROCESSANDO_NA_PRODEST
    process.updated_by_id = actor.user_id
    process.updated_by_name = actor.user_name
    process.save()
    _record_history(
        process,
        actor,
        action=(
            "ORGANOGRAMA_SIMULACAO_SOLICITADA"
            if envio.flgdryrun
            else "ORGANOGRAMA_ENVIO_SOLICITADO"
        ),
        previous=previous,
        message=(
            "Simulação do organograma solicitada à PRODEST."
            if envio.flgdryrun
            else "Envio definitivo do organograma solicitado à PRODEST."
        ),
        details={
            "idenvioorganograma": envio.pk,
            "idimportacaoplanilha": envio.idimportacaoplanilha_id,
            "dry_run": envio.flgdryrun,
        },
    )
    return process


@transaction.atomic
def register_organogram_result(
    envio: EnvioOrganogramaProdest,
    *,
    success: bool,
    source_changed: bool = False,
    actor: AuditActor,
) -> ProcessoCargaInicial:
    process = ProcessoCargaInicial.objects.select_for_update().get(
        pk=envio.idprocessocargainicial_id
    )
    latest_id = (
        EnvioOrganogramaProdest.objects.filter(
            idprocessocargainicial=process,
        )
        .order_by("-datsolicitacao", "-idenvioorganograma")
        .values_list("pk", flat=True)
        .first()
    )
    if latest_id != envio.pk:
        return process

    previous = _snapshot(process)
    if source_changed:
        pass
    elif success and envio.flgdryrun:
        process.strfaseatual = FaseProcessoCargaInicial.PRONTO_PARA_ENVIO
        process.strstatusorganograma = StatusOrganogramaProcesso.PRONTO
    elif success:
        process.strfaseatual = FaseProcessoCargaInicial.PREPARANDO_LOTACOES
        process.strstatusorganograma = StatusOrganogramaProcesso.CONCLUIDO
        if process.strstatuslotacao == StatusLotacaoProcesso.BLOQUEADA:
            process.strstatuslotacao = StatusLotacaoProcesso.NAO_INICIADA
    else:
        process.strfaseatual = FaseProcessoCargaInicial.PREPARANDO_ORGANOGRAMA
        process.strstatusorganograma = StatusOrganogramaProcesso.ERRO
    process.updated_by_id = actor.user_id
    process.updated_by_name = actor.user_name
    process.save()
    _record_history(
        process,
        actor,
        action=_organogram_result_action(
            envio.flgdryrun,
            success,
            source_changed,
        ),
        previous=previous,
        message=_organogram_result_message(
            envio.flgdryrun,
            success,
            source_changed,
        ),
        details={
            "idenvioorganograma": envio.pk,
            "idimportacaoplanilha": envio.idimportacaoplanilha_id,
            "carga_id": str(envio.idexternocarga or ""),
            "dry_run": envio.flgdryrun,
            "origem_alterada": source_changed,
        },
    )
    return process


def _organogram_result_action(
    dry_run: bool,
    success: bool,
    source_changed: bool,
) -> str:
    prefix = "ORGANOGRAMA_SIMULACAO" if dry_run else "ORGANOGRAMA_ENVIO"
    if source_changed:
        return f"{prefix}_CONCLUIDA_ORIGEM_ALTERADA"
    return f"{prefix}_{'CONCLUIDA' if success else 'ERRO'}"


def _organogram_result_message(
    dry_run: bool,
    success: bool,
    source_changed: bool,
) -> str:
    operation = "Simulação" if dry_run else "Envio definitivo"
    if source_changed:
        completion = "concluída" if dry_run else "concluído"
        return (
            f"{operation} {completion} na PRODEST, mas o organograma local foi "
            "alterado depois da solicitação. É necessário realizar nova tentativa."
        )
    if dry_run:
        result = "concluída com sucesso" if success else "encerrada com erro"
    else:
        result = "concluído com sucesso" if success else "encerrado com erro"
    return f"{operation} do organograma {result} na PRODEST."


def _snapshot(process: ProcessoCargaInicial) -> tuple[str, str, str]:
    return (
        process.strfaseatual,
        process.strstatusorganograma,
        process.strstatuslotacao,
    )


def _record_history(
    process: ProcessoCargaInicial,
    actor: AuditActor,
    *,
    action: str,
    previous: tuple[str, str, str],
    message: str,
    details: dict | None = None,
) -> HistoricoProcessoCargaInicial:
    return HistoricoProcessoCargaInicial.objects.create(
        idprocessocargainicial=process,
        stracao=action,
        strfaseanterior=previous[0],
        strfasenova=process.strfaseatual,
        strstatusorganogramaanterior=previous[1],
        strstatusorganogramanovo=process.strstatusorganograma,
        strstatuslotacaoanterior=previous[2],
        strstatuslotacaonovo=process.strstatuslotacao,
        strmensagem=message,
        jsondetalhes=details or {},
        created_by_id=actor.user_id,
        created_by_name=actor.user_name,
        updated_by_id=actor.user_id,
        updated_by_name=actor.user_name,
    )
