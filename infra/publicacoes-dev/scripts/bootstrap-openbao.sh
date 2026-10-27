#!/usr/bin/env bash
set -euo pipefail

replace_app_identities=false
if [[ "${1:-}" == "--replace-app-identities" ]]; then
    replace_app_identities=true
    shift
fi
if [[ "$#" -ne 0 ]]; then
    printf 'Uso: %s [--replace-app-identities]\n' "$0" >&2
    exit 2
fi

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${infra_dir}/runtime/openbao"
compose="${infra_dir}/scripts/compose.sh"
python_bin="${infra_dir}/../../.venv/bin/python"

if [[ ! -x "${python_bin}" ]]; then
    printf '%s\n' 'Python do ambiente virtual não encontrado.' >&2
    exit 1
fi

umask 077
mkdir -p "${runtime_dir}"

"${compose}" up -d openbao

status_file="${runtime_dir}/status.json"
ready=false
for _attempt in $(seq 1 60); do
    if "${compose}" exec -T openbao sh -ec \
        'BAO_ADDR=http://127.0.0.1:8200 bao status -format=json' \
        >"${status_file}" 2>/dev/null; then
        ready=true
        break
    fi
    if "${python_bin}" -c \
        'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' \
        "${status_file}" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 1
done

if [[ "${ready}" != "true" ]]; then
    printf '%s\n' 'OpenBao não respondeu com estado válido após 60 segundos.' >&2
    exit 1
fi

initialized="$("${python_bin}" -c \
    'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(str(data.get("initialized", False)).lower())' \
    "${status_file}")"

init_file="${runtime_dir}/init.json"
if [[ "${initialized}" != "true" ]]; then
    tmp_file="${init_file}.tmp"
    "${compose}" exec -T openbao sh -ec \
        'BAO_ADDR=http://127.0.0.1:8200 bao operator init -key-shares=1 -key-threshold=1 -format=json' \
        >"${tmp_file}"
    chmod 600 "${tmp_file}"
    mv "${tmp_file}" "${init_file}"
elif [[ ! -s "${init_file}" ]]; then
    printf '%s\n' \
        'OpenBao já inicializado, mas runtime/openbao/init.json está ausente.' \
        'Restaure as chaves locais; o bootstrap não pode recriá-las.' >&2
    exit 1
fi

unseal_key="$(${python_bin} -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["unseal_keys_b64"][0])' \
    "${init_file}")"
root_token="$(${python_bin} -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["root_token"])' \
    "${init_file}")"

sealed="$("${python_bin}" -c \
    'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(str(data.get("sealed", True)).lower())' \
    "${status_file}")"
if [[ "${sealed}" == "true" ]]; then
    "${compose}" exec -T openbao sh -ec \
        'BAO_ADDR=http://127.0.0.1:8200 bao operator unseal "$1" >/dev/null' \
        sh "${unseal_key}"
fi

bao_exec() {
    "${compose}" exec -T \
        -e BAO_ADDR=http://127.0.0.1:8200 \
        -e BAO_TOKEN="${root_token}" \
        openbao bao "$@"
}

ensure_secret_id() {
    local role_name="$1"
    local secret_id_file="$2"
    local old_secret_id

    if [[ "${replace_app_identities}" == "true" && -s "${secret_id_file}" ]]; then
        old_secret_id=$(<"${secret_id_file}")
        bao_exec write \
            "auth/approle/role/${role_name}/secret-id/destroy" \
            secret_id="${old_secret_id}" >/dev/null || true
        unset old_secret_id
        rm -f "${secret_id_file}"
    fi
    if [[ ! -s "${secret_id_file}" ]]; then
        bao_exec write -f -field=secret_id \
            "auth/approle/role/${role_name}/secret-id" \
            >"${secret_id_file}"
    fi
    chmod 600 "${secret_id_file}"
}

if ! bao_exec secrets list -format=json | grep -q '"publicacoes/"'; then
    bao_exec secrets enable -path=publicacoes kv-v2 >/dev/null
fi
if ! bao_exec secrets list -format=json | grep -q '"carga-org-lot/"'; then
    bao_exec secrets enable -path=carga-org-lot kv-v2 >/dev/null
fi

bao_exec policy write publicacoes-dev \
    /openbao/publicacoes-policy.hcl >/dev/null

if ! bao_exec auth list -format=json | grep -q '"approle/"'; then
    bao_exec auth enable approle >/dev/null
fi

bao_exec write auth/approle/role/publicacoes-dev \
    token_policies=publicacoes-dev \
    token_ttl=1h \
    token_max_ttl=4h \
    secret_id_ttl=0 \
    secret_id_num_uses=0 >/dev/null

bao_exec kv put publicacoes/dev/preflight \
    marker=publicacoes-dev >/dev/null

bao_exec read -field=role_id \
    auth/approle/role/publicacoes-dev/role-id \
    >"${runtime_dir}/role_id"
ensure_secret_id publicacoes-dev "${runtime_dir}/secret_id"
chmod 600 "${runtime_dir}/role_id"

for environment in hml prd; do
    role_name="carga-org-lot-${environment}-dev"
    policy_name="${role_name}"
    bao_exec policy write "${policy_name}" \
        "/openbao/carga-org-lot-${environment}-policy.hcl" >/dev/null
    bao_exec write "auth/approle/role/${role_name}" \
        token_policies="${policy_name}" \
        token_ttl=15m \
        token_max_ttl=1h \
        secret_id_ttl=0 \
        secret_id_num_uses=0 >/dev/null
    bao_exec read -field=role_id \
        "auth/approle/role/${role_name}/role-id" \
        >"${runtime_dir}/carga_org_lot_${environment}_role_id"
    secret_id_file="${runtime_dir}/carga_org_lot_${environment}_secret_id"
    ensure_secret_id "${role_name}" "${secret_id_file}"
    chmod 600 \
        "${runtime_dir}/carga_org_lot_${environment}_role_id" \
        "${secret_id_file}"
done

printf '%s\n' 'OpenBao inicializado e AppRole de DEV provisionada.'
