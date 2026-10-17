#!/bin/sh
set -eu

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
log_path="/var/lib/agent-quiet-run/ci-${run_id}.log"

exec /opt/agent-quiet-run/bin/quiet-run \
  --label project-ci \
  --log "$log_path" \
  --timeout-seconds 3600 \
  -- /srv/example-project/scripts/ci.sh
