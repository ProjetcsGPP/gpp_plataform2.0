#!/bin/sh
set -eu

access_key="$(cat /run/secrets/s3_bootstrap_access_key)"
secret_key="$(cat /run/secrets/s3_bootstrap_secret_key)"

for bucket in publicacoes-quarantine publicacoes-approved; do
    status="$(curl -sS -o /dev/null -w '%{http_code}' \
        --aws-sigv4 'aws:amz:us-east-1:s3' \
        --user "${access_key}:${secret_key}" \
        -I "http://seaweedfs:8333/${bucket}")"
    if [ "${status}" = "200" ]; then
        continue
    fi
    status="$(curl -sS -o /dev/null -w '%{http_code}' \
        --aws-sigv4 'aws:amz:us-east-1:s3' \
        --user "${access_key}:${secret_key}" \
        -X PUT "http://seaweedfs:8333/${bucket}")"
    if [ "${status}" != "200" ]; then
        printf 'Falha ao criar %s: HTTP %s\n' "${bucket}" "${status}" >&2
        exit 1
    fi
done

printf '%s\n' 'Buckets privados de desenvolvimento provisionados.'
