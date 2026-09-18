# 05-fp8-retry-loop-construction

**Status:** needs-triage
**Pattern:** FAIL_PATTERNS FP-8 — retry-loop construction wobble (T-13-add-retry-backoff)
**Evidence:** runs `20260917T071103`, `20260917T071554` (3 red attempts each, correct
file, check ladder clean), log `n-sweep-20260917T071553Z/T-13-add-retry-backoff.run1.log`;
shapes: early marker return ×3, wrong `sleep` arity ×1, `None`-as-int loop bound ×1.
Shaping A/B: generic excerpts still FAIL — model-side, content exonerated.

## Objective

Raise the 4B's success rate on control-flow-restructuring fixes (retry/backoff
loops) by decomposing the step instead of trusting one whole-file shot.

## Fix ladder (cheapest first)

1. **Skeleton-first split (DESIGN §2.2 guided decomposition, applied to content):**
   sub-step A emits the loop SHAPE as a fill-in form (harness-proposed skeleton:
   `for delay in DELAYS_S[:retries]: ...` with slots), sub-step B fills the body;
   harness stitches and validates. Never a free re-think — a form.
2. **A/B per §9.12:** guided skeleton vs one-shot on T-13 + controls, N=3 each;
   keep only if the delta beats the confidence interval.
3. If skeleton-first wins, generalize the step type (`implement` variants for
   flow-restructure classes — the TASK_TAXONOMY routing table decides).

## Acceptance

T-13 through the golden path with the skeleton step: N=3 mini-sweep (T-13 + 2
controls) with pass-rate delta beyond the N-run CI, then full corpus.

## Progress log (append-only)

- 2026-09-17 owner session: pattern diagnosed across 4 runs + shaping A/B;
  ticket parked at needs-triage (M4 milestone closure takes priority).

- 2026-09-18 owner session: A/B RAN (guided fix_plan before each implement emit,
  8-task family, N=3). Guided **11/24 (45.8%)** vs one-shot baseline **4/24 (16.7%)**;
  T-16 1/3->3/3, T-21 1/3->3/3, T-18 0/3->2/3, T-24 0/3->1/3, T-26 0/3->2/3;
  T-13 2/3->0/3 (high-variance task), T-27/T-28 unchanged 0/3. Cost: +1 call/attempt.
  VERDICT: guided decomposition keeps — but see ticket 07/§9.10: the M0 baseline
  (85.6%, 1.4 calls/task) beats both variants on this family, so the durable home
  for "guided" is inside an escalation ladder (cheap path first), not the default
  heavy path.
