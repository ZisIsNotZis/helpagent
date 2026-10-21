#!/usr/bin/env bash
# R2 RESUME queue: the 9 (chunk, arm) jobs the dead worker left incomplete.
# -P 4 lanes, matching the original run_queue.sh concurrency (server n_slots=4).
# Heaviest ("full") jobs first so they occupy lanes longest.
set -u
BASE=/tmp/wave1/final/r2
mkdir -p "$BASE/runs" "$BASE/logs"
cd "$BASE"

c2="T-11-wrong-exception-type,T-12-str-enum-compare,T-13-add-retry-backoff,T-14-add-export-sorting,T-15-stale-registry-entry,T-16-class-state-leak,T-17-log-hour-format,T-18-env-config-precedence,T-19-slug-separator,T-20-average-truncation"
c3="T-21-swallowed-corruption,T-22-case-sort-order,T-23-stack-is-empty,T-24-json-report-flag,T-25-chunked-helper,T-26-plan-dataclass-port,T-27-snakecase-ingest,T-28-plugin-registry-scaffold,T-29-prerelease-version-parsing,T-30-naive-datetime-compare"
c4="T-31-parameter-threading,T-32-sliding-window-limiter,T-33-serializer-contract,T-34-expression-tokenizer,T-35-interval-merge-invariants,A-01-word-count,A-02-protein-translation,A-03-book-store,A-04-connect,A-05-zebra-puzzle"

: > "$BASE/resume_queue.txt"
for line in \
  "c4|full|$c4" "c3|full|$c3" "c2|full|$c2" "c4|own-review|$c4" \
  "c4|own-iv|$c4" "c3|own-review|$c3" "c3|own-iv|$c3" \
  "c4|own-test-only|$c4" "c4|dev-only|$c4"; do
  echo "$line" >> "$BASE/resume_queue.txt"
done

echo "$(date -Iseconds)|resume-queue-start|jobs=$(wc -l < "$BASE/resume_queue.txt")" >> "$BASE/queue.log"
xargs -a "$BASE/resume_queue.txt" -d '\n' -P 4 -I{} bash "$BASE/job_resume.sh" '{}'
echo "$(date -Iseconds)|resume-queue-done" >> "$BASE/queue.log"
