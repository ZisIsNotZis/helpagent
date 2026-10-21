#!/usr/bin/env bash
# Launch the harness arm on disjoint task lanes, one process per lane.
#   run_our_arm.sh <round-name> <n-seeds>
# Each lane is a separate v2_measure process with its own out root
# (/tmp/wave1/final/<round>/<lane>); lanes are merged after they finish.
set -u
cd /home/z/vibe/helpagent
ROUND="$1"
N="$2"
BASE="/tmp/wave1/final/$ROUND"
mkdir -p "$BASE"
while read -r lane tasks; do
  [ -z "${lane:-}" ] && continue
  nohup uv run python bench/v2_measure.py \
    --tasks "$tasks" --n "$N" --server http://127.0.0.1:8834 \
    --out "$BASE/$lane" > "$BASE/$lane.log" 2>&1 &
  echo "launched $lane pid=$! (n=$N)"
done < /tmp/wave1/final/our_lanes.txt
date -Iseconds > "$BASE/started_at.txt"
echo "round=$ROUND n=$N started $(cat "$BASE/started_at.txt")"
