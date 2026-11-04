#!/usr/bin/env bash
# Arranque de la demo: API (uvicorn) y worker (Celery) en el MISMO contenedor (Render free).
#
# - Worker con pool `solo` (un proceso, concurrencia 1) para caber en 512 MB, sin gossip,
#   mingle ni heartbeat (menos comandos en la cuota de Upstash).
# - Si cualquiera de los dos termina, se detiene el otro y el contenedor sale con error: Render
#   lo reinicia. Las migraciones NO corren aquí (las corre deploy.yml antes del deploy).
set -Eeuo pipefail

PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-info}"

celery -A app.workers.celery_app worker \
  --pool=solo --concurrency=1 --prefetch-multiplier=1 \
  --without-gossip --without-mingle --without-heartbeat \
  --loglevel="${LOG_LEVEL,,}" &
worker_pid=$!

uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT}" --workers 1 \
  --proxy-headers --forwarded-allow-ips='*' \
  --no-server-header --log-level "${LOG_LEVEL,,}" &
api_pid=$!

shutdown() {
  kill -TERM "${api_pid}" "${worker_pid}" 2>/dev/null || true
  wait "${api_pid}" "${worker_pid}" 2>/dev/null || true
}
trap 'shutdown; exit 0' TERM INT

# Espera al primero que termine.
set +e
wait -n "${api_pid}" "${worker_pid}"
status=$?
set -e
echo "Un proceso terminó (código ${status}); deteniendo el contenedor." >&2
shutdown
exit "${status:-1}"
