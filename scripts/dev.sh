#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_python="${project_dir}/.venv/bin/python"

if [[ ! -x "${backend_python}" ]]; then
  echo "RoadTrace backend environment is missing. Follow the setup steps in README.md first." >&2
  exit 1
fi

cleanup() {
  if [[ -n "${api_pid:-}" ]]; then
    kill "${api_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"${backend_python}" -m uvicorn app.main:app \
  --app-dir "${project_dir}/backend" \
  --host 127.0.0.1 \
  --port 8000 \
  --reload &
api_pid=$!

cd "${project_dir}/frontend"
npm run dev
