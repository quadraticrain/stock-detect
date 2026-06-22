#!/usr/bin/env bash
# Resume sequential 180d fetch from a given account list.
set -euo pipefail

REPO="quadraticrain/stock-detect"
WORKFLOW="scan-mysql.yml"
ACCOUNTS=("$@")

if [ "${#ACCOUNTS[@]}" -eq 0 ]; then
  echo "usage: $0 account1 [account2 ...]" >&2
  exit 1
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a /tmp/stock-detect-sequential-fetch.log; }

for acct in "${ACCOUNTS[@]}"; do
  log "START @$acct"
  gh workflow run "$WORKFLOW" --repo "$REPO" \
    -f "accounts=${acct}" \
    -f window_days=180 \
    -f max_posts=4000 \
    -f max_pages=40
  sleep 10
  run_id="$(gh run list --repo "$REPO" --workflow="$WORKFLOW" --limit 1 --json databaseId,headBranch -q '.[0] | select(.headBranch=="main") | .databaseId')"
  if [ -z "$run_id" ]; then
    log "ERROR: could not resolve run_id for $acct"
    exit 1
  fi
  log "WATCH run_id=$run_id account=$acct url=https://github.com/$REPO/actions/runs/$run_id"
  if gh run watch "$run_id" --repo "$REPO" --exit-status >>/tmp/stock-detect-sequential-fetch.log 2>&1; then
    log "OK @$acct"
  else
    log "FAILED @$acct run=$run_id"
    exit 1
  fi
done

log "ALL DONE accounts=${ACCOUNTS[*]}"
