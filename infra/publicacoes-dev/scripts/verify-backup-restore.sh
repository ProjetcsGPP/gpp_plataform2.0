#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose="${infra_dir}/scripts/compose.sh"
runtime_dir="${infra_dir}/runtime"
backup_dir="${runtime_dir}/backups"
encryption_key="${runtime_dir}/secrets/backup_encryption_password"
restore_db="gpp_publicacoes_restore_check"
probe_table="publicacoes._backup_restore_probe"
probe_value="publicacoes-backup-restore-ok"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
plain_dump="${backup_dir}/.${timestamp}.dump"
encrypted_dump="${backup_dir}/publicacoes-${timestamp}.dump.enc"

umask 077
mkdir -p "${backup_dir}"

cleanup() {
    "${compose}" exec -T postgres psql \
        -U gpp_admin \
        -d gpp_plataform_dev \
        -v ON_ERROR_STOP=1 \
        -c "DROP TABLE IF EXISTS ${probe_table}" >/dev/null 2>&1 || true
    "${compose}" exec -T postgres dropdb \
        -U gpp_admin \
        --if-exists \
        "${restore_db}" >/dev/null 2>&1 || true
    rm -f "${plain_dump}"
}
trap cleanup EXIT

"${compose}" exec -T postgres sh -ec '
    export PGPASSWORD="$(cat /run/secrets/postgres_app_password)"
    psql -h 127.0.0.1 -U gpp_app -d gpp_plataform_dev -v ON_ERROR_STOP=1 \
      -c "CREATE TABLE publicacoes._backup_restore_probe (value text NOT NULL)" \
      -c "INSERT INTO publicacoes._backup_restore_probe VALUES ('"'"'publicacoes-backup-restore-ok'"'"')"
' >/dev/null

"${compose}" exec -T postgres pg_dump \
    -U gpp_admin \
    -d gpp_plataform_dev \
    -Fc >"${plain_dump}"

openssl enc \
    -aes-256-cbc \
    -salt \
    -pbkdf2 \
    -iter 200000 \
    -pass "file:${encryption_key}" \
    -in "${plain_dump}" \
    -out "${encrypted_dump}"
chmod 600 "${encrypted_dump}"

"${compose}" exec -T postgres psql \
    -U gpp_admin \
    -d gpp_plataform_dev \
    -v ON_ERROR_STOP=1 \
    -c "DROP TABLE ${probe_table}" >/dev/null

"${compose}" exec -T postgres dropdb \
    -U gpp_admin \
    --if-exists \
    "${restore_db}" >/dev/null
"${compose}" exec -T postgres createdb \
    -U gpp_admin \
    "${restore_db}"

openssl enc \
    -d \
    -aes-256-cbc \
    -pbkdf2 \
    -iter 200000 \
    -pass "file:${encryption_key}" \
    -in "${encrypted_dump}" \
    | "${compose}" exec -T postgres pg_restore \
        -U gpp_admin \
        -d "${restore_db}" \
        --exit-on-error

restored_value="$("${compose}" exec -T postgres psql \
    -U gpp_admin \
    -d "${restore_db}" \
    -Atqc "SELECT value FROM ${probe_table}")"

if [[ "${restored_value}" != "${probe_value}" ]]; then
    printf '%s\n' 'Restore não recuperou o marcador esperado.' >&2
    exit 1
fi

printf 'Backup criptografado e restore aprovados: %s\n' "${encrypted_dump}"
