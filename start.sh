#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

export MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_USER="${MYSQL_USER:-root}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-data_agent}"
export DATA_AGENT_OUTPUT_DIR="${DATA_AGENT_OUTPUT_DIR:-outputs/tables}"
export DATA_AGENT_HOST="${DATA_AGENT_HOST:-127.0.0.1}"
export DATA_AGENT_PORT="${DATA_AGENT_PORT:-8011}"
export DATA_AGENT_PYTHON="${DATA_AGENT_PYTHON:-}"

if [ -z "$DATA_AGENT_PYTHON" ]; then
  if [ -x "/usr/local/opt/python@3.10/bin/python3.10" ]; then
    DATA_AGENT_PYTHON="/usr/local/opt/python@3.10/bin/python3.10"
  else
    DATA_AGENT_PYTHON="$(command -v python3)"
  fi
fi

if [ -z "${IWENCAI_API_KEY:-}" ]; then
  echo "ERROR: IWENCAI_API_KEY is not set."
  echo "Set it first, for example:"
  echo "  export IWENCAI_API_KEY='your-key'"
  echo "Or create a .env file from .env.example."
  exit 1
fi

mkdir -p "$DATA_AGENT_OUTPUT_DIR" logs

echo "Installing Python dependencies..."
"$DATA_AGENT_PYTHON" -m pip install -r requirements.txt

MYSQL_ARGS=(
  -h"${MYSQL_HOST}"
  -P"${MYSQL_PORT}"
  -u"${MYSQL_USER}"
)
if [ -n "${MYSQL_PASSWORD}" ]; then
  MYSQL_ARGS+=("-p${MYSQL_PASSWORD}")
fi

echo "Initializing MySQL database '${MYSQL_DATABASE}'..."
MYSQL_READY=0
for attempt in 1 2 3 4 5; do
  if mysql "${MYSQL_ARGS[@]}" -e "SELECT 1" >/dev/null 2>&1; then
    MYSQL_READY=1
    break
  fi
  echo "MySQL is not ready yet, retrying (${attempt}/5)..."
  sleep 1
done

if [ "$MYSQL_READY" = "1" ]; then
  if ! mysql "${MYSQL_ARGS[@]}" < app/storage/schema.sql; then
    echo "WARNING: MySQL schema initialization failed. API will still start; persistence may be degraded."
  fi
else
  echo "WARNING: MySQL is unavailable at ${MYSQL_HOST}:${MYSQL_PORT}. API will still start; persistence may be degraded."
fi

echo "Starting FinDataPilot at http://${DATA_AGENT_HOST}:${DATA_AGENT_PORT}"
echo "Health check: http://${DATA_AGENT_HOST}:${DATA_AGENT_PORT}/health"
exec "$DATA_AGENT_PYTHON" -m uvicorn app.main:app --host "$DATA_AGENT_HOST" --port "$DATA_AGENT_PORT"
