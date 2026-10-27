#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${infra_dir}/runtime"
secrets_dir="${runtime_dir}/secrets"
tls_dir="${runtime_dir}/tls"
seaweedfs_dir="${runtime_dir}/seaweedfs"

umask 077
mkdir -p "${secrets_dir}" "${tls_dir}" "${seaweedfs_dir}"

generate_secret() {
    local target="$1"
    local bytes="$2"
    if [[ ! -s "${target}" ]]; then
        openssl rand -hex "${bytes}" >"${target}"
    fi
}

generate_secret "${secrets_dir}/postgres_admin_password" 32
generate_secret "${secrets_dir}/postgres_app_password" 32
generate_secret "${secrets_dir}/backup_encryption_password" 32
generate_secret "${secrets_dir}/redis_password" 32
for identity in collector scanner promoter publisher; do
    generate_secret "${secrets_dir}/s3_${identity}_access_key" 16
    generate_secret "${secrets_dir}/s3_${identity}_secret_key" 32
done
generate_secret "${secrets_dir}/s3_bootstrap_access_key" 16
generate_secret "${secrets_dir}/s3_bootstrap_secret_key" 32
generate_secret "${secrets_dir}/seaweedfs_filer_signing_key" 32

if [[ ! -s "${runtime_dir}/.env" ]]; then
    cp "${infra_dir}/.env.example" "${runtime_dir}/.env"
fi

{
    printf '%s\n' '{'
    printf '%s\n' '  "identities": ['
    printf '    {"name":"bootstrap","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin"]},\n' \
        "$(<"${secrets_dir}/s3_bootstrap_access_key")" \
        "$(<"${secrets_dir}/s3_bootstrap_secret_key")"
    printf '    {"name":"collector","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Write:publicacoes-quarantine","List:publicacoes-quarantine"]},\n' \
        "$(<"${secrets_dir}/s3_collector_access_key")" \
        "$(<"${secrets_dir}/s3_collector_secret_key")"
    printf '    {"name":"scanner","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Read:publicacoes-quarantine","List:publicacoes-quarantine"]},\n' \
        "$(<"${secrets_dir}/s3_scanner_access_key")" \
        "$(<"${secrets_dir}/s3_scanner_secret_key")"
    printf '    {"name":"promoter","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Read:publicacoes-quarantine","List:publicacoes-quarantine","Read:publicacoes-approved","Write:publicacoes-approved","List:publicacoes-approved"]},\n' \
        "$(<"${secrets_dir}/s3_promoter_access_key")" \
        "$(<"${secrets_dir}/s3_promoter_secret_key")"
    printf '    {"name":"publisher","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Read:publicacoes-approved","List:publicacoes-approved"]}\n' \
        "$(<"${secrets_dir}/s3_publisher_access_key")" \
        "$(<"${secrets_dir}/s3_publisher_secret_key")"
    printf '%s\n' '  ]'
    printf '%s\n' '}'
} >"${runtime_dir}/s3.json"

cat >"${seaweedfs_dir}/security.toml" <<EOF
[jwt.filer_signing]
key = "$(<"${secrets_dir}/seaweedfs_filer_signing_key")"
expires_after_seconds = 30
EOF

if [[ ! -s "${tls_dir}/dev.key" || ! -s "${tls_dir}/dev.crt" ]]; then
    openssl req \
        -x509 \
        -newkey rsa:3072 \
        -sha256 \
        -nodes \
        -days 30 \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
        -keyout "${tls_dir}/dev.key" \
        -out "${tls_dir}/dev.crt" \
        >/dev/null 2>&1
fi

chmod 600 \
    "${secrets_dir}"/* \
    "${runtime_dir}/s3.json" \
    "${seaweedfs_dir}"/* \
    "${tls_dir}"/*
printf 'Runtime local criado em %s\n' "${runtime_dir}"
