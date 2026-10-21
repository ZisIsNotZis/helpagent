#!/usr/bin/env bash
# One R2 lane job: run ONE arm over ONE task chunk, n=3 seeds.
# Usage (from xargs): job.sh '<chunk>|<arm>|<comma tasks>'
set -u
cd /home/z/vibe/helpagent
BASE=/tmp/wave1/final/r2
line="$1"
chunk="${line%%|*}"; rest="${line#*|}"; arm="${rest%%|*}"; tasks="${rest#*|}"
out="$BASE/runs/$chunk/$arm"
log="$BASE/logs/$chunk-$arm.log"
mkdir -p "$out" "$BASE/logs"
t0=$(date +%s)
uv run python "$BASE/r2_lane.py" --arm "$arm" --tasks "$tasks" --n 3 \
  --server http://127.0.0.1:8834 --out "$out" > "$log" 2>&1
rc=$?
t1=$(date +%s)
echo "$(date -Iseconds)|job-done|$chunk|$arm|rc=$rc|secs=$((t1-t0))" >> "$BASE/queue.log"
exit $rc
