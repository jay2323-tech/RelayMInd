#!/bin/sh
# Start FalkorDB inside the container (localhost only, random password), then the RelayMind app.
set -e
export FALKORDB_HOST=127.0.0.1
export FALKORDB_PORT=6379
if [ -z "${FALKORDB_PASSWORD}" ]; then
  FALKORDB_PASSWORD="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  export FALKORDB_PASSWORD
fi
mkdir -p "${HOME}/falkordb-data"
redis-server --bind 127.0.0.1 --port 6379 --protected-mode yes \
  --requirepass "${FALKORDB_PASSWORD}" --dir "${HOME}/falkordb-data" --appendonly yes \
  --loadmodule /var/lib/falkordb/bin/falkordb.so --daemonize yes
exec /opt/venv/bin/python scripts/prod_start.py
