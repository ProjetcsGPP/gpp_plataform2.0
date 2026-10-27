#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose="${infra_dir}/scripts/compose.sh"
secret_file="${infra_dir}/runtime/secrets/postgres_test_runner_password"

umask 077
if [[ ! -s "${secret_file}" ]]; then
    openssl rand -hex 32 >"${secret_file}"
    chmod 600 "${secret_file}"
fi

test_password="$(<"${secret_file}")"
"${compose}" exec -T postgres \
    psql \
    --set=ON_ERROR_STOP=1 \
    --set=test_password="${test_password}" \
    --username gpp_admin \
    --dbname postgres <<'SQL'
SELECT 'CREATE ROLE gpp_test_runner'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gpp_test_runner')
\gexec

ALTER ROLE gpp_test_runner WITH
    LOGIN
    NOSUPERUSER
    CREATEDB
    NOCREATEROLE
    NOREPLICATION
    PASSWORD :'test_password';
SQL

printf '%s\n' 'Papel técnico isolado para testes provisionado.'
