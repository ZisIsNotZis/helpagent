#!/usr/bin/env bash
# One lane of the r3 experiment. Processes jobs assigned by round-robin index.
#   lane.sh <lane_index> <nlanes> <port> [jobfile]
# Job file lines: "<arm> <task> <seed>"
# Skips jobs whose run.json already exists (resumable / already-measured seed 1).
set -u
LANE="$1"; NLANES="$2"; PORT="$3"; JOBFILE="${4:-/tmp/wave1/final/r3/jobs.txt}"
R3=/tmp/wave1/final/r3
cd /home/z/vibe/helpagent
LOG="$R3/logs/lane$LANE.log"
echo "[lane$LANE] START port=$PORT $(date -Iseconds)" >> "$LOG"
i=0
while read -r arm task seed; do
  [ -z "${arm:-}" ] && continue
  i=$((i+1))
  if [ $(( (i-1) % NLANES )) -ne "$LANE" ]; then continue; fi
  out="$R3/$arm/$task-$seed"
  if [ -f "$out/run.json" ]; then
    echo "[lane$LANE] skip(have) $arm $task $seed" >> "$LOG"; continue
  fi
  case "$arm" in
    leaf)
      drv="bench/v2_leaf.py"; extra="--verify full" ;;
    tree-greedy)
      drv="bench/v2_tree.py"; extra="--how-explore 1" ;;
    tree-tournament)
      drv="bench/v2_tree.py"; extra="--how-explore 3" ;;
    *) echo "[lane$LANE] UNKNOWN arm $arm" >> "$LOG"; continue ;;
  esac
  case "$task" in A-*) root=bench/anchor;; *) root=bench/corpus;; esac
  mkdir -p "$out"
  t0=$(date +%s)
  echo "[lane$LANE] start $arm $task $seed $(date -Iseconds)" >> "$LOG"
  timeout 3900 uv run python "$drv" --task "$root/$task" \
     --server "http://127.0.0.1:$PORT" --calls 48 --deadline-hours 1 \
     $extra --out "$out" > "$out/run.log" 2>&1
  rc=$?
  echo "[lane$LANE] done  $arm $task $seed rc=$rc $(( $(date +%s) - t0 ))s $(date -Iseconds)" >> "$LOG"
done < "$JOBFILE"
echo "[lane$LANE] ALL DONE $(date -Iseconds)" >> "$LOG"
