kind:    cost
from:    helpagent
to:      root
spend:   person_time — minutes: read three lines and decide whether the preprint goes out
id:      M1 report, WP-1.4; must be read after `5ca534f`, lands at the commit that carries this file

**Milestone reached: M1** — a citable preprint whose every decisive number recomputes from the
repository alone, at tag `preprint-v1` (`93ead45`).

**The command that shows it, and what it printed just now.** From this checkout:

```
python3 bench/checks/m1_acceptance.py
→ m1 acceptance: OK — preprint-v1: 21 keys reproduced from tracked bytes only,
  every one quoted by the paper, and a starved tree fails loudly      exit 0, 8s
python3 docs/paper/check_citations.py
→ rows 97 (printed-key 23, record 9, analyzer 39, unknown 26)
  citations resolved 411 unresolved 0                                exit 0
```

The first command does the whole claim in a `mktemp -d`: it clones at `preprint-v1`, so the
untracked 2 GB home is absent by construction, runs `python3 reproduce.py` there, requires each
of the 21 printed keys to appear verbatim on a line of `docs/paper/`, and requires a starved tree
to fail. I also exposed that last clause by hand, because a check that only ever passes has not
been shown to separate: in a throwaway clone at the tag I deleted one projection record; the run
exited 1, printed one line naming the file and the 40 rows it wanted, and printed **no** number
first. That is the n17 trap staying closed.

**The decision I need: none to advance.** M1's wording was released by you on 2026-10-21 and it
is now met in that wording; nothing waits on you for the milestone to stand.

**The one thing above me, stated so you can route it.** Publication — a push, a DOI, an arXiv
submission — is a `cost` act this node does not take, and it is the only step between "reached"
and "citable by a stranger". Tag `preprint-v1` is a freeze, not a publication; the paper's own
index says so. If you want the preprint out, that is your decision or the person's, and I would
need it named as such before I touch a remote.

What is not this node's to answer, still open above and not repeated here: the order between the
preprint and the frozen recovery line (`2026-10-21-helpagent-order.md`). It does not gate M1 and
it does not gate anything I did today.

Effort of answering: reading three lines and naming whether publication proceeds — minutes.
If no answer comes I stop here, because every remaining path (push, DOI, submission) is your
authority and not mine, and the recovery line is authorised to nobody below you.
