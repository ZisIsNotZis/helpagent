#!/usr/bin/env bash
# N=25 driver (segregated mode, identical to the N=17 run's final driver): add seeds
# 18..25 to BOTH arms, four disjoint lanes each, on :8834 -- but ONE ARM AT A TIME within
# each seed round (our 4 lanes, wait; then pi 4 lanes, wait). Rationale kept from the N=17
# run: on this host the isolated 4-process arm rates beat the 8-process concurrent rate
# (measured again here: ~1.9 rows/min concurrent vs ~2.0+ rows/min segregated), because the
# two arms contend for the same 12 cores and 4 server slots. Same drivers, same lanes,
# same rule. A seed advances the analysis nmax only when BOTH arms have exactly 40 rows.
# Resume-safe; stops early on ACHIEVED or BEHIND.
set -u
cd /home/z/vibe/helpagent
BASE=/tmp/wave1/final/n25
OUTFILE=/home/z/vibe/helpagent/.scratch/28-three-requirements/issues/fix-wave-1-measurement-n25.md
LOG=$BASE/driver-seg.log
mkdir -p "$BASE"
date -Iseconds >> "$LOG"; echo "n25 seg driver start pid=$$" >> "$LOG"

rows_ours() { cat "$BASE"/our-extra/seed"$1"/lane*/none/results.jsonl 2>/dev/null | wc -l; }
rows_pi()   { cat "$BASE"/pi-extra/seed"$1"/lane*/results.jsonl 2>/dev/null | wc -l; }

run_our_round() {
  local k="$1" pids=""
  while read -r lane tasks; do
    [ -z "${lane:-}" ] && continue
    uv run python bench/v2_measure.py --tasks "$tasks" --n 1 \
      --server http://127.0.0.1:8834 --out "$BASE/our-extra/seed$k/$lane" \
      > "$BASE/our-extra/seed$k/$lane.log" 2>&1 &
    pids="$pids $!"
  done < /tmp/wave1/final/our_lanes.txt
  wait $pids
}

run_pi_round() {
  local k="$1" pids=""
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
    if [ "$(rows_ours "$k")" -lt 40 ]; then
      date -Iseconds >> "$LOG"; echo "seed $k OUR round LAUNCH" >> "$LOG"
      run_our_round "$k"
      date -Iseconds >> "$LOG"; echo "seed $k OUR round DONE rows=$(rows_ours "$k")" >> "$LOG"
    fi
    if [ "$(rows_pi "$k")" -lt 40 ]; then
      date -Iseconds >> "$LOG"; echo "seed $k PI round LAUNCH" >> "$LOG"
      run_pi_round "$k"
      date -Iseconds >> "$LOG"; echo "seed $k PI round DONE rows=$(rows_pi "$k")" >> "$LOG"
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
    date -Iseconds >> "$LOG"; echo "n25 seg driver STOP: verdict=$V at nmax=$NMAX" >> "$LOG"
    echo "N25_SEG_DRIVER_DONE verdict=$V seed=$NMAX"
    exit 0
  fi
done
date -Iseconds >> "$LOG"; echo "n25 seg driver STOP: reached N=25 (rule unresolved)" >> "$LOG"
echo "N25_SEG_DRIVER_DONE verdict=N25 seed=25"
