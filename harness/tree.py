"""Task tree — the one plan artifact (DESIGN §4.8, KERNEL_API §4.1–4.2).

Handles are plain data/validation surfaces over kernel-owned state: ``NodeHandle``
performs no model invocation, no exec, no work-tree mutation. The kernel re-validates
every mutation at the tree commit point (KERNEL_API §4.2 G4 DECISION: script assigns
statuses directly; transition validation happens at commit, not at assignment).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harness.artifacts import Artifact, ArtifactStore

Status = Literal["pending", "in-progress", "done", "blocked", "stale", "needs-user"]

#: Transition table enforced at commit (KERNEL_API §4.2). Same-status assignment is a
#: no-op, not a transition. ``pending → done`` is deliberately illegal: closure goes
#: through the kernel gate (:meth:`NodeHandle.close`), which reaches ``done`` via
#: ``in-progress`` (see close()). ``done`` may only reopen to ``in-progress`` or be
#: invalidated to ``stale`` (tree-edit cascade).
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in-progress", "blocked", "needs-user", "stale"},
    "in-progress": {"done", "blocked", "needs-user", "pending", "stale"},
    "done": {"in-progress", "stale"},
    "blocked": {"in-progress", "pending", "needs-user", "stale"},
    "needs-user": {"in-progress", "pending", "blocked", "stale"},
    "stale": {"in-progress", "pending", "done", "blocked", "needs-user"},
}


class StatusTransitionInvalid(Exception):
    """Illegal status transition, raised at commit (KERNEL_API §4.2)."""


# ---------------------------------------------------------------------------
# Node schema pieces
# ---------------------------------------------------------------------------


class ArtifactRef(BaseModel):
    """Typed artifact reference with an explicit producer id (KERNEL_API §4.1)."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)


class ACEntry(BaseModel):
    """One check of an AC test map: ``{ac_id → [check_id, command | subjective]}``
    rendered as an entry (KERNEL_API §4.2 set_ac_test_map)."""

    model_config = ConfigDict(extra="forbid")

    ac_id: str = Field(pattern=r"^AC-[0-9]{1,3}$")
    statement: str = Field(min_length=1)
    check_kind: Literal["test", "script-assertion", "subjective"]
    check_hint: str | None = None
    command: str | None = None

    @model_validator(mode="after")
    def _subjective_needs_hint(self) -> Self:
        if self.check_kind == "subjective" and not (self.check_hint or "").strip():
            raise ValueError("subjective check requires check_hint (KERNEL_API §4.2)")
        return self

    @property
    def key(self) -> str:
        """Resolution/verdict key: the executable command, else the check hint (a test
        id), else the ac_id. DECISION: test ids are normalized into this key — the
        doc's "command or test id" both land here as exact strings."""
        return self.command or self.check_hint or self.ac_id


class Node(BaseModel):
    """Universal node schema (KERNEL_API §4.1): ``{id, what, why, input, output,
    ac_test_map, risk, produced_artifact_id, status, children}``.

    ``files`` is an additional operational field: ready_leaves' file-overlap writer
    grouping needs each leaf's declared files boundary (KERNEL_API §4.1: "leaves are
    grouped by overlap of their declared ``files`` boundary"). DECISION: kept on the
    node because the universal schema has no other home for the boundary the grouping
    rule requires; it is the seam scope attached at expansion time.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    what: str = Field(min_length=1)
    why: str = ""
    input: list[ArtifactRef] = Field(default_factory=list)
    output: list[ArtifactRef] = Field(default_factory=list)
    ac_test_map: list[ACEntry] = Field(default_factory=list)
    risk: str = ""
    produced_artifact_id: str | None = None
    status: Status = "pending"
    children: list[str] = Field(default_factory=list)  # child node ids
    files: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Findings / results — shaped results, never exception leaks (KERNEL_API §4.1)
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    node_id: str | None = None
    detail: str = ""


class ValidationFindings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Finding] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.items


class CheckResults(BaseModel):
    """Deterministic check verdicts passed into close(); keyed by check key
    (command or test id). ``skip`` covers skipped/flaky — not a pass (KERNEL_API §4.1)."""

    model_config = ConfigDict(extra="forbid")

    verdicts: dict[str, Literal["pass", "fail", "skip"]] = Field(default_factory=dict)


@dataclass
class CloseResult:
    """KERNEL_API §4.2: close refuses with ``False`` + reasons. Bool-like so
    ``if node.close(...)`` reads as the doc's ``-> bool`` while carrying the
    structured rejection reasons."""

    ok: bool
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


# ---------------------------------------------------------------------------
# TaskTree
# ---------------------------------------------------------------------------


class TaskTree:
    """Kernel-owned plan artifact. Nodes are stored flat; ``children`` hold ids.
    All mutation paths (script status assignment, insert cascade, close, refresh)
    re-validate at :meth:`commit`."""

    def __init__(self, what: str, why: str = "", risk: str = "", files: Iterable[str] | None = None) -> None:
        self._nodes: dict[str, Node] = {}
        self._order: list[str] = []
        self._pending: dict[str, Status] = {}
        self._producers: dict[str, str] = {}  # artifact_id -> producing node id
        self._counter = 0
        self.artifacts = ArtifactStore()  # kernel-owned store; attach enforces linkage
        self.root_id = self._new_node(what=what, why=why, risk=risk, files=list(files or []))

    # artifacts -------------------------------------------------------------------

    def attach(self, node: NodeHandle | str, artifact: Artifact) -> ValidationFindings:
        """Link a produced artifact to its producer (KERNEL_API §4.6): sets
        ``produced_artifact_id``, appends the typed ArtifactRef to the node's outputs,
        and enforces the single-producer rule — the same artifact_id attached to a
        second node is a validation finding, never a silent overwrite. The artifact
        schema (incl. producer linkage as a schema field) is validated by the store
        boundary; content was secret-filtered there (DESIGN §4.2)."""
        findings = ValidationFindings()
        nid = node if isinstance(node, str) else node.id
        self._node(nid)  # raises if unknown
        existing = self._nodes[nid].produced_artifact_id
        if existing is not None and existing != artifact.artifact_id:
            findings.items.append(
                Finding(kind="artifact-relink", node_id=nid,
                        detail=f"node already produces {existing!r}; refusing relink to {artifact.artifact_id!r}")
            )
            return findings
        prior = self._producers.get(artifact.artifact_id)
        if prior is not None and prior != nid:
            findings.items.append(
                Finding(kind="duplicate-producer", node_id=nid,
                        detail=f"artifact {artifact.artifact_id!r} already produced by {prior!r}")
            )
            return findings
        if artifact.artifact_id not in self.artifacts:
            self.artifacts.put(artifact.artifact_id, nid, artifact.kind, artifact.content)
        if existing != artifact.artifact_id:
            self._nodes[nid].produced_artifact_id = artifact.artifact_id
            self._nodes[nid].output.append(
                ArtifactRef(artifact_id=artifact.artifact_id, producer_id=nid)
            )
            self._producers[artifact.artifact_id] = nid
        return findings

    # -- construction -------------------------------------------------------

    def _new_node(self, **kw) -> str:
        self._counter += 1
        nid = f"N-{self._counter}"
        self._nodes[nid] = Node(id=nid, **kw)
        self._order.append(nid)
        return nid

    def insert_ticket(
        self,
        parent: NodeHandle,
        issue: str,
        *,
        why: str = "",
        risk: str = "",
        files: Iterable[str] | None = None,
        input: Iterable[ArtifactRef | dict] | None = None,
        output: Iterable[str] | None = None,
    ) -> NodeHandle:
        """Tree edit (KERNEL_API §4.1): kernel assigns the id, runs the cascade —
        insertion under a ``done`` parent reopens it and touched-branch descendants
        are marked ``stale`` (must re-verify)."""
        self.commit()
        parent_node = self._nodes[self._require(parent.id)]
        refs = []
        for r in input or ():
            refs.append(r if isinstance(r, ArtifactRef) else ArtifactRef.model_validate(r))
        cid = self._new_node(
            what=issue,
            why=why,
            risk=risk,
            files=list(files or []),
            input=refs,
            output=[ArtifactRef(artifact_id=a, producer_id="PENDING") for a in output or ()],
        )
        # producer ids are kernel-assigned: backfill the node's own outputs
        produced = self._nodes[cid].output
        for ref in produced:
            ref.producer_id = cid
        parent_node.children.append(cid)
        self._cascade_insert(parent_node)
        return NodeHandle(self, cid)

    def insert_attempt(self, node: NodeHandle, hypothesis: str, **kw) -> NodeHandle:
        """Bounded-attempt rule (DESIGN §4.8): "next hypothesis = new sibling" —
        DECISION: the attempt lands under ``node.parent`` (or under ``node`` itself
        when node is the root), so attempts of one hypothesis chain are siblings."""
        self.commit()
        target = node.parent or node
        return self.insert_ticket(target, hypothesis, **kw)

    # -- accessors ----------------------------------------------------------

    def _require(self, node_id: str) -> str:
        if node_id not in self._nodes:
            raise KeyError(f"unknown node id: {node_id!r}")
        return node_id

    @property
    def root(self) -> NodeHandle:
        return NodeHandle(self, self.root_id)

    def get(self, node_id: str) -> NodeHandle:
        return NodeHandle(self, self._require(node_id))

    def nodes(self) -> list[NodeHandle]:
        return [NodeHandle(self, nid) for nid in self._order]

    def _node(self, node_id: str) -> Node:
        return self._nodes[self._require(node_id)]

    def _parent_of(self, node_id: str) -> str | None:
        for nid in self._order:
            if node_id in self._nodes[nid].children:
                return nid
        return None

    def _descendants(self, node_id: str) -> list[str]:
        out: list[str] = []
        stack = list(self._nodes[node_id].children)
        while stack:
            cid = stack.pop()
            out.append(cid)
            stack.extend(self._nodes[cid].children)
        return out

    def _depths(self) -> dict[str, int]:
        depths = {self.root_id: 0}
        stack = [self.root_id]
        while stack:
            nid = stack.pop()
            for cid in self._nodes[nid].children:
                depths[cid] = depths[nid] + 1
                stack.append(cid)
        return depths

    # -- status transitions (validated at commit) ----------------------------

    def commit(self) -> None:
        """Validate every pending script status assignment against the transition
        table, then apply atomically (all-or-nothing). Illegal ⇒
        StatusTransitionInvalid and nothing is applied."""
        if not self._pending:
            return
        for nid, target in self._pending.items():
            self._require(nid)
            current = self._nodes[nid].status
            if target != current and target not in TRANSITIONS[current]:
                raise StatusTransitionInvalid(f"{nid}: {current!r} -> {target!r} is not a legal transition")
        for nid, target in self._pending.items():
            self._nodes[nid].status = target
        self._pending.clear()

    def _transition(self, node: Node, target: Status) -> None:
        """Kernel-internal immediate transition (cascade/close/refresh). Still table-
        validated — kernel paths only use legal transitions by construction."""
        if target == node.status:
            return
        if target not in TRANSITIONS[node.status]:
            raise StatusTransitionInvalid(f"{node.id}: {node.status!r} -> {target!r} is not a legal transition")
        node.status = target

    # -- tree edits / cascade -----------------------------------------------

    def _cascade_insert(self, parent: Node) -> None:
        """Tree-edit cascade (DESIGN §4.8): touched branch ⇒ children marked stale;
        done parent reopens. DECISION: only ``done`` descendants become stale — stale
        means "previously verified work must re-verify"; pending work is untouched."""
        if parent.status == "done":
            self._transition(parent, "in-progress")
        for did in self._descendants(parent.id):
            d = self._nodes[did]
            if d.status == "done":
                self._transition(d, "stale")
        self.refresh_status()

    # -- DAG validation -------------------------------------------------------

    def validate_dag(self) -> ValidationFindings:
        """Validates I/O edges into an execution DAG: orphan inputs, duplicate
        producers, cycles ⇒ structured findings returned, never a silent stall and
        never an exception leak (KERNEL_API §4.1, DESIGN §4.8)."""
        findings: list[Finding] = []
        produced_by: dict[str, str] = {}
        for node in self._nodes.values():
            for ref in node.output:
                if ref.artifact_id in produced_by and produced_by[ref.artifact_id] != node.id:
                    findings.append(Finding(
                        kind="duplicate-producer",
                        node_id=node.id,
                        detail=f"artifact {ref.artifact_id!r} produced by both "
                               f"{produced_by[ref.artifact_id]} and {node.id}",
                    ))
                else:
                    produced_by[ref.artifact_id] = node.id
        edges: dict[str, set[str]] = {}
        for node in self._nodes.values():
            edges.setdefault(node.id, set())
            for ref in node.input:
                producer = produced_by.get(ref.artifact_id)
                if producer is None or producer != ref.producer_id or producer == node.id:
                    detail = (
                        f"input {ref.artifact_id!r} declares producer {ref.producer_id!r} but no other "
                        "node produces it"
                        if producer != node.id
                        else f"input {ref.artifact_id!r} depends on the node's own output"
                    )
                    findings.append(Finding(kind="orphan-input", node_id=node.id, detail=detail))
                else:
                    edges[node.id].add(producer)
        # cycle detection (consumer -> producer edges), iterative DFS three-color
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in self._nodes}
        for start in self._nodes:
            if color[start] != WHITE:
                continue
            stack = [(start, iter(sorted(edges.get(start, ()))))]
            color[start] = GRAY
            path = [start]
            while stack:
                nid, it = stack[-1]
                advanced = False
                for nxt in it:
                    if color[nxt] == GRAY:
                        cycle = path[path.index(nxt):] + [nxt]
                        findings.append(Finding(
                            kind="cycle",
                            node_id=nid,
                            detail="producer cycle: " + " -> ".join(cycle),
                        ))
                    elif color[nxt] == WHITE:
                        color[nxt] = GRAY
                        path.append(nxt)
                        stack.append((nxt, iter(sorted(edges.get(nxt, ())))))
                        advanced = True
                        break
                if not advanced:
                    color[nid] = BLACK
                    stack.pop()
                    if path and path[-1] == nid:
                        path.pop()
        return ValidationFindings(items=findings)

    # -- scheduling -----------------------------------------------------------

    def ready_leaves(self) -> list[NodeHandle]:
        """Leaves whose deps are satisfied, not held, and whose files are unlocked —
        at most one writer per file-overlap group (KERNEL_API §4.1). Read-only nodes
        (no files boundary) are never serialized against writers."""
        self.commit()
        done = {nid for nid, n in self._nodes.items() if n.status == "done"}
        candidates: list[Node] = []
        for nid in self._order:
            n = self._nodes[nid]
            if n.children or n.status not in ("pending", "stale"):
                continue
            deps_ok = all(
                (p := self._nodes.get(ref.producer_id)) is not None
                and p.status == "done"
                and any(o.artifact_id == ref.artifact_id for o in p.output)
                for ref in n.input
            )
            if deps_ok:
                candidates.append(n)
        claimed: set[str] = set()
        for nid in self._order:  # in-progress writers hold their group
            n = self._nodes[nid]
            if n.status == "in-progress" and not self._nodes[nid].children:
                claimed.update(n.files)
        ready: list[Node] = []
        taken: set[str] = set()
        for n in candidates:
            fs = set(n.files)
            if not fs:
                ready.append(n)  # read-only: own group
                continue
            if fs & claimed or fs & taken:
                continue  # one writer per overlap group per scheduling tick
            ready.append(n)
            taken |= fs
        return [NodeHandle(self, n.id) for n in ready]

    def has_work(self) -> bool:
        """Read-only: any node still pending execution/verification (KERNEL_API §4.1)."""
        self.commit()
        return any(n.status in ("pending", "in-progress", "stale") for n in self._nodes.values())

    def expansion_findings(self) -> ValidationFindings:
        """Read-only view for the plan-stabilization loop."""
        return self.validate_dag()

    # -- status closure propagation -------------------------------------------

    def refresh_status(self) -> None:
        """Re-validates upward (KERNEL_API §4.1): reopens done parents whose subtree
        was touched; auto-closes mapless internal nodes on (c) alone. DECISION: nodes
        WITH a map do not auto-close here — condition (b) needs check results, which
        only :meth:`NodeHandle.close` receives; their closure stays script-proposed."""
        self.commit()
        depths = self._depths()
        changed = True
        while changed:
            changed = False
            for nid in sorted(self._nodes, key=lambda x: -depths.get(x, 0)):
                node = self._nodes[nid]
                if not node.children:
                    continue
                kids = [self._nodes[c] for c in node.children]
                if all(k.status == "done" for k in kids):
                    if node.status in ("pending", "in-progress", "stale") and not node.ac_test_map:
                        self._force_close(node)
                        changed = True
                elif node.status == "done":
                    self._transition(node, "in-progress")  # re-validate done parent
                    changed = True

    def _force_close(self, node: Node) -> None:
        """Reach ``done`` through legal transitions only (pending → in-progress → done;
        stale → done directly)."""
        while node.status != "done":
            self._transition(node, "in-progress" if node.status == "pending" else "done")

    # -- snapshot ---------------------------------------------------------------

    def snapshot(self) -> dict:
        """Read-only nested view; feeds run-summary (KERNEL_API §4.1)."""

        def ser(nid: str) -> dict:
            n = self._nodes[nid]
            return {
                "id": n.id,
                "what": n.what,
                "why": n.why,
                "risk": n.risk,
                "status": n.status,
                "produced_artifact_id": n.produced_artifact_id,
                "input": [r.model_dump() for r in n.input],
                "output": [r.model_dump() for r in n.output],
                "files": list(n.files),
                "ac_test_map": [e.model_dump() for e in n.ac_test_map],
                "children": [ser(c) for c in n.children],
            }

        return ser(self.root_id)


class NodeHandle:
    """Typed handle over one node (KERNEL_API §4.2). Data, not a primitive."""

    __slots__ = ("_tree", "_id")

    def __init__(self, tree: TaskTree, node_id: str) -> None:
        self._tree = tree
        self._id = node_id

    # identity ----------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NodeHandle) and (self._id, id(self._tree)) == (other._id, id(other._tree))

    def __hash__(self) -> int:
        return hash((self._id, id(self._tree)))

    def __repr__(self) -> str:
        return f"<NodeHandle {self._id} status={self.status!r}>"

    @property
    def _node(self) -> Node:
        return self._tree._node(self._id)

    # read-only fields ----------------------------------------------------------

    @property
    def what(self) -> str:
        return self._node.what

    @property
    def why(self) -> str:
        return self._node.why

    @property
    def risk(self) -> str:
        return self._node.risk

    @property
    def files(self) -> list[str]:
        return list(self._node.files)

    @property
    def produced_artifact_id(self) -> str | None:
        """Read-only field (KERNEL_API §4.2); set via :meth:`TaskTree.attach`."""
        return self._node.produced_artifact_id

    def attach(self, artifact: Artifact) -> ValidationFindings:
        """Handle-form of :meth:`TaskTree.attach` (KERNEL_API §4.6)."""
        return self._tree.attach(self, artifact)

    @property
    def input(self) -> list[ArtifactRef]:
        return list(self._node.input)

    @property
    def output(self) -> list[ArtifactRef]:
        return list(self._node.output)

    @property
    def ac_test_map(self) -> list[ACEntry]:
        return list(self._node.ac_test_map)

    # structure -----------------------------------------------------------------

    @property
    def children(self) -> list[NodeHandle]:
        return [NodeHandle(self._tree, cid) for cid in self._node.children]

    @property
    def parent(self) -> NodeHandle | None:
        pid = self._tree._parent_of(self._id)
        return NodeHandle(self._tree, pid) if pid else None

    @property
    def is_leaf(self) -> bool:
        return not self._node.children

    # status — buffered assignment, validated at commit ---------------------------

    @property
    def status(self) -> Status:
        pending = self._tree._pending.get(self._id)
        return pending if pending is not None else self._node.status

    @status.setter
    def status(self, value: Status) -> None:
        # KERNEL_API §4.2 G4 DECISION: assignment is direct; the kernel re-validates
        # at refresh/commit — invalid states are observable between the two.
        self._tree._pending[self._id] = value

    # AC map ----------------------------------------------------------------------

    def set_ac_test_map(self, raw: Iterable[ACEntry | dict]) -> ValidationFindings:
        """Kernel validates every ``ac_id → ≥1 executable check`` (KERNEL_API §4.2);
        invalid ⇒ findings returned, never an exception leak. Leaf maps are mandatory;
        internal maps are optional integration views (their entries must resolve to a
        descendant check at close time)."""
        node = self._node
        findings: list[Finding] = []
        entries: list[ACEntry] = []
        for item in raw:
            try:
                entry = item if isinstance(item, ACEntry) else ACEntry.model_validate(item)
            except Exception as exc:  # shaped finding, not a leak
                findings.append(Finding(kind="invalid-ac-entry", node_id=self._id, detail=str(exc)))
                continue
            entries.append(entry)
        by_ac: dict[str, int] = {}
        for e in entries:
            by_ac[e.ac_id] = by_ac.get(e.ac_id, 0) + 1
        if not node.children and not entries:
            findings.append(Finding(
                kind="empty-leaf-map",
                node_id=self._id,
                detail="leaf AC map is mandatory (DESIGN §4.8); empty map only valid for internal nodes",
            ))
        for ac_id, n in by_ac.items():
            if n < 1:  # unreachable by construction; re-checked for close() symmetry
                findings.append(Finding(kind="ac-without-check", node_id=self._id, detail=f"{ac_id} has no check"))
        if findings:
            return ValidationFindings(items=findings)
        node.ac_test_map = entries
        return ValidationFindings(items=[])

    # closure ----------------------------------------------------------------------

    def close(
        self,
        results: CheckResults | None = None,
        quality: dict | None = None,
        verdicts: dict[str, str] | None = None,
    ) -> CloseResult:
        """Script proposes closure; the kernel re-checks (a) every AC in the map has
        ≥1 check, (b) those checks pass (results/verdicts passed in), (c) all children
        closed — and refuses with structured reasons if not green (KERNEL_API §4.2).
        The model never decides closure. ``quality`` (judge-panel quality artifact) is
        accepted for API parity and consumed by later milestones. A node without a map
        closes on (c) alone."""
        tree = self._tree
        tree.commit()
        node = self._node
        if node.status == "done":
            return CloseResult(ok=True, reasons=[])
        reasons: list[str] = []
        if node.status in ("blocked", "needs-user"):
            reasons.append(f"node is held ({node.status}); resolve before closure")
        verdicts = verdicts or {}
        results = results or CheckResults()
        if node.children:
            open_kids = [self._tree._nodes[c].id for c in node.children
                         if self._tree._nodes[c].status != "done"]
            if open_kids:
                reasons.append(f"children not closed: {open_kids}")
            if node.ac_test_map:
                desc_keys = self._descendant_check_keys()
                for e in node.ac_test_map:
                    if e.key not in desc_keys:
                        reasons.append(
                            f"integration check {e.key!r} for {e.ac_id} resolves to no descendant check "
                            "(internal maps are views over descendant checks, KERNEL_API §4.2)"
                        )
                    elif results.verdicts.get(e.key) != "pass":
                        reasons.append(
                            f"integration check {e.key!r} for {e.ac_id} verdict="
                            f"{results.verdicts.get(e.key, 'missing')!r}"
                        )
            # empty map + all children closed ⇒ (c) alone is sufficient
        else:
            if not node.ac_test_map:
                reasons.append("leaf requires a non-empty AC test map (DESIGN §4.8)")
            else:
                acs: dict[str, int] = {}
                for e in node.ac_test_map:
                    acs[e.ac_id] = acs.get(e.ac_id, 0) + 1
                for ac_id, n in acs.items():
                    if n < 1:
                        reasons.append(f"AC {ac_id} has no check")
                for e in node.ac_test_map:
                    if e.check_kind == "subjective":
                        v = verdicts.get(e.ac_id)
                        if v != "pass":
                            reasons.append(f"subjective AC {e.ac_id} lacks a passing judge verdict")
                    else:
                        v = results.verdicts.get(e.key)
                        if v is None:
                            reasons.append(f"check {e.key!r} for AC {e.ac_id} has no verdict (missing test)")
                        elif v != "pass":
                            reasons.append(f"check {e.key!r} for AC {e.ac_id} verdict={v!r}")
        if reasons:
            return CloseResult(ok=False, reasons=reasons)
        tree._force_close(node)
        return CloseResult(ok=True, reasons=[])

    def _descendant_check_keys(self) -> set[str]:
        keys: set[str] = set()
        for did in self._tree._descendants(self._id):
            for e in self._tree._nodes[did].ac_test_map:
                keys.add(e.key)
        return keys
