"""Preparação, envio e acompanhamento do organograma na PRODEST."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.carga_org_lot.models import (
    EnvioOrganogramaProdest,
    FaseIntegracaoProdest,
    ImportacaoPlanilha,
    ResultadoRelatorioValidacao,
    StatusEnvioOrganograma,
    StatusEventoOperacional,
    StatusImportacaoLocal,
)

from .cargarh import (
    CargaRHClient,
    CargaRHConfigurationError,
    CargaRHRequestError,
)
from .organograma import ORGANOGRAMA_TYPE_ID
from .integration_events import record_operational_event
from .workflow import (
    AuditActor,
    get_or_create_active_process,
    register_organogram_result,
    register_organogram_submission,
)


logger = logging.getLogger(__name__)


class OrganogramSubmissionError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        envio=None,
        details=None,
        kind="validation",
    ):
        super().__init__(message)
        self.envio = envio
        self.details = details or {}
        self.kind = kind


def build_organogram_payload(importacao: ImportacaoPlanilha) -> dict:
    if importacao.idtipocarga_id != ORGANOGRAMA_TYPE_ID:
        raise OrganogramSubmissionError(
            "A importação selecionada não é de organograma."
        )
    if importacao.strstatusimportacao in {
        StatusImportacaoLocal.REJEITADA,
        StatusImportacaoLocal.ERRO_PROCESSAMENTO,
    }:
        raise OrganogramSubmissionError(
            "Uma importação rejeitada ou com erro não pode ser enviada."
        )
    report = getattr(importacao, "relatorio_validacao", None)
    if report is None or report.strresultado != ResultadoRelatorioValidacao.VALIDO:
        raise OrganogramSubmissionError(
            "A importação precisa possuir uma validação local concluída com sucesso."
        )

    items = list(importacao.itens_organograma.all())
    roots = [item for item in items if item.idpai_id is None]
    if len(roots) != 1:
        raise OrganogramSubmissionError(
            "O organograma deve possuir exatamente uma raiz antes do envio."
        )
    root = roots[0]
    by_id = {item.pk: item for item in items}
    organs = sorted(
        (item for item in items if item.idpai_id == root.pk),
        key=_item_order,
    )
    if not organs:
        raise OrganogramSubmissionError(
            "O organograma deve possuir ao menos um órgão antes do envio."
        )

    units_by_organ = {organ.pk: [] for organ in organs}
    for item in items:
        if item.pk == root.pk or item.idpai_id == root.pk:
            continue
        organ_id = _owning_organ_id(item, by_id, root.pk)
        if organ_id not in units_by_organ:
            raise OrganogramSubmissionError(
                "Há uma unidade fora da hierarquia de um órgão."
            )
        units_by_organ[organ_id].append(item)

    payload_organs = []
    for organ in organs:
        units = sorted(units_by_organ[organ.pk], key=_item_order)
        payload_organs.append(
            {
                "nome": organ.strnome,
                "sigla": organ.strsigla,
                "unidades": [
                    {
                        "nome": unit.strnome,
                        "sigla": unit.strsigla,
                        "unidadePai": (
                            None
                            if unit.idpai_id == organ.pk
                            else by_id[unit.idpai_id].strsigla
                        ),
                    }
                    for unit in units
                ],
            }
        )
    return {
        "patriarcaId": str(importacao.idpatriarca.idexternopatriarca),
        "orgaos": payload_organs,
    }


def submit_organogram(
    importacao: ImportacaoPlanilha,
    *,
    dry_run: bool,
    actor: AuditActor,
    client=None,
) -> EnvioOrganogramaProdest:
    envio = prepare_organogram_submission(
        importacao,
        dry_run=dry_run,
        actor=actor,
    )
    return execute_organogram_submission(envio, actor=actor, client=client)


def prepare_organogram_submission(
    importacao: ImportacaoPlanilha,
    *,
    dry_run: bool,
    actor: AuditActor,
) -> EnvioOrganogramaProdest:
    payload = build_organogram_payload(importacao)
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    process = importacao.idprocessocargainicial
    if process is None:
        process = get_or_create_active_process(importacao.idpatriarca, actor)
        importacao.idprocessocargainicial = process
        importacao.save(update_fields=["idprocessocargainicial"])

    with transaction.atomic():
        envio = EnvioOrganogramaProdest.objects.create(
            idimportacaoplanilha=importacao,
            idprocessocargainicial=process,
            flgdryrun=dry_run,
            strambiente=settings.CARGARH_ENVIRONMENT,
            strstatus=StatusEnvioOrganograma.SOLICITANDO,
            jsonpayloadenviado=payload,
            strhashpayload=hashlib.sha256(
                canonical_payload.encode("utf-8")
            ).hexdigest(),
            created_by_id=actor.user_id,
            created_by_name=actor.user_name,
            updated_by_id=actor.user_id,
            updated_by_name=actor.user_name,
        )
        register_organogram_submission(envio, actor=actor)

    record_operational_event(
        envio,
        code="SOLICITACAO_RECEBIDA",
        phase=FaseIntegracaoProdest.PREPARACAO,
        status=StatusEventoOperacional.AGUARDANDO,
        title="Solicitação recebida",
        message="O envio foi incluído na fila de processamento.",
        actor=actor,
        deduplicate=False,
    )
    record_operational_event(
        envio,
        code="PAYLOAD_PREPARADO",
        phase=FaseIntegracaoProdest.PREPARACAO,
        status=StatusEventoOperacional.SUCESSO,
        title="Organograma preparado",
        message="O organograma foi validado e preparado para envio.",
        actor=actor,
        details={"quantidade_orgaos": len(payload.get("orgaos", []))},
        deduplicate=False,
    )
    return envio


def execute_organogram_submission(
    envio: EnvioOrganogramaProdest,
    *,
    actor: AuditActor,
    client=None,
) -> EnvioOrganogramaProdest:
    importacao = envio.idimportacaoplanilha
    process = envio.idprocessocargainicial
    payload = envio.jsonpayloadenviado
    record_operational_event(
        envio,
        code="AUTENTICACAO_INICIADA",
        phase=FaseIntegracaoProdest.AUTENTICACAO,
        status=StatusEventoOperacional.EM_ANDAMENTO,
        title="Validando acesso à PRODEST",
        message="O backend está validando a comunicação segura com a PRODEST.",
        actor=actor,
    )

    cargarh = client or CargaRHClient(
        patriarch_id=importacao.idpatriarca_id,
        process_id=process.pk,
        submission_id=envio.pk,
        actor=actor,
    )
    try:
        carga_id = cargarh.submit_organogram(
                importacao.idpatriarca.idexternopatriarca,
                payload,
                dry_run=envio.flgdryrun,
        )
    except (CargaRHConfigurationError, CargaRHRequestError) as exc:
        details = getattr(exc, "details", {})
        _mark_submission_error(
            envio,
            str(exc),
            actor,
            details=details,
            status_code=getattr(exc, "status_code", None),
        )
        record_operational_event(
            envio,
            code=(
                "AUTENTICACAO_REJEITADA"
                if getattr(exc, "status_code", None) in {401, 403}
                else "ENVIO_REJEITADO"
            ),
            phase=(
                FaseIntegracaoProdest.AUTENTICACAO
                if getattr(exc, "status_code", None) in {401, 403}
                else FaseIntegracaoProdest.ENVIO
            ),
            status=StatusEventoOperacional.ERRO,
            title="Não foi possível enviar o organograma",
            message=(
                "Nenhuma carga remota foi confirmada. " + str(exc)
            ),
            actor=actor,
            details={"http_status": getattr(exc, "status_code", None)},
        )
        raise OrganogramSubmissionError(
            str(exc),
            envio=envio,
            details=details,
            kind=(
                "configuration"
                if isinstance(exc, CargaRHConfigurationError)
                else "upstream"
            ),
        ) from exc

    envio.idexternocarga = carga_id
    envio.strstatus = StatusEnvioOrganograma.PROCESSANDO
    envio.strmensagemerro = ""
    now = timezone.now()
    envio.datiniciomonitoramento = now
    envio.datproximaconsulta = now + timedelta(
        seconds=settings.CARGA_ORG_LOT_MONITOR_INTERVAL_SECONDS
    )
    envio.updated_by_id = actor.user_id
    envio.updated_by_name = actor.user_name
    envio.save()
    record_operational_event(
        envio,
        code="CARGA_REMOTA_CRIADA",
        phase=FaseIntegracaoProdest.PROCESSAMENTO,
        status=StatusEventoOperacional.EM_ANDAMENTO,
        title="Carga recebida pela PRODEST",
        message="A PRODEST recebeu o organograma e iniciou o processamento.",
        actor=actor,
        details={"idexternocarga": str(carga_id)},
    )
    return envio


def refresh_submission_status(
    envio: EnvioOrganogramaProdest,
    *,
    actor: AuditActor,
    client=None,
) -> EnvioOrganogramaProdest:
    if envio.idexternocarga is None:
        raise OrganogramSubmissionError(
            "Esta tentativa não possui um identificador de carga da PRODEST.",
            envio=envio,
        )
    cargarh = client or CargaRHClient(
        patriarch_id=envio.idimportacaoplanilha.idpatriarca_id,
        process_id=envio.idprocessocargainicial_id,
        submission_id=envio.pk,
        external_load_id=envio.idexternocarga,
        actor=actor,
    )
    try:
        remote_status = cargarh.get_status(envio.idexternocarga)
    except (CargaRHConfigurationError, CargaRHRequestError) as exc:
        envio.strmensagemerro = str(exc)
        envio.datultimaconsulta = timezone.now()
        envio.updated_by_id = actor.user_id
        envio.updated_by_name = actor.user_name
        envio.save()
        raise OrganogramSubmissionError(
            str(exc),
            envio=envio,
            details=getattr(exc, "details", {}),
            kind=(
                "configuration"
                if isinstance(exc, CargaRHConfigurationError)
                else "upstream"
            ),
        ) from exc

    previous_status = envio.strstatus
    previous_remote_status = envio.jsonstatusprodest
    envio.jsonstatusprodest = remote_status
    envio.datultimaconsulta = timezone.now()
    envio.strmensagemerro = ""
    if remote_status.get("finalizada"):
        success = not _remote_status_has_error(remote_status)
        source_changed = success and _source_changed_since_submission(envio)
        if source_changed:
            envio.strstatus = StatusEnvioOrganograma.CONCLUIDO_DESATUALIZADO
        else:
            envio.strstatus = (
                StatusEnvioOrganograma.CONCLUIDO
                if success
                else StatusEnvioOrganograma.ERRO
            )
        envio.datfinalizacao = timezone.now()
        envio.datfimmonitoramento = envio.datfinalizacao
        envio.datproximaconsulta = None
        if source_changed:
            envio.strmensagemerro = (
                "A PRODEST concluiu a carga, mas o organograma local foi "
                "alterado após a solicitação. Realize uma nova tentativa."
            )
        elif not success:
            envio.strmensagemerro = _remote_error_message(remote_status)
    else:
        success = False
        source_changed = False
        envio.strstatus = StatusEnvioOrganograma.PROCESSANDO
        envio.datproximaconsulta = timezone.now() + timedelta(
            seconds=settings.CARGA_ORG_LOT_MONITOR_INTERVAL_SECONDS
        )
    envio.updated_by_id = actor.user_id
    envio.updated_by_name = actor.user_name
    envio.save()

    if remote_status != previous_remote_status:
        record_operational_event(
            envio,
            code=(
                "PROCESSAMENTO_CONCLUIDO"
                if remote_status.get("finalizada") and success
                else "PROCESSAMENTO_COM_ERRO"
                if remote_status.get("finalizada")
                else "ETAPA_PRODEST_ATUALIZADA"
            ),
            phase=(
                FaseIntegracaoProdest.RELATORIO
                if remote_status.get("finalizada") and success
                else FaseIntegracaoProdest.CONCLUSAO
                if remote_status.get("finalizada")
                else FaseIntegracaoProdest.PROCESSAMENTO
            ),
            status=(
                StatusEventoOperacional.SUCESSO
                if remote_status.get("finalizada") and success
                else StatusEventoOperacional.ERRO
                if remote_status.get("finalizada")
                else StatusEventoOperacional.EM_ANDAMENTO
            ),
            title=(
                "Processamento concluído"
                if remote_status.get("finalizada") and success
                else "Processamento encerrado com erro"
                if remote_status.get("finalizada")
                else "Etapa da PRODEST atualizada"
            ),
            message=(
                "A PRODEST concluiu o processamento do organograma."
                if remote_status.get("finalizada") and success
                else envio.strmensagemerro
                if remote_status.get("finalizada")
                else "A PRODEST atualizou a etapa de processamento da carga."
            ),
            actor=actor,
            details={"etapas": remote_status.get("etapas", [])},
        )

    if remote_status.get("finalizada") and not envio.jsonrelatorioprodest:
        try:
            envio.jsonrelatorioprodest = cargarh.get_report(
                envio.idexternocarga
            )
            envio.save(update_fields=["jsonrelatorioprodest", "updated_at"])
            record_operational_event(
                envio,
                code="RELATORIO_DISPONIVEL",
                phase=FaseIntegracaoProdest.CONCLUSAO,
                status=StatusEventoOperacional.SUCESSO,
                title="Relatório disponível",
                message="O relatório final da PRODEST está disponível.",
                actor=actor,
            )
        except (CargaRHConfigurationError, CargaRHRequestError) as exc:
            # O status confirmado não deve ser perdido caso o relatório ainda
            # esteja sendo consolidado. O endpoint explícito permite tentar de
            # novo sem reenviar a carga.
            logger.info(
                "CARGARH_REPORT_NOT_READY envio=%s type=%s",
                envio.pk,
                type(exc).__name__,
            )

    if remote_status.get("finalizada") and previous_status != envio.strstatus:
        register_organogram_result(
            envio,
            success=success,
            source_changed=source_changed,
            actor=actor,
        )
    return envio


def refresh_submission_report(
    envio: EnvioOrganogramaProdest,
    *,
    actor: AuditActor,
    client=None,
) -> EnvioOrganogramaProdest:
    if envio.idexternocarga is None:
        raise OrganogramSubmissionError(
            "Esta tentativa não possui um identificador de carga da PRODEST.",
            envio=envio,
        )
    cargarh = client or CargaRHClient(
        patriarch_id=envio.idimportacaoplanilha.idpatriarca_id,
        process_id=envio.idprocessocargainicial_id,
        submission_id=envio.pk,
        external_load_id=envio.idexternocarga,
        actor=actor,
    )
    try:
        report = cargarh.get_report(envio.idexternocarga)
    except (CargaRHConfigurationError, CargaRHRequestError) as exc:
        raise OrganogramSubmissionError(
            str(exc),
            envio=envio,
            details=getattr(exc, "details", {}),
            kind=(
                "configuration"
                if isinstance(exc, CargaRHConfigurationError)
                else "upstream"
            ),
        ) from exc
    envio.jsonrelatorioprodest = report
    envio.datultimaconsulta = timezone.now()
    envio.updated_by_id = actor.user_id
    envio.updated_by_name = actor.user_name
    envio.save()
    record_operational_event(
        envio,
        code="RELATORIO_DISPONIVEL",
        phase=FaseIntegracaoProdest.CONCLUSAO,
        status=StatusEventoOperacional.SUCESSO,
        title="Relatório disponível",
        message="O relatório final da PRODEST está disponível.",
        actor=actor,
    )
    return envio


def _mark_submission_error(
    envio,
    message,
    actor,
    *,
    details=None,
    status_code=None,
):
    envio.strstatus = StatusEnvioOrganograma.ERRO
    envio.strmensagemerro = message
    envio.jsonstatusprodest = {
        "falha_solicitacao": {
            "http_status": status_code,
            "problem": details or {},
        }
    }
    envio.datfinalizacao = timezone.now()
    envio.updated_by_id = actor.user_id
    envio.updated_by_name = actor.user_name
    envio.save()
    register_organogram_result(envio, success=False, actor=actor)


def _owning_organ_id(item, by_id, root_id):
    parent = by_id.get(item.idpai_id)
    visited = set()
    while parent is not None and parent.pk not in visited:
        if parent.idpai_id == root_id:
            return parent.pk
        visited.add(parent.pk)
        parent = by_id.get(parent.idpai_id)
    return None


def _item_order(item):
    return (item.strnumero, item.intlinhaorigem, item.pk)


def _source_changed_since_submission(envio):
    try:
        current_payload = build_organogram_payload(envio.idimportacaoplanilha)
    except OrganogramSubmissionError:
        return True
    canonical_payload = json.dumps(
        current_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    current_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return current_hash != envio.strhashpayload


def _remote_status_has_error(remote_status):
    if remote_status.get("mensagemErro"):
        return True
    return any(
        stage.get("status") in {4, "4", "Erro"}
        for stage in remote_status.get("etapas", [])
        if isinstance(stage, dict)
    )


def _remote_error_message(remote_status):
    if remote_status.get("mensagemErro"):
        return str(remote_status["mensagemErro"])
    messages = [
        str(stage["mensagemErro"])
        for stage in remote_status.get("etapas", [])
        if isinstance(stage, dict) and stage.get("mensagemErro")
    ]
    return " | ".join(messages) or "A carga foi finalizada com erro na PRODEST."
