# Docs migration to the level scheme

The rule is `/home/z/vibe/agent-policy/LAW.md` §Docs, as realised in `/home/z/vibe/agent.my/docs/`:
`docs/<N>_<NAME>.md`, one level per meaning, `# EXPLICIT` / `# CONFIRMED` / `# INFERRED` zoning
inside each file, no event dates, references by name rather than by line number. `AGENTS.md`
keeps only rule overrides and the few facts that must be known before anything else.

## Target layout

| file | holds | built from |
| --- | --- | --- |
| `docs/0_ROADMAP.md` | order of work: milestones reached, the frozen recovery line, what is deliberately not on the roadmap | AGENTS §Roadmap, `docs/ROADMAP.md`, LEARNINGS §8, root `STATUS.md` |
| `docs/0_STAGING.md` | facts with no home yet, and the assumptions of this migration | new |
| `docs/1_PROBLEM.md` | why the work is worth doing | README, LEARNINGS §4, DESIGN §1 |
| `docs/2_GOAL.md` | goals, success criteria, final verdicts, scope, retractions, limits | STATUS §2–§5, §10, FINDINGS §1, §2, §4, §5, ROADMAP slices and criteria, paper-plan |
| `docs/3_REQUIREMENT.md` | method requirements: preregistration, fair comparison, determinism, reproducibility, publication boundary | LEARNINGS §2, §3, CONTRIBUTING invariants, AGENTS reproduce contract |
| `docs/4_USECASE.md` | who does what: read the paper, check a claim, recompute, maintain the home | new synthesis |
| `docs/5_PRODUCT.md` | the deliverable: the preprint, the entry point, read order, reusability, what is deliberately absent | paper-plan §结构, `docs/paper/README.md`, LEARNINGS §6 §7, AGENTS decisions |
| `docs/6_ARCHITECTURE.md` | the harness design and the one flow, and the evidence pipeline | DESIGN, FLOW, STATUS §1 §8, LEARNINGS §1 |
| `docs/7_INTERFACE.md` | kernel primitives, handle objects, envelopes, the entry-point contract | KERNEL_API, ENVELOPE_SCHEMAS, AGENTS reproduce contract |
| `docs/8_DETAIL.md` | measured detail: cost, false successes, what did not help, negative results, analyzer and projection internals | STATUS §6 §7 §9, FINDINGS §3, LEARNINGS §5, AGENTS in-flight and repository-alone |
| `docs/9_IMPLEMENTATION.md` | gate, corpus, environment, commands, the work record | CONTRIBUTING, STATUS §11 §12, LEARNINGS §9, AGENTS secured/evidence/pointers, README how-to-run |
| `docs/paper/` | the preprint and its checker — exempt: it is the deliverable, renders itself and is checked by `m1_acceptance.py` | stays |
| `docs/mockups/` | the UI mockup of the CLI that was never built | stays |

Deleted after landing: root `STATUS.md`, `FINDINGS.md`, `docs/STATUS.md`, `docs/ROADMAP.md`,
`docs/DESIGN.md`, `docs/FLOW.md`, `docs/KERNEL_API.md`, `docs/ENVELOPE_SCHEMAS.md`,
`docs/LEARNINGS.md`, `docs/paper-plan.md`. `.scratch/` stays: it is the work record, not docs.

## Invariants the migration must not break

1. `python3 docs/paper/check_citations.py` exits 0 with 0 unresolved: every `path:line` written
   today is rewritten to `path#anchor`, and the checker re-verifies that every number still sits
   in the text it cites.
2. `python3 docs/paper/build_preprint.py --check` is current after the paper's references change.
3. `python3 bench/checks/m1_acceptance.py` still prints OK (it runs at the frozen tag).
4. No fact is lost: every non-blank source line lands in a target file, or is listed as
   deliberately dropped with the reason.
5. `.scratch/` and `bench/` are not rewritten.

## Assumptions taken by the manager (overturnable)

- `docs/paper/` is exempt from the level scheme. It is the deliverable: self-contained,
  rendered by a build script, its numbers gated against the entry point, cited by a public
  fingerprint. Filing it into levels would break the render and the acceptance.
- `.scratch/` is the work record (786 tracked files) and is not documentation; it is named as
  such in `9_IMPLEMENTATION.md` and left untouched.
- The level scheme is applied where content exists; no empty level file is created.
- Headings are the reference unit (`path#slug`), since a line number is a derived number and
  this node's own rule is that derived numbers are not stored by hand.

## Result

Landed in one advance. `docs/` is now `0_ROADMAP`, `0_STAGING`, `1_PROBLEM`, `2_GOAL`,
`3_REQUIREMENT`, `4_USECASE`, `5_PRODUCT`, `6_ARCHITECTURE`, `6_FLOW`, `7_INTERFACE`,
`7_ENVELOPES`, `8_DETAIL`, `9_IMPLEMENTATION`, plus the exempt `docs/paper/` and `docs/mockups/`.
The eleven documents it replaced are gone; `git` keeps them.

Two files per level, not one, for levels 6 and 7: about 240 comments in `harness/`, `tests/` and
`bench/` cite `DESIGN §4.2`, `FLOW §6`, `KERNEL_API §3.4` and `ENVELOPE_SCHEMAS §10`, and those
four documents number their sections from their own start, so two of them cannot share a file
without colliding. Section numbers are therefore preserved and the file names changed; the code
comments were rewritten to the new paths, mechanically, without touching a line of logic.

The paper's 527 line-number citations became heading anchors (`path#anchor`) through
`rewrite_refs.py` and the four section maps beside it, and `check_citations.py` — extended to read
anchors in prose, in the numbers table, and in every document's own cross-references — re-verified
that every cited value still sits in the text that now carries it. Two new checks hold the shape:
`docs/paper/check_citations.py` for references, `bench/checks/docs_layout.py` for the levels, the
zones, the anchor uniqueness and the ban on line-number references.
