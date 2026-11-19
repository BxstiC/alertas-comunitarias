#!/bin/bash
set -Eeuo pipefail

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=replication_user="$REPLICATION_USER" \
  --set=replication_password="$REPLICATION_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I WITH REPLICATION LOGIN PASSWORD %L',
  :'replication_user',
  :'replication_password'
) \gexec
SQL
