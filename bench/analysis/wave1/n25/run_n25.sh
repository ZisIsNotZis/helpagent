#!/usr/bin/env bash
# N=25 driver: add seeds 18..25 to BOTH arms, 4 disjoint lanes each, all 8 lane
# processes concurrently per seed round, on :8834. Same drivers/config as the N=17 run
# (ours: bench/v2_measure.py --n 1; pi: bench/pi_baseline.py --n 1 --reasoning
# --thinking max with a per-run temp agent dir). Resume-safe; stops early on
# ACHIEVED or BEHIND. A seed only advances the analysis nmax when BOTH arms have
# exactly 40 rows, so a partial round can never enter the CI.
set -u
cd /home/z/vibe/helpagent
BASE=/tmp/wave1/final/n25
OUTFILE=/home/z/vibe/helpagent/.scratch/28-three-requirements/issues/fix-wave-1-measurement-n25.md
LOG=$BASE/driver.log
mkdir -p "$BASE"
date -Iseconds >> "$LOG"; echo "n25 driver start pid=$$" >> "$LOG"

rows_ours() { cat "$BASE"/our-extra/seed"$1"/lane*/none/results.jsonl 2>/dev/null | wc -l; }
rows_pi()   { cat "$BASE"/pi-extra/seed"$1"/lane*/results.jsonl 2>/dev/null | wc -l; }

run_round() {
  local k="$1" pids=""
  while read -r lane tasks; do
    [ -z "${lane:-}" ] && continue
    uv run python bench/v2_measure.py --tasks "$tasks" --n 1 \
      --server http://127.0.0.1:8834 --out "$BASE/our-extra/seed$k/$lane" \
      > "$BASE/our-extra/seed$k/$lane.log" 2>&1 &
    pids="$pids $!"
  done < /tmp/wave1/final/our_lanes.txt
  while read -r lane tasks; do
    [ -z "${lane:-}" ] && continue
    uv run python bench/pi_baseline.py --tasks "$tasks" --n 1 \
      --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \
      --out "$BASE/pi-extra/seed$k/$lane" > "$BASE/pi-extra/seed$k/$lane.log" 2>&1 &
    pids="$pids $!"
  done < /tmp/wave1/final/pi_lanes.txt
  wait $pids
}

NMAX=17
for k in $(seq 18 25); do
  mkdir -p "$BASE/our-extra/seed$k" "$BASE/pi-extra/seed$k"
  if [ "$(rows_ours "$k")" -eq 40 ] && [ "$(rows_pi "$k")" -eq 40 ]; then
    date -Iseconds >> "$LOG"; echo "seed $k already complete (skip)" >> "$LOG"
  else
    if [ "$(rows_ours "$k")" -ne 0 ] || [ "$(rows_pi "$k")" -ne 0 ]; then
      date -Iseconds >> "$LOG"; echo "seed $k PARTIAL ours=$(rows_ours "$k") pi=$(rows_pi "$k"): clearing" >> "$LOG"
      rm -rf "$BASE/our-extra/seed$k" "$BASE/pi-extra/seed$k"
      mkdir -p "$BASE/our-extra/seed$k" "$BASE/pi-extra/seed$k"
    fi
    date -Iseconds >> "$LOG"; echo "seed $k round LAUNCH (8 lanes concurrent)" >> "$LOG"
    run_round "$k"
    date -Iseconds >> "$LOG"; echo "seed $k round DONE ours=$(rows_ours "$k") pi=$(rows_pi "$k")" >> "$LOG"
    if [ "$(rows_ours "$k")" -ne 40 ] || [ "$(rows_pi "$k")" -ne 40 ]; then
      date -Iseconds >> "$LOG"; echo "seed $k INCOMPLETE: one clean retry" >> "$LOG"
      rm -rf "$BASE/our-extra/seed$k" "$BASE/pi-extra/seed$k"
      mkdir -p "$BASE/our-extra/seed$k" "$BASE/pi-extra/seed$k"
      run_round "$k"
      date -Iseconds >> "$LOG"; echo "seed $k retry DONE ours=$(rows_ours "$k") pi=$(rows_pi "$k")" >> "$LOG"
    fi
  fi

  if [ "$(rows_ours "$k")" -eq 40 ] && [ "$(rows_pi "$k")" -eq 40 ]; then NMAX=$k; fi
  date -Iseconds >> "$LOG"; echo "seed $k advancing nmax=$NMAX" >> "$LOG"

  CHK=$(python3 "$BASE/analyze_n25.py" --nmax "$NMAX" --out "$BASE/analysis-n25.json" \
        --checkpoint "$OUTFILE" 2>>"$LOG")
  V=$(printf '%s' "$CHK" | python3 -c "import sys,json;print(json.load(sys.stdin)['verdict'])" 2>>"$LOG")
  date -Iseconds >> "$LOG"; echo "seed $k (nmax=$NMAX) verdict=$V" >> "$LOG"
  echo "$CHK" >> "$LOG"
  if [ "$V" = "ACHIEVED" ] || [ "$V" = "BEHIND" ]; then
    date -Iseconds >> "$LOG"; echo "n25 driver STOP: verdict=$V at nmax=$NMAX" >> "$LOG"
    echo "N25_DRIVER_DONE verdict=$V seed=$NMAX"
    exit 0
  fi
done
date -Iseconds >> "$LOG"; echo "n25 driver STOP: reached N=25 (rule unresolved)" >> "$LOG"
echo "N25_DRIVER_DONE verdict=N25 seed=25"
