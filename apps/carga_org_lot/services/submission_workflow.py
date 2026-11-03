"""Representação canônica das fases de integração com a PRODEST."""

from __future__ import annotations

from collections.abc import Iterable

from apps.carga_org_lot.models import (
    FaseIntegracaoProdest,
    OperacaoIntegracaoProdest,
    ResultadoIntegracaoProdest,
    StatusEnvioOrganograma,
    StatusEventoOperacional,
    VisibilidadeEventoIntegracao,
)


PHASES = tuple(value for value, _label in FaseIntegracaoProdest.choices)
TECHNICAL_PHASES = {
    OperacaoIntegracaoProdest.OBTER_TOKEN: FaseIntegracaoProdest.AUTENTICACAO,
    OperacaoIntegracaoProdest.ENVIAR_ORGANOGRAMA_INICIAL: (
        FaseIntegracaoProdest.ENVIO
    ),
    OperacaoIntegracaoProdest.CONSULTAR_STATUS: (
        FaseIntegracaoProdest.PROCESSAMENTO
    ),
    OperacaoIntegracaoProdest.CONSULTAR_RELATORIO: (
        FaseIntegracaoProdest.RELATORIO
    ),
}
EVENT_CODE_PHASES = {
    "AUTENTICACAO_REJEITADA": FaseIntegracaoProdest.AUTENTICACAO,
    "ENVIO_REJEITADO": FaseIntegracaoProdest.ENVIO,
}
ERROR_RESULTS = {
    ResultadoIntegracaoProdest.ERRO_HTTP,
    ResultadoIntegracaoProdest.TIMEOUT,
    ResultadoIntegracaoProdest.ERRO_CONEXAO,
}


def canonical_event_phase(event) -> str:
    """Corrige a fase de exibição sem alterar a trilha histórica imutável."""
    if event.strcodigo in EVENT_CODE_PHASES:
        return EVENT_CODE_PHASES[event.strcodigo]
    if event.strvisibilidade == VisibilidadeEventoIntegracao.TECNICA:
        return TECHNICAL_PHASES.get(event.stroperacao, event.strfase)
    return event.strfase


def build_submission_workflow(submission) -> dict:
    """Monta as etapas conforme eventos e operações realmente executados."""
    events = _submission_events(submission)
    stages = {
        phase: {
            "codigo": phase,
            "nome": FaseIntegracaoProdest(phase).label,
            "ordem": index,
            "status": StatusEventoOperacional.AGUARDANDO,
            "status_nome": StatusEventoOperacional.AGUARDANDO.label,
            "mensagem": "Esta etapa ainda não foi iniciada.",
            "data_ultima_atividade": None,
            "atual": False,
        }
        for index, phase in enumerate(PHASES, start=1)
    }

    operational_events = [
        event
        for event in events
        if event.strvisibilidade == VisibilidadeEventoIntegracao.OPERACIONAL
    ]
    for event in operational_events:
        phase = canonical_event_phase(event)
        if phase not in stages or not event.strstatusoperacional:
            continue
        _update_stage(
            stages[phase],
            status=event.strstatusoperacional,
            message=event.strmensagem,
            occurred_at=event.datocorrencia,
        )

    latest_technical = {}
    for event in events:
        if event.strvisibilidade != VisibilidadeEventoIntegracao.TECNICA:
            continue
        phase = canonical_event_phase(event)
        if phase in stages:
            latest_technical[phase] = event

    for phase, event in latest_technical.items():
        status = (
            StatusEventoOperacional.SUCESSO
            if event.strresultado == ResultadoIntegracaoProdest.SUCESSO
            else StatusEventoOperacional.ERRO
            if event.strresultado in ERROR_RESULTS
            else None
        )
        if status is None:
            continue
        message = event.strmensagem
        if phase == FaseIntegracaoProdest.AUTENTICACAO and status == (
            StatusEventoOperacional.SUCESSO
        ):
            message = _authentication_message(event)
            stages[phase]["origem_autenticacao"] = event.jsondetalhes.get(
                "origem_token", ""
            )
        _update_stage(
            stages[phase],
            status=status,
            message=message,
            occurred_at=event.datocorrencia,
        )

    _apply_submission_state(submission, stages)
    current_phase = _current_phase(submission, stages)
    stages[current_phase]["atual"] = True
    current = stages[current_phase]
    return {
        "fase_atual": current_phase,
        "fase_atual_nome": current["nome"],
        "status_atual": current["status"],
        "status_atual_nome": current["status_nome"],
        "mensagem_atual": current["mensagem"],
        "etapas": list(stages.values()),
    }


def _submission_events(submission) -> list:
    prefetched = getattr(submission, "_prefetched_objects_cache", {}).get(
        "eventos_integracao_prodest"
    )
    events: Iterable = (
        prefetched
        if prefetched is not None
        else submission.eventos_integracao_prodest.all()
    )
    return sorted(
        events,
        key=lambda event: (event.datocorrencia, event.ideventointegracao),
    )


def _update_stage(stage, *, status, message, occurred_at=None):
    stage["status"] = status
    stage["status_nome"] = StatusEventoOperacional(status).label
    stage["mensagem"] = message
    if occurred_at is not None:
        stage["data_ultima_atividade"] = occurred_at.isoformat()


def _authentication_message(event) -> str:
    if event.jsondetalhes.get("origem_token") == "CACHE_COMPARTILHADO":
        return "A credencial segura ainda válida foi reutilizada."
    return "Um novo acesso seguro foi obtido junto ao Acesso Cidadão."


def _apply_submission_state(submission, stages):
    if submission.idexternocarga:
        _mark_success_if_incomplete(stages[FaseIntegracaoProdest.AUTENTICACAO])
        _mark_success_if_incomplete(stages[FaseIntegracaoProdest.ENVIO])

    if submission.strstatus == StatusEnvioOrganograma.PROCESSANDO:
        processing = stages[FaseIntegracaoProdest.PROCESSAMENTO]
        if processing["status"] not in {
            StatusEventoOperacional.AVISO,
            StatusEventoOperacional.ERRO,
        }:
            _update_stage(
                processing,
                status=StatusEventoOperacional.EM_ANDAMENTO,
                message="A PRODEST está processando a carga enviada.",
            )
    elif submission.strstatus in {
        StatusEnvioOrganograma.CONCLUIDO,
        StatusEnvioOrganograma.CONCLUIDO_DESATUALIZADO,
    }:
        for phase in (
            FaseIntegracaoProdest.AUTENTICACAO,
            FaseIntegracaoProdest.ENVIO,
            FaseIntegracaoProdest.PROCESSAMENTO,
        ):
            _mark_success_if_incomplete(stages[phase])

    if submission.jsonrelatorioprodest:
        _update_stage(
            stages[FaseIntegracaoProdest.RELATORIO],
            status=StatusEventoOperacional.SUCESSO,
            message="O relatório final da PRODEST está disponível.",
        )

    if submission.strstatus == StatusEnvioOrganograma.CONCLUIDO:
        _update_stage(
            stages[FaseIntegracaoProdest.CONCLUSAO],
            status=StatusEventoOperacional.SUCESSO,
            message="A carga inicial do organograma foi concluída.",
        )
    elif submission.strstatus == StatusEnvioOrganograma.CONCLUIDO_DESATUALIZADO:
        _update_stage(
            stages[FaseIntegracaoProdest.CONCLUSAO],
            status=StatusEventoOperacional.AVISO,
            message=(
                "A carga foi concluída, mas o organograma local foi alterado "
                "depois do envio."
            ),
        )

    reached = max(
        (
            stage["ordem"]
            for stage in stages.values()
            if stage["status"] != StatusEventoOperacional.AGUARDANDO
        ),
        default=1,
    )
    for stage in stages.values():
        if stage["ordem"] < reached:
            _mark_success_if_incomplete(stage)


def _mark_success_if_incomplete(stage):
    if stage["status"] in {
        StatusEventoOperacional.AGUARDANDO,
        StatusEventoOperacional.EM_ANDAMENTO,
    }:
        _update_stage(
            stage,
            status=StatusEventoOperacional.SUCESSO,
            message="Etapa concluída.",
        )


def _current_phase(submission, stages) -> str:
    error_phases = [
        phase
        for phase in PHASES
        if stages[phase]["status"] == StatusEventoOperacional.ERRO
    ]
    if error_phases:
        return error_phases[-1]
    active_phases = [
        phase
        for phase in PHASES
        if stages[phase]["status"] in {
            StatusEventoOperacional.EM_ANDAMENTO,
            StatusEventoOperacional.AVISO,
        }
    ]
    if active_phases:
        return active_phases[-1]
    completed_phases = [
        phase
        for phase in PHASES
        if stages[phase]["status"] == StatusEventoOperacional.SUCESSO
    ]
    if completed_phases:
        return completed_phases[-1]
    if submission.strfaseatual in stages:
        return submission.strfaseatual
    return FaseIntegracaoProdest.PREPARACAO
