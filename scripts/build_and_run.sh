#!/usr/bin/env bash
set -euo pipefail

IMAGE="thordata-mcp:0.4.1"
CONTAINER_NAME="thordata-mcp-dev"
PORT="${PORT:-8000}"

printf '\n[1/4] Build %s\n' "$IMAGE"
docker build -t "$IMAGE" .

printf '\n[2/4] Stop previous container\n'
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

printf '\n[3/4] Run container\n'
set +e
docker run -d --name "$CONTAINER_NAME" -p "${PORT}:8000" --env-file .env "$IMAGE" >/dev/null
RUN_EXIT=$?
set -e
if [[ $RUN_EXIT != 0 ]]; then
  echo "❌ docker run failed. Common cause: port ${PORT} is already in use."
  echo "✅ Fix: stop the process using ${PORT}, or run: PORT=8001 bash scripts/build_and_run.sh"
  exit 1
fi

# If container exits immediately, print logs
sleep 1
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "❌ Container exited immediately. Logs:"
  docker logs --tail 200 "$CONTAINER_NAME" || true
  exit 1
fi

printf 'Waiting for /debug/healthz';
for i in {1..60}; do
  sleep 1 && printf '.'
  if curl -s "http://127.0.0.1:${PORT}/debug/healthz" | grep -q '"status":"ok"'; then break; fi
  if [[ $i == 60 ]]; then
    echo "\nTimeout"
    echo "❌ Container logs (last 200 lines):"
    docker logs --tail 200 "$CONTAINER_NAME" || true
    exit 1
  fi
done
printf '\n'

printf '[4/4] Smoke test list\n'
curl -s -X POST "http://127.0.0.1:${PORT}/debug/tools/list" -d '{}' | head -c 400
printf '\nOK\n'