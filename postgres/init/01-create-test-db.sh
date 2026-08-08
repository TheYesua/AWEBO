#!/usr/bin/env bash
# Crea la BD `awebo_test` la primera vez que el volumen de Postgres se
# inicializa. Si ya existe (re-inicios del contenedor), este script no se
# vuelve a ejecutar (Postgres solo lanza /docker-entrypoint-initdb.d/* en
# instalaciones limpias).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE awebo_test OWNER $POSTGRES_USER;
EOSQL
