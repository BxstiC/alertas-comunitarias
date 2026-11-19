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

# Mientras siga siendo standby, primary_conninfo se reescribe en cada arranque con el
# PRIMARY_HOST actual y el .pgpass del volumen. Así una réplica creada con otro host
# (p. ej. db-primary en la versión anterior) no queda intentando conectar sin contraseña.
# Si fue promovida (sin standby.signal) no se toca.
if [[ -f "$PGDATA/standby.signal" ]]; then
  # Host y usuario son identificadores simples (sin espacios ni comillas).
  conninfo="host=''$PRIMARY_HOST'' port=$PRIMARY_PORT user=''$REPLICATION_USER'' passfile=''$passfile'' application_name=db-replica"
  sed -i '/^primary_conninfo[[:space:]]*=/d' "$PGDATA/postgresql.auto.conf"
  printf "primary_conninfo = '%s'\n" "$conninfo" >> "$PGDATA/postgresql.auto.conf"
  chown postgres:postgres "$PGDATA/postgresql.auto.conf"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
