#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_env="${infra_dir}/runtime/.env"

if [[ ! -f "${runtime_env}" ]]; then
    printf '%s\n' 'Runtime ausente. Execute scripts/bootstrap-runtime.sh.' >&2
    exit 1
fi

exec docker compose \
    --project-directory "${infra_dir}" \
    --env-file "${runtime_env}" \
    -f "${infra_dir}/compose.yaml" \
    "$@"
