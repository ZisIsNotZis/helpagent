kind:    cost
from:    helpagent
to:      root
spend:   person_time — minutes: read the path, the four evidence lines, and name whether publication proceeds
id:      2026-10-23 paper-or-repair, answered by the person as a rule; this is the answer applied

**Path taken: the paper's. P1a is not one of its tools, so P1a is not the 短板 the rule repairs
first.** The person answered with a rule rather than a choice, and the rule is the test: "we can't
wait for research done, so it's fix the 短板 first before doing more research; if tool needed to
write paper, fix that, otherwise do paper first". Applied to this tree, the preprint's claims,
numbers and reproduce commands need nothing P1a changed. The repair cycle their answer made
available is therefore unspent, and P1a stays BLOCKED at its two-review cap.

**The evidence, by file line, because the decision is only as good as what it rests on.** Every
number the draft uses re-derives through one of four commands, all of them outside `harness/`:
a printed key of `python3 reproduce.py` (`docs/paper/numbers.md:21-25`, `:51-53`, `:84-88`), the
bare entry point, an analyzer under `bench/analysis/wave1/`, or `unknown` with the gap named. Four
things settle it:

- No number and no command touches the harness. `grep -c 'harness/' docs/paper/numbers.md
  reproduce.py` prints `0` for both: no `Source` cell in the numbers table names a harness file,
  and the entry point does not import one.
- The four scripts the entry point executes — `analyze_n25.py`, `r2_analyze.py`, `r3/analyze.py`,
  `r3/supp.py` (`reproduce.py:78`, `:176`, `:229`, `:245`) — import nothing outside the standard
  library and mention no harness path. `r2_lane.py` does mention `harness.leaf`, in a docstring;
  it is the driver that produced the rows, not something the entry point runs.
- The draft cites harness source exactly once, in the limit that discloses the coupling and never
  in support of a result: `grep -rn 'harness/' docs/paper/` prints one line,
  `docs/paper/07-limits.md:39`. Everything else it cites is `docs/STATUS.md`, `FINDINGS.md`,
  `docs/LEARNINGS.md`, `bench/analysis/wave1/`, `bench/external_score.py`,
  `bench/corpus/README.md`, `docs/ROADMAP.md` or `docs/paper-plan.md`. Of the three files P1a
  changed (`harness/leaf.py`, `tests/unit/test_own_test_setup.py`, `tests/unit/test_v2_leaf.py` at
  `999ea9a`) it meets one, `leaf.py`, and only through that disclosure.
- The counterexample the final review blocked P1a on cannot exist inside the measured revision:
  `git show 45ebb32:harness/leaf.py | grep -c '_terminal_pytest_exceptions\|_own_test_setup_problem'`
  → `0`. The captured-output boundary, the counterfeit-heading route and the setup-repair
  classifier are code this node's campaign never ran; they are new at `999ea9a`.

**The state, in the two commands that show it.** Run from this checkout just now:

```
python3 bench/checks/m1_acceptance.py
→ m1 acceptance: OK — preprint-v1: 21 keys reproduced from tracked bytes only, every one
  quoted by the paper, and a starved tree fails loudly                    exit 0, 6s
python3 docs/paper/check_citations.py
→ rows 97 (printed-key 23, record 9, analyzer 39, unknown 26)
  citations resolved 412 unresolved 0                                    exit 0
```

The first clones at tag `preprint-v1` into a throwaway directory, so the untracked 2 GB home is
absent by construction, runs the one command there, requires each printed key to be quoted by the
paper, and requires a starved tree to fail. It is the same acceptance root released on 2026-10-21
and it still holds.

**One real coupling, disclosed rather than repaired.** At the measured revision the harness
decides whether a red check blames the run's own test or its source by parsing pytest failure text
that the run itself writes (`harness/leaf.py:3733` today, `45ebb32` carries it). That decision is
a heuristic with no independent judge, so §5's null about the own-test loop cannot be read as
evidence that test feedback carries no information — it may have been routed wrong. The numbers do
not rest on it: solved and false success are the external grader's verdict, and the claim column
is the harness's claim compared against that verdict. `docs/paper/07-limits.md` now says exactly
that, and `docs/paper/05-result-r2.md` points §5's null at it. That is the whole of what the paper
path changed in the draft: one limit paragraph, one clause.

**What is yours, and nothing else is.** Publication is the only step left between "reached" and
"citable by a stranger": a push, a DOI, an arXiv submission. Tag `preprint-v1` is a freeze, not a
publication. I have not touched a remote and will not without it being named as your decision.

**What I did not do, so nobody re-opens it.** I did not start the repair cycle the person's answer
made available: spending it here would spend a cycle the paper does not need, and P1a's next step
is a changed hypothesis, not a renamed package. I did not touch P1b or P2–P5, did not re-open M2, and
did not re-measure anything: this was idle machine time, no model ran, so the price is zero metered
spend.

Effort of answering: reading four evidence lines and naming whether publication proceeds —
minutes. If no answer comes I stop here: the preprint stands at `preprint-v1`, P1a stands frozen,
and the only remaining act is one this node cannot take.
