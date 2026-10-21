#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${PROJECT_DIR}/.venv/bin/python}"
CELERY_BIN="${CELERY_BIN:-${PROJECT_DIR}/.venv/bin/celery}"
VENV_ACTIVATE="${VENV_ACTIVATE:-${PROJECT_DIR}/.venv/bin/activate}"
CODE_BIN="${CODE_BIN:-code}"
DJANGO_ADDRESS="${DJANGO_ADDRESS:-127.0.0.1:8000}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-INFO}"

declare -a CHILD_PIDS=()
SHUTTING_DOWN=0

log() {
    printf '[localhost_dev] %s\n' "$*"
}

cleanup() {
    local exit_code="${1:-$?}"

    if (( SHUTTING_DOWN )); then
        return
    fi
    SHUTTING_DOWN=1

    trap - EXIT INT TERM
    log "Encerrando os processos locais..."

    local pid
    for pid in "${CHILD_PIDS[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill -TERM "${pid}" 2>/dev/null || true
        fi
    done

    for pid in "${CHILD_PIDS[@]}"; do
        wait "${pid}" 2>/dev/null || true
    done

    log "Todos os processos foram encerrados."
    exit "${exit_code}"
}

handle_signal() {
    cleanup 130
}

require_executable() {
    local executable="$1"
    local description="$2"

    if [[ ! -x "${executable}" ]]; then
        log "ERRO: ${description} não encontrado ou não executável: ${executable}"
        log "Ative/crie o ambiente virtual e instale as dependências antes de continuar."
        exit 1
    fi
}

trap 'cleanup $?' EXIT
trap handle_signal INT TERM

require_executable "${PYTHON_BIN}" "Python do ambiente virtual"
require_executable "${CELERY_BIN}" "Celery do ambiente virtual"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    log "ERRO: script de ativação do ambiente virtual não encontrado: ${VENV_ACTIVATE}"
    exit 1
fi

if ! command -v "${CODE_BIN}" >/dev/null 2>&1; then
    log "ERRO: VS Code não está instalado ou não está disponível no PATH: ${CODE_BIN}"
    exit 1
fi

if ! command -v redis-cli >/dev/null 2>&1; then
    log "ERRO: redis-cli não está instalado ou não está disponível no PATH."
    exit 1
fi

if [[ "$(redis-cli ping 2>/dev/null || true)" != "PONG" ]]; then
    log "ERRO: o Redis local não respondeu."
    log "Inicie o serviço Redis e execute este script novamente."
    exit 1
fi

cd "${PROJECT_DIR}"

log "Redis disponível."
log "Ativando ambiente virtual..."
# shellcheck disable=SC1091
source "${VENV_ACTIVATE}"

log "Abrindo o projeto no VS Code..."
"${CODE_BIN}" "${PROJECT_DIR}"

log "Iniciando Celery Worker..."
"${CELERY_BIN}" -A config worker --loglevel="${CELERY_LOG_LEVEL}" &
CHILD_PIDS+=("$!")

log "Iniciando Celery Beat..."
"${CELERY_BIN}" -A config beat --loglevel="${CELERY_LOG_LEVEL}" &
CHILD_PIDS+=("$!")

log "Iniciando Django em http://${DJANGO_ADDRESS}/ ..."
"${PYTHON_BIN}" manage.py runserver "${DJANGO_ADDRESS}" &
CHILD_PIDS+=("$!")

log "Ambiente iniciado. Pressione Ctrl+C para encerrar tudo."

set +e
wait -n "${CHILD_PIDS[@]}"
PROCESS_EXIT_CODE=$?
set -e

if (( PROCESS_EXIT_CODE != 0 )); then
    log "Um dos processos terminou com erro (${PROCESS_EXIT_CODE})."
else
    log "Um dos processos foi encerrado."
fi

cleanup "${PROCESS_EXIT_CODE}"
