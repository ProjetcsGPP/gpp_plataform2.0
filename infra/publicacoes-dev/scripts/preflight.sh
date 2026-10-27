#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose="${infra_dir}/scripts/compose.sh"
python_bin="${infra_dir}/../../.venv/bin/python"
failures=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        printf 'OK   %s\n' "${label}"
    else
        printf 'FAIL %s\n' "${label}" >&2
        failures=$((failures + 1))
    fi
}

memcached_responds() {
    local port
    port="$(awk -F= '$1 == "MEMCACHED_PORT" {print $2}' \
        "${infra_dir}/runtime/.env")"
    printf 'version\r\n' \
        | nc -w 2 127.0.0.1 "${port}" \
        | grep -q '^VERSION '
}

redis_rejects_unauthenticated() {
    "${compose}" exec -T redis redis-cli ping \
        | grep -q '^NOAUTH '
}

redis_rejects_admin_command() {
    "${compose}" exec -T redis sh -ec \
        'password="$(cat /run/secrets/redis_password)"; redis-cli --user publicacoes --pass "$password" --no-auth-warning CONFIG GET dir' \
        | grep -q '^NOPERM '
}

clamav_detects_eicar() {
    local result
    result="$(printf '%s' \
        'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' \
        | "${compose}" exec -T clamav clamdscan --no-summary - 2>&1 \
        || true)"
    grep -q 'FOUND' <<<"${result}"
}

clamav_accepts_clean_file() {
    printf '%s' 'arquivo limpo de teste' \
        | "${compose}" exec -T clamav clamdscan --no-summary - \
        | grep -q 'OK'
}

clamav_fails_closed_when_unavailable() {
    local status
    set +e
    printf '%s' 'arquivo limpo de teste' \
        | "${compose}" exec -T clamav clamdscan \
            --config-file=/dev/null \
            --no-summary - >/dev/null 2>&1
    status=$?
    set -e
    [[ "${status}" -gt 1 ]]
}

openbao_approle_contract() {
    local role_id secret_id response token status openbao_port
    openbao_port="$(awk -F= '$1 == "OPENBAO_PORT" {print $2}' \
        "${infra_dir}/runtime/.env")"
    role_id="$(<"${infra_dir}/runtime/openbao/role_id")"
    secret_id="$(<"${infra_dir}/runtime/openbao/secret_id")"
    response="$(curl -fsS \
        -X POST \
        -H 'Content-Type: application/json' \
        --data "{\"role_id\":\"${role_id}\",\"secret_id\":\"${secret_id}\"}" \
        "http://127.0.0.1:${openbao_port}/v1/auth/approle/login")"
    token="$(printf '%s' "${response}" | "${python_bin}" -c \
        'import json,sys; print(json.load(sys.stdin)["auth"]["client_token"])')"
    curl -fsS \
        -H "X-Vault-Token: ${token}" \
        "http://127.0.0.1:${openbao_port}/v1/publicacoes/data/dev/preflight" \
        | grep -q 'publicacoes-dev'
    status="$(curl -sS -o /dev/null -w '%{http_code}' \
        -X POST \
        -H "X-Vault-Token: ${token}" \
        -H 'Content-Type: application/json' \
        --data '{"data":{"marker":"must-not-write"}}' \
        "http://127.0.0.1:${openbao_port}/v1/publicacoes/data/dev/preflight")"
    [[ "${status}" == "403" ]]
}

cargarh_openbao_isolation_contract() {
    local openbao_port prd_role prd_secret hml_role hml_secret
    local response prd_token hml_token status
    openbao_port="$(awk -F= '$1 == "OPENBAO_PORT" {print $2}' \
        "${infra_dir}/runtime/.env")"
    prd_role="$(<"${infra_dir}/runtime/openbao/carga_org_lot_prd_role_id")"
    prd_secret="$(<"${infra_dir}/runtime/openbao/carga_org_lot_prd_secret_id")"
    hml_role="$(<"${infra_dir}/runtime/openbao/carga_org_lot_hml_role_id")"
    hml_secret="$(<"${infra_dir}/runtime/openbao/carga_org_lot_hml_secret_id")"

    response="$(curl -fsS -X POST -H 'Content-Type: application/json' \
        --data "{\"role_id\":\"${prd_role}\",\"secret_id\":\"${prd_secret}\"}" \
        "http://127.0.0.1:${openbao_port}/v1/auth/approle/login")"
    prd_token="$(printf '%s' "${response}" | "${python_bin}" -c \
        'import json,sys; print(json.load(sys.stdin)["auth"]["client_token"])')"
    response="$(curl -fsS -X POST -H 'Content-Type: application/json' \
        --data "{\"role_id\":\"${hml_role}\",\"secret_id\":\"${hml_secret}\"}" \
        "http://127.0.0.1:${openbao_port}/v1/auth/approle/login")"
    hml_token="$(printf '%s' "${response}" | "${python_bin}" -c \
        'import json,sys; print(json.load(sys.stdin)["auth"]["client_token"])')"

    status="$(curl -sS -o /dev/null -w '%{http_code}' \
        -H "X-Vault-Token: ${prd_token}" \
        "http://127.0.0.1:${openbao_port}/v1/carga-org-lot/data/dev/cargarh/prd")"
    [[ "${status}" == "200" ]]
    status="$(curl -sS -o /dev/null -w '%{http_code}' \
        -H "X-Vault-Token: ${hml_token}" \
        "http://127.0.0.1:${openbao_port}/v1/carga-org-lot/data/dev/cargarh/prd")"
    [[ "${status}" == "403" ]]
    status="$(curl -sS -o /dev/null -w '%{http_code}' \
        -X POST \
        -H "X-Vault-Token: ${prd_token}" \
        -H 'Content-Type: application/json' \
        --data '{"data":{"client_id":"must-not-write"}}' \
        "http://127.0.0.1:${openbao_port}/v1/carga-org-lot/data/dev/cargarh/prd")"
    [[ "${status}" == "403" ]]
}

postgres_least_privilege_contract() {
    local role_state owners
    role_state="$("${compose}" exec -T postgres psql \
        -U gpp_admin \
        -d gpp_plataform_dev \
        -Atqc "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname = 'gpp_app'")"
    [[ "${role_state}" == "gpp_app|f|f|f|f" ]]
    owners="$("${compose}" exec -T postgres psql \
        -U gpp_admin \
        -d gpp_plataform_dev \
        -Atqc "SELECT nspname || ':' || pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname IN ('public', 'acoes_pngi', 'carga_org_lot', 'publicacoes') ORDER BY nspname")"
    grep -q '^publicacoes:gpp_app$' <<<"${owners}"
    grep -q '^carga_org_lot:gpp_app$' <<<"${owners}"
    grep -q '^acoes_pngi:gpp_app$' <<<"${owners}"
}

ports_are_loopback_only() {
    local mapping service container_port
    while read -r service container_port; do
        mapping="$("${compose}" port "${service}" "${container_port}")"
        [[ "${mapping}" == 127.0.0.1:* ]]
    done <<'EOF'
postgres 5432
redis 6379
memcached 11211
seaweedfs 8333
clamav 3310
openbao 8200
nginx 8443
EOF
}

nginx_security_contract() {
    local nginx_port public_headers private_headers upload_status marker logs
    local json_line rate_results
    nginx_port="$(awk -F= '$1 == "NGINX_HTTPS_PORT" {print $2}' \
        "${infra_dir}/runtime/.env")"
    public_headers="$(curl -kfsSI \
        "https://127.0.0.1:${nginx_port}/infra/cache-public-contract")"
    private_headers="$(curl -kfsSI \
        "https://127.0.0.1:${nginx_port}/infra/cache-private-contract")"
    grep -Eqi '^Cache-Control: public, max-age=60' <<<"${public_headers}"
    grep -Eqi '^Cache-Control: private, no-store' <<<"${private_headers}"

    upload_status="$(head -c 27262976 /dev/zero \
        | curl -ksS -o /dev/null -w '%{http_code}' \
            -X POST --data-binary @- \
            "https://127.0.0.1:${nginx_port}/api/upload-limit-probe")"
    [[ "${upload_status}" == "413" ]]

    marker="gpp-redaction-probe-$RANDOM-$RANDOM"
    curl -kfsS -o /dev/null \
        -H "Authorization: Bearer ${marker}" \
        "https://127.0.0.1:${nginx_port}/infra/log-redaction-contract?token=${marker}"
    logs="$("${compose}" logs --no-color --tail=20 nginx)"
    ! grep -q "${marker}" <<<"${logs}"
    json_line="$(grep '{"time"' <<<"${logs}" | tail -n 1 | sed 's/^[^{]*//')"
    printf '%s' "${json_line}" | "${python_bin}" -c '
import json
import sys

event = json.load(sys.stdin)
required = {"time", "request_id", "method", "uri", "status", "duration"}
if not required.issubset(event):
    raise SystemExit(1)
' 

    rate_results="$(mktemp "${infra_dir}/runtime/rate-limit.XXXXXX")"
    for _request in $(seq 1 80); do
        curl -ksS -o /dev/null -w '%{http_code}\n' \
            "https://127.0.0.1:${nginx_port}/api/rate-limit-probe" \
            >>"${rate_results}" &
    done
    wait || true
    grep -q '^429$' "${rate_results}"
    rm -f "${rate_results}"
}

nginx_ignores_untrusted_forwarding_headers() {
    local config
    config="$("${compose}" exec -T nginx nginx -T 2>&1)"
    grep -q 'proxy_set_header X-Forwarded-For \$remote_addr;' <<<"${config}"
    grep -q 'proxy_set_header X-Forwarded-Proto https;' <<<"${config}"
}

s3_status() {
    local identity="$1"
    local method="$2"
    local bucket="$3"
    local key="${4:-}"
    local access_key secret_key s3_port url
    access_key="$(<"${infra_dir}/runtime/secrets/s3_${identity}_access_key")"
    secret_key="$(<"${infra_dir}/runtime/secrets/s3_${identity}_secret_key")"
    s3_port="$(awk -F= '$1 == "S3_PORT" {print $2}' \
        "${infra_dir}/runtime/.env")"
    url="http://127.0.0.1:${s3_port}/${bucket}"
    if [[ -n "${key}" ]]; then
        url="${url}/${key}"
    fi
    if [[ "${method}" == "PUT" ]]; then
        curl -sS -o /dev/null -w '%{http_code}' \
            --aws-sigv4 'aws:amz:us-east-1:s3' \
            --user "${access_key}:${secret_key}" \
            -X PUT --data-binary 'publicacoes-security-preflight' "${url}"
    else
        curl -sS -o /dev/null -w '%{http_code}' \
            --aws-sigv4 'aws:amz:us-east-1:s3' \
            --user "${access_key}:${secret_key}" \
            -X "${method}" "${url}"
    fi
}

s3_contract() {
    local key="security-preflight.txt"
    [[ "$(s3_status collector PUT publicacoes-quarantine "${key}")" == "200" ]]
    [[ "$(s3_status collector PUT publicacoes-approved "${key}")" == "403" ]]
    [[ "$(s3_status scanner GET publicacoes-quarantine "${key}")" == "200" ]]
    [[ "$(s3_status promoter GET publicacoes-quarantine "${key}")" == "200" ]]
    [[ "$(s3_status promoter PUT publicacoes-approved "${key}")" == "200" ]]
    [[ "$(s3_status scanner GET publicacoes-approved "${key}")" == "403" ]]
    [[ "$(s3_status publisher GET publicacoes-approved "${key}")" == "200" ]]
    [[ "$(s3_status publisher GET publicacoes-quarantine "${key}")" == "403" ]]
}

check "Compose válido" "${compose}" config --quiet
check "PostgreSQL responde" "${compose}" exec -T postgres \
    pg_isready -U gpp_admin -d gpp_plataform_dev
check "PostgreSQL aplica privilégio mínimo" postgres_least_privilege_contract
check "Redis autenticado responde" "${compose}" exec -T redis sh -ec \
    'password="$(cat /run/secrets/redis_password)"; redis-cli --user publicacoes --pass "$password" --no-auth-warning ping | grep -q PONG'
check "Redis rejeita cliente sem autenticação" redis_rejects_unauthenticated
check "Redis rejeita comando administrativo" redis_rejects_admin_command
check "Memcached aceita conexão" memcached_responds
check "SeaweedFS está saudável" "${compose}" exec -T seaweedfs \
    curl -sS http://127.0.0.1:8333/
check "Papéis S3 respeitam quarentena e área aprovada" s3_contract
check "ClamAV responde" "${compose}" exec -T clamav clamdscan --ping 2
check "ClamAV aceita arquivo limpo" clamav_accepts_clean_file
check "ClamAV detecta EICAR" clamav_detects_eicar
check "Falha do scanner permanece fechada" clamav_fails_closed_when_unavailable
check "OpenBao está desbloqueado" "${compose}" exec -T openbao sh -ec \
    'BAO_ADDR=http://127.0.0.1:8200 bao status'
check "AppRole lê segredo e não pode alterá-lo" openbao_approle_contract
check "CargaRH PRD lê segredo e HML permanece isolado" \
    cargarh_openbao_isolation_contract

nginx_port="$(awk -F= '$1 == "NGINX_HTTPS_PORT" {print $2}' "${infra_dir}/runtime/.env")"
check "Nginx TLS responde" curl -kfsS \
    "https://127.0.0.1:${nginx_port}/infra/healthz"
check "Portas estão vinculadas somente ao loopback" ports_are_loopback_only
check "Proxy aplica cache, limite e redação" nginx_security_contract
check "Proxy sobrescreve headers de encaminhamento" \
    nginx_ignores_untrusted_forwarding_headers
check "Política de egress bloqueia SSRF" \
    "${python_bin}" "${infra_dir}/scripts/egress_policy.py" --self-test

if [[ "${failures}" -ne 0 ]]; then
    printf '%s verificação(ões) falharam.\n' "${failures}" >&2
    exit 1
fi

printf '%s\n' 'Preflight básico aprovado.'
