#!/usr/bin/env bash
# One poll: recompute the analysis at the highest fully-complete seed and append a
# checkpoint line (N, per-arm means, delta, CI, rule) to the authorized output file,
# plus a short in-flight progress line. Safe to run repeatedly.
set -u
BASE=/tmp/wave1/final/n25
OUTFILE=/home/z/vibe/helpagent/.scratch/28-three-requirements/issues/fix-wave-1-measurement-n25.md
TS=$(date -Iseconds)

NMAX=17
for k in $(seq 18 25); do
  o=$(cat "$BASE"/our-extra/seed"$k"/lane*/none/results.jsonl 2>/dev/null | wc -l)
  p=$(cat "$BASE"/pi-extra/seed"$k"/lane*/results.jsonl 2>/dev/null | wc -l)
  if [ "$o" -eq 40 ] && [ "$p" -eq 40 ]; then NMAX=$k; fi
done
python3 "$BASE/analyze_n25.py" --nmax "$NMAX" --out "$BASE/analysis-n25.json" --checkpoint "$OUTFILE" > /dev/null

progress=""
for k in $(seq 18 25); do
  o=$(cat "$BASE"/our-extra/seed"$k"/lane*/none/results.jsonl 2>/dev/null | wc -l)
  p=$(cat "$BASE"/pi-extra/seed"$k"/lane*/results.jsonl 2>/dev/null | wc -l)
  if [ "$o" -gt 0 ] || [ "$p" -gt 0 ]; then progress="$progress seed$k:ours$o/40,pi$p/40"; fi
done
alive=$(pgrep -f "run_n25" | head -1)
echo "* ${TS} — checkpoint N=$NMAX (analyzer line above); in-flight:${progress:- none}; driver_pid=${alive:-stopped}." >> "$OUTFILE"
