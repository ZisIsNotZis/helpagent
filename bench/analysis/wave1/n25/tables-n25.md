### Per-task (ours N=25 · pi N=25)

| task | band | ours act | pi act | ours clm | pi clm | ours false | pi false |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01-word-count | anchors | 1/25 | 4/25 | 1/25 | 4/25 | 1/25 | 1/25 |
| A-02-protein-translation | anchors | 0/25 | 0/25 | 7/25 | 5/25 | 7/25 | 5/25 |
| A-03-book-store | anchors | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 |
| A-04-connect | anchors | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 |
| A-05-zebra-puzzle | anchors | 0/25 | 1/25 | 1/25 | 3/25 | 1/25 | 2/25 |
| T-01-ttl-seconds-ms | easy | 25/25 | 24/25 | 13/25 | 24/25 | 0/25 | 0/25 |
| T-02-off-by-one | easy | 25/25 | 24/25 | 5/25 | 22/25 | 0/25 | 0/25 |
| T-03-wrong-comparison | easy | 23/25 | 23/25 | 0/25 | 22/25 | 0/25 | 0/25 |
| T-04-missing-default | easy | 25/25 | 25/25 | 24/25 | 25/25 | 0/25 | 0/25 |
| T-05-mutable-default | easy | 10/25 | 17/25 | 0/25 | 15/25 | 0/25 | 0/25 |
| T-06-tz-naive-compare | easy | 25/25 | 24/25 | 1/25 | 25/25 | 0/25 | 1/25 |
| T-07-f-string-sql | easy | 23/25 | 25/25 | 0/25 | 24/25 | 0/25 | 0/25 |
| T-08-add-cache-invalidation | easy | 20/25 | 22/25 | 2/25 | 21/25 | 0/25 | 0/25 |
| T-09-add-rate-limit-hook | easy | 24/25 | 17/25 | 5/25 | 12/25 | 0/25 | 1/25 |
| T-10-port-dict-keys-view | easy | 25/25 | 25/25 | 0/25 | 25/25 | 0/25 | 0/25 |
| T-11-wrong-exception-type | mid1 | 25/25 | 25/25 | 0/25 | 23/25 | 0/25 | 0/25 |
| T-12-str-enum-compare | mid1 | 24/25 | 6/25 | 0/25 | 14/25 | 0/25 | 9/25 |
| T-13-add-retry-backoff | mid1 | 1/25 | 6/25 | 0/25 | 3/25 | 0/25 | 0/25 |
| T-14-add-export-sorting | mid1 | 18/25 | 22/25 | 9/25 | 25/25 | 0/25 | 3/25 |
| T-15-stale-registry-entry | mid1 | 24/25 | 23/25 | 24/25 | 22/25 | 0/25 | 0/25 |
| T-16-class-state-leak | mid1 | 17/25 | 25/25 | 9/25 | 24/25 | 0/25 | 0/25 |
| T-17-log-hour-format | mid1 | 22/25 | 20/25 | 3/25 | 15/25 | 0/25 | 0/25 |
| T-18-env-config-precedence | mid1 | 15/25 | 16/25 | 23/25 | 15/25 | 9/25 | 2/25 |
| T-19-slug-separator | mid1 | 25/25 | 25/25 | 6/25 | 24/25 | 0/25 | 0/25 |
| T-20-average-truncation | mid1 | 25/25 | 25/25 | 7/25 | 24/25 | 0/25 | 0/25 |
| T-21-swallowed-corruption | mid2 | 25/25 | 21/25 | 20/25 | 22/25 | 0/25 | 1/25 |
| T-22-case-sort-order | mid2 | 23/25 | 25/25 | 16/25 | 25/25 | 0/25 | 0/25 |
| T-23-stack-is-empty | mid2 | 25/25 | 25/25 | 10/25 | 25/25 | 0/25 | 0/25 |
| T-24-json-report-flag | mid2 | 2/25 | 10/25 | 0/25 | 15/25 | 0/25 | 5/25 |
| T-25-chunked-helper | mid2 | 25/25 | 20/25 | 17/25 | 23/25 | 0/25 | 4/25 |
| T-26-plan-dataclass-port | mid2 | 2/25 | 10/25 | 0/25 | 10/25 | 0/25 | 1/25 |
| T-27-snakecase-ingest | mid2 | 0/25 | 0/25 | 1/25 | 2/25 | 1/25 | 2/25 |
| T-28-plugin-registry-scaffold | mid2 | 7/25 | 10/25 | 0/25 | 23/25 | 0/25 | 14/25 |
| T-29-prerelease-version-parsing | mid2 | 19/25 | 12/25 | 9/25 | 12/25 | 0/25 | 0/25 |
| T-30-naive-datetime-compare | mid2 | 15/25 | 25/25 | 0/25 | 24/25 | 0/25 | 0/25 |
| T-31-parameter-threading | tail | 25/25 | 21/25 | 0/25 | 22/25 | 0/25 | 1/25 |
| T-32-sliding-window-limiter | tail | 2/25 | 0/25 | 2/25 | 5/25 | 2/25 | 5/25 |
| T-33-serializer-contract | tail | 23/25 | 1/25 | 8/25 | 1/25 | 0/25 | 1/25 |
| T-34-expression-tokenizer | tail | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 |
| T-35-interval-merge-invariants | tail | 1/25 | 20/25 | 1/25 | 22/25 | 1/25 | 3/25 |

### Per-band (each cell = mean per-task actual, N=25/task)

| band | ours | pi |
| --- | --- | --- |
| easy (10 tasks) | 9.00/10 | 9.04/10 |
| mid1 (10 tasks) | 7.84/10 | 7.72/10 |
| mid2 (10 tasks) | 5.72/10 | 6.32/10 |
| tail (5 tasks) | 2.04/5 | 1.68/5 |
| anchors (5 tasks) | 0.04/5 | 0.20/5 |
| **total (40 tasks)** | **24.640/40** | **24.960/40** |

### Arm summary

| metric | ours | pi |
| --- | --- | --- |
| actual | 616/1000 = 61.6% | 624/1000 = 62.4% |
| actual per 40-task run | mean 24.640, sd 1.221 | mean 24.960, sd 2.150 |
| claimed (not comparable) | 224/1000 | 647/1000 |
| false success | 22/1000 = 2.20% | 61/1000 = 6.10% |
| wall s/task (4-lane) | 99.8 | 125.4 |
| tokens/task (4-lane) | 18916 | unmeasured (pi carries no token counters) |
| crashes / timeouts | 0 / 0 | 0 / 0 |

Ours seed totals (1..25):
`26, 24, 25, 27, 23, 26, 24, 26, 25, 24, 24, 24, 27, 24, 24, 26, 24, 23, 25, 24, 23, 26, 23, 24, 25`

pi seed totals (1..25):
`24, 24, 23, 23, 24, 28, 23, 26, 27, 27, 27, 26, 25, 22, 27, 26, 26, 30, 21, 25, 24, 21, 25, 25, 25`

