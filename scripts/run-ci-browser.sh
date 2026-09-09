#!/usr/bin/env bash
# Native CI runner servers. Local Docker profile uses these same fixtures/tests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p backend/artifacts/browser
export ENVIRONMENT=test LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=dummy
export ANTHROPIC_MODEL=e2e-model SYMBOL_RESOLUTION_LLM_ENABLED=false
export ANTHROPIC_BASE_URL=http://127.0.0.1:18092
export CORS_ORIGINS='["http://127.0.0.1:3000"]'
export VITE_API_URL=http://127.0.0.1:18091
export E2E_BACKEND_URL="$VITE_API_URL" PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000
pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
}
trap cleanup EXIT
(cd backend && exec python -m uvicorn tests.e2e.anthropic_stub:app --host 127.0.0.1 --port 18092) >backend/artifacts/browser/llm.log 2>&1 &
pids+=("$!")
(cd backend && exec python -m uvicorn tests.e2e.hardening_app:app --host 127.0.0.1 --port 18091) >backend/artifacts/browser/backend.log 2>&1 &
pids+=("$!")
(cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1) >backend/artifacts/browser/frontend.log 2>&1 &
pids+=("$!")
ready=false
for ((i=0; i<60; i++)); do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then echo 'Browser fixture server exited' >&2; exit 1; fi
  done
  if curl -fsS --max-time 2 "$ANTHROPIC_BASE_URL/health" >/dev/null 2>&1 &&
    curl -fsS --max-time 2 "$E2E_BACKEND_URL/api/health" >/dev/null 2>&1 &&
    curl -fsS --max-time 2 "$PLAYWRIGHT_BASE_URL" >/dev/null 2>&1; then ready=true; break; fi
  sleep 2
done
if [[ "$ready" != true ]]; then echo 'Browser fixture readiness timed out' >&2; exit 1; fi
python scripts/check-runtime-versions.py --backend-url "$E2E_BACKEND_URL"
cd frontend
npm run test:e2e:ci
