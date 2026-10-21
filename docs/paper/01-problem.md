# 1. The problem: how a harness's "improvement" gets falsified

A coding harness is a wrapper around a language model: intake, planning, editing, testing,
review, delivery. Every wrapper is a bet that a process written as code buys capability that
the same model driving a free-form agent CLI does not have. The bet is cheap to make and
expensive to check, because the wrapper can be its own witness. Four readings make a harness
look improved without any improvement existing:

1. **The harness grades itself.** Its own tests, its own review, its own claim of success.
   With one model behind all of them, a shared misreading can pass code, own test,
   independent test and review together, and the external grader is then the only arbiter
   (`docs/STATUS.md:188`, `docs/LEARNINGS.md:80`).
2. **The comparison is throttled.** If our configuration clamps the baseline — thinking off,
   a small context window — the baseline loses and the harness "wins". The campaign made this
   mistake once and retracted the comparison it produced (`docs/LEARNINGS.md:147`); the
   correction moved the result *against* the harness (`docs/STATUS.md:21`).
3. **The number moves with seeds.** One run of `40` tasks is a draw from a task population
   with large between-task heterogeneity. Any single run can be read as a win, and more runs
   can be collected until one is (`docs/STATUS.md:57`).
4. **The harness can destroy capability it already had.** Delivered bytes were compared
   against every revision the run wrote, not only the ones it claimed; that forensic found
   cases where a revision that already passed the grader was discarded and a failing one
   delivered (T-17 and T-28 — `docs/STATUS.md:67`). The
   campaign's starting position, ours `24/40` against `27/40` (`docs/STATUS.md:64`), was
   therefore a harness-side loss, not a capability ceiling (`docs/LEARNINGS.md:145`).

These four are the design constraints on any measurement that wants to be believed. They
produce the questions this paper answers:

- **R1.** On the same model, does the program-shaped harness beat a mature CLI, within a
  margin fixed before the data was read?
- **R2.** Does the verification ladder — own test, independent test, review, a single claim
  gate — carry information, and what does it cost?
- **R3.** Does decomposing a task into a tree of children, one candidate per approach, buy
  anything over a single monolithic leaf?

The answers, in short and without softening, are: **INCONCLUSIVE** at the pre-registered
margin (`docs/STATUS.md:28`), **partly and not as stated** for verification
(`docs/STATUS.md:29`), and **NEGATIVE** for the current tree bundle (`docs/STATUS.md:30`).
The campaign's goals — parity or superiority, verification that carries information, a product
CLI — remain unmet or unresolved, and are not disproved (`docs/STATUS.md:4`).

## What this paper contributes

1. A measurement protocol in which the scoring instrument never enters the run, the decision
   rule is fixed before any outcome is read, and the interval is task-clustered (§2).
2. A stopping result worth publishing on its own terms: a pre-registered test that returned
   INCONCLUSIVE at its maximum sample size, with a computed reason why more seeds on this
   corpus would not have resolved it (§3).
3. One strong negative point: the leaf fixed `47/70` runs, the two tree arms fixed `14/70` and
   `15/70` (`docs/STATUS.md:109`). It is a negative for a bundle, and §4 states exactly
   what it does and does not refute.
4. A verification ablation with one positive, several unresolved, and an unfavourable cost
   result (§5).
5. The negative results and the retractions as method rather than as debris (§6): each
   retraction names the claim that died and why, and each negative result names a plausible
   design that lost.

The role of the last two items is worth stating plainly, because it is the part of this work
most likely to be reused: a campaign that reports only what worked leaves the next project to
rediscover what did not.
