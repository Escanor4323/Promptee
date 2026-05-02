#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker/docker-compose.milvus.yml"
FASTAPI_HOST="${FASTAPI_HOST:-0.0.0.0}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
HEALTH_URL="http://localhost:${FASTAPI_PORT}/api/v1/health"
HEALTH_TIMEOUT=30

cleanup() {
    echo "Shutting down Promptee services..."
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    echo "Shutdown complete."
    exit 0
}

trap cleanup SIGTERM SIGINT

echo "Starting Milvus Standalone..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Starting FastAPI Uvicorn server..."
cd "$PROJECT_DIR/backend"
uvicorn app.main:app --host "$FASTAPI_HOST" --port "$FASTAPI_PORT" > /dev/null 2>&1 &

echo "Waiting for health check at $HEALTH_URL (timeout: ${HEALTH_TIMEOUT}s)..."
elapsed=0
while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        echo "Health check passed. Promptee is ready."
        exit 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done

echo "ERROR: Health check failed after ${HEALTH_TIMEOUT}s. Aborting."
cleanup
exit 1
