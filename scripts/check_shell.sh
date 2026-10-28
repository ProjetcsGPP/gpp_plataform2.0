#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if ! command -v shellcheck >/dev/null 2>&1; then
    printf '%s\n' \
        'ERRO: ShellCheck não está instalado.' \
        'Ubuntu/Debian: sudo apt-get install -y shellcheck' >&2
    exit 127
fi

cd "${PROJECT_DIR}"
mapfile -d '' -t shell_files < <(
    git ls-files -z -co --exclude-standard -- '*.sh'
)

if (( ${#shell_files[@]} == 0 )); then
    printf '%s\n' 'Nenhum script shell foi encontrado.'
    exit 0
fi

printf 'Validando %d script(s) shell com ShellCheck %s...\n' \
    "${#shell_files[@]}" "$(shellcheck --version | awk '/^version:/ {print $2}')"
shellcheck "${shell_files[@]}"
printf '%s\n' 'Validação ShellCheck concluída sem problemas.'
