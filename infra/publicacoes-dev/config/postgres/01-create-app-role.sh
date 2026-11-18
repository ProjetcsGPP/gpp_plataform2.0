#!/bin/sh
set -eu

app_password="$(cat "${GPP_APP_PASSWORD_FILE}")"

psql \
  --set=ON_ERROR_STOP=1 \
  --set=app_password="${app_password}" \
  --set=db_name="${POSTGRES_DB}" \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" <<'SQL'
SELECT 'CREATE ROLE gpp_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gpp_app')
\gexec

ALTER ROLE gpp_app WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    PASSWORD :'app_password';

ALTER SCHEMA public OWNER TO gpp_app;
CREATE SCHEMA IF NOT EXISTS acoes_pngi AUTHORIZATION gpp_app;
CREATE SCHEMA IF NOT EXISTS carga_org_lot AUTHORIZATION gpp_app;
CREATE SCHEMA IF NOT EXISTS publicacoes AUTHORIZATION gpp_app;
ALTER SCHEMA acoes_pngi OWNER TO gpp_app;
ALTER SCHEMA carga_org_lot OWNER TO gpp_app;
ALTER SCHEMA publicacoes OWNER TO gpp_app;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO gpp_app;
GRANT ALL PRIVILEGES ON SCHEMA public TO gpp_app;
SQL
