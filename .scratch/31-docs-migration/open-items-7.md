# Open items for `docs/7_INTERFACE.md`

Not interface, and so not migrated into `docs/7_INTERFACE.md`: the gaps the kernel spec raised
against its own primitive set. Copied verbatim from `KERNEL_API.md` §8, with cross-references
rewritten to the new homes.

## 8. Gaps requiring a 7th primitive or kernel-internal reclassification

**G1. `k.triage_rules(failures)` (D1 mechanical failure triage).** Not one of the six
primitives; not a method on any handle the script otherwise holds; yet it is real kernel
logic (deterministic rule-library application, H job). **Raised.**
Recommendation: reclassify as a read-only query surface on the Knowledge Service, exposed
as `index.rules.triage(failures)` — same status as the Index handle: deterministic,
consumes/produces data only, no model invocation, no budget. This respects `docs/7_INTERFACE.md` §1's criterion
(never invokes/executes/mutates/pauses/governs) without a 7th primitive. Alternative if
rejected: make triage a step the script performs via `llm()` with an M fallback — but
that contradicts D1's "H rules → M fallback" ordering. *(Recommendation stands: handle
query surface, not a primitive.)*

**G2. Script-authored artifacts that are not `llm()` results.** `k.artifacts.write` was
folded into `tree.attach` on the grounds that every scripted artifact in v1 originates
from an `llm()` call. If a future script needs to persist a purely harness-computed
artifact (e.g. a benchmark stats artifact), `tree.attach` must accept store-less drafts —
still a tree-handle method, since schema validation + secret filter + single-producer are
kernel-side anyway. No 7th primitive required; watch for scripts wanting *unattached*
artifact storage (store-level `put/get`), which would be a genuine new surface.

**G3. `k.lock` as a general facility.** Folded into `boot_recover`. If scripts ever need
other critical sections (v1 has none — work-tree exclusivity is kernel-enforced via
file-overlap groups), a general script-facing lock would be a new capability outside all
six primitives. Keep it kernel-internal until a concrete script needs it.

**G4. Direct `node.status` assignment vs handle-enforced transitions.** The script
assigns statuses directly. Kernel re-validation at commit is the minimal
reconciliation, but it means invalid states are observable between assignment and commit.
If that proves bug-prone, switch to `node.set_status()` with an eager transition table —
a handle-method change, not a primitive change.

No seventh primitive is introduced by this spec. Every script call in is
accounted for in `docs/7_INTERFACE.md` §2.

## Unresolved in the move

- **§8's slot in `docs/7_INTERFACE.md`.** The section is gone, so §8 is retired there and a
  one-line pointer stands between §7 and §9: a citation of `KERNEL_API §8` must not resolve to
  something that is now §9. If the gaps ever fold back into the interface, they take the number
  back.
- **Erasure semantics cited as "§2.4".** The architecture doc names erasure semantics as §2.4 and
  files the subsystem under §4; there is no §2.4 heading to resolve. Written as the bare path
  `docs/6_ARCHITECTURE.md`, with no section number. Add `path#anchor` once that file's headings
  are fixed.
- **"per-category sub-budgets §4.3".** That is the composer section of the architecture doc, not
  §4.3 of the kernel spec. Written as the bare path `docs/6_ARCHITECTURE.md`.
- **Architecture section numbers dropped from citations.** Every `DESIGN §N` citation in both
  source documents is written as the bare path `docs/6_ARCHITECTURE.md`: that file's heading set
  is not fixed, so no anchor can be named yet. Restore `path#anchor` when it lands.
- **Mangled text repaired, nothing invented:**
  "(`scripts/v1/`,.md)" became "(`scripts/v1/*.md`)"; "(DESIGN §4.8,)" became the bare path
  `docs/6_ARCHITECTURE.md`; "(dropped 2026-10-06; see docs/FLOW.md).md §8" became
  "(dropped 2026-10-06; see `docs/6_ARCHITECTURE.md`)" — the flow doc folds into that file.
- **Truncated sentences kept as they are.** The reconciliation heading reads "every `k.*` call
  in" and its closing sentence reads "Every script call in is accounted for": an earlier
  pass cut a `scripts/v1/*.md` mention mid-sentence. Section numbers and titles are kept exactly,
  so both stand verbatim; repairing them means inventing the missing object.
- **Two documents, two number series.** `docs/7_INTERFACE.md` numbers its sections from §1 and
  `docs/7_ENVELOPES.md` from §0; each citation in `harness/`, `tests/` and `bench/` names the
  document alongside the number. A cross-document reference therefore always carries the file:
  `docs/7_ENVELOPES.md` §23, `docs/7_INTERFACE.md` §4.1.
