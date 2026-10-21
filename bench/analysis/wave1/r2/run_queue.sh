#!/usr/bin/env bash
# R2 five-arm ladder queue: 5 arms x 4 task chunks = 20 jobs, 4 concurrent lanes.
# Each job = one r2_lane.py process (see r2_lane.py: bench.v2_measure machinery,
# 40-task corpus, n=3 seeds -> 30 runs/job, 600 runs total).
set -u
BASE=/tmp/wave1/final/r2
mkdir -p "$BASE/runs" "$BASE/logs"
cd "$BASE"

c1="T-01-ttl-seconds-ms,T-02-off-by-one,T-03-wrong-comparison,T-04-missing-default,T-05-mutable-default,T-06-tz-naive-compare,T-07-f-string-sql,T-08-add-cache-invalidation,T-09-add-rate-limit-hook,T-10-port-dict-keys-view"
c2="T-11-wrong-exception-type,T-12-str-enum-compare,T-13-add-retry-backoff,T-14-add-export-sorting,T-15-stale-registry-entry,T-16-class-state-leak,T-17-log-hour-format,T-18-env-config-precedence,T-19-slug-separator,T-20-average-truncation"
c3="T-21-swallowed-corruption,T-22-case-sort-order,T-23-stack-is-empty,T-24-json-report-flag,T-25-chunked-helper,T-26-plan-dataclass-port,T-27-snakecase-ingest,T-28-plugin-registry-scaffold,T-29-prerelease-version-parsing,T-30-naive-datetime-compare"
c4="T-31-parameter-threading,T-32-sliding-window-limiter,T-33-serializer-contract,T-34-expression-tokenizer,T-35-interval-merge-invariants,A-01-word-count,A-02-protein-translation,A-03-book-store,A-04-connect,A-05-zebra-puzzle"

: > "$BASE/queue.txt"
for chunk in c1 c2 c3 c4; do
  tasks="${!chunk}"            # indirect expansion: $c1..$c4
  for arm in dev-only own-test-only own-iv own-review full; do
    echo "$chunk|$arm|$tasks" >> "$BASE/queue.txt"
  done
done

echo "$(date -Iseconds)|queue-start|jobs=$(wc -l < "$BASE/queue.txt")" >> "$BASE/queue.log"
xargs -a "$BASE/queue.txt" -d '\n' -P 4 -I{} bash "$BASE/job.sh" '{}'
echo "$(date -Iseconds)|queue-done" >> "$BASE/queue.log"
