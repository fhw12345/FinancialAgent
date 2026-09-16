#!/usr/bin/env bash
# Same recorded external boundaries locally/CI; real application routes and storage.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
profile="${1:-hardening}"
case "$profile" in hardening|copilot|decision)  ;; *) echo 'Unknown browser profile' >&2; exit 2;; esac
logs="backend/artifacts/browser/$profile"
mkdir -p "$logs"
# Preserve the previous lane's reports before Playwright replaces its output dirs.
if [[ "$profile" != hardening ]]; then
  previous="$(mktemp -d backend/artifacts/browser/previous-XXXXXX)"
  for dir in playwright-report test-results; do
    if [[ -d "frontend/$dir" ]]; then mv "frontend/$dir" "$previous/$dir"; fi
  done
fi
export ENVIRONMENT=test SYMBOL_RESOLUTION_LLM_ENABLED=false
export CORS_ORIGINS='["http://127.0.0.1:3000"]'
export VITE_API_URL=http://127.0.0.1:18091
export E2E_BACKEND_URL="$VITE_API_URL" PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000
pids=()
auth_dir=""
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
  if [[ -n "$auth_dir" ]]; then rm -rf -- "$auth_dir"; fi
}
trap cleanup EXIT
if [[ "$profile" == hardening ]]; then
  export LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=dummy ANTHROPIC_MODEL=e2e-model
  export ANTHROPIC_BASE_URL=http://127.0.0.1:18092
  fixture=hardening_app
  suite=test:e2e:ci
  (cd backend && exec python -m uvicorn tests.e2e.anthropic_stub:app --host 127.0.0.1 --port 18092) >"$logs/llm.log" 2>&1 &
  pids+=("$!")
else
  export LLM_PROVIDER=github_copilot
  auth_dir="$(mktemp -d)" # Never put even recorded credentials in CI artifacts.
  export COPILOT_STATE_DIR="$auth_dir"
  if [[ "$profile" == decision ]]; then
    fixture=decision_policy_app
    suite=test:e2e:decision-safety
  else
    fixture=copilot_app
    suite=test:e2e:copilot
  fi
fi
(cd backend && exec python -m uvicorn "tests.e2e.$fixture:app" --host 127.0.0.1 --port 18091) >"$logs/backend.log" 2>&1 &
pids+=("$!")
(cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1) >"$logs/frontend.log" 2>&1 &
pids+=("$!")
ready=false
for ((i=0; i<60; i++)); do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then echo 'Browser fixture server exited' >&2; exit 1; fi
  done
  if [[ "$profile" == hardening ]] && ! curl -fsS --max-time 2 "$ANTHROPIC_BASE_URL/health" >/dev/null 2>&1; then sleep 2; continue; fi
  if curl -fsS --max-time 2 "$E2E_BACKEND_URL/api/health" >/dev/null 2>&1 &&
    curl -fsS --max-time 2 "$PLAYWRIGHT_BASE_URL" >/dev/null 2>&1; then ready=true; break; fi
  sleep 2
done
if [[ "$ready" != true ]]; then echo 'Browser fixture readiness timed out' >&2; exit 1; fi
python scripts/check-runtime-versions.py --backend-url "$E2E_BACKEND_URL"
cd frontend
npm run "$suite"
