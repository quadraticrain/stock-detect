#!/usr/bin/env bash
set -euo pipefail

REPO="quadraticrain/stock-detect"
WORKFLOW="scan-mysql.yml"
LOG="/tmp/stock-detect-sequential-fetch.log"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

wait_run() {
  local run_id="$1" acct="$2"
  log "WATCH @$acct run=$run_id"
  if gh run watch "$run_id" --repo "$REPO" --exit-status >>"$LOG" 2>&1; then
    log "OK @$acct"
  else
    log "FAIL @$acct run=$run_id"
    exit 1
  fi
}

trigger_and_wait() {
  local acct="$1"
  log "START @$acct"
  gh workflow run "$WORKFLOW" --repo "$REPO" \
    -f "accounts=${acct}" \
    -f window_days=180 \
    -f max_posts=4000 \
    -f max_pages=40
  sleep 12
  local run_id
  run_id="$(gh run list --repo "$REPO" --workflow="$WORKFLOW" --limit 1 --json databaseId -q '.[0].databaseId')"
  wait_run "$run_id" "$acct"
}

# If elonmusk run still active, wait for it; else trigger fresh.
ELON_RUN="${1:-27959891643}"
status="$(gh run view "$ELON_RUN" --repo "$REPO" --json status -q .status 2>/dev/null || echo unknown)"
if [ "$status" = "in_progress" ] || [ "$status" = "queued" ]; then
  wait_run "$ELON_RUN" "elonmusk"
elif [ "$status" = "completed" ]; then
  log "SKIP elonmusk already completed run=$ELON_RUN"
else
  trigger_and_wait "elonmusk"
fi

for acct in mingchikuo; do
  trigger_and_wait "$acct"
done

log "ALL DONE"
