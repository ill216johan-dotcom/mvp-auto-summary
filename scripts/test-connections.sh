#!/bin/bash
# ============================================================
# Test all external service connections
# Run after docker-compose up to verify everything works
# Usage: ./test-connections.sh
# ============================================================

set -euo pipefail

# Load .env if exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    printf "%-35s" "  $name..."
    if eval "$cmd" >/dev/null 2>&1; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  MVP Auto-Summary: Connection Tests"
echo "============================================"
echo ""

echo "[Local Services]"
check "n8n (port ${N8N_PORT:-5678})" \
    "curl -sf http://localhost:${N8N_PORT:-5678}/healthz"

check "open-notebook (port ${NOTEBOOK_PORT:-8888})" \
    "curl -sf http://localhost:${NOTEBOOK_PORT:-8888}/"

check "PostgreSQL (port ${POSTGRES_PORT:-5432})" \
    "pg_isready -h localhost -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-n8n}"

check "SurrealDB (port ${SURREAL_PORT:-8000})" \
    "curl -sf http://localhost:${SURREAL_PORT:-8000}/health"

echo ""
echo "[NFS Mount]"
check "/mnt/recordings mounted" \
    "mountpoint -q /mnt/recordings"

check "/mnt/recordings readable" \
    "ls /mnt/recordings >/dev/null 2>&1"

echo ""
echo "[External APIs]"
check "Yandex SpeechKit API" \
    "curl -sf -o /dev/null -w '%{http_code}' https://transcribe.api.cloud.yandex.net/ | grep -q '40[0-9]\\|200'"

check "Yandex Object Storage" \
    "curl -sf -o /dev/null https://storage.yandexcloud.net/"

check "GLM-4 API (z.ai)" \
    "curl -sf -o /dev/null https://api.z.ai/"

check "Telegram Bot API" \
    "curl -sf 'https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe' | grep -q 'ok'"

echo ""
echo "[Tools]"
check "ffmpeg installed" \
    "which ffmpeg"

check "ffmpeg functional" \
    "ffmpeg -version"

echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Some checks failed. Fix them before running workflows."
    exit 1
fi
