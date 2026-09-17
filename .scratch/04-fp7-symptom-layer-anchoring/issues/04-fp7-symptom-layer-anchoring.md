# 04-fp7-symptom-layer-anchoring

**Status:** needs-triage
**Pattern:** FAIL_PATTERNS FP-7 — symptom-layer anchoring (T-01-ttl-seconds-ms)
**Evidence:** runs `bench/runs/20260917T061713/golden/T-01-ttl-seconds-ms` (sweep,
3 red attempts) and `bench/runs/20260917T063255/golden/T-01-ttl-seconds-ms`
(resample, 3 red attempts); spec chose `auth/sessions.py`, real fix is
`auth/config.py` SESSION_TTL_SECONDS 60→3600.

## Objective

The spec/locate step must surface the layer where the misconfigured VALUE lives.
The failing-test excerpt only names session-layer symbols — the model cannot see
`config.py`'s constant, so it "fixes" expiry math where the symptom shows.

## Fix ladder (cheapest first, per the 2026-09-17 alignment)

1. **Composer-side constant surfacing** (harness lookup, never the model's job —
   DESIGN §2.1): extract module-level constant assignments (same pass as
   `extract_symbols`) and inject a "repo constants" block into the `write_spec`
   context; flag constants whose name/value clash with the request semantics
   (`SECONDS = 60` next to "expire after one hour" is a red flag a lookup can
   catch deterministically).
2. **Spec hard rule** (composer wording, FP-1 lesson: only hard rules survive
   temp 0.2): "fix where the VALUE lives, not where the symptom shows; when the
   request names a config origin, the boundary must include the config module."
3. Structural: locate-driven context injection (M7 composer full version) — the
   designed home; steps 1–2 must prove out against the corpus first.
4. Companion: task_class=scaffold wobble on this task (FP-5 family) — pin example
   when A2 lands.

## Acceptance

T-01 through the golden path with the composer change: first-or-retry PASS, and
an N=1 mini-sweep (T-01 + 2 control tasks) showing no regression, then the full
corpus N=1 before calling it closed.

## Progress log (append-only)

- 2026-09-17 owner session: pattern diagnosed from the M3-sweep T-01 failure +
  resample; M3 exonerated (all attempts `write_committed`, pytest red — model-side).
  Ticket parked at needs-triage; M3 closure takes priority in this session.
