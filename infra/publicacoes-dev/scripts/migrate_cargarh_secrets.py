#!/usr/bin/env python3
"""Migra as credenciais CargaRH do .env para o OpenBao local."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import django
import requests


PROJECT_DIR = Path(__file__).resolve().parents[3]
INFRA_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_DIR / ".env"
OPENBAO_RUNTIME = INFRA_DIR / "runtime" / "openbao"


def _setting_line(key, value):
    return f"{key}={json.dumps(str(value), ensure_ascii=False)}\n"


def _rewrite_env(settings):
    environment = settings.CARGARH_ENVIRONMENT
    selected_prefix = f"CARGARH_{environment}"
    selected_values = {
        f"{selected_prefix}_TOKEN_URL": settings.CARGARH_TOKEN_URL,
        f"{selected_prefix}_API_BASE_URL": settings.CARGARH_API_BASE_URL,
        f"{selected_prefix}_CLIENT_SCOPE": settings.CARGARH_CLIENT_SCOPE,
        f"{selected_prefix}_TARGET_ENVIRONMENT": (
            settings.CARGARH_TARGET_ENVIRONMENT
        ),
    }
    removed_keys = {
        "CARGARH_CLIENT_ID",
        "CARGARH_CLIENT_SECRET",
        "CARGARH_CREDENTIALS_PROVIDER",
        "CARGARH_TOKEN_URL",
        "CARGARH_API_BASE_URL",
        "CARGARH_CLIENT_SCOPE",
        "CARGARH_TARGET_ENVIRONMENT",
        *selected_values,
    }
    original_lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    preserved = []
    existing_keys = set()
    for line in original_lines:
        stripped = line.lstrip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in removed_keys:
            continue
        if key:
            existing_keys.add(key)
        preserved.append(line if line.endswith("\n") else f"{line}\n")

    additions = [
        "\n# CargaRH/PRODEST: credenciais no OpenBao; somente configuração aqui.\n",
        _setting_line("CARGARH_CREDENTIALS_PROVIDER", "openbao"),
    ]
    additions.extend(
        _setting_line(key, value) for key, value in selected_values.items()
    )
    other_environment = "PRD" if environment == "HML" else "HML"
    for suffix in (
        "TOKEN_URL",
        "API_BASE_URL",
        "CLIENT_SCOPE",
        "TARGET_ENVIRONMENT",
    ):
        key = f"CARGARH_{other_environment}_{suffix}"
        if key not in existing_keys:
            additions.append(_setting_line(key, ""))

    mode = stat.S_IMODE(ENV_FILE.stat().st_mode)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ENV_FILE.parent,
            prefix=".env.cargarh.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.writelines(preserved + additions)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, ENV_FILE)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main():
    sys.path.insert(0, str(PROJECT_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    django.setup()

    from django.conf import settings

    from apps.core.services.secret_store import OpenBaoAppRoleKV2Store

    environment = settings.CARGARH_ENVIRONMENT
    if environment not in {"HML", "PRD"}:
        raise SystemExit("CARGARH_ENVIRONMENT deve ser HML ou PRD.")
    client_id = settings.CARGARH_CLIENT_ID.strip()
    client_secret = settings.CARGARH_CLIENT_SECRET.strip()
    if not client_id or not client_secret:
        raise SystemExit("As credenciais legadas do CargaRH não estão disponíveis.")

    init_data = json.loads(
        (OPENBAO_RUNTIME / "init.json").read_text(encoding="utf-8")
    )
    root_token = init_data["root_token"]
    environment_lower = environment.lower()
    address = settings.OPENBAO_ADDR.rstrip("/")
    secret_path = f"dev/cargarh/{environment_lower}"
    response = requests.post(
        f"{address}/v1/carga-org-lot/data/{secret_path}",
        headers={"X-Vault-Token": root_token},
        json={
            "data": {
                "client_id": client_id,
                "client_secret": client_secret,
            }
        },
        timeout=settings.OPENBAO_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    store = OpenBaoAppRoleKV2Store(
        address=address,
        role_id_file=(
            OPENBAO_RUNTIME / f"carga_org_lot_{environment_lower}_role_id"
        ),
        secret_id_file=(
            OPENBAO_RUNTIME / f"carga_org_lot_{environment_lower}_secret_id"
        ),
        mount_point="carga-org-lot",
        secret_path=secret_path,
        timeout=settings.OPENBAO_TIMEOUT_SECONDS,
        allow_insecure_loopback=settings.DEBUG,
    )
    stored = store.read()
    if (
        stored.get("client_id") != client_id
        or stored.get("client_secret") != client_secret
    ):
        raise SystemExit("A validação das credenciais gravadas no cofre falhou.")

    _rewrite_env(settings)
    print(
        f"Credenciais CargaRH {environment} migradas; valores removidos do .env."
    )


if __name__ == "__main__":
    main()
