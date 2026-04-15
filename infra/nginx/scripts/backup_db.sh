#!/bin/bash
# Daily PostgreSQL backup for Agency OS
# Add to crontab: 0 2 * * * /opt/agencyos/infra/scripts/backup_db.sh

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
DB_HOST="DATA_VM_TAILSCALE_IP"
DB_USER="agencyos_user"
DB_NAME="agencyos"
BACKUP_DIR="/opt/agencyos/backups/postgres"
RETAIN_DAYS=14
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/agencyos_${TIMESTAMP}.sql.gz"

# ── Create backup dir ─────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup: $BACKUP_FILE"

# ── Dump and compress ─────────────────────────────────────────────────────────
PGPASSWORD="${PGPASSWORD:-}" pg_dump \
    -h "$DB_HOST" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-password \
    --verbose \
    --format=plain \
    | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup complete: $(du -sh "$BACKUP_FILE" | cut -f1)"

# ── Remove old backups ────────────────────────────────────────────────────────
find "$BACKUP_DIR" -name "agencyos_*.sql.gz" -mtime +"$RETAIN_DAYS" -delete
echo "[$(date)] Cleaned backups older than ${RETAIN_DAYS} days"

# ── Also backup Qdrant data ───────────────────────────────────────────────────
QDRANT_BACKUP_DIR="/opt/agencyos/backups/qdrant"
mkdir -p "$QDRANT_BACKUP_DIR"

# Snapshot via Qdrant REST API
curl -sf "http://DATA_VM_TAILSCALE_IP:6333/snapshots" -X POST \
    -H "Content-Type: application/json" \
    -d '{}' \
    --output "$QDRANT_BACKUP_DIR/snapshot_${TIMESTAMP}.json" \
    && echo "[$(date)] Qdrant snapshot created" \
    || echo "[$(date)] WARNING: Qdrant snapshot failed"

echo "[$(date)] All backups complete"