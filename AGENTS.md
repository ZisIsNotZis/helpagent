# helpagent — node document

The law this node runs under is `/home/z/vibe/agent-policy/LAW.md`: read once, not copied here.
This file holds only the overrides that law needs on this tree, and the state a session must know
before it reads anything else. Everything else is in `docs/`.

## State

The campaign ran to its pre-registered end and stopped: three verdicts archived (capability parity
**INCONCLUSIVE**, verification information **PARTLY / not as stated**, tree decomposition
**NEGATIVE**), and the product CLI was never built. What the repository owed was a form in which
that measurement can be read and checked by somebody who is not this machine, and it is delivered:
a public preprint, one reproduce command, a traceability table, and a frozen revision.

M0 (the campaign bytes secured in a declared home and hashed) and M1 (a citable preprint whose
every decisive number recomputes from the repository alone) are reached. The paper path is
finished; nothing here waits on a worker. What remains is the person's — a DOI, an arXiv
submission, approval of M2 — or a new research programme this roadmap does not authorise
(`docs/0_ROADMAP.md`).

Two commands show that state rather than claim it:

```sh
python3 reproduce.py                      # every decisive number, from committed rows only
python3 docs/paper/check_citations.py     # the paper still quotes them; 0 unresolved
python3 bench/checks/docs_layout.py       # docs/ is still filed by level; 0 problems
```

## Overrides that hold on this tree

- **`docs/paper/` is the deliverable and stands outside the level scheme.** It is self-contained,
  `preprint.md` is a render built by `python3 docs/paper/build_preprint.py`, its numbers are gated
  against the entry point, and a public tag names a revision of it. Never hand-edit the render;
  edit the section file and rebuild.
- **The decisive evidence is not in git.** `bench/runs/wave1/` holds 2.0 GB of campaign bytes,
  untracked and verified by `bench/manifests/wave1.sha256`. The preprint does not need it: the
  numbers recompute from `bench/projection/`, half a megabyte, which is tracked.
- **`.scratch/` is the work record, never truth.** Tickets, measurement records and provenance
  live there; `docs/` states the current fact. A conflict between them resolves for `docs/`.
- **Section numbers in `docs/6_ARCHITECTURE.md`, `docs/6_FLOW.md`, `docs/7_INTERFACE.md` and
  `docs/7_ENVELOPES.md` are load-bearing.** About 240 comments in `harness/`, `tests/` and `bench/`
  cite them as `DESIGN §4.2` or `ENVELOPE_SCHEMAS §10`; do not renumber, and keep those comments'
  name→file mapping current.
- **Documents are referenced by anchor, not by line.** A citation is `path#heading-slug` (heading
  lowercased, every run of non-alphanumerics collapsed to one hyphen). `docs/paper/check_citations.py`
  resolves these and re-checks that each number still sits in the text it cites.
- **Mail lands in `mail/`**, one file per message, and is deleted once its fact is landed in `docs/`
  — deleting is tidying, not a reply.

## Where to read

`README.md` is the front door. `docs/0_ROADMAP.md` is the order of work and what is deliberately
not on it; `docs/2_GOAL.md` holds the verdicts and what they cannot carry; `docs/5_PRODUCT.md`
holds the deliverable and its publication boundary; `docs/9_IMPLEMENTATION.md#docs-and-the-work-record`
holds the documentation rule as it applies to this tree.
