#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose="${infra_dir}/scripts/compose.sh"
secret_file="${infra_dir}/runtime/secrets/postgres_admin_password"
temporary_secret="$(mktemp "${secret_file}.XXXXXX")"

cleanup() {
    rm -f "${temporary_secret}"
}
trap cleanup EXIT

umask 077
openssl rand -hex 32 >"${temporary_secret}"
new_password="$(<"${temporary_secret}")"

"${compose}" exec -T postgres \
    psql \
    --set=ON_ERROR_STOP=1 \
    --set=admin_password="${new_password}" \
    --username gpp_admin \
    --dbname postgres <<'SQL'
ALTER ROLE gpp_admin PASSWORD :'admin_password';
SQL

chmod 600 "${temporary_secret}"
mv -f "${temporary_secret}" "${secret_file}"
printf '%s\n' 'Credencial administrativa do PostgreSQL rotacionada.'
