#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${infra_dir}/runtime"
evidence_dir="${runtime_dir}/security-evidence"
cache_dir="${runtime_dir}/trivy-cache"
work_dir="${runtime_dir}/scan-work"
trivy_image="ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c"

names=(postgres redis memcached seaweedfs clamav openbao nginx)
images=(
    "postgres:16.15-bookworm@sha256:d81f7b51697014367236d07ec58b54153fc28f828b72bf247fe5c7487520bcb0"
    "redis:7.2.16-alpine3.21@sha256:ee061d86c25773048211e99f00d63b47b9ecfe28560113e16cce2c962d5bec1c"
    "memcached:1.6.45-alpine@sha256:6a089e37cbb8acd75c80c6c0667fe57ec54db68782fb1b3afb1d0eb265e50070"
    "chrislusf/seaweedfs:4.51@sha256:f7a49e3f3972ebed5be2ed4befa4a0c68eb7bdddba6e692d42729ceb545134b8"
    "clamav/clamav:1.5.4@sha256:bda39705e291105049c3936e2803ac90b955172af8030f94f05dce1252df6c6d"
    "quay.io/openbao/openbao:2.7.1@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf"
    "gpp-publicacoes/nginx-dev:1.30.6-alpine-security-20261026"
)

umask 077
mkdir -p "${evidence_dir}" "${cache_dir}" "${work_dir}"

cleanup() {
    rm -f "${work_dir}/image.tar"
}
trap cleanup EXIT

docker pull "${trivy_image}" >/dev/null

for index in "${!images[@]}"; do
    name="${names[index]}"
    image="${images[index]}"
    if [[ "${FORCE_SECURITY_SCAN:-0}" != "1" \
        && -s "${evidence_dir}/${name}.cdx.json" \
        && -s "${evidence_dir}/${name}.vuln.json" ]]; then
        printf 'Evidência existente preservada para %s.\n' "${name}"
        continue
    fi
    printf 'Analisando %s...\n' "${name}"
    docker image save --output "${work_dir}/image.tar" "${image}"
    package_args=()
    if [[ "${name}" == "nginx" ]]; then
        package_args=(--pkg-types os)
    fi

    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -e TRIVY_CACHE_DIR=/cache \
        -v "${cache_dir}:/cache" \
        -v "${work_dir}:/scan:ro" \
        -v "${evidence_dir}:/evidence" \
        "${trivy_image}" image \
        --input /scan/image.tar \
        --format cyclonedx \
        --output "/evidence/${name}.cdx.json" \
        --no-progress \
        "${package_args[@]}" \
        --scanners vuln

    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -e TRIVY_CACHE_DIR=/cache \
        -v "${cache_dir}:/cache" \
        -v "${work_dir}:/scan:ro" \
        -v "${evidence_dir}:/evidence" \
        "${trivy_image}" image \
        --input /scan/image.tar \
        --format json \
        --output "/evidence/${name}.vuln.json" \
        --no-progress \
        "${package_args[@]}" \
        --scanners vuln

    rm -f "${work_dir}/image.tar"
done

"${infra_dir}/../../.venv/bin/python" \
    "${infra_dir}/scripts/summarize_security_evidence.py" \
    "${evidence_dir}" >"${evidence_dir}/summary.json"

printf 'SBOMs e relatórios gravados em %s\n' "${evidence_dir}"
printf '%s\n' 'Achados não são suprimidos nem aprovados automaticamente.'
