#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Usage: $0 --confirm /path/to/backup.dump" >&2
  exit 2
fi
: "${DATABASE_URL:?DATABASE_URL is required}"
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$2"
echo "restore completed"
