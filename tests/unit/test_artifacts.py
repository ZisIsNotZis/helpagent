"""Artifact store invariants (docs/6_ARCHITECTURE.md §4.2, docs/7_INTERFACE.md §4.6,):
bounded without truncation (split-window path), secret filter at the store
boundary, producer linkage as a schema field, single-producer rule."""

import pytest
from pydantic import ValidationError

from harness.artifacts import (
    CODE_KINDS,
    SIZE_CAP,
    Artifact,
    ArtifactStore,
    SplitWindowRequired,
    filter_secrets,
)
from harness.tree import TaskTree


# -- secret filter ------------------------------------------------------------


def test_secret_filter_redacts_known_patterns_and_counts():
    dirty = (
        "aws=AKIAIOSFODNN7EXAMPLE key\n"
        "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD\n"
        "password=hunter2\n"
        "postgres://admin:s3cret@db.internal:5432/app\n"
        "clean line stays\n"
    )
    filtered, n = filter_secrets(dirty)
    assert n == 4
    assert "AKIAIOSFODNN7EXAMPLE" not in filtered
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in filtered
    assert "hunter2" not in filtered
    assert "s3cret" not in filtered
    assert "[REDACTED]" in filtered
    assert "clean line stays" in filtered


def test_secret_filter_handles_pem_blocks():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQ\nmoredatanevermatch\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    filtered, n = filter_secrets(pem)
    assert n == 1 and "MIIEpAIBAAKCAQ" not in filtered and "[REDACTED]" in filtered


def test_store_never_persists_secrets_and_counts_without_logging_them():
    store = ArtifactStore()
    art = store.put("a-1", "n-1", "file", "password=letmein\nx = 1\n")
    assert "letmein" not in art.content
    assert art.redactions == 1 and store.total_redactions == 1


# -- bounded, never truncated ---------------------------------------------------


def test_artifact_size_cap_triggers_split_window_not_truncation():
    store = ArtifactStore()
    big = "x = 1\n" * (SIZE_CAP // 6 + 5)  # > cap, code kind
    with pytest.raises(SplitWindowRequired) as exc:
        store.put("a-big", "n-1", "write_test", big)
    assert "split-window" in str(exc.value)
    assert "a-big" not in store                       # nothing half-written
    assert len(big) > SIZE_CAP                        # and the content itself is intact
    small = store.put("a-small", "n-1", "write_test", "x = 1\n")
    assert small.content == "x = 1\n"                 # under cap: byte-faithful


def test_non_code_overflow_is_rejected_at_validation():
    # non-code kinds have no split path — the backstop validator rejects outright
    with pytest.raises(ValidationError):
        Artifact(artifact_id="a", node_id="n", kind="summary", content="y" * (SIZE_CAP + 1))


def test_code_kinds_cover_the_content_emitting_envelope():
    assert "write_test" in CODE_KINDS


# -- producer linkage via tree.attach -------------------------------------------


def _tree_with_leaf():
    tree = TaskTree(what="root")
    leaf = tree.add(tree.root, what="fix the thing", files=["calc.py"]) if hasattr(tree, "add") else None
    if leaf is None:  # fall back to whatever the construction API is
        leaf = tree.insert_ticket(tree.root, "fix the thing") if hasattr(tree, "insert_ticket") else None
    return tree, leaf


def test_producer_linkage_is_schema_field():
    # linkage is a REQUIRED schema field: an artifact without node_id is unrepresentable
    with pytest.raises(ValidationError):
        Artifact(artifact_id="a-1", kind="file", content="x = 1\n")  # type: ignore[call-arg]
    tree = TaskTree(what="root")
    leaf = tree.insert_ticket(tree.root, "leaf")
    art = Artifact(artifact_id="art-1", node_id=leaf.id, kind="file", content="x = 1\n")
    findings = tree.attach(leaf, art)
    assert findings.items == []
    assert leaf.produced_artifact_id == "art-1"
    assert leaf.output[0].artifact_id == "art-1" and leaf.output[0].producer_id == leaf.id
    assert "art-1" in tree.artifacts


def test_single_producer_rule_is_a_finding_not_a_silent_overwrite():
    tree = TaskTree(what="root")
    leaf1 = tree.insert_ticket(tree.root, "leaf-1")
    leaf2 = tree.insert_ticket(tree.root, "leaf-2")
    art = Artifact(artifact_id="art-1", node_id=leaf1.id, kind="file", content="x = 1\n")
    assert tree.attach(leaf1, art).items == []
    dup = Artifact(artifact_id="art-1", node_id=leaf2.id, kind="file", content="x = 1\n")
    findings = tree.attach(leaf2, dup)
    assert [f.kind for f in findings.items] == ["duplicate-producer"]
    assert leaf2.produced_artifact_id is None            # nothing overwritten
    assert leaf1.produced_artifact_id == "art-1"         # original producer stands


def test_relink_of_a_node_to_a_different_artifact_is_refused():
    tree = TaskTree(what="root")
    leaf = tree.insert_ticket(tree.root, "leaf")
    a1 = Artifact(artifact_id="art-1", node_id=leaf.id, kind="file", content="x = 1\n")
    a2 = Artifact(artifact_id="art-2", node_id=leaf.id, kind="file", content="x = 2\n")
    assert tree.attach(leaf, a1).items == []
    findings = tree.attach(leaf, a2)
    assert [f.kind for f in findings.items] == ["artifact-relink"]
    assert leaf.produced_artifact_id == "art-1"


def test_attach_flows_through_the_secret_filter():
    tree = TaskTree(what="root")
    leaf = tree.insert_ticket(tree.root, "leaf")
    art = Artifact(artifact_id="art-1", node_id=leaf.id, kind="file",
                   content="password=hunter2\nx = 1\n")
    tree.attach(leaf, art)
    stored = tree.artifacts.get("art-1")
    assert "hunter2" not in stored.content and "[REDACTED]" in stored.content


def test_attach_of_oversize_code_artifact_raises_split_window():
    tree = TaskTree(what="root")
    leaf = tree.insert_ticket(tree.root, "leaf")
    big = Artifact(artifact_id="art-big", node_id=leaf.id, kind="write_test",
                   content="x = 1\n" * (SIZE_CAP // 6 + 5))
    with pytest.raises(SplitWindowRequired):
        tree.attach(leaf, big)
    assert leaf.produced_artifact_id is None             # failed attach links nothing
