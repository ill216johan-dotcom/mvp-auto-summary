#!/bin/bash
# ============================================================
# Backup PostgreSQL and SurrealDB data
# Run daily via cron: 0 2 * * * /path/to/backup-db.sh
# Usage: ./backup-db.sh [backup_dir]
# ============================================================

set -euo pipefail

# Load .env if exists
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/../.env" | xargs)
fi

BACKUP_DIR="${1:-/var/backups/mvp-auto-summary}"
DATE=$(date +%Y-%m-%d_%H-%M)
RETENTION_DAYS=14

mkdir -p "$BACKUP_DIR"

echo "============================================"
echo "  MVP Auto-Summary: Database Backup"
echo "  Date: $DATE"
echo "============================================"

# --- PostgreSQL ---
echo ""
echo "[PostgreSQL]"
PG_BACKUP="$BACKUP_DIR/postgres_${DATE}.sql.gz"
docker exec mvp-auto-summary-postgres-1 \
    pg_dump -U "${POSTGRES_USER:-n8n}" "${POSTGRES_DB:-n8n}" \
    | gzip > "$PG_BACKUP"
echo "  Saved: $PG_BACKUP ($(du -h "$PG_BACKUP" | cut -f1))"

# --- SurrealDB (export) ---
echo ""
echo "[SurrealDB]"
SURREAL_BACKUP="$BACKUP_DIR/surrealdb_${DATE}.surql.gz"
docker exec mvp-auto-summary-surrealdb-1 \
    /surreal export \
    --conn http://localhost:8000 \
    --user "${SURREAL_USER:-root}" \
    --pass "${SURREAL_PASSWORD:-changeme}" \
    --ns open_notebook \
    --db open_notebook \
    - \
    | gzip > "$SURREAL_BACKUP"
echo "  Saved: $SURREAL_BACKUP ($(du -h "$SURREAL_BACKUP" | cut -f1))"

# --- Cleanup old backups ---
echo ""
echo "[Cleanup]"
DELETED=$(find "$BACKUP_DIR" -name "*.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo "  Removed $DELETED backups older than $RETENTION_DAYS days"

echo ""
echo "============================================"
echo "  Backup complete!"
echo "============================================"
