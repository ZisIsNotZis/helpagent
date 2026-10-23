# 8. Reproduce: one command, its keys, and how it fails loudly

Everything in this paper can be re-derived from the repository alone, with no network, no model
server and no access to the campaign's archive. The interface is fixed in the repository's own
node document so that two implementers cannot diverge from it
(`AGENTS.md` §Current facts):

```sh
python3 reproduce.py
```

Run from a clean clone at the repository root. It needs no temporary path, no model server, no
network, and it must not require the untracked campaign archive (`AGENTS.md` §Current facts). It prints one
`key value` line per decisive number and exits 0 only when every printed value equals the value
recorded at campaign time (`AGENTS.md` §Current facts). The paper quotes these keys verbatim, so accepting
this section is a diff and not a reading (`AGENTS.md` §Current facts).

## The keys, verbatim

The six keys the node document names by hand, with the values this paper quotes:

| key | value |
| --- | --- |
| `r1_a_mean_tasks` | `24.640` |
| `r1_delta_tasks` | `-0.320` |
| `r1_lo95` | `-3.520` |
| `r1_hi95` | `3.080` |
| `r3_leaf` | `47/70` |
| `r3_tree_greedy` | `14/70` |

The entry point prints more than those six, and the paper uses every one of them: the baseline's
mean, the row count, the shortfall against the margin, the interval-width quantities of §3
(`r1_width_n17`, `r1_width_n25`, `r1_width_min`, `r1_half_width`, `r1_within_share_pct`,
`r1_asymptotic_width`, `r1_needed_estimate`), `r3_tree_tournament`, the two R3 call means, the
five R2 arm totals, and the R2 contrasts (`r2_full_minus_own_iv_correctness`,
`r2_full_minus_own_iv_ci`, `r2_full_minus_own_iv_p`, `r2_full_minus_own_review_claimed`,
`r2_full_minus_own_review_false`). The node document delegates the R2 rows to the entry point in
the same sentence (`AGENTS.md` §Current facts); the exact key list is what the program prints, and the
numbers table carries every one of them. A key named on the command line selects that line —
`python3 reproduce.py r1_delta_tasks` prints one line — and a key the program does not print is
refused with the list of keys it does.

## Expected output

A correct run prints exactly this, in this order:

```text
r1_a_mean_tasks 24.640
r1_b_mean_tasks 24.960
r1_delta_tasks -0.320
r1_lo95 -3.520
r1_hi95 3.080
r1_rows_per_arm 1000
r1_shortfall_tasks 0.520
r1_width_n17 6.53
r1_width_n25 6.60
r1_width_min 6.43
r1_half_width 3.3
r1_within_share_pct 8.7
r1_asymptotic_width 6.3
r1_needed_estimate 0.3
r3_leaf 47/70
r3_tree_greedy 14/70
r3_tree_tournament 15/70
r3_leaf_mean_calls 14.4
r3_tree_greedy_mean_calls 31.6
r2_arm_dev_only 70/120
r2_arm_own_test 66/120
r2_arm_own_iv 65/120
r2_arm_own_review 71/120
r2_arm_full 77/120
r2_full_minus_own_iv_correctness +4.00
r2_full_minus_own_iv_ci [1.33,7.00]
r2_full_minus_own_iv_p 0.012
r2_full_minus_own_review_claimed -8.67
r2_full_minus_own_review_false -3.00
```

The R2 literals in this block are a re-formatting of the same numbers the ablation table quotes
in task units, which is why the entry point prints them with a sign and two decimals.

## What it asserts before it prints anything

The entry point runs the campaign's own analyzers, unmodified, over a committed projection of
the campaign rows, and compares each analyzer's output with the record committed beside it
before printing a single number: R1 against every key of its record, R2 against its text bytes
and its parsed JSON, R3 and its supplement against their text bytes (`reproduce.py:10`). The
values are not typed in twice; each printed line is read out of the analyzer's own output by a
named pattern, and a pattern that does not match stops the run (`reproduce.py:272`).

It also asserts its inputs. The checks that stop the run, in the order they run, are the ones
the failure mode of §3 needs:

- **a missing input** stops with a line naming the file and what was wanted
  (`reproduce.py:65`);
- **an empty input** stops with a line naming the file, the row count it read and the count it
  wanted (`reproduce.py:70`);
- **a short sample** stops per seed and per arm, naming the arm, the seed, the rows found and
  the rows wanted, before any aggregate is computed (`reproduce.py:116`).

So the reproduction fails loudly by construction: a missing root, a zero-row file and a short
sample each stop the run with a named line before any number is printed
(`AGENTS.md` §Current facts). This is the lesson of the trap in §3 — the campaign's readers return
an empty list for a file that is not there, so a starved input does not raise, it reports a
different experiment (`bench/analysis/wave1/NUMBERS.md:75`).

## The negative control, and what a green run does not mean

A reproduction path is only worth its green run if it fails when the target error is present.
The bounded control is to starve one input in a copy of the repository and run the same command:

```sh
git clone --no-hardlinks . /tmp/starved && cd /tmp/starved
rm -rf bench/projection/wave1/final/n17
python3 reproduce.py; echo "exit=$?"
```

Expected: one named line on standard error naming the missing input and the rows it wanted, no
`key value` line at all, and a non-zero exit. A green run of `python3 reproduce.py` in the
repository therefore means every printed key equals its campaign-time value; it does not mean the
interpretation is right (§7), and it does not prove the campaign archive is intact — that
is the hash manifest's job, and it is a different command.

## Where the numbers table lives

Every number this paper uses — decisive, derived, and unknown — is a row of
[`numbers.md`](numbers.md), with its source coordinates and the command that re-derives it. A
number that no committed command re-derives is marked unknown there with the gap named, and this
paper does not state it as if it had been re-derived.
