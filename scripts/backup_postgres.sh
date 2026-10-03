#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=./backups}"
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
pg_dump "$DATABASE_URL" --format=custom --file="$BACKUP_DIR/dina-$stamp.dump"
pg_restore --list "$BACKUP_DIR/dina-$stamp.dump" >/dev/null
echo "Backup verified: $BACKUP_DIR/dina-$stamp.dump"
