#!/bin/bash
# Runs every 5 minutes via cron
# 0/5 * * * * /opt/agencyos/infra/scripts/healthcheck.sh

API_URL="http://localhost:8000/health"
ALERT_EMAIL="admin@yourdomain.com"
LOG_FILE="/var/log/agencyos/healthcheck.log"

mkdir -p /var/log/agencyos

check_service() {
    local name=$1
    local cmd=$2

    if eval "$cmd" > /dev/null 2>&1; then
        echo "[$(date)] ✓ $name OK"
    else
        echo "[$(date)] ✗ $name FAILED — restarting"
        case "$name" in
            "API")       docker restart agencyos_api ;;
            "Celery")    docker restart agencyos_celery_worker ;;
            "Beat")      docker restart agencyos_celery_beat ;;
        esac
    fi
}

{
    check_service "API"    "curl -sf $API_URL"
    check_service "Celery" "docker exec agencyos_celery_worker celery -A celery_worker.celery_app inspect ping --timeout=5"
    check_service "Beat"   "docker ps --filter name=agencyos_celery_beat --filter status=running -q | grep -q ."
} >> "$LOG_FILE" 2>&1

# Keep log under 10MB
if [ "$(du -sm "$LOG_FILE" | cut -f1)" -gt 10 ]; then
    tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi