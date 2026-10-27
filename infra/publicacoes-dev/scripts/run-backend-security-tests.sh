#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$(cd "${infra_dir}/../.." && pwd)"
secret_file="${infra_dir}/runtime/secrets/postgres_test_runner_password"
pgpass_file="$(mktemp)"

cleanup() {
    rm -f "${pgpass_file}"
}
trap cleanup EXIT

umask 077
if [[ ! -s "${secret_file}" ]]; then
    printf '%s\n' \
        'Credencial de testes ausente. Execute scripts/bootstrap-test-runner.sh.' \
        >&2
    exit 1
fi

printf '127.0.0.1:55432:*:gpp_test_runner:%s\n' \
    "$(<"${secret_file}")" >"${pgpass_file}"
chmod 600 "${pgpass_file}"

export PGPASSFILE="${pgpass_file}"
export DJANGO_SETTINGS_MODULE="config.settings.test_publicacoes_dev"

cd "${project_dir}"
"${project_dir}/.venv/bin/pytest" "$@"
