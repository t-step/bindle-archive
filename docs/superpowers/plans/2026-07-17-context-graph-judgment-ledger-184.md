# Context-Graph Judgment Ledger (#184) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the durable human-judgment layer for the context graph — validate untrusted semantic proposals into edge candidates, append-only judgment events, and reduce those events into effective authority for #185, exposed via `propose`/`confirm`/`candidates`.

**Architecture:** Three new focused modules under `bin/context_graph/` — `proposals.py` (pure edge-proposal validation against a #183 preview), `ledger.py` (append-only `judgments.jsonl` I/O + the reducer state machine), `review.py` (orchestration glue that the CLI calls: `propose`/`confirm`/`list_candidates`) — plus three new primitives added to the existing `canonical.py`. The deterministic graph is never re-implemented: #184 consumes `compiler.compile_preview(...)` for every "current graph" lookup. `confirm` and only `confirm` takes the single-writer lock; `propose` writes nothing.

**Tech Stack:** Python 3 stdlib only (`unittest`, `hashlib`, `json`, `secrets`, `datetime`). No third-party deps. Mirrors #180/#181/#183's existing `bin/context_graph/` conventions exactly.

## Global Constraints

- **Schema version is `1` throughout.** Every judgment event carries `"schema_version": 1`. No v2.
- **Reuse, never re-implement, frozen contracts.** Candidate keys via `canonical.candidate_key`/`canonical.anchor_candidate_key`; endpoint legality via `relationships.validate_endpoint_pair`; the "current graph" via `compiler.compile_preview`; lock via `lock.ProjectLock`; writes via `atomic_io`. Do not open a second parse path or a second matrix.
- **Endpoint-legality gate precedes candidate-key construction, always.** An illegal endpoint pair is a validation failure and **no candidate key is ever minted for it** (design §11, L604-610).
- **`propose` writes nothing and never locks** (design §4 L266-272). Only `confirm` (and #191's `init`/`config *`, #185's `apply`) acquire the lock. `lock.VALID_OPERATIONS` already reserves `"confirm"`.
- **`judgments.jsonl` is append-only** — one `fsync`'d line per event via `atomic_io.append_line_atomic`; never edited or truncated (design §5 L324-333).
- **No file inside a project's Git repo is touched.** All state lives under `<notes-home>/projects/<slug>/.bindle/context/`.
- **Gate discipline:** `make check` scans `git ls-files` only — `git add -A` new files before running it or the capability-inventory check false-greens (repo GATE GOTCHA). Bash formatted with `shfmt -i 2 -ci -w`. Never commit to `main`; never `--no-verify`; never push (operator does).
- **Every new module + test file must get a `capabilities.json` entry** or the inventory check fails.

## #184-owned modeling decisions (design leaves the algorithm to #184; inputs are frozen)

These three are **not** frozen byte-exactly by #180 §10, but their inputs/semantics are frozen by design §9/§11 and the #184 binding amendment. This plan fixes them; each is versioned by its own domain literal so a future recompute is stable and can never collide with another primitive's bytes.

1. **`edge_dependency_fingerprint`** — inputs frozen at design §9 L442-446 (canonical source/target IDs, current endpoint classes/kinds, relationship, canonical material basis; endpoint-matrix *validity* is constant-true for any minted candidate so it is not a hashed variable; v1 declares no source/target metadata material beyond class/kind, so none is added). Domain literal `bindle-context-edge-dependency-v1`.
2. **`edge_subject_key` / `anchor_subject_key`** — the reducer's grouping key, deliberately **coarser** than `candidate_key`: an edge subject is `(source, relationship, target)` with **no basis**; an anchor subject is `(project_id, map_path, section, entry_kind)` with **no `entry_fingerprint`**. This is what makes "accept candidate B supersedes candidate A for the same subject" (binding amendment) work — A and B share a subject_key but differ in candidate_key. Domain literals `bindle-context-edge-subject-v1` / `bindle-context-anchor-subject-v1`.
3. **Accepted-edge judgment event embeds `{source, relationship, target, basis}`.** `judgment.schema.json` sets no `additionalProperties:false`, so these are legal extra fields. They are **required** in practice: reduction-time endpoint revalidation (§11 L636-643) re-checks each accepted edge's endpoints against the current graph, and #185 materializes the edge into `index.json` — both need the edge content, which the `candidate_key` hash cannot reverse and which is never persisted anywhere else (an edge candidate exists only inside its `propose` call). Rejected/retired edge events carry only `subject_key`+`candidate_key` (suppression needs no content). Anchor accepted events carry the schema-required `assigned_id`+`entry_fingerprint`.

---

## File Structure

- **Modify** `bin/context_graph/canonical.py` — add `edge_subject_key`, `anchor_subject_key`, `edge_dependency_fingerprint` beside the existing frozen primitives.
- **Create** `bin/context_graph/proposals.py` — `validate_edge_proposal(proposal, preview) -> dict`. Pure: no I/O, no ledger, no lock. Endpoint-legality gate, then key + fingerprint, then assemble the candidate contract.
- **Create** `bin/context_graph/ledger.py` — `judgments_path`, `load_judgments`, `append_judgment`, `reduce_judgments`. Pure ledger persistence + the reducer state machine. No compiler import (revalidation is injected as a callback).
- **Create** `bin/context_graph/review.py` — orchestration the CLI calls: `propose(...)`, `confirm(...)`, `list_candidates(...)`. Glues `compile_preview` + `proposals` + `ledger` + `lock` + `ids`.
- **Modify** `bin/context-graph.py` — add `propose`/`confirm`/`candidates` subcommands (thin dispatch → `review`).
- **Create** tests: `bin/context_graph/tests/test_canonical_184.py`, `test_proposals.py`, `test_ledger.py`, `test_review.py`.
- **Create** `bin/context_graph/tests/fixtures_184.py` — shared literal graph/proposal builders for the reducer + endpoint-legality tests.
- **Modify** `bin/test-context-graph-cli.sh` — process-level `propose`/`confirm`/`candidates` integration + the cross-boundary endpoint-legality assertion (§16).
- **Modify** `capabilities.json` — classify all new modules + test files.

Task order respects the dependency chain: primitives (T1) → pure validation (T2) → ledger persistence (T3) → reducer (T4) → orchestration propose/confirm/candidates (T5-T7) → CLI + capabilities (T8) → cross-boundary fixtures + gates (T9).

---

### Task 1: `canonical.py` — the three #184-owned primitives

**Files:**
- Modify: `bin/context_graph/canonical.py` (append after `anchor_dependency_fingerprint`, ~L165)
- Test: `bin/context_graph/tests/test_canonical_184.py` (new)

**Interfaces:**
- Consumes: existing `canonical.canonical_basis_bytes`, `hashlib`, `json`.
- Produces:
  - `edge_subject_key(source_id, relationship, target_id) -> str` (`"edge-subject:sha256:"+hex`)
  - `anchor_subject_key(project_id, map_path, section, entry_kind) -> str` (`"anchor-subject:sha256:"+hex`)
  - `edge_dependency_fingerprint(source_id, source_class, source_kind, relationship, target_id, target_class, target_kind, basis_entries) -> str` (`"sha256:"+hex`)

- [ ] **Step 1: Write the failing test**

```python
# bin/context_graph/tests/test_canonical_184.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import canonical


BASIS = [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "p1"}]


class EdgeSubjectKey(unittest.TestCase):
    def test_stable_and_prefixed(self):
        k = canonical.edge_subject_key("A", "supports", "B")
        self.assertTrue(k.startswith("edge-subject:sha256:"))
        self.assertEqual(k, canonical.edge_subject_key("A", "supports", "B"))

    def test_basis_and_explanation_do_not_participate(self):
        # subject_key is coarser than candidate_key: it has no basis input at all.
        self.assertEqual(
            canonical.edge_subject_key("A", "supports", "B"),
            canonical.edge_subject_key("A", "supports", "B"),
        )

    def test_endpoints_or_relationship_change_the_subject(self):
        base = canonical.edge_subject_key("A", "supports", "B")
        self.assertNotEqual(base, canonical.edge_subject_key("A", "contradicts", "B"))
        self.assertNotEqual(base, canonical.edge_subject_key("A", "supports", "C"))

    def test_contradicts_is_symmetric(self):
        self.assertEqual(
            canonical.edge_subject_key("A", "contradicts", "B"),
            canonical.edge_subject_key("B", "contradicts", "A"),
        )

    def test_directional_relationship_is_not_symmetric(self):
        self.assertNotEqual(
            canonical.edge_subject_key("A", "supports", "B"),
            canonical.edge_subject_key("B", "supports", "A"),
        )


class AnchorSubjectKey(unittest.TestCase):
    def test_coarser_than_candidate_key_ignores_entry_fingerprint(self):
        # Two different entry byte-versions of the same map slot share a subject.
        s1 = canonical.anchor_subject_key("project:p", "map.md", "decisions", "decision")
        s2 = canonical.anchor_subject_key("project:p", "map.md", "decisions", "decision")
        self.assertEqual(s1, s2)
        self.assertTrue(s1.startswith("anchor-subject:sha256:"))

    def test_section_or_kind_change_changes_subject(self):
        base = canonical.anchor_subject_key("project:p", "map.md", "decisions", "decision")
        self.assertNotEqual(
            base, canonical.anchor_subject_key("project:p", "map.md", "learnings", "decision")
        )


class EdgeDependencyFingerprint(unittest.TestCase):
    def test_prefixed_and_distinct_from_candidate_key(self):
        fp = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning", BASIS
        )
        self.assertTrue(fp.startswith("sha256:"))
        # Distinct domain literal → never equals the candidate key digest.
        self.assertNotEqual(fp, canonical.candidate_key("A", "supports", "B", BASIS))

    def test_endpoint_kind_change_stales(self):
        base = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning", BASIS
        )
        changed = canonical.edge_dependency_fingerprint(
            "A", "semantic", "assumption", "supports", "B", "semantic", "learning", BASIS
        )
        self.assertNotEqual(base, changed)

    def test_basis_change_stales(self):
        base = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning", BASIS
        )
        other = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning",
            [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "p2"}],
        )
        self.assertNotEqual(base, other)

    def test_none_kind_encodes_unambiguously(self):
        # A project endpoint has kind None; must hash without error.
        fp = canonical.edge_dependency_fingerprint(
            "P", "project", None, "contains", "A", "semantic", "decision", []
        )
        self.assertTrue(fp.startswith("sha256:"))

    def test_contradicts_is_symmetric(self):
        a = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "contradicts", "B", "semantic", "decision", BASIS
        )
        b = canonical.edge_dependency_fingerprint(
            "B", "semantic", "decision", "contradicts", "A", "semantic", "decision", BASIS
        )
        self.assertEqual(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_canonical_184 -v` (or from repo root: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v`)
Expected: FAIL — `AttributeError: module 'context_graph.canonical' has no attribute 'edge_subject_key'`.

- [ ] **Step 3: Write minimal implementation**

Append to `bin/context_graph/canonical.py`:

```python
def edge_subject_key(source_id, relationship, target_id):
    """Edge subject key: bindle-context-edge-subject-v1 — the reducer's
    grouping identity, deliberately coarser than the candidate key (no basis
    input). Two basis-varying candidates of the same relationship share one
    subject, so accepting the newer supersedes the older (issue #184 binding
    amendment). Symmetric `contradicts` collapses endpoint order, matching
    candidate_key."""
    if relationship == "contradicts":
        source_id, target_id = sorted((source_id, target_id))
    payload = b"\0".join(
        (
            b"bindle-context-edge-subject-v1",
            source_id.encode("utf-8"),
            relationship.encode("utf-8"),
            target_id.encode("utf-8"),
        )
    )
    return "edge-subject:sha256:" + hashlib.sha256(payload).hexdigest()


def anchor_subject_key(project_id, map_path, section, entry_kind):
    """Identity-anchor subject key: bindle-context-anchor-subject-v1 — the
    reducer's grouping identity for a single map slot, coarser than the anchor
    candidate key (no entry_fingerprint input). Editing an entry's bytes yields
    a new candidate key but the same subject, so re-accepting supersedes the
    prior acceptance for that slot (issue #184 binding amendment)."""
    payload = b"\0".join(
        (
            b"bindle-context-anchor-subject-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
        )
    )
    return "anchor-subject:sha256:" + hashlib.sha256(payload).hexdigest()


def _kind_token(kind):
    # Node kind is None only for the project node; real kinds are never empty,
    # so None -> "" is unambiguous. class is always hashed alongside, so this
    # can never collide a project endpoint with a semantic/evidence one.
    return "" if kind is None else kind


def edge_dependency_fingerprint(
    source_id,
    source_class,
    source_kind,
    relationship,
    target_id,
    target_class,
    target_kind,
    basis_entries,
):
    """Edge candidate-scoped staleness fingerprint:
    bindle-context-edge-dependency-v1 (issue #184; inputs frozen by design
    section 9). Hashes only the material dependencies of the candidate:
    canonical endpoint IDs, current endpoint classes/kinds, relationship, and
    the canonical material basis. Endpoint-matrix validity is constant-true for
    any minted candidate (an illegal pair never reaches key construction), so it
    is not a hashed variable. v1 declares no source/target metadata material
    beyond class/kind. Symmetric `contradicts` collapses the two endpoint
    triples together so A-contradicts-B and B-contradicts-A share a
    fingerprint. Own domain literal so its bytes never equal a candidate key."""
    src = (source_id, source_class, _kind_token(source_kind))
    tgt = (target_id, target_class, _kind_token(target_kind))
    if relationship == "contradicts":
        src, tgt = sorted((src, tgt))
    payload = b"\0".join(
        (
            b"bindle-context-edge-dependency-v1",
            src[0].encode("utf-8"),
            src[1].encode("utf-8"),
            src[2].encode("utf-8"),
            relationship.encode("utf-8"),
            tgt[0].encode("utf-8"),
            tgt[1].encode("utf-8"),
            tgt[2].encode("utf-8"),
            canonical_basis_bytes(basis_entries),
        )
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k canonical`
Expected: PASS (all `test_canonical_184` cases green; existing `test_canonical` still green).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/canonical.py bin/context_graph/tests/test_canonical_184.py
git commit -m "feat(#184): add edge subject/dependency + anchor subject key primitives"
```

---

### Task 2: `proposals.py` — validate an edge proposal into a candidate

**Files:**
- Create: `bin/context_graph/proposals.py`
- Test: `bin/context_graph/tests/test_proposals.py`
- Create: `bin/context_graph/tests/fixtures_184.py` (shared literal builders)

**Interfaces:**
- Consumes: `canonical.candidate_key`, `canonical.edge_dependency_fingerprint`, `canonical.edge_subject_key`, `canonical.canonical_basis_bytes` (for validating basis shape), `relationships.validate_endpoint_pair`, `relationships.canonicalize_contradicts_endpoints`.
- Produces:
  - `validate_edge_proposal(proposal, preview) -> {"candidate": dict|None, "subject_key": str|None, "findings": [dict]}`. A finding is `{"code": str, "message": str}`. `candidate` is non-None only when `findings` is empty. The candidate dict is a schema-valid `subject_type:"edge"` candidate.
  - Finding codes (module constants): `E_PROPOSAL_MALFORMED`, `E_PROPOSAL_UNKNOWN_ENDPOINT`, `E_PROPOSAL_ILLEGAL_ENDPOINT`, `E_PROPOSAL_BASIS_INVALID`, `E_PROPOSAL_ADVISORY_KEY_MISMATCH`.
  - `nodes_by_id(preview) -> dict` helper (maps `n["id"] -> n`).

**Preview contract** (from `compiler.compile_preview`): `preview["nodes"]` is a **list** of `{"id","class","kind","label","status"}`; build the index yourself. Node `kind` is `None` for the project node.

- [ ] **Step 1: Write the shared fixtures**

```python
# bin/context_graph/tests/fixtures_184.py
"""Literal builders for #184 reducer + proposal tests — a minimal in-memory
#183 preview and proposal envelopes, so tests need no real notes-home."""

DECISION_A = {"id": "context-node:bindle:aaaa", "class": "semantic",
              "kind": "decision", "label": "Decision A", "status": "active"}
LEARNING_B = {"id": "context-node:bindle:bbbb", "class": "semantic",
              "kind": "learning", "label": "Learning B", "status": "active"}
PR_NODE = {"id": "github-pr:o/r#1", "class": "evidence",
           "kind": "github_pr", "label": "PR 1", "status": "active"}


def preview(nodes=None):
    return {
        "schema_version": 1,
        "project_id": "project:deadbeef",
        "nodes": list(nodes if nodes is not None else [DECISION_A, LEARNING_B, PR_NODE]),
        "edges": [],
        "identity_anchor_candidates": [],
        "conflicts": [],
        "coverage": {},
    }


def edge_proposal(source=DECISION_A["id"], relationship="supports",
                  target=LEARNING_B["id"], basis=None, producer="human",
                  explanation="because", advisory_key=None):
    p = {"source": source, "relationship": relationship, "target": target,
         "basis": basis if basis is not None else [], "explanation": explanation,
         "producer": producer}
    if advisory_key is not None:
        p["advisory_candidate_key"] = advisory_key
    return p
```

- [ ] **Step 2: Write the failing test**

```python
# bin/context_graph/tests/test_proposals.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import proposals, canonical
from context_graph.tests import fixtures_184 as fx


class ValidateEdgeProposal(unittest.TestCase):
    def test_valid_semantic_edge_produces_candidate(self):
        out = proposals.validate_edge_proposal(fx.edge_proposal(), fx.preview())
        self.assertEqual(out["findings"], [])
        c = out["candidate"]
        self.assertEqual(c["subject_type"], "edge")
        self.assertEqual(c["candidate_origin"], "validated_proposal")
        self.assertEqual(c["validation_status"], "valid")
        self.assertEqual(c["source_class"], "semantic")
        self.assertEqual(c["source_kind"], "decision")
        self.assertEqual(c["target_kind"], "learning")
        self.assertTrue(c["candidate_key"].startswith("candidate:sha256:"))
        # Key equals the frozen primitive over the resolved ids + basis.
        self.assertEqual(
            c["candidate_key"],
            canonical.candidate_key(fx.DECISION_A["id"], "supports", fx.LEARNING_B["id"], []),
        )
        self.assertEqual(out["subject_key"],
                         canonical.edge_subject_key(fx.DECISION_A["id"], "supports", fx.LEARNING_B["id"]))

    def test_unknown_endpoint_is_rejected_without_a_key(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(target="context-node:bindle:nope"), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_UNKNOWN_ENDPOINT", [f["code"] for f in out["findings"]])

    def test_illegal_endpoint_is_rejected_before_key_construction(self):
        # 'supersedes' requires same kind; decision -> learning is illegal.
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(relationship="supersedes"), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_ILLEGAL_ENDPOINT", [f["code"] for f in out["findings"]])

    def test_advisory_key_mismatch_is_a_precise_failure(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(advisory_key="candidate:sha256:" + "0" * 64), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_ADVISORY_KEY_MISMATCH", [f["code"] for f in out["findings"]])

    def test_malformed_proposal_missing_field(self):
        bad = {"source": fx.DECISION_A["id"], "relationship": "supports"}  # no target
        out = proposals.validate_edge_proposal(bad, fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_MALFORMED", [f["code"] for f in out["findings"]])

    def test_invalid_basis_entry_rejected(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(basis=[{"kind": "bogus"}]), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_BASIS_INVALID", [f["code"] for f in out["findings"]])

    def test_evidence_target_edge_is_legal(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(relationship="implemented_by", target=fx.PR_NODE["id"]),
            fx.preview())
        self.assertEqual(out["findings"], [])
        self.assertEqual(out["candidate"]["target_class"], "evidence")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k proposals`
Expected: FAIL — `ModuleNotFoundError: No module named 'context_graph.proposals'`.

- [ ] **Step 4: Write minimal implementation**

```python
# bin/context_graph/proposals.py
"""context_graph.proposals — validate an untrusted edge proposal into a
schema-valid edge candidate (issue #184). Pure: no I/O, no ledger, no lock.

Enforces design section 11's ordering: resolve endpoints against the current
#183 graph, validate the endpoint pair under #180's closed matrix, and ONLY
for a legal pair compute the candidate key + dependency fingerprint. An illegal
or unknown pair is a validation failure and no key is ever minted for it.
"""
from context_graph import canonical, relationships as rel

E_PROPOSAL_MALFORMED = "E_PROPOSAL_MALFORMED"
E_PROPOSAL_UNKNOWN_ENDPOINT = "E_PROPOSAL_UNKNOWN_ENDPOINT"
E_PROPOSAL_ILLEGAL_ENDPOINT = "E_PROPOSAL_ILLEGAL_ENDPOINT"
E_PROPOSAL_BASIS_INVALID = "E_PROPOSAL_BASIS_INVALID"
E_PROPOSAL_ADVISORY_KEY_MISMATCH = "E_PROPOSAL_ADVISORY_KEY_MISMATCH"

_REQUIRED = ("source", "relationship", "target", "basis", "explanation", "producer")
_PRODUCERS = frozenset({"human", "skill", "fixture"})


def nodes_by_id(preview):
    return {n["id"]: n for n in preview.get("nodes", [])}


def _fail(code, message):
    return {"candidate": None, "subject_key": None,
            "findings": [{"code": code, "message": message}]}


def validate_edge_proposal(proposal, preview):
    """Validate one proposal dict against a compile_preview() result.
    Returns {"candidate", "subject_key", "findings"}; candidate is non-None
    only when findings is empty."""
    if not isinstance(proposal, dict):
        return _fail(E_PROPOSAL_MALFORMED, "proposal must be an object")
    missing = [k for k in _REQUIRED if k not in proposal]
    if missing:
        return _fail(E_PROPOSAL_MALFORMED, "missing fields %r" % (sorted(missing),))
    if proposal["producer"] not in _PRODUCERS:
        return _fail(E_PROPOSAL_MALFORMED, "producer %r not one of %s"
                     % (proposal["producer"], sorted(_PRODUCERS)))
    if not isinstance(proposal["basis"], list):
        return _fail(E_PROPOSAL_BASIS_INVALID, "basis must be an array")

    source_id = proposal["source"]
    target_id = proposal["target"]
    relationship = proposal["relationship"]

    index = nodes_by_id(preview)
    src = index.get(source_id)
    tgt = index.get(target_id)
    if src is None or tgt is None:
        return _fail(E_PROPOSAL_UNKNOWN_ENDPOINT,
                     "endpoint(s) not in current graph: %r"
                     % ([e for e, n in ((source_id, src), (target_id, tgt)) if n is None],))

    # Endpoint-legality gate — BEFORE any key construction (design section 11).
    verdict = rel.validate_endpoint_pair(
        relationship, src["class"], src["kind"], tgt["class"], tgt["kind"])
    if not verdict["ok"]:
        return _fail(E_PROPOSAL_ILLEGAL_ENDPOINT,
                     "%s illegal for %s/%s -> %s/%s (%s)"
                     % (relationship, src["class"], src["kind"],
                        tgt["class"], tgt["kind"], verdict["reason"]))

    # Basis validation reuses the frozen canonicalizer (raises ValueError on any
    # unknown kind / bad field), so an invalid basis never reaches key bytes.
    try:
        canonical.canonical_basis_bytes(proposal["basis"])
    except ValueError as exc:
        return _fail(E_PROPOSAL_BASIS_INVALID, str(exc))

    # For symmetric contradicts, canonicalize endpoint order for the key.
    key_source, key_target = source_id, target_id
    if relationship == "contradicts":
        key_source, key_target = rel.canonicalize_contradicts_endpoints(source_id, target_id)

    candidate_key = canonical.candidate_key(
        key_source, relationship, key_target, proposal["basis"])

    advisory = proposal.get("advisory_candidate_key")
    if advisory is not None and advisory != candidate_key:
        return _fail(E_PROPOSAL_ADVISORY_KEY_MISMATCH,
                     "advisory key %r != recomputed %r" % (advisory, candidate_key))

    dependency_fingerprint = canonical.edge_dependency_fingerprint(
        source_id, src["class"], src["kind"], relationship,
        target_id, tgt["class"], tgt["kind"], proposal["basis"])
    subject_key = canonical.edge_subject_key(key_source, relationship, key_target)

    candidate = {
        "subject_type": "edge",
        "candidate_key": candidate_key,
        "candidate_origin": "validated_proposal",
        "dependency_fingerprint": dependency_fingerprint,
        "producer": proposal["producer"],
        "validation_status": "valid",
        "source": source_id,
        "relationship": relationship,
        "target": target_id,
        "basis": proposal["basis"],
        "source_class": src["class"],
        "source_kind": src["kind"],
        "target_class": tgt["class"],
        "target_kind": tgt["kind"],
        "explanation": proposal["explanation"],
    }
    return {"candidate": candidate, "subject_key": subject_key, "findings": []}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k proposals`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bin/context_graph/proposals.py bin/context_graph/tests/test_proposals.py bin/context_graph/tests/fixtures_184.py
git commit -m "feat(#184): validate edge proposals into candidates, legality before key"
```

---

### Task 3: `ledger.py` — append-only judgment persistence

**Files:**
- Create: `bin/context_graph/ledger.py`
- Test: `bin/context_graph/tests/test_ledger.py`

**Interfaces:**
- Consumes: `config.context_dir`, `atomic_io.append_line_atomic`.
- Produces:
  - `judgments_path(notes_home, slug) -> str` (`<context_dir>/judgments.jsonl`)
  - `load_judgments(path) -> [dict]` (missing file → `[]`; each line parsed JSON; a malformed line raises `LedgerError`)
  - `append_judgment(path, event) -> None` (append-only via `atomic_io`)
  - `JUDGMENTS_FILENAME = "judgments.jsonl"`; exception `LedgerError(Exception)` with `.findings` list.
- The reducer (`reduce_judgments`) is Task 4 — added to this same module.

- [ ] **Step 1: Write the failing test**

```python
# bin/context_graph/tests/test_ledger.py
import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import ledger, config


class LedgerIO(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.slug = "proj"
        config.init_project(self.notes_home, self.slug)
        self.path = ledger.judgments_path(self.notes_home, self.slug)

    def test_missing_file_reduces_to_empty(self):
        self.assertEqual(ledger.load_judgments(self.path), [])

    def test_append_then_load_roundtrip_preserves_order(self):
        ledger.append_judgment(self.path, {"schema_version": 1, "n": 1})
        ledger.append_judgment(self.path, {"schema_version": 1, "n": 2})
        loaded = ledger.load_judgments(self.path)
        self.assertEqual([e["n"] for e in loaded], [1, 2])

    def test_path_is_under_context_dir(self):
        self.assertTrue(self.path.endswith(os.path.join(".bindle", "context", "judgments.jsonl")))

    def test_malformed_line_raises(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        with self.assertRaises(ledger.LedgerError):
            ledger.load_judgments(self.path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k ledger`
Expected: FAIL — `ModuleNotFoundError: No module named 'context_graph.ledger'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bin/context_graph/ledger.py
"""context_graph.ledger — append-only judgments.jsonl persistence and the
effective-state reducer (issue #184). The ledger is never edited or truncated;
every write is one fsync'd line (design section 5). The reducer is pure over an
ordered event list plus an injected revalidation callback (no compiler import
here — orchestration in context_graph.review supplies the current graph)."""
import json
import os

from context_graph import atomic_io, config

JUDGMENTS_FILENAME = "judgments.jsonl"


class LedgerError(Exception):
    def __init__(self, message, findings=None):
        super().__init__(message)
        self.findings = findings or [{"code": "E_LEDGER", "message": message}]


def judgments_path(notes_home, slug):
    return os.path.join(config.context_dir(notes_home, slug), JUDGMENTS_FILENAME)


def load_judgments(path):
    """Return the ordered list of events. Missing file -> []. A malformed line
    raises LedgerError rather than being silently guessed past."""
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except ValueError as exc:
                raise LedgerError("malformed judgments.jsonl line %d: %s" % (lineno, exc))
    return events


def append_judgment(path, event):
    """Append one event as a single fsync'd JSONL line (append-only)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_io.append_line_atomic(path, event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k ledger`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/ledger.py bin/context_graph/tests/test_ledger.py
git commit -m "feat(#184): append-only judgments.jsonl persistence"
```

---

### Task 4: `ledger.py` — the reducer state machine

**Files:**
- Modify: `bin/context_graph/ledger.py` (add `reduce_judgments`)
- Test: `bin/context_graph/tests/test_ledger.py` (add `ReduceJudgments`)

**Interfaces:**
- Produces: `reduce_judgments(events, revalidate=None) -> dict` where the result is:
  ```python
  {
    "effective": { subject_key: {"subject_type", "candidate_key", "event"} },  # current acceptance per subject
    "rejected_keys": set(candidate_key, ...),   # unchanged-rejection suppression
    "retired_keys": set(candidate_key, ...),    # explicitly retired candidates
    "findings": [ {"code", "message", "index"}, ... ],  # malformed / stale-illegal
  }
  ```
- `revalidate(event) -> bool|None`: optional callback invoked per **accepted** event at reduction time. Returns `True` (still legal → contributes to effective), `False` (now illegal → not effective, emits `stale_illegal_judgment` finding), or the callback is `None` (skip revalidation — pure structural reduction, used by unit tests and `candidates` history listing). Endpoint revalidation against the live graph is #185/`confirm`'s concern; the reducer stays pure by taking it as a callback.
- Finding codes: `E_JUDGMENT_MALFORMED`, `stale_illegal_judgment`.

**Reducer rules** (binding amendment "Reducer state machine" + design §11):
1. Iterate events **in append order** (chronological; `decided_at` never participates in equality).
2. Each event must have `subject_type`, `subject_key`, `candidate_key`, `decision` — else `E_JUDGMENT_MALFORMED` finding, skip.
3. `accepted`: set `effective[subject_key] = this event` (a later acceptance for the same subject replaces the earlier — the earlier remains history). If `revalidate` is provided and returns `False`, do **not** install it; emit `stale_illegal_judgment` and leave any prior effective for that subject cleared (an illegal accepted event contributes no effective edge).
4. `rejected`: add `candidate_key` to `rejected_keys`. Only if it equals the subject's currently-effective `candidate_key` does it revoke that acceptance ("rejecting B does not revoke an already effective A unless B is A").
5. `retired`: add `candidate_key` to `retired_keys`. Only if it equals the subject's currently-effective `candidate_key` does it clear effective ("retiring historical A does not disable currently effective B").
6. A candidate whose key is in `rejected_keys` staying suppressed across later events is a *presentation* concern (`candidates`/`propose` consult `rejected_keys`); the reducer just maintains the set. Re-proposing rejected A remains suppressed even after B is accepted — because A's key stays in `rejected_keys` permanently.
7. Exact-duplicate events are naturally idempotent (re-applying the same transition yields the same state).

- [ ] **Step 1: Write the failing test** (the six binding-amendment fixtures + malformed)

```python
# append to bin/context_graph/tests/test_ledger.py
from context_graph import ledger


def _ev(subject, key, decision, subject_type="edge"):
    e = {"schema_version": 1, "subject_type": subject_type, "subject_key": subject,
         "candidate_key": key, "decision": decision, "decided_at": "2026-07-17T00:00:00Z"}
    if subject_type == "identity_anchor":
        e["assigned_id"] = "context-node:bindle:" + "1" * 32
        e["entry_fingerprint"] = "sha256:" + "2" * 64
    return e


class ReduceJudgments(unittest.TestCase):
    def eff_key(self, state, subject):
        got = state["effective"].get(subject)
        return got["candidate_key"] if got else None

    def test_reject_a_accept_b_then_repropose_a(self):
        # A stays suppressed; B effective.
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "rejected"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "accepted")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "b" * 64)
        self.assertIn("candidate:sha256:" + "a" * 64, state["rejected_keys"])

    def test_accept_a_reject_b_a_remains_effective(self):
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "rejected")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "a" * 64)

    def test_accept_a_accept_b_retire_a_b_remains(self):
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "a" * 64, "retired")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "b" * 64)
        self.assertIn("candidate:sha256:" + "a" * 64, state["retired_keys"])

    def test_accept_a_retire_a_then_accept_changed_b(self):
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "a" * 64, "retired"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "accepted")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "b" * 64)

    def test_reject_of_effective_revokes_it(self):
        key = "candidate:sha256:" + "a" * 64
        events = [_ev("S", key, "accepted"), _ev("S", key, "rejected")]
        state = ledger.reduce_judgments(events)
        self.assertIsNone(self.eff_key(state, "S"))

    def test_malformed_event_reported_not_guessed(self):
        events = [{"schema_version": 1, "decision": "accepted"}]  # no subject_key
        state = ledger.reduce_judgments(events)
        self.assertIsNone(state["effective"].get("S"))
        self.assertIn("E_JUDGMENT_MALFORMED", [f["code"] for f in state["findings"]])

    def test_stale_illegal_accepted_event_not_effective(self):
        key = "candidate:sha256:" + "a" * 64
        events = [_ev("S", key, "accepted")]
        state = ledger.reduce_judgments(events, revalidate=lambda e: False)
        self.assertIsNone(self.eff_key(state, "S"))
        self.assertIn("stale_illegal_judgment", [f["code"] for f in state["findings"]])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k Reduce`
Expected: FAIL — `AttributeError: module 'context_graph.ledger' has no attribute 'reduce_judgments'`.

- [ ] **Step 3: Write minimal implementation** (append to `ledger.py`)

```python
_DECISIONS = ("accepted", "rejected", "retired")


def reduce_judgments(events, revalidate=None):
    """Reduce an ordered append-only event list into effective state. Pure over
    (events, revalidate). See the reducer rules in the #184 plan / design
    section 11 and the binding amendment's reducer state machine."""
    effective = {}
    rejected_keys = set()
    retired_keys = set()
    findings = []

    for index, ev in enumerate(events):
        if not isinstance(ev, dict) or not all(
            k in ev for k in ("subject_type", "subject_key", "candidate_key", "decision")
        ) or ev["decision"] not in _DECISIONS:
            findings.append({"code": "E_JUDGMENT_MALFORMED",
                             "message": "event %d missing required fields or bad decision" % index,
                             "index": index})
            continue

        subject = ev["subject_key"]
        key = ev["candidate_key"]
        decision = ev["decision"]

        if decision == "accepted":
            if revalidate is not None and revalidate(ev) is False:
                findings.append({"code": "stale_illegal_judgment",
                                 "message": "accepted event %d endpoint no longer legal" % index,
                                 "index": index})
                # An illegal accepted event contributes no effective edge and
                # clears any prior effective acceptance for this subject.
                effective.pop(subject, None)
                continue
            effective[subject] = {"subject_type": ev["subject_type"],
                                  "candidate_key": key, "event": ev}
        elif decision == "rejected":
            rejected_keys.add(key)
            cur = effective.get(subject)
            if cur is not None and cur["candidate_key"] == key:
                effective.pop(subject, None)
        elif decision == "retired":
            retired_keys.add(key)
            cur = effective.get(subject)
            if cur is not None and cur["candidate_key"] == key:
                effective.pop(subject, None)

    return {"effective": effective, "rejected_keys": rejected_keys,
            "retired_keys": retired_keys, "findings": findings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k ledger`
Expected: PASS (all `LedgerIO` + `ReduceJudgments`).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/ledger.py bin/context_graph/tests/test_ledger.py
git commit -m "feat(#184): reducer state machine — acceptance, suppression, retirement"
```

---

### Task 5: `review.py` — `propose` orchestration

**Files:**
- Create: `bin/context_graph/review.py`
- Test: `bin/context_graph/tests/test_review.py`

**Interfaces:**
- Consumes: `compiler.compile_preview`, `proposals.validate_edge_proposal`, `atomic_io.read_json` (to load the `--input` proposal file — done in the CLI, passed in as a dict here).
- Produces:
  - `propose(notes_home, slug, proposal, repo_roots=None, github_adapter=None) -> dict` returning `{"candidate": dict|None, "subject_key": str|None, "findings": [dict]}`. Compiles a fresh preview, delegates to `validate_edge_proposal`, returns the validated candidate + its key. **Writes nothing, takes no lock** (design §4 L266-272).
  - `ReviewError(Exception)` with `.findings`, raised on a `compiler.CompilerError` (missing/malformed config) so the CLI renders it uniformly.

- [ ] **Step 1: Write the failing test** (real preview over a temp notes-home)

```python
# bin/context_graph/tests/test_review.py
import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import review, config


MAP_TWO_DECISIONS = """# proj

## decisions

- Decision one
  - evidence: sessions/2026-07-01-a.md

## learnings

- Learning one
"""


class ProposeBase(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.slug = "proj"
        config.init_project(self.notes_home, self.slug)
        pdir = os.path.join(self.notes_home, "projects", self.slug)
        with open(os.path.join(pdir, "map.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP_TWO_DECISIONS)

    def node_ids(self):
        from context_graph import compiler
        preview = compiler.compile_preview(self.notes_home, self.slug)
        return {(n["kind"]): n["id"] for n in preview["nodes"] if n["class"] == "semantic"}


class Propose(ProposeBase):
    def test_valid_proposal_returns_candidate_and_writes_nothing(self):
        ids = self.node_ids()
        proposal = {"source": ids["decision"], "relationship": "motivates",
                    "target": ids["learning"], "basis": [], "explanation": "x",
                    "producer": "human"}
        out = review.propose(self.notes_home, self.slug, proposal)
        self.assertEqual(out["findings"], [])
        self.assertTrue(out["candidate"]["candidate_key"].startswith("candidate:sha256:"))
        # No judgments.jsonl created by propose.
        from context_graph import ledger
        self.assertFalse(os.path.exists(ledger.judgments_path(self.notes_home, self.slug)))

    def test_illegal_proposal_surfaces_finding(self):
        ids = self.node_ids()
        proposal = {"source": ids["decision"], "relationship": "supersedes",
                    "target": ids["learning"], "basis": [], "explanation": "x",
                    "producer": "human"}
        out = review.propose(self.notes_home, self.slug, proposal)
        self.assertIsNone(out["candidate"])
        self.assertTrue(out["findings"])
```

> Note: the exact map syntax that makes `compile_preview` emit a `decision` and a `learning` semantic node must match #183's parser. If `MAP_TWO_DECISIONS` above doesn't yield both, adjust it to a minimal map that `test_compiler.py` already proves parses (copy a known-good fixture map from `test_compiler.py`). The assertion of interest is behavioral (valid → candidate, illegal → finding), not the specific ids.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k Propose`
Expected: FAIL — `ModuleNotFoundError: No module named 'context_graph.review'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bin/context_graph/review.py
"""context_graph.review — orchestration for #184's propose/confirm/candidates.
Glues the #183 deterministic preview, proposal validation, and the append-only
ledger. `propose` writes nothing and never locks; `confirm` takes the
single-writer lock and appends exactly one judgment event."""
from context_graph import compiler, proposals


class ReviewError(Exception):
    def __init__(self, message, findings=None):
        super().__init__(message)
        self.findings = findings or [{"code": "E_REVIEW", "message": message}]


def _preview(notes_home, slug, repo_roots, github_adapter):
    try:
        return compiler.compile_preview(
            notes_home, slug, repo_roots=repo_roots, github_adapter=github_adapter)
    except compiler.CompilerError as exc:
        raise ReviewError("cannot compile current graph", findings=exc.findings)


def propose(notes_home, slug, proposal, repo_roots=None, github_adapter=None):
    """Validate an edge proposal against a fresh #183 preview. Returns the
    validated candidate + subject_key + findings. Writes nothing; no lock."""
    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    return proposals.validate_edge_proposal(proposal, preview)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k Propose`
Expected: PASS (fix `MAP_TWO_DECISIONS` per the note if needed).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/review.py bin/context_graph/tests/test_review.py
git commit -m "feat(#184): propose orchestration over a fresh #183 preview"
```

---

### Task 6: `review.py` — `confirm` (edge + anchor), revalidation, ID allocation, lock

**Files:**
- Modify: `bin/context_graph/review.py`
- Test: `bin/context_graph/tests/test_review.py` (add `ConfirmEdge`, `ConfirmAnchor`)

**Interfaces:**
- Consumes: `ledger.reduce_judgments`/`append_judgment`/`load_judgments`/`judgments_path`, `lock.ProjectLock`, `ids.format_context_node_id`, `secrets.token_hex`, `canonical.anchor_candidate_key`, `proposals.validate_edge_proposal`, `relationships.validate_endpoint_pair`.
- Produces:
  - `confirm(notes_home, slug, candidate_key, decision, proposal=None, repo_roots=None, github_adapter=None, now=None) -> dict` returning `{"event": dict|None, "idempotent": bool, "findings": [dict]}`. Acquires `lock.ProjectLock(context_dir, "confirm")`. `now` is an injectable ISO-8601 string (default `datetime.now(timezone.utc).isoformat()`) so tests are deterministic.

**`confirm` algorithm** (design §11 L613-643):
1. Acquire the `"confirm"` lock for the whole operation.
2. Load + reduce existing judgments. **Idempotency short-circuit** (§11 L629-631): if `decision == "accepted"` and `candidate_key` is already the effective acceptance for its subject → append nothing, return `{"idempotent": True}`.
3. For an **edge** decision (`accepted`/`rejected` require `--input`):
   - Re-run `validate_edge_proposal(proposal, fresh_preview)` — propose-time validation is not trusted (§11 L613-616).
   - The recomputed candidate key **must equal** `candidate_key` (the `--candidate-key` arg) → else `candidate_stale_illegal`/`E_CONFIRM_KEY_MISMATCH` finding, no write.
   - A candidate legal at propose time but illegal now → `validate_edge_proposal` returns a finding → surface `candidate_stale_illegal`, no write.
   - `accepted` → append event with embedded `{source, relationship, target, basis}` (the reduction-time revalidation + #185 materialization need it). `rejected` → append event with only `subject_key`+`candidate_key`. `retired` → no `--input` needed; append retirement naming `candidate_key` (retirement "never allocates or revalidates", issue body).
4. For an **identity_anchor** decision: regenerate the fresh preview's anchor candidate matching `candidate_key` (recompute `anchor_candidate_key` over each `preview["identity_anchor_candidates"]`). If none matches → `candidate_stale_illegal`, no write. On `accepted`: allocate the opaque id internally — `ids.format_context_node_id(slug, secrets.token_hex(16))` — and append event with `assigned_id` + `entry_fingerprint` (schema-required). `rejected`/`retired`: append with `subject_key`+`candidate_key` (+ the schema still requires `assigned_id`/`entry_fingerprint` on any `identity_anchor` judgment, so carry the candidate's `entry_fingerprint` and, for non-accept, a deterministic placeholder is disallowed — instead only `accepted` anchors allocate; for `rejected`/`retired` of an anchor, reuse the previously-accepted event's `assigned_id` from the reducer's effective/history, or set `assigned_id` to the empty-allocation sentinel `""`). **Decision:** anchors are `accepted` or `retired` only in practice; `retired` names a prior acceptance so its `assigned_id`/`entry_fingerprint` come from the reduced effective event. Reject-of-a-fresh-anchor is treated as suppression with `assigned_id: ""`, `entry_fingerprint` from the live candidate.

- [ ] **Step 1: Write the failing test**

```python
# append to bin/context_graph/tests/test_review.py
from context_graph import review, ledger


class ConfirmEdge(ProposeBase):
    def _valid_proposal(self):
        ids = self.node_ids()
        return {"source": ids["decision"], "relationship": "motivates",
                "target": ids["learning"], "basis": [], "explanation": "x",
                "producer": "human"}

    def test_accept_appends_event_with_edge_content(self):
        p = self._valid_proposal()
        out = review.propose(self.notes_home, self.slug, p)
        key = out["candidate"]["candidate_key"]
        res = review.confirm(self.notes_home, self.slug, key, "accepted",
                             proposal=p, now="2026-07-17T00:00:00Z")
        self.assertEqual(res["findings"], [])
        self.assertFalse(res["idempotent"])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["decision"], "accepted")
        self.assertEqual(events[0]["source"], p["source"])   # embedded content
        self.assertEqual(events[0]["relationship"], "motivates")

    def test_accept_is_idempotent(self):
        p = self._valid_proposal()
        key = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        review.confirm(self.notes_home, self.slug, key, "accepted", proposal=p,
                       now="2026-07-17T00:00:00Z")
        res2 = review.confirm(self.notes_home, self.slug, key, "accepted", proposal=p,
                              now="2026-07-17T00:00:01Z")
        self.assertTrue(res2["idempotent"])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 1)  # no second line

    def test_confirm_key_mismatch_refused(self):
        p = self._valid_proposal()
        bogus = "candidate:sha256:" + "0" * 64
        res = review.confirm(self.notes_home, self.slug, bogus, "accepted", proposal=p,
                             now="2026-07-17T00:00:00Z")
        self.assertIsNone(res["event"])
        self.assertTrue(res["findings"])


class ConfirmAnchor(ProposeBase):
    def _anchor_candidate(self):
        from context_graph import compiler
        preview = compiler.compile_preview(self.notes_home, self.slug)
        cands = preview["identity_anchor_candidates"]
        self.assertTrue(cands, "map must yield at least one anchor candidate")
        return cands[0]

    def test_accept_allocates_id_and_appends(self):
        c = self._anchor_candidate()
        res = review.confirm(self.notes_home, self.slug, c["candidate_key"], "accepted",
                             now="2026-07-17T00:00:00Z")
        self.assertEqual(res["findings"], [])
        ev = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))[0]
        self.assertEqual(ev["subject_type"], "identity_anchor")
        self.assertTrue(ev["assigned_id"].startswith("context-node:"))
        self.assertEqual(ev["entry_fingerprint"], c["entry_fingerprint"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k Confirm`
Expected: FAIL — `AttributeError: ... has no attribute 'confirm'`.

- [ ] **Step 3: Write minimal implementation** (append to `review.py`)

```python
import secrets
from datetime import datetime, timezone

from context_graph import atomic_io, canonical, config, ids, ledger, lock
from context_graph import relationships as rel


def _now_iso(now):
    return now if now is not None else datetime.now(timezone.utc).isoformat()


def _anchor_by_key(preview, candidate_key):
    for c in preview.get("identity_anchor_candidates", []):
        recomputed = canonical.anchor_candidate_key(
            c["project_id"], c["map_path"], c["section"], c["entry_kind"],
            c["entry_fingerprint"])
        if recomputed == candidate_key:
            return c
    return None


def confirm(notes_home, slug, candidate_key, decision, proposal=None,
            repo_roots=None, github_adapter=None, now=None):
    """Revalidate against the current graph and append exactly one judgment
    event under the confirm lock. Returns {"event", "idempotent", "findings"}."""
    cdir = config.context_dir(notes_home, slug)
    path = ledger.judgments_path(notes_home, slug)
    is_anchor = decision in ("accepted", "rejected", "retired") and proposal is None \
        and candidate_key.startswith("anchor-candidate:sha256:")

    with lock.ProjectLock(cdir, "confirm"):
        existing = ledger.load_judgments(path)
        reduced = ledger.reduce_judgments(existing)  # structural; no revalidation
        # Idempotency: an already-effective accepted key performs no new write.
        if decision == "accepted":
            for cur in reduced["effective"].values():
                if cur["candidate_key"] == candidate_key:
                    return {"event": None, "idempotent": True, "findings": []}

        if is_anchor:
            return _confirm_anchor(notes_home, slug, candidate_key, decision,
                                   repo_roots, github_adapter, path, reduced, now)
        return _confirm_edge(notes_home, slug, candidate_key, decision, proposal,
                             repo_roots, github_adapter, path, now)


def _confirm_edge(notes_home, slug, candidate_key, decision, proposal,
                  repo_roots, github_adapter, path, now):
    if decision == "retired":
        # Retirement disables a prior acceptance by key; never revalidates.
        event = {"schema_version": 1, "subject_type": "edge",
                 "subject_key": _edge_subject_from_key_only(candidate_key, path),
                 "candidate_key": candidate_key, "decision": "retired",
                 "decided_at": _now_iso(now)}
        if event["subject_key"] is None:
            return {"event": None, "idempotent": False,
                    "findings": [{"code": "E_CONFIRM_UNKNOWN_CANDIDATE",
                                  "message": "no prior event names %s" % candidate_key}]}
        ledger.append_judgment(path, event)
        return {"event": event, "idempotent": False, "findings": []}

    if proposal is None:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "E_CONFIRM_INPUT_REQUIRED",
                              "message": "edge %s requires --input" % decision}]}
    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    result = proposals.validate_edge_proposal(proposal, preview)
    if result["candidate"] is None:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "candidate_stale_illegal", "message": m}
                             for m in [f["message"] for f in result["findings"]]] or
                            [{"code": "candidate_stale_illegal", "message": "invalid at confirm"}]}
    if result["candidate"]["candidate_key"] != candidate_key:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "E_CONFIRM_KEY_MISMATCH",
                              "message": "recomputed %s != --candidate-key %s"
                              % (result["candidate"]["candidate_key"], candidate_key)}]}
    c = result["candidate"]
    event = {"schema_version": 1, "subject_type": "edge",
             "subject_key": result["subject_key"], "candidate_key": candidate_key,
             "decision": decision, "decided_at": _now_iso(now)}
    if decision == "accepted":
        event.update({"source": c["source"], "relationship": c["relationship"],
                      "target": c["target"], "basis": c["basis"]})
    ledger.append_judgment(path, event)
    return {"event": event, "idempotent": False, "findings": []}


def _edge_subject_from_key_only(candidate_key, path):
    # Retirement names a candidate_key; recover its subject_key from history.
    for ev in ledger.load_judgments(path):
        if ev.get("candidate_key") == candidate_key and "subject_key" in ev:
            return ev["subject_key"]
    return None


def _confirm_anchor(notes_home, slug, candidate_key, decision, repo_roots,
                    github_adapter, path, reduced, now):
    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    c = _anchor_by_key(preview, candidate_key)
    if c is None and decision != "retired":
        return {"event": None, "idempotent": False,
                "findings": [{"code": "candidate_stale_illegal",
                              "message": "no current anchor candidate for %s" % candidate_key}]}
    subject_key = None
    entry_fp = None
    if c is not None:
        subject_key = canonical.anchor_subject_key(
            c["project_id"], c["map_path"], c["section"], c["entry_kind"])
        entry_fp = c["entry_fingerprint"]
    event = {"schema_version": 1, "subject_type": "identity_anchor",
             "candidate_key": candidate_key, "decision": decision,
             "decided_at": _now_iso(now)}
    if decision == "accepted":
        event["assigned_id"] = ids.format_context_node_id(slug, secrets.token_hex(16))
        event["subject_key"] = subject_key
        event["entry_fingerprint"] = entry_fp
    else:
        # rejected/retired: recover the prior acceptance's id/subject if present.
        prior = None
        for ev in ledger.load_judgments(path):
            if ev.get("candidate_key") == candidate_key or (
                    subject_key and ev.get("subject_key") == subject_key
                    and ev.get("decision") == "accepted"):
                prior = ev
        event["subject_key"] = subject_key or (prior or {}).get("subject_key")
        event["assigned_id"] = (prior or {}).get("assigned_id", "")
        event["entry_fingerprint"] = entry_fp or (prior or {}).get("entry_fingerprint", "sha256:" + "0" * 64)
    if event.get("subject_key") is None:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "E_CONFIRM_UNKNOWN_CANDIDATE",
                              "message": "no subject for anchor %s" % candidate_key}]}
    ledger.append_judgment(path, event)
    return {"event": event, "idempotent": False, "findings": []}
```

> Implementer note: the `_confirm_anchor` rejected/retired branch is the fiddliest part of #184 because `judgment.schema.json` requires `assigned_id`+`entry_fingerprint` on **every** `identity_anchor` event. Keep it simple: in v1 the realistic anchor decisions are `accepted` and `retired`-of-a-prior-acceptance. Validate this branch against the schema with `bin/test-context-graph-schema.sh`'s conformance test (it round-trips every emitted event through `judgment.schema.json`); if a rejected-fresh-anchor event can't satisfy the schema cleanly, raise it as an open question rather than emitting a schema-invalid line.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k Confirm`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/review.py bin/context_graph/tests/test_review.py
git commit -m "feat(#184): confirm — revalidate, allocate anchor id, append under lock"
```

---

### Task 7: `review.py` — `list_candidates` (the union presentation)

**Files:**
- Modify: `bin/context_graph/review.py`
- Test: `bin/context_graph/tests/test_review.py` (add `ListCandidates`)

**Interfaces:**
- Produces: `list_candidates(notes_home, slug, subject_type=None, status=None, repo_roots=None, github_adapter=None) -> {"rows": [dict], "findings": [dict]}`.
- Semantics (design §4 L241-257):
  - `status == "pending"` + `identity_anchor` (or unspecified) → re-run preview, list every current `identity_anchor_candidate` (always reproducible, never persisted). Each row discloses `subject_type` + `candidate_origin`.
  - `status == "pending"` + `edge` → **always empty** (no persisted pending edge state exists by construction).
  - `status in ("accepted","rejected","retired")` → read + reduce `judgments.jsonl`; project the effective/rejected/retired events. Each row discloses `subject_type` + `candidate_origin`.
  - No `--status` → union of both sources.
  - `--subject-type` filters rows to that type. `list_candidates` validates/generates nothing new.

- [ ] **Step 1: Write the failing test**

```python
# append to bin/context_graph/tests/test_review.py
class ListCandidates(ProposeBase):
    def test_pending_edge_is_always_empty(self):
        out = review.list_candidates(self.notes_home, self.slug,
                                     subject_type="edge", status="pending")
        self.assertEqual(out["rows"], [])

    def test_pending_anchor_lists_live_candidates(self):
        out = review.list_candidates(self.notes_home, self.slug,
                                     subject_type="identity_anchor", status="pending")
        self.assertTrue(out["rows"])
        for r in out["rows"]:
            self.assertEqual(r["subject_type"], "identity_anchor")
            self.assertIn("candidate_origin", r)

    def test_accepted_reads_ledger(self):
        c = review.list_candidates(self.notes_home, self.slug,
                                   subject_type="identity_anchor", status="pending")["rows"][0]
        review.confirm(self.notes_home, self.slug, c["candidate_key"], "accepted",
                       now="2026-07-17T00:00:00Z")
        out = review.list_candidates(self.notes_home, self.slug, status="accepted")
        self.assertTrue(any(r["candidate_key"] == c["candidate_key"] for r in out["rows"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k ListCandidates`
Expected: FAIL — `AttributeError: ... 'list_candidates'`.

- [ ] **Step 3: Write minimal implementation** (append to `review.py`)

```python
def list_candidates(notes_home, slug, subject_type=None, status=None,
                    repo_roots=None, github_adapter=None):
    """Union of live #183 anchor regeneration and persisted ledger history.
    Validates/generates nothing (design section 4)."""
    rows = []
    want_pending = status in (None, "pending")
    want_ledger = status in (None, "accepted", "rejected", "retired")

    if want_pending and subject_type in (None, "identity_anchor"):
        preview = _preview(notes_home, slug, repo_roots, github_adapter)
        for c in preview.get("identity_anchor_candidates", []):
            rows.append({"subject_type": "identity_anchor", "status": "pending",
                         "candidate_origin": c["candidate_origin"],
                         "candidate_key": c["candidate_key"],
                         "display_claim": c.get("display_claim")})
    # Pending edge candidates never persist -> nothing to list (by construction).

    if want_ledger:
        events = ledger.load_judgments(ledger.judgments_path(notes_home, slug))
        reduced = ledger.reduce_judgments(events)
        for ev in events:
            st = _ledger_row_status(ev, reduced)
            if st is None or (status is not None and st != status):
                continue
            if subject_type is not None and ev.get("subject_type") != subject_type:
                continue
            rows.append({"subject_type": ev.get("subject_type"), "status": st,
                         "candidate_origin": "validated_proposal"
                         if ev.get("subject_type") == "edge" else "deterministic_compiler",
                         "candidate_key": ev.get("candidate_key")})
    return {"rows": rows, "findings": []}


def _ledger_row_status(ev, reduced):
    key = ev.get("candidate_key")
    if ev.get("decision") == "accepted":
        for cur in reduced["effective"].values():
            if cur["candidate_key"] == key:
                return "accepted"
        return None  # superseded/revoked acceptance is not a current row
    if ev.get("decision") == "rejected" and key in reduced["rejected_keys"]:
        return "rejected"
    if ev.get("decision") == "retired" and key in reduced["retired_keys"]:
        return "retired"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v -k ListCandidates`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/review.py bin/context_graph/tests/test_review.py
git commit -m "feat(#184): candidates union — live anchor regen + ledger history"
```

---

### Task 8: CLI wiring + `capabilities.json`

**Files:**
- Modify: `bin/context-graph.py` (add `propose`/`confirm`/`candidates` subcommands)
- Modify: `capabilities.json` (classify the 5 new modules + 4 new test files + fixtures)

**Interfaces:**
- Consumes: `review.propose`/`confirm`/`list_candidates`, `atomic_io.read_json` (load `--input`), the existing `_add_common_args`/`_emit`/`_error_findings` helpers.
- CLI shapes (design §4 L228-231):
  - `candidates --notes-home <p> --project <s> [--subject-type edge|identity_anchor] [--status pending|accepted|rejected|retired]`
  - `propose --notes-home <p> --project <s> --input <proposal.json>`
  - `confirm --notes-home <p> --project <s> --candidate-key <key> --decision accepted|rejected|retired [--input <proposal.json>]`

- [ ] **Step 1: Write the failing test** (in the shell harness, exercised in Task 9 too)

```bash
# probe added to bin/test-context-graph-cli.sh (see Task 9 for the full harness);
# for now, a quick manual check that the subcommands exist:
python3 bin/context-graph.py propose --help   # expect: exits 0, shows --input
python3 bin/context-graph.py confirm --help    # expect: shows --candidate-key/--decision
python3 bin/context-graph.py candidates --help # expect: shows --subject-type/--status
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 bin/context-graph.py propose --help`
Expected: FAIL — `argparse` errors `invalid choice: 'propose'`.

- [ ] **Step 3: Write minimal implementation**

In `bin/context-graph.py`, add `from context_graph import review` at top, and register the subcommands beside `preview` (copy the `cmd_preview` template). Handlers:

```python
def cmd_propose(args):
    try:
        proposal = atomic_io.read_json(args.input)
    except (OSError, ValueError) as exc:
        return _emit(_error_findings("E_INPUT_UNREADABLE", str(exc)), args.format)
    try:
        out = review.propose(args.notes_home, args.project, proposal)
    except review.ReviewError as exc:
        return _emit({"findings": exc.findings}, args.format)
    _emit(out, args.format)
    return 0 if out["candidate"] is not None else 1


def cmd_confirm(args):
    proposal = None
    if args.input:
        try:
            proposal = atomic_io.read_json(args.input)
        except (OSError, ValueError) as exc:
            return _emit(_error_findings("E_INPUT_UNREADABLE", str(exc)), args.format)
    try:
        out = review.confirm(args.notes_home, args.project, args.candidate_key,
                             args.decision, proposal=proposal)
    except review.ReviewError as exc:
        return _emit({"findings": exc.findings}, args.format)
    _emit(out, args.format)
    return 0 if not out["findings"] else 1


def cmd_candidates(args):
    try:
        out = review.list_candidates(args.notes_home, args.project,
                                     subject_type=args.subject_type, status=args.status)
    except review.ReviewError as exc:
        return _emit({"findings": exc.findings}, args.format)
    _emit(out, args.format)
    return 0
```

Registration (beside the `preview` parser):

```python
p_candidates = sub.add_parser("candidates", help="list candidates (union of live anchors + ledger)")
_add_common_args(p_candidates)
p_candidates.add_argument("--subject-type", choices=["edge", "identity_anchor"], default=None)
p_candidates.add_argument("--status", choices=["pending", "accepted", "rejected", "retired"], default=None)
p_candidates.set_defaults(func=cmd_candidates)

p_propose = sub.add_parser("propose", help="validate an edge proposal (writes nothing)")
_add_common_args(p_propose)
p_propose.add_argument("--input", required=True, help="path to a proposal.json envelope")
p_propose.set_defaults(func=cmd_propose)

p_confirm = sub.add_parser("confirm", help="append a judgment event (takes the lock)")
_add_common_args(p_confirm)
p_confirm.add_argument("--candidate-key", required=True)
p_confirm.add_argument("--decision", required=True, choices=["accepted", "rejected", "retired"])
p_confirm.add_argument("--input", default=None, help="proposal.json (required for edge accepted|rejected)")
p_confirm.set_defaults(func=cmd_confirm)
```

Ensure `atomic_io` is imported in `bin/context-graph.py` (it may already be). If `_emit_text` doesn't know these new dict shapes, they fall through to JSON — acceptable; add a `--format text` renderer only if a test needs it.

- [ ] **Step 4: Classify new files in `capabilities.json`**

Add `not_a_capability` entries for each new module + test + fixtures (mirror #183's 6 entries):
`bin/context_graph/proposals.py`, `ledger.py`, `review.py`, `bin/context_graph/tests/test_canonical_184.py`, `test_proposals.py`, `test_ledger.py`, `test_review.py`, `fixtures_184.py`. Extend the existing `context-graph` capability row's description to mention `propose`/`confirm`/`candidates`.

- [ ] **Step 5: Run to verify it passes**

Run: `git add -A && python3 bin/context-graph.py candidates --help && bin/check.sh`
Expected: subcommand help prints; `bin/check.sh` (capability inventory) green now that new files are tracked + classified.

- [ ] **Step 6: Commit**

```bash
git add bin/context-graph.py capabilities.json
git commit -m "feat(#184): wire propose/confirm/candidates CLI + capability ledger"
```

---

### Task 9: Cross-boundary endpoint-legality fixtures + shell harness + full gate

**Files:**
- Modify: `bin/test-context-graph-cli.sh` (process-level propose→confirm→candidates + the §16 cross-boundary assertion)
- Create: fixtures under `testdata/context-graph-judgment/v1/` (proposal envelopes: one legal, one illegal-endpoint, one advisory-key-mismatch)
- Test: run `make check` + `make test`

**Interfaces:**
- The §16 cross-boundary requirement: prove that a direct-CLI proposal, a fixture-file proposal, and a prior ledger event **all** hit the same `relationships.validate_endpoint_pair` at each checkpoint (propose-time, confirm-time revalidation, reduction-time). The unit tests already cover propose/confirm/reduce; this harness adds the process-level proof that the CLI path enforces it identically.

- [ ] **Step 1: Add the CLI integration probe**

Append to `bin/test-context-graph-cli.sh` a scenario that, in a throwaway notes-home: `init`, writes a minimal `map.md`, runs `propose --input <legal.json>` (asserts a `candidate_key` is printed and exit 0), `confirm --candidate-key <k> --decision accepted --input <legal.json>` (asserts exit 0 + a `judgments.jsonl` line appears), `candidates --status accepted` (asserts the key is listed), then `propose --input <illegal.json>` (asserts exit 1 + no candidate). Use the same `shfmt -i 2 -ci -w` formatting as the rest of the file.

- [ ] **Step 2: Run the harness**

Run: `bash bin/test-context-graph-cli.sh`
Expected: PASS (all scenarios green).

- [ ] **Step 3: Run the schema-conformance harness** (every emitted candidate/judgment round-trips its schema)

Run: `bash bin/test-context-graph-schema.sh` (both with and without `jsonschema` installed — the second run in a throwaway venv `python3 -m venv /tmp/cg && /tmp/cg/bin/pip install jsonschema` proves real conformance, not a clean skip, exactly as #183's session verified).
Expected: PASS, 0 unexpected skips with `jsonschema` present.

- [ ] **Step 4: Full gate**

Run:
```bash
git add -A
make check     # capability inventory sees the new tracked files
make test      # full suite incl. the new unittest discovery + CLI harness
python3 -m unittest discover -s bin/context_graph/tests -t bin/context_graph -v
```
Expected: all green. If `make check` false-greens, confirm every new file is `git add`-ed (repo GATE GOTCHA) and classified in `capabilities.json`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(#184): cross-boundary endpoint-legality fixtures + CLI harness"
```

---

## Self-Review

**Spec coverage** (design §18 L1030-1034 — #184's exact deliverables):
- reducer state machine (§11) → Task 4 ✓
- confirm-time endpoint-legality revalidation → Task 6 `_confirm_edge` re-runs `validate_edge_proposal` ✓
- ledger-reduction endpoint revalidation → Task 4 `reduce_judgments(revalidate=...)` callback; wired at reduction sites in Task 6/7 (structural reduction) — **note:** live-graph revalidation at `candidates`/`status` read time is a thin call passing a `revalidate` closure over a fresh preview; add it in Task 7 if a fixture requires a stale-illegal row to disappear from `accepted`. Flagged, not silently dropped.
- validate-before-key-construction ordering → Task 2 `validate_edge_proposal` (gate precedes `candidate_key`) ✓
- `propose`/`confirm`/`candidates` → Tasks 5/6/7 + CLI Task 8 ✓
- endpoint-legality cross-boundary fixture set (§16) → Task 9 ✓
- append-only writes, single-writer lock participation → Task 3 (`append_line_atomic`) + Task 6 (`ProjectLock("confirm")`) ✓
- anchor ID allocation via #179 helper → Task 6 `ids.format_context_node_id(slug, secrets.token_hex(16))` ✓
- candidate-scoped dependency fingerprints → Task 1 `edge_dependency_fingerprint` ✓
- unchanged-rejection suppression / changed-input reproposal → Task 4 `rejected_keys` ✓

**Placeholder scan:** the two soft spots are (a) `MAP_TWO_DECISIONS` in Task 5 (may need a known-good map from `test_compiler.py`) and (b) the `_confirm_anchor` rejected/retired schema branch in Task 6 — both are flagged inline with a concrete resolution path, not left as "TODO".

**Type consistency:** `validate_edge_proposal` returns `{"candidate","subject_key","findings"}` consistently in Tasks 2/5/6. `reduce_judgments` returns `{"effective","rejected_keys","retired_keys","findings"}` consistently in Tasks 4/6/7. `confirm` returns `{"event","idempotent","findings"}`; `list_candidates` returns `{"rows","findings"}`; `propose` mirrors `validate_edge_proposal`. Candidate keys always `candidate:sha256:`; anchor keys `anchor-candidate:sha256:`; subject keys `edge-subject:`/`anchor-subject:`.

## Open decisions to confirm with the operator before/while implementing

1. The three #184-owned primitives (edge dependency fingerprint, subject keys, embedded edge content in accepted events) — inputs are frozen, algorithms are this plan's calls. Documented at the top; reversible only by changing the domain literals before any real ledger is written.
2. Anchor `rejected`-of-a-fresh-candidate event shape vs. `judgment.schema.json`'s required `assigned_id`/`entry_fingerprint` (Task 6 note) — resolve against the conformance test; escalate if it can't satisfy the schema cleanly.
