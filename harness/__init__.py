"""helpagent harness — kernel-side building blocks (M1 slice).

- :mod:`harness.envelopes` — every envelope schema from ENVELOPE_SCHEMAS §0–§23 + registry
- :mod:`harness.tree` — TaskTree / NodeHandle (KERNEL_API §4.1–4.2)
- :mod:`harness.fake_model` — FakeModelRunner + misbehavior helpers
- :mod:`harness.runner` — llm_step glue, prompt composer, minimal ledger
"""

from harness.envelopes import (
    SCHEMAS,
    Ambiguities,
    Ambiguity,
    Bug,
    ChildFill,
    ChildPlan,
    DraftAC,
    DraftACs,
    DebugJudge,
    Envelope,
    Expand,
    FailureJudge,
    FindAmbiguities,
    FixAttempt,
    GateDecide,
    HowEntry,
    HowList,
    IdentifyBugs,
    Implement,
    Interface,
    InterpretProbe,
    JUDGE_STEP_PREFIX,
    JudgeAspect,
    Lesson,
    LessonEnvelope,
    NewIssue,
    PlanNode,
    Problem,
    ProposeGrowth,
    ProposeProbe,
    ProposedNode,
    RankedFix,
    ReviseTaskCard,
    RunSummary,
    SpecIssue,
    SpecReview,
    SplitIssue,
    SplitReview,
    STOPWORDS,
    TaskCard,
    TestCase,
    TestPlan,
    WriteSpec,
    WriteTest,
    build_judge_aspect_model,
)
from harness.fake_model import (
    CallRecord,
    EnvelopeSpec,
    FakeModelRunner,
    code_with_syntax_error,
    malformed_json,
    ok_edit,
    render_prompt,
    schema_violation,
    unable,
)
from harness.runner import (
    FailureSummary,
    LLMRequest,
    SchemaViolation,
    compose_prompt,
    ledger_entries,
    llm_step,
    note,
    reset_ledger_for_tests,
    schema_for_step,
)
from harness.tree import (
    ACEntry,
    ArtifactRef,
    CheckResults,
    CloseResult,
    Finding,
    Node,
    NodeHandle,
    StatusTransitionInvalid,
    TaskTree,
    TRANSITIONS,
    ValidationFindings,
)

__all__ = [
    # envelopes
    "SCHEMAS", "JUDGE_STEP_PREFIX", "STOPWORDS", "Envelope", "TaskCard", "Ambiguity",
    "Ambiguities", "FindAmbiguities", "ReviseTaskCard", "ChildFill", "Expand",
    "SplitIssue", "SplitReview", "DraftAC", "DraftACs", "Interface", "WriteSpec",
    "SpecIssue", "SpecReview", "TestCase", "TestPlan", "WriteTest", "Implement",
    "Problem", "FailureJudge", "Bug", "IdentifyBugs", "ProposeProbe", "InterpretProbe",
    "Lesson", "LessonEnvelope", "RankedFix", "DebugJudge", "NewIssue", "FixAttempt", "JudgeAspect",
    "build_judge_aspect_model", "RunSummary", "GateDecide", "ProposedNode",
    "ProposeGrowth", "ChildPlan", "PlanNode", "HowEntry", "HowList",
    # tree
    "TRANSITIONS", "StatusTransitionInvalid", "ArtifactRef", "ACEntry", "Node",
    "NodeHandle", "TaskTree", "Finding", "ValidationFindings", "CheckResults",
    "CloseResult",
    # fake model
    "EnvelopeSpec", "CallRecord", "FakeModelRunner", "ok_edit", "unable",
    "malformed_json", "schema_violation", "code_with_syntax_error", "render_prompt",
    # runner
    "LLMRequest", "FailureSummary", "SchemaViolation", "compose_prompt", "llm_step",
    "schema_for_step", "note", "ledger_entries", "reset_ledger_for_tests",
]
