#!/bin/bash
set -Eeuo pipefail

export PGDATA="${PGDATA:-/var/lib/postgresql/data}"
export PRIMARY_HOST="${PRIMARY_HOST:-db-primary}"
export PRIMARY_PORT="${PRIMARY_PORT:-5432}"

escaped_host=$(printf '%s' "$PRIMARY_HOST" | sed 's/\\/\\\\/g; s/:/\\:/g')
escaped_user=$(printf '%s' "$REPLICATION_USER" | sed 's/\\/\\\\/g; s/:/\\:/g')
escaped_password=$(printf '%s' "$REPLICATION_PASSWORD" | sed 's/\\/\\\\/g; s/:/\\:/g')
temporary_passfile=/var/lib/postgresql/replica.pgpass
printf '%s:%s:replication:%s:%s\n' \
  "$escaped_host" "$PRIMARY_PORT" "$escaped_user" "$escaped_password" > "$temporary_passfile"
chown postgres:postgres "$temporary_passfile"
chmod 600 "$temporary_passfile"

if [[ ! -s "$PGDATA/PG_VERSION" ]]; then
  mkdir -p "$PGDATA"
  chown postgres:postgres "$PGDATA"

  export PGPASSFILE="$temporary_passfile"
  gosu postgres pg_basebackup \
    --host="$PRIMARY_HOST" \
    --port="$PRIMARY_PORT" \
    --username="$REPLICATION_USER" \
    --pgdata="$PGDATA" \
    --format=plain \
    --wal-method=stream \
    --progress \
    --write-recovery-conf
fi

passfile="$PGDATA/.pgpass"
cp "$temporary_passfile" "$passfile"
chown postgres:postgres "$passfile"
chmod 600 "$passfile"
export PGPASSFILE="$passfile"
unset PGPASSWORD

exec /usr/local/bin/docker-entrypoint.sh "$@"
