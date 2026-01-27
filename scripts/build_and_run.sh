#!/usr/bin/env bash
set -euo pipefail

IMAGE="thordata-mcp:0.3.0"
CONTAINER_NAME="thordata-mcp-dev"
PORT="8000"

echo "[1/4] Building image: ${IMAGE}"
docker build -t "${IMAGE}" .

echo "[2/4] Stopping previous container (if any): ${CONTAINER_NAME}"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

echo "[3/4] Starting container on port ${PORT}"
docker run -d --name "${CONTAINER_NAME}" -p "${PORT}:8000" --env-file .env "${IMAGE}" >/dev/null

echo "Waiting for server to become ready..."
sleep 3

echo "[4/4] Smoke test: /debug/tools/list"
curl -s -X POST "http://127.0.0.1:${PORT}/debug/tools/list" -d '{}' | head -c 400

echo

echo "OK"
echo "Container: ${CONTAINER_NAME}"
echo "Image: ${IMAGE}"
echo "Server: http://127.0.0.1:${PORT}"
echo "Example: curl -s -X POST http://127.0.0.1:${PORT}/debug/tools/call -H 'Content-Type: application/json' -d '{\"name\":\"serp.search\",\"input\":{\"query\":\"thordata proxy\"}}'"
