#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose="${infra_dir}/scripts/compose.sh"

"${compose}" up -d postgres
"${compose}" exec -T postgres \
    /docker-entrypoint-initdb.d/01-create-app-role.sh

printf '%s\n' 'Papel técnico e schemas PostgreSQL provisionados.'
