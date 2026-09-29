# Ticket 15 — Public bare-model vs +Harness report

## Why

A downstream consumer needs a **reproducible, public** number. The resume/portfolio
agent (`~/vibe/resume_private`) is positioning the owner for roles whose JDs ask for a
*measured* pass-rate delta between a bare model and the harness:

- DeepSeek「Agent Harness 团队」(研发工程 / 研究) — "熟练使用 AI Agent 工具…是 Agent 产品的高强度用户".
- DeepSeek「AI 跨界技术人才」— "实际的行动与成果来支持你的热情".
- OpenAI / Anthropic "Agent-Harness / Evals Engineer" — externally reproducible eval.

Those numbers already exist internally but are not published in a reproducible form.

## Deliverable

1. `benchmark/reports/bare_vs_harness.md` (public, committed):
   - base model + commit hash + task set + control tasks;
   - **bare vs +harness** pass rate for each set (orig-30 / hard-5 / anchor-5);
   - exact reproduce commands (one block, copy-pasteable);
   - honest caveats — including that the **old** full pipeline *lost* to bare
     (73.3% vs 85.6%) and was superseded by tiering.
2. Link it from `benchmark/reports/` index and add a `CHANGELOG.md` entry.

## Numbers to verify / refresh (do not trust blindly)

Source of record: `.scratch/07-corpus-30/issues/07-corpus-30.md:50` and `docs/DESIGN.md:268`.

| set | +harness | bare |
|---|---|---|
| orig-30 | 84/90 (93.3%) | 85.6% |
| hard-5 | 6/15 (40%) | — (golden 26.7%) |
| anchor-5 (Exercism official) | 7/15 (46.7%) | 33.3% |

Also recorded: bare drops 79% → 33% on external tasks; old full-pipeline 73.3% (⚠️ worse than bare).

Re-run at a frozen commit before publishing; report N and variance.

## Handoff contract (back to the resume agent)

This repo does **not** own the resume. After publishing, write a compact, resume-ready
summary to:

```
/home/z/vibe/resume_private/.scratch/inbox/helpagent-bare-vs-harness.md
```

Contents: final numbers, date, commit hash, exact reproduce command, and 1–2 **honest**
caveats. Do not edit any file under `resume_private/data/`; the resume agent owns that.

If a resume-safe one-liner is obvious, include it as a single quoted line for reuse.

## Definition of done

- [ ] `benchmark/reports/bare_vs_harness.md` committed & pushed.
- [ ] `/home/z/vibe/resume_private/.scratch/inbox/helpagent-bare-vs-harness.md` written.
- [ ] `bench/FAIL_PATTERNS.md` OPEN items unchanged or annotated (FP-5, FP-8 currently OPEN).
