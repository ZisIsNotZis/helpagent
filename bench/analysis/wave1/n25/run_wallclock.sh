#!/usr/bin/env bash
# Fresh single-lane wall-clock cost subset for BOTH arms (server otherwise idle), same 8
# tasks as the N=9 subset so the two cost columns stay comparable. Our arm: v2_measure
# --wall-clock (one sequential process). pi arm: one sequential pi_baseline process.
set -u
cd /home/z/vibe/helpagent
BASE=/tmp/wave1/final/n25
TASKS="T-01-ttl-seconds-ms,T-04-missing-default,T-14-add-export-sorting,T-24-json-report-flag,T-28-plugin-registry-scaffold,T-32-sliding-window-limiter,T-34-expression-tokenizer,A-01-word-count"
mkdir -p "$BASE/our-wallclock" "$BASE/pi-wallclock"
date -Iseconds > "$BASE/our-wallclock/started_at.txt"
uv run python bench/v2_measure.py --tasks "$TASKS" --n 1 --wall-clock \
  --server http://127.0.0.1:8834 --out "$BASE/our-wallclock" > "$BASE/our-wallclock/lane.log" 2>&1
date -Iseconds > "$BASE/our-wallclock/finished_at.txt"
echo "OUR WALLCLOCK DONE $(cat "$BASE/our-wallclock/finished_at.txt")"

date -Iseconds > "$BASE/pi-wallclock/started_at.txt"
uv run python bench/pi_baseline.py --tasks "$TASKS" --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \
  --out "$BASE/pi-wallclock" > "$BASE/pi-wallclock/lane.log" 2>&1
date -Iseconds > "$BASE/pi-wallclock/finished_at.txt"
echo "PI WALLCLOCK DONE $(cat "$BASE/pi-wallclock/finished_at.txt")"
