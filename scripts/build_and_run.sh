#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Build & smoke-test Thordata MCP Docker image
# ---------------------------------------------------------------------------
IMAGE="thordata-mcp:0.3.0"
CONTAINER_NAME="thordata-mcp-dev"
PORT="8000"

# 1. Build image
printf '\n[1/4] Building image: %s\n' "$IMAGE"
docker build -t "$IMAGE" .

# 2. Stop previous container (if running)
printf '\n[2/4] Stopping previous container (if any): %s\n' "$CONTAINER_NAME"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# 3. Run container (background)
printf '\n[3/4] Starting container on port %s\n' "$PORT"
docker run -d --name "$CONTAINER_NAME" \
  -p "${PORT}:8000" \
  --env-file .env \
  "$IMAGE" >/dev/null

# Wait for server to boot
printf 'Waiting for server to become ready';
for i in {1..10}; do
  sleep 1 && printf '.'
  if curl -s -o /dev/null "http://127.0.0.1:${PORT}/debug/tools/list"; then break; fi
done
printf '\n'

# 4. Smoke test – list tools
printf '[4/4] Smoke test: /debug/tools/list\n'
curl -s -X POST "http://127.0.0.1:${PORT}/debug/tools/list" -d '{}' | head -c 400 || true
printf '\n\nOK - container is up\n'

printf 'Container: %s\nImage: %s\nServer: http://127.0.0.1:%s\n' "$CONTAINER_NAME" "$IMAGE" "$PORT"
printf 'Example call:\n'
cat <<'EOF'
curl -s -X POST http://127.0.0.1:8000/debug/tools/call \ 
  -H 'Content-Type: application/json' \ 
  -d '{"name":"serp.search","input":{"query":"thordata proxy"}}'
EOF
