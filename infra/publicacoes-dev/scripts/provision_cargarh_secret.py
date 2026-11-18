#!/usr/bin/env python3
"""Cadastra ou substitui explicitamente uma credencial CargaRH local."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

import requests


INFRA_DIR = Path(__file__).resolve().parents[1]
OPENBAO_RUNTIME = INFRA_DIR / "runtime" / "openbao"
OPENBAO_ENV = INFRA_DIR / "runtime" / ".env"


def _runtime_port():
    for line in OPENBAO_ENV.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "OPENBAO_PORT":
            return value.strip()
    return "58200"


def _read_value(path, prompt, *, secret=False):
    if path:
        value = Path(path).read_text(encoding="utf-8").strip()
    elif secret:
        value = getpass.getpass(prompt).strip()
    else:
        value = input(prompt).strip()
    if not value:
        raise SystemExit("O valor informado não pode ser vazio.")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("HML", "PRD"), required=True)
    parser.add_argument("--client-id-file")
    parser.add_argument("--client-secret-file")
    args = parser.parse_args()

    client_id = _read_value(args.client_id_file, "Client ID: ")
    client_secret = _read_value(
        args.client_secret_file,
        "Client secret: ",
        secret=True,
    )
    init_data = json.loads(
        (OPENBAO_RUNTIME / "init.json").read_text(encoding="utf-8")
    )
    root_token = init_data["root_token"]
    environment = args.environment.lower()
    address = f"http://127.0.0.1:{_runtime_port()}"
    secret_url = (
        f"{address}/v1/carga-org-lot/data/dev/cargarh/{environment}"
    )
    response = requests.post(
        secret_url,
        headers={"X-Vault-Token": root_token},
        json={"data": {"client_id": client_id, "client_secret": client_secret}},
        timeout=5,
    )
    response.raise_for_status()

    role_id = (
        OPENBAO_RUNTIME / f"carga_org_lot_{environment}_role_id"
    ).read_text(encoding="utf-8").strip()
    secret_id = (
        OPENBAO_RUNTIME / f"carga_org_lot_{environment}_secret_id"
    ).read_text(encoding="utf-8").strip()
    login_response = requests.post(
        f"{address}/v1/auth/approle/login",
        json={"role_id": role_id, "secret_id": secret_id},
        timeout=5,
    )
    login_response.raise_for_status()
    token = login_response.json()["auth"]["client_token"]
    read_response = requests.get(
        secret_url,
        headers={"X-Vault-Token": token},
        timeout=5,
    )
    read_response.raise_for_status()
    stored = read_response.json()["data"]["data"]
    if (
        stored.get("client_id") != client_id
        or stored.get("client_secret") != client_secret
    ):
        raise SystemExit("A leitura de validação retornou valores divergentes.")
    print(f"Credencial CargaRH {args.environment} cadastrada e validada.")


if __name__ == "__main__":
    main()
