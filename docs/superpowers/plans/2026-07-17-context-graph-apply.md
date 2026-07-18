# Context-graph apply phase (#185) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `bin/context-graph.py apply` — the explicit, idempotent apply phase that recomputes deterministic state (#183), integrates effective human judgments (#184), inserts approved identity-anchor markers into `map.md`, and atomically writes the rebuildable `index.json` and the managed region of `context.md`.

**Architecture:** A thin CLI verb (`cmd_apply`) delegates to `context_graph.apply.apply()`, which acquires the project single-writer lock and runs the frozen 8-step pipeline from the design doc §12: recompute #183 → reduce #184 → construct planned `map.md` bytes with only authorized anchor markers → re-parse/re-compile the planned bytes into the final graph → materialize effective judged edges with endpoint-legality revalidation → whole-state validate → byte-compare no-op → atomic per-file writes in order (map, index, context) → release lock. Four small, independently testable units back it: `index_writer` (graph→index.json object), `projection` (graph→`context.md` managed region + lifecycle), `map_writer` (authorized anchor marker insertion, minimal diff), and `apply` (the orchestrator). One backward-compatible seam is added to `compiler.compile_preview` so apply can compile planned map bytes without a disk write.

**Tech Stack:** Python 3 stdlib only. Tests are `unittest.TestCase` under `bin/context_graph/tests/test_<module>.py`, auto-discovered by `python3 -m unittest discover` (no pytest, no new shell harness). JSON Schema draft-07 via the repo's existing `jsonschema`-optional conformance test.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the frozen contract (issue #185 body + `docs/design/2026-07-17-context-graph-foundation.md` §5, §7, §12, §15).

- **Six allowed write paths only**, all under `<notes-home>/projects/<project-slug>/`: `map.md` (approved anchor markers only), `context.md` (managed region only), `.bindle/context/{config.json,judgments.jsonl,index.json,.lock}`. Apply writes only `map.md`, `.bindle/context/index.json`, `context.md`. **No context-graph state file is ever written into a project's Git repository.**
- **Apply generates nothing:** no proposals, no candidates, no ledger appends. It consumes deterministic facts (#183) + effective judgments (#184) only.
- **`project_id` is immutable authority:** apply verifies config has one valid opaque `project_id`, the recomputed project node uses it, and any existing index names the same id. Apply never allocates, regenerates, migrates, or repairs it. Mismatch stops affected writes.
- **Atomic per-file, honest — never cross-file:** each of the three artifacts is written via temp-file-in-target-dir + `os.replace` (`atomic_io.write_atomic` / `write_json_atomic`). Write order is `map.md` → `index.json` → `context.md`. `judgments.jsonl` is never touched.
- **Whole-state validation precedes the first write** (§12 step 6): the complete planned state is validated against #180's invariant set (`validation.validate_bundle`) before any byte is written; any illegal endpoint pair aborts the entire apply.
- **Semantic no-op:** each artifact's planned bytes are byte-compared against current on-disk bytes; an unchanged artifact is not rewritten (no temp file, no rename, no mtime change). A second unchanged apply performs zero writes.
- **Managed-region marker (frozen name):** `<!-- bindle:context-graph:generated:begin -->` and `<!-- bindle:context-graph:generated:end -->`. This supersedes the illustrative `bindle:context:start`/`end` in #185's own body.
- **Deterministic output ordering:** nodes sorted by `id`, edges sorted by `key`; `index.json` rendered via `atomic_io.write_json_atomic` (`json.dumps(obj, indent=2, sort_keys=True) + "\n"`). No run-only timestamp participates in byte-equality.
- **Single-writer lock:** `with lock.ProjectLock(config.context_dir(nh, slug), "apply"):` — `"apply"` is already in `lock.VALID_OPERATIONS`. Release is guaranteed by the context manager's `__exit__` (even on exception). A hard kill leaves a stale `operation:"apply"` lock, surfaced by `config status`.
- **Endpoint legality is revalidated at materialization:** every judged edge revalidates via `relationships.validate_endpoint_pair(...)` against the *final* graph's node classes/kinds — a name is never trusted. A previously-accepted but now-illegal edge is a conflict, not materialized, and (§12 step 6) aborts the whole apply if it reaches whole-state validation.
- **Gate discipline:** `make check` and `make test` must be green before every commit. Every new `bin/context_graph/*.py` module and `tests/test_*.py` file needs a `not_a_capability` row in `capabilities.json` or `make check` fails (the FOOTGUN since #29). `make check` scans git-tracked files only — `git add` new files before trusting a green. Never commit to `main`; never `--no-verify`.
- **Doc cross-references inside this plan use inline code** (`` `path.md` ``), never Markdown links — `bin/check.sh`'s link checker resolves every Markdown link relative to this file's directory and would fail the gate.

---

## File Structure

**New modules** (`bin/context_graph/`):
- `index_writer.py` — pure: final graph → `index.json` object (deterministic ordering, schema-conformant). One responsibility: index materialization.
- `projection.py` — pure: final graph → `context.md` managed-region Markdown, plus the file-lifecycle planner (create / update / markerless-refuse / malformed-refuse / no-op / adopt). One responsibility: the presentation surface and its ownership rules.
- `map_writer.py` — pure: current `map.md` text + authorized anchor events → planned `map.md` bytes (minimal diff, only the target anchor line changes). One responsibility: the authorized map mutation.
- `apply.py` — the orchestrator: `build_plan()` (side-effect-free planned-state construction + validation) and `apply()` (lock + no-op compare + atomic writes). One responsibility: sequencing and the mutation lifecycle.

**New tests** (`bin/context_graph/tests/`): `test_index_writer.py`, `test_projection.py`, `test_map_writer.py`, `test_apply.py`.

**Modified:**
- `bin/context_graph/compiler.py` — add backward-compatible `map_text_override=None` to `compile_preview` (and thread it into `_read_map`'s call site) so apply compiles planned bytes without a disk write.
- `bin/context-graph.py` — register the `apply` subcommand + `cmd_apply` handler; extend `cmd_config_status` with orphaned-temp-file reporting.
- `schemas/context-graph/v1/index.schema.json` — extend from the current 4-field stub to the real materialized-index shape required by #185's acceptance criteria (node/edge item schemas, `project_id`, `edges[].origin`, `conflicts`, `unresolved_evidence`, `suppressed_rejections`).
- `bin/context_graph/tests/test_schema_conformance.py` — add bidirectional conformance for the extended `index.schema.json`.
- `capabilities.json` — one `not_a_capability` row per new module + test file; update the `context-graph` capability description to mention `apply`.
- `docs/context-graph-schema.md` — document the extended index shape (companion to the schema change).

**Decision callouts to confirm at the plan-review gate** (both mandated by the issue's own acceptance criteria; both mirror #183's in-PR `kind`-enum amendment):
1. **Index schema extension (Task 1).** The current `index.schema.json` (`additionalProperties:false`, only `schema_version/nodes/edges/coverage`, bare-array `nodes`/`edges`) cannot hold the conflicts/origins/unresolved-evidence/rejection-suppression the issue requires. #185 is the first real writer of `index.json`, so it extends the schema. Alternative rejected: burying conflicts inside nodes/edges — the issue lists them as distinct index contents.
2. **`config status` orphan-temp extension, not a new top-level `status` (Task 11).** #185's issue body names only `apply`. Incomplete-apply detection reuses the existing lock, already reported by `config status`. #185 adds only orphaned-temp-file reporting to that existing command; bare top-level `status`/`validate` stay with #186. Alternative rejected: building a new `status` verb now — scope creep beyond the issue body.

---

## Task 1: Extend `index.schema.json` + conformance test

**Files:**
- Modify: `schemas/context-graph/v1/index.schema.json`
- Modify: `bin/context_graph/tests/test_schema_conformance.py`
- Modify: `docs/context-graph-schema.md`

**Interfaces:**
- Produces: the frozen `index.json` envelope shape every later task renders against — top-level keys `schema_version` (const 1), `project_id` (string), `nodes` (array of node objects), `edges` (array of edge objects), `coverage` (the 7-key enum object, unchanged), `conflicts` (array), `unresolved_evidence` (array), `suppressed_rejections` (array). `edges[]` items carry `origin` ∈ `{"deterministic","human_judgment"}`.

- [ ] **Step 1: Write the failing conformance test**

Add to `bin/context_graph/tests/test_schema_conformance.py` a test that a minimal real index validates and that an unknown top-level key is rejected:

```python
def test_index_schema_accepts_materialized_index(self):
    schema = _load_schema("index.schema.json")
    doc = {
        "schema_version": 1,
        "project_id": "context-project:abc123",
        "nodes": [{"id": "context-project:abc123", "class": "project",
                   "kind": None, "label": "Demo", "status": "active"}],
        "edges": [{"key": "a|supports|b", "source": "a", "relationship": "supports",
                   "target": "b", "status": "confirmed", "origin": "human_judgment",
                   "basis": [], "review_trigger": False}],
        "coverage": {"project_map": "complete", "sessions": "complete",
                     "handoffs": "complete", "documents": "complete",
                     "github_issues": "complete", "github_prs": "complete",
                     "commits": "complete"},
        "conflicts": [], "unresolved_evidence": [], "suppressed_rejections": [],
    }
    _validate(doc, schema)  # must not raise

def test_index_schema_rejects_unknown_top_level_key(self):
    schema = _load_schema("index.schema.json")
    doc = {"schema_version": 1, "nodes": [], "edges": [],
           "coverage": {}, "surprise": 1}
    with self.assertRaises(Exception):
        _validate(doc, schema)
```

If `_load_schema`/`_validate` helpers do not already exist in this file, mirror the existing conformance-test helpers used for `node.schema.json` (read the file first and reuse its exact pattern rather than inventing new helper names).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_schema_conformance -v`
Expected: FAIL — the current stub has `additionalProperties:false` with no `project_id`/`conflicts`/… so the first test raises on the extra keys.

- [ ] **Step 3: Extend the schema**

Replace `schemas/context-graph/v1/index.schema.json` with the extended shape (keep `additionalProperties:false`, add the new properties, give `nodes`/`edges` item schemas that mirror `node.schema.json`/`edge.schema.json` by `$ref` where those exist, else inline the same required fields):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/index.schema.json",
  "title": "context-graph v1 derived materialized index (rebuildable, presentation only)",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "project_id", "nodes", "edges", "coverage",
               "conflicts", "unresolved_evidence", "suppressed_rejections"],
  "properties": {
    "schema_version": { "const": 1 },
    "project_id": { "type": "string", "minLength": 1 },
    "nodes": { "type": "array", "items": { "$ref": "node.schema.json" } },
    "edges": { "type": "array", "items": { "$ref": "edge.schema.json" } },
    "coverage": {
      "type": "object",
      "properties": {
        "project_map": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] },
        "sessions": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] },
        "handoffs": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] },
        "documents": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] },
        "github_issues": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] },
        "github_prs": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] },
        "commits": { "enum": ["complete", "partial", "uncertain", "unavailable", "unsupported"] }
      }
    },
    "conflicts": { "type": "array" },
    "unresolved_evidence": { "type": "array" },
    "suppressed_rejections": { "type": "array" }
  }
}
```

Before writing, **read `node.schema.json` and `edge.schema.json`** to confirm draft-07 `$ref` to a sibling filename resolves in this repo's conformance harness. If the harness loads schemas by `$id` (not by relative path), inline the node/edge `required` field lists instead of `$ref` (the conformance test in Step 1 tells you which: if `$ref` fails to resolve, the valid doc will error).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_schema_conformance -v`
Expected: PASS (both new tests).

- [ ] **Step 5: Document the extended shape**

Add a short subsection to `docs/context-graph-schema.md` describing the extended `index.json` fields (`project_id`, `edges[].origin`, `conflicts`, `unresolved_evidence`, `suppressed_rejections`) — one sentence each. Cross-reference other docs with inline code, never Markdown links.

- [ ] **Step 6: Commit**

```bash
git add schemas/context-graph/v1/index.schema.json \
        bin/context_graph/tests/test_schema_conformance.py \
        docs/context-graph-schema.md
git commit -m "feat(#185): extend index.schema.json to the materialized-index shape"
```

---

## Task 2: `index_writer.render_index` — final graph → index.json object

**Files:**
- Create: `bin/context_graph/index_writer.py`
- Test: `bin/context_graph/tests/test_index_writer.py`

**Interfaces:**
- Consumes: a `final_graph` dict shaped like `compiler.compile_preview`'s return (`project_id`, `nodes`, `edges`, `coverage`, `conflicts`) plus the apply-added `unresolved_evidence` and `suppressed_rejections` lists (Task 8 supplies them).
- Produces: `render_index(final_graph) -> dict` — a schema-conformant `index.json` object with `nodes` sorted by `id`, `edges` sorted by `key`, `edges[].origin` preserved, and the three list fields defaulted to `[]` when absent. Pure; no I/O.

- [ ] **Step 1: Write the failing test**

```python
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import index_writer


class RenderIndexTest(unittest.TestCase):
    def _graph(self):
        return {
            "schema_version": 1,
            "project_id": "context-project:abc",
            "nodes": [
                {"id": "n:b", "class": "semantic", "kind": "decision", "label": "B", "status": "active"},
                {"id": "n:a", "class": "semantic", "kind": "decision", "label": "A", "status": "active"},
            ],
            "edges": [
                {"key": "n:b|supports|n:a", "source": "n:b", "relationship": "supports",
                 "target": "n:a", "status": "confirmed", "origin": "human_judgment",
                 "basis": [], "review_trigger": False},
            ],
            "coverage": {"project_map": "complete", "sessions": "complete",
                         "handoffs": "complete", "documents": "complete",
                         "github_issues": "complete", "github_prs": "complete",
                         "commits": "complete"},
            "conflicts": [],
        }

    def test_nodes_sorted_by_id(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual([n["id"] for n in out["nodes"]], ["n:a", "n:b"])

    def test_edge_origin_and_key_preserved(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual(out["edges"][0]["origin"], "human_judgment")
        self.assertEqual(out["edges"][0]["key"], "n:b|supports|n:a")

    def test_list_fields_default_empty(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual(out["unresolved_evidence"], [])
        self.assertEqual(out["suppressed_rejections"], [])
        self.assertEqual(out["conflicts"], [])

    def test_project_id_and_version(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual(out["project_id"], "context-project:abc")
        self.assertEqual(out["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_index_writer -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'context_graph.index_writer'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Render the rebuildable per-project index.json from a final graph.

Pure and deterministic: nodes sorted by id, edges by key, no run-only
timestamp is included so byte-equality holds across identical runs
(design doc section 12, "Semantic no-op").
"""

SCHEMA_VERSION = 1


def render_index(final_graph):
    """final_graph: a compile_preview-shaped dict extended by apply with
    unresolved_evidence / suppressed_rejections. Returns a schema-conformant
    index.json object. Writes nothing."""
    nodes = sorted(final_graph.get("nodes", []), key=lambda n: n["id"])
    edges = sorted(final_graph.get("edges", []), key=lambda e: e["key"])
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": final_graph["project_id"],
        "nodes": nodes,
        "edges": edges,
        "coverage": final_graph.get("coverage", {}),
        "conflicts": final_graph.get("conflicts", []),
        "unresolved_evidence": final_graph.get("unresolved_evidence", []),
        "suppressed_rejections": final_graph.get("suppressed_rejections", []),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_index_writer -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/index_writer.py bin/context_graph/tests/test_index_writer.py
git commit -m "feat(#185): index_writer renders the deterministic materialized index"
```

---

## Task 3: `map_writer.plan_map_bytes` — authorized anchor marker insertion

**Files:**
- Create: `bin/context_graph/map_writer.py`
- Test: `bin/context_graph/tests/test_map_writer.py`

**Interfaces:**
- Consumes: current `map.md` text; the parsed entries from `map_parser.parse_project_map(text)["entries"]`; a list of authorized anchor events (each an effective-accepted `identity_anchor` ledger event carrying `assigned_id` + `entry_fingerprint`); and `canonical.entry_fingerprint` to match an event to its current unanchored entry.
- Produces: `plan_map_bytes(map_text, entries, authorized_anchors) -> (new_text, findings)`. Inserts `<!-- bindle:context-id: <assigned_id> -->` at the end of each matched entry's anchor line (§7 placement: claim heading / top-level bullet / tension-parent bullet). Only that one line changes per anchor; every other byte is identical. An authorized anchor with no current matching unanchored entry yields a finding (`stale_anchor_no_entry`) and no insertion. An entry that is already anchored is never re-anchored. Pure; no I/O.

- [ ] **Step 1: Write the failing test**

```python
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import map_writer, map_parser, canonical

MAP = """# Demo — project map

## Decisions

### Use a single-writer lock
why: correctness
so: no concurrent identity allocation

## Learnings
## Assumptions & tensions
## Open questions
## Superseded
"""


class PlanMapBytesTest(unittest.TestCase):
    def _entries(self, text):
        return map_parser.parse_project_map(text)["entries"]

    def _fp_of_first_unanchored(self, text):
        for e in self._entries(text):
            if not e["anchored"]:
                return canonical.entry_fingerprint(e["entry_bytes"])
        raise AssertionError("no unanchored entry in fixture")

    def test_inserts_marker_on_anchor_line_only(self):
        fp = self._fp_of_first_unanchored(MAP)
        anchors = [{"subject_type": "identity_anchor",
                    "assigned_id": "context-node:demo:deadbeef",
                    "entry_fingerprint": fp}]
        new_text, findings = map_writer.plan_map_bytes(MAP, self._entries(MAP), anchors)
        self.assertEqual(findings, [])
        self.assertIn("### Use a single-writer lock <!-- bindle:context-id: context-node:demo:deadbeef -->",
                      new_text)
        # exactly one line differs
        diff = [(a, b) for a, b in zip(MAP.splitlines(), new_text.splitlines()) if a != b]
        self.assertEqual(len(diff), 1)

    def test_unmatched_anchor_reports_and_writes_nothing(self):
        anchors = [{"subject_type": "identity_anchor",
                    "assigned_id": "context-node:demo:0000",
                    "entry_fingerprint": "sha256:nomatch"}]
        new_text, findings = map_writer.plan_map_bytes(MAP, self._entries(MAP), anchors)
        self.assertEqual(new_text, MAP)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "stale_anchor_no_entry")

    def test_no_anchors_is_identity(self):
        new_text, findings = map_writer.plan_map_bytes(MAP, self._entries(MAP), [])
        self.assertEqual(new_text, MAP)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
```

Before implementing, **verify `canonical.entry_fingerprint`'s exact call signature** (recon: `canonical.py:112`) — it may take the entry's marker-stripped bytes, or `(entry_bytes, ...)`. Match the test's `_fp_of_first_unanchored` helper to the real signature; the compiler builds identity-anchor candidates the same way at `compiler.py:306-318`, so mirror that call site exactly.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_map_writer -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'context_graph.map_writer'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Insert authorized identity-anchor markers into map.md with a minimal
diff. Only the target entry's anchor line changes; every other byte is
preserved. This is the same "never regenerate the file, never reorder the
owner's prose" discipline knowledge-promotion.md uses for map writes
(design doc section 12, "map.md marker writes")."""

from context_graph import canonical

_MARKER = "<!-- bindle:context-id: %s -->"


def _finding(code, message, **extra):
    out = {"code": code, "message": message}
    out.update(extra)
    return out


def plan_map_bytes(map_text, entries, authorized_anchors):
    """Return (new_text, findings). Inserts one anchor marker per authorized
    anchor whose entry_fingerprint matches a current *unanchored* entry, at
    the end of that entry's anchor line. Unmatched anchors are reported and
    change nothing."""
    # fingerprint -> unanchored entry
    by_fp = {}
    for e in entries:
        if not e["anchored"]:
            by_fp[canonical.entry_fingerprint(e["entry_bytes"])] = e

    insertions = {}  # 1-based line number -> assigned_id
    findings = []
    for anchor in authorized_anchors:
        fp = anchor["entry_fingerprint"]
        entry = by_fp.get(fp)
        if entry is None:
            findings.append(_finding(
                "stale_anchor_no_entry",
                "authorized anchor %r matches no current unanchored entry"
                % (anchor["assigned_id"],),
                assigned_id=anchor["assigned_id"], entry_fingerprint=fp))
            continue
        insertions[entry["line"]] = anchor["assigned_id"]

    if not insertions:
        return map_text, findings

    lines = map_text.split("\n")
    for line_no, assigned_id in insertions.items():
        idx = line_no - 1
        lines[idx] = lines[idx].rstrip() + " " + (_MARKER % assigned_id)
    return "\n".join(lines), findings
```

Confirm `entry["line"]` is 1-based and points at the anchor line (recon: `map_parser._new_entry` sets `line`; the compiler treats it as the anchor line). If the parser reports a different anchor-line field, use that field name instead — the test's `diff` assertion catches a wrong line.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_map_writer -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/map_writer.py bin/context_graph/tests/test_map_writer.py
git commit -m "feat(#185): map_writer inserts authorized anchor markers, minimal diff"
```

---

## Task 4: `projection` markers + `render_managed_region`

**Files:**
- Create: `bin/context_graph/projection.py`
- Test: `bin/context_graph/tests/test_projection.py`

**Interfaces:**
- Produces: module constants `BEGIN = "<!-- bindle:context-graph:generated:begin -->"`, `END = "<!-- bindle:context-graph:generated:end -->"`; and `render_managed_region(final_graph) -> str` — the deterministic Markdown body (headings from #185's projection structure: decision/learning graph, evidence & delivery, review-triggering coupling, unconnected durable entries, evidence coverage, conflicts), ordered stably, no run-only timestamp. Pure.

- [ ] **Step 1: Write the failing test**

```python
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import projection


def _graph():
    return {
        "project_id": "context-project:abc",
        "nodes": [
            {"id": "n:a", "class": "semantic", "kind": "decision", "label": "Use a lock", "status": "active"},
            {"id": "e:s1", "class": "evidence", "kind": "session", "label": "2026-07-01 note", "status": "active"},
        ],
        "edges": [
            {"key": "n:a|implemented_by|e:s1", "source": "n:a", "relationship": "implemented_by",
             "target": "e:s1", "status": "confirmed", "origin": "human_judgment",
             "basis": [], "review_trigger": False},
        ],
        "coverage": {"project_map": "complete", "sessions": "complete", "handoffs": "complete",
                     "documents": "complete", "github_issues": "complete",
                     "github_prs": "complete", "commits": "complete"},
        "conflicts": [],
    }


class RenderManagedRegionTest(unittest.TestCase):
    def test_contains_expected_sections(self):
        body = projection.render_managed_region(_graph())
        for heading in ["## Decision and learning graph", "## Evidence and delivery",
                        "## Review-triggering coupling", "## Unconnected durable entries",
                        "## Evidence coverage", "## Conflicts"]:
            self.assertIn(heading, body)

    def test_deterministic(self):
        self.assertEqual(projection.render_managed_region(_graph()),
                         projection.render_managed_region(_graph()))

    def test_evidence_attribution_rendered(self):
        body = projection.render_managed_region(_graph())
        self.assertIn("Use a lock", body)
        self.assertIn("implemented_by", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_projection -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Implement `BEGIN`/`END` constants and `render_managed_region`. Group nodes by `class`, render semantic entries with their confirmed relationships, evidence attribution edges (`discussed_in`/`implemented_by`/`validated_by`), a review-triggering-coupling section from `review_trigger` edges, an unconnected-durable-entries section (semantic nodes with no edges), the 7-key coverage block, and conflicts. Sort every list by a stable key (`id`/`key`). Do not embed a timestamp. Keep it a bounded reading surface, not a full graph dump (design doc §12 "Projection requirements"). Write real rendering code — no placeholder headings with empty bodies; each section iterates its slice of the graph.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_projection -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/projection.py bin/context_graph/tests/test_projection.py
git commit -m "feat(#185): projection renders the deterministic context.md managed region"
```

---

## Task 5: `projection.plan_context_md` — file lifecycle planner

**Files:**
- Modify: `bin/context_graph/projection.py`
- Modify: `bin/context_graph/tests/test_projection.py`

**Interfaces:**
- Consumes: the current `context.md` text (or `None` if absent) and the rendered managed-region body from Task 4.
- Produces: `plan_context_md(existing_text, managed_body) -> dict`. Returns one of:
  - `{"action": "create", "text": <full file with skeleton + marker pair + maintainer section>}` when `existing_text is None`;
  - `{"action": "update", "text": <existing bytes with only the region between BEGIN/END replaced>}` when exactly one valid marker pair is present and the region differs;
  - `{"action": "noop"}` when the file exists with a valid pair and the managed region already equals `managed_body` byte-for-byte;
  - `{"action": "conflict", "code": "context_md_unmanaged"}` when the file exists with no marker pair;
  - `{"action": "conflict", "code": "context_md_malformed_markers"}` for duplicate / nested / reversed / partial markers.
  Pure; no I/O. Content outside the marker pair is preserved byte-for-byte.

- [ ] **Step 1: Write the failing tests**

```python
from context_graph import projection as P

SKELE_BODY = "## Decision and learning graph\n(none)\n"


class PlanContextMdTest(unittest.TestCase):
    def test_absent_creates_skeleton_with_markers(self):
        out = P.plan_context_md(None, SKELE_BODY)
        self.assertEqual(out["action"], "create")
        self.assertIn(P.BEGIN, out["text"])
        self.assertIn(P.END, out["text"])
        self.assertIn(SKELE_BODY, out["text"])

    def test_update_replaces_only_managed_region(self):
        existing = ("# Demo — context\n" + P.BEGIN + "\nOLD\n" + P.END +
                    "\n## Maintainer notes\nkeep me\n")
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out["action"], "update")
        self.assertIn("keep me", out["text"])
        self.assertIn(SKELE_BODY, out["text"])
        self.assertNotIn("OLD", out["text"])

    def test_identical_region_is_noop(self):
        existing = P.BEGIN + "\n" + SKELE_BODY + P.END + "\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out["action"], "noop")

    def test_markerless_is_conflict(self):
        out = P.plan_context_md("# hand written, no markers\n", SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_unmanaged"})

    def test_duplicate_markers_is_conflict(self):
        existing = P.BEGIN + "\nA\n" + P.END + "\n" + P.BEGIN + "\nB\n" + P.END + "\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_malformed_markers"})

    def test_reversed_markers_is_conflict(self):
        existing = P.END + "\nx\n" + P.BEGIN + "\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_malformed_markers"})

    def test_partial_marker_is_conflict(self):
        existing = P.BEGIN + "\nonly begin, no end\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_malformed_markers"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_projection -v`
Expected: FAIL — `plan_context_md` not defined.

- [ ] **Step 3: Write minimal implementation**

Add a marker scanner (count `BEGIN`/`END` occurrences and check ordering) plus `plan_context_md`. Rules: 0 begin + 0 end + text present → `context_md_unmanaged`; exactly one begin then one end in order → update/noop; anything else (counts unequal, end-before-begin, nested) → `context_md_malformed_markers`. The `create` skeleton wraps `managed_body` in `BEGIN`/`END` under a `# <title> — context` heading and appends a `## Maintainer notes` user-owned section (design doc §12 suggested structure). For `update`, replace the substring from `BEGIN` through `END` (inclusive) with the freshly wrapped region, leaving all other bytes untouched. Include a `_title_for(final_graph)` or accept the title as a parameter — pick one and thread it consistently (Task 8 passes the project display name).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_projection -v`
Expected: PASS (all lifecycle tests).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/projection.py bin/context_graph/tests/test_projection.py
git commit -m "feat(#185): context.md lifecycle planner (create/update/noop/conflict)"
```

---

## Task 6: `projection.plan_adopt_context_md` — `--adopt-context-md` guard

**Files:**
- Modify: `bin/context_graph/projection.py`
- Modify: `bin/context_graph/tests/test_projection.py`

**Interfaces:**
- Consumes: current `context.md` text (must be present) and the managed-region body.
- Produces: `plan_adopt_context_md(existing_text, managed_body) -> dict`. If the file is **still markerless**, returns `{"action": "adopt", "text": <existing content wrapped in BEGIN/END with the managed region inserted, existing prose preserved as maintainer notes>}` — non-destructive regardless of ordinary prose edits. If the file has since gained a managed-region marker (valid or malformed), returns `{"action": "conflict", "code": "context_md_adopt_state_changed"}`. Pure.

- [ ] **Step 1: Write the failing tests**

```python
class AdoptContextMdTest(unittest.TestCase):
    def test_still_markerless_adopts(self):
        out = P.plan_adopt_context_md("hand written notes\n", SKELE_BODY)
        self.assertEqual(out["action"], "adopt")
        self.assertIn(P.BEGIN, out["text"])
        self.assertIn("hand written notes", out["text"])

    def test_gained_marker_refuses(self):
        existing = P.BEGIN + "\nx\n" + P.END + "\n"
        out = P.plan_adopt_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_adopt_state_changed"})

    def test_gained_malformed_marker_refuses(self):
        out = P.plan_adopt_context_md(P.BEGIN + "\nno end\n", SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_adopt_state_changed"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_projection -v`
Expected: FAIL — `plan_adopt_context_md` not defined.

- [ ] **Step 3: Write minimal implementation**

Reuse the Task-5 marker scanner: if any `BEGIN` or `END` occurrence exists (well-formed or not), refuse with `context_md_adopt_state_changed`; otherwise wrap the current content (as maintainer notes) plus the managed region and return `adopt`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_projection -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/projection.py bin/context_graph/tests/test_projection.py
git commit -m "feat(#185): --adopt-context-md guard (still-markerless only)"
```

---

## Task 7: `compiler.compile_preview` — `map_text_override` seam

**Files:**
- Modify: `bin/context_graph/compiler.py`
- Modify: `bin/context_graph/tests/test_compiler.py`

**Interfaces:**
- Produces: `compile_preview(notes_home, project_slug, repo_roots=None, github_adapter=None, map_text_override=None)`. When `map_text_override` is a string, the map is parsed from it (with `project_map` coverage `"complete"`) instead of reading `map.md` from disk; when `None` (default), behavior is byte-identical to today. This lets apply compile the *planned* map bytes without a disk write (design doc §12 steps 4–5).

- [ ] **Step 1: Write the failing test**

```python
def test_map_text_override_used_instead_of_disk(self):
    # a project whose on-disk map has zero decisions ...
    # (build a throwaway notes-home via config.init_project as other tests do)
    override = ("# Demo\n\n## Decisions\n\n### Overridden decision\n"
                "why: x\nso: y\n\n## Learnings\n## Assumptions & tensions\n"
                "## Open questions\n## Superseded\n")
    preview = compiler.compile_preview(self.notes_home, self.slug,
                                       map_text_override=override)
    labels = [n["label"] for n in preview["nodes"]]
    self.assertIn("Overridden decision", labels)
```

Model the setUp on the existing `test_compiler.py` fixtures (recon: `config.init_project` + write a `map.md`). The on-disk `map.md` should NOT contain "Overridden decision", proving the override path is taken.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_compiler -v`
Expected: FAIL — `compile_preview() got an unexpected keyword argument 'map_text_override'`.

- [ ] **Step 3: Write minimal implementation**

At `compiler.py:226` add the parameter with default `None`. At the Phase-3 map read (`compiler.py:244`), branch:

```python
if map_text_override is not None:
    map_text, project_map_coverage = map_text_override, "complete"
else:
    map_text, project_map_coverage = _read_map(notes_home, project_slug)
```

Change nothing else. Every existing caller omits the argument, so behavior is unchanged.

- [ ] **Step 4: Run tests to verify pass + no regression**

Run: `cd bin/context_graph && python3 -m unittest tests.test_compiler -v`
Expected: PASS including the new test; all existing compiler tests still green.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/compiler.py bin/context_graph/tests/test_compiler.py
git commit -m "feat(#185): compile_preview accepts an in-memory map_text_override"
```

---

## Task 8: `apply.build_plan` — side-effect-free planned-state construction

**Files:**
- Create: `bin/context_graph/apply.py`
- Test: `bin/context_graph/tests/test_apply.py`

**Interfaces:**
- Consumes: `compiler.compile_preview` (incl. the Task-7 override), `ledger.load_judgments`/`reduce_judgments`, `relationships.validate_endpoint_pair`, `validation.validate_bundle`, `map_writer.plan_map_bytes`, `index_writer.render_index`, `projection.render_managed_region`/`plan_context_md`/`plan_adopt_context_md`, `config` path helpers.
- Produces: `build_plan(notes_home, project_slug, repo_roots=None, adopt_context_md=False, github_adapter=None) -> dict` with keys: `ok` (bool — false if any hard abort), `findings` (list), `conflicts` (list), and, when `ok`, `artifacts` = `{"map": {"path", "planned_bytes"}, "index": {"path", "planned_obj", "planned_bytes"}, "context": {"path", "plan": <projection plan dict>}}`. Performs steps 1–6 of §12. Writes nothing. This is the whole risky core, made testable without touching disk.

Pipeline inside `build_plan` (design doc §12 steps 1–6):
1. `base = compile_preview(nh, slug, repo_roots, adapter)` — raises `CompilerError` only on missing/malformed config or unreadable map; surface as findings + `ok=False`.
2. Verify `project_id`: config's id == `base["project_id"]` == any existing `index.json`'s `project_id`; mismatch → finding `project_id_mismatch`, `ok=False`.
3. `events = load_judgments(judgments_path)`; `reduced = reduce_judgments(events, revalidate=<anchor-fingerprint checker vs base>)`. Collect effective accepted anchors (`subject_type=="identity_anchor"`) and effective edge events.
4. `planned_map, map_findings = plan_map_bytes(base_map_text, base_entries, accepted_anchors)`.
5. `final = compile_preview(nh, slug, repo_roots, adapter, map_text_override=planned_map)` — the planned map now yields newly-anchored nodes (guarantees first-apply anchors appear this run, §12 step 4).
6. Materialize judged edges: for each effective edge event, resolve source/target nodes in `final["nodes"]`; if either is missing → finding `judged_edge_missing_endpoint` (edge dropped); else `validate_endpoint_pair(...)` — if `not ok` → finding `stale_illegal_judgment` (edge dropped). Append surviving judged edges (`origin="human_judgment"`) to `final["edges"]`, de-duplicated by edge `key`.
7. Attach `unresolved_evidence` / `suppressed_rejections` (from `base`/`reduced`) onto `final`.
8. `validate_bundle({"config":cfg,"nodes":final["nodes"],"edges":final["edges"],"candidates":[],"judgments":events})` — any hard invariant failure (illegal endpoint that slipped through) → `ok=False`, whole apply aborts (§12 step 6). Report via findings.
9. Render artifacts: `planned_index = index_writer.render_index(final)`; `managed = projection.render_managed_region(final)`; read current `context.md` (or None); `ctx_plan = plan_adopt_context_md(...) if adopt_context_md else plan_context_md(...)`.

- [ ] **Step 1: Write the failing test (first-apply anchor appears via planned-bytes reparse)**

```python
import os, sys, unittest, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import apply, config, ledger, review, map_parser, canonical

MAP = ("# Demo\n\n## Decisions\n\n### Use a single-writer lock\n"
       "why: correctness\nso: no double allocation\n\n## Learnings\n"
       "## Assumptions & tensions\n## Open questions\n## Superseded\n")


class BuildPlanAnchorTest(unittest.TestCase):
    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        pdir = os.path.join(self.nh, "projects", self.slug)
        with open(os.path.join(pdir, "map.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP)
        # accept an identity anchor for the one unanchored decision via #184's real path
        review.confirm(self.nh, self.slug, subject_type="identity_anchor",
                       decision="accepted", candidate_key=self._anchor_key())

    def _anchor_key(self):
        # regenerate the deterministic anchor candidate key the compiler exposes
        from context_graph import compiler
        preview = compiler.compile_preview(self.nh, self.slug)
        return preview["identity_anchor_candidates"][0]["candidate_key"]

    def test_first_apply_anchor_node_present(self):
        plan = apply.build_plan(self.nh, self.slug)
        self.assertTrue(plan["ok"], plan.get("findings"))
        labels = [n["label"] for n in plan["artifacts"]["index"]["planned_obj"]["nodes"]]
        self.assertIn("Use a single-writer lock", labels)
        # the planned map carries the inserted marker
        self.assertIn("bindle:context-id:", plan["artifacts"]["map"]["planned_bytes"])
```

**Confirm `review.confirm`'s real signature first** (recon: `review.py:57`, and the CLI `cmd_confirm` at `context-graph.py:264`) — the keyword names above (`subject_type`, `candidate_key`, `decision`) must match. If `review.confirm` takes different argument names or an event-builder, drive the acceptance exactly as `test_review.py` does. The point of the test is: one accepted anchor + `build_plan` → the anchored node appears in the planned index and the marker in the planned map.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_apply -v`
Expected: FAIL — `context_graph.apply` missing.

- [ ] **Step 3: Implement `build_plan`**

Write `apply.py` implementing steps 1–9 above. Use `config.context_dir`/`project_dir` for paths (`index.json` and `.lock` in the context dir; `map.md` and `context.md` in the project dir). Render `planned_bytes` for the index via the same serialization `write_json_atomic` uses (`json.dumps(obj, indent=2, sort_keys=True) + "\n"`) so the Task-9 byte-compare matches what will be written. Keep `build_plan` free of any write. Define an `ApplyError`/findings shape mirroring `CompilerError`/`ReviewError` for uniform CLI rendering.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_apply -v`
Expected: PASS.

- [ ] **Step 5: Add the abort test (legal-at-accept, illegal-at-apply)**

Add a test where a judged edge is accepted while legal, then the map changes an endpoint's kind so the edge is illegal at apply time; assert `build_plan(...)["ok"] is False` and a `stale_illegal_judgment` (or whole-state) finding is present, and no `artifacts` are produced. Run it; make it pass (the step-6/step-8 logic should already handle it — if not, fix `build_plan`).

- [ ] **Step 6: Commit**

```bash
git add bin/context_graph/apply.py bin/context_graph/tests/test_apply.py
git commit -m "feat(#185): apply.build_plan constructs and validates the full planned state"
```

---

## Task 9: `apply.apply` — lock, no-op compare, atomic writes

**Files:**
- Modify: `bin/context_graph/apply.py`
- Modify: `bin/context_graph/tests/test_apply.py`

**Interfaces:**
- Consumes: `build_plan` (Task 8), `lock.ProjectLock`, `atomic_io.write_atomic`/`write_json_atomic`, existing on-disk bytes for byte-comparison.
- Produces: `apply(notes_home, project_slug, repo_roots=None, adopt_context_md=False, github_adapter=None) -> dict` with `ok`, `findings`, `conflicts`, and `writes` (list of `{"path", "written": bool, "reason"}`). Acquires `ProjectLock(context_dir, "apply")` for the whole operation; calls `build_plan` inside the lock; for each of `map.md`, `index.json`, `context.md`, byte-compares planned vs on-disk and writes atomically only if different (semantic no-op); writes in the fixed order map → index → context; skips `context.md` on a `conflict`/`noop` plan action (reporting the code) while still writing map + index; releases the lock on completion or exception.

- [ ] **Step 1: Write the failing tests**

```python
class ApplyWriteTest(unittest.TestCase):
    # setUp identical to BuildPlanAnchorTest ...

    def _mtimes(self):
        pdir = os.path.join(self.nh, "projects", self.slug)
        cdir = os.path.join(pdir, ".bindle", "context")
        return {
            "map": os.path.getmtime(os.path.join(pdir, "map.md")),
            "index": os.path.getmtime(os.path.join(cdir, "index.json")),
            "context": os.path.getmtime(os.path.join(pdir, "context.md")),
        }

    def test_first_apply_writes_all_three(self):
        res = apply.apply(self.nh, self.slug)
        self.assertTrue(res["ok"], res.get("findings"))
        pdir = os.path.join(self.nh, "projects", self.slug)
        self.assertTrue(os.path.exists(os.path.join(pdir, "context.md")))
        self.assertTrue(os.path.exists(os.path.join(pdir, ".bindle", "context", "index.json")))
        self.assertIn("bindle:context-id:", open(os.path.join(pdir, "map.md")).read())

    def test_second_unchanged_apply_zero_writes(self):
        apply.apply(self.nh, self.slug)
        before = self._mtimes()
        res = apply.apply(self.nh, self.slug)
        after = self._mtimes()
        self.assertEqual(before, after)  # no mtime advances
        self.assertTrue(all(not w["written"] for w in res["writes"]))

    def test_markerless_context_md_refused_but_map_index_written(self):
        pdir = os.path.join(self.nh, "projects", self.slug)
        with open(os.path.join(pdir, "context.md"), "w") as fh:
            fh.write("hand written, no markers\n")
        res = apply.apply(self.nh, self.slug)
        self.assertEqual(open(os.path.join(pdir, "context.md")).read(),
                         "hand written, no markers\n")  # untouched
        codes = [c.get("code") for c in res["conflicts"]]
        self.assertIn("context_md_unmanaged", codes)
        self.assertTrue(os.path.exists(os.path.join(pdir, ".bindle", "context", "index.json")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_apply -v`
Expected: FAIL — `apply.apply` not defined.

- [ ] **Step 3: Implement `apply`**

```python
def apply(notes_home, project_slug, repo_roots=None,
          adopt_context_md=False, github_adapter=None):
    cdir = config.context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "apply"):
        plan = build_plan(notes_home, project_slug, repo_roots,
                          adopt_context_md, github_adapter)
        if not plan["ok"]:
            return {"ok": False, "findings": plan["findings"],
                    "conflicts": plan.get("conflicts", []), "writes": []}
        writes = []
        writes.append(_write_if_changed(plan["artifacts"]["map"]["path"],
                                        plan["artifacts"]["map"]["planned_bytes"]))
        writes.append(_write_if_changed(plan["artifacts"]["index"]["path"],
                                        plan["artifacts"]["index"]["planned_bytes"]))
        conflicts = list(plan.get("conflicts", []))
        writes.append(_write_context(plan["artifacts"]["context"], conflicts))
        return {"ok": True, "findings": plan["findings"],
                "conflicts": conflicts, "writes": writes}
```

Implement `_write_if_changed(path, planned_bytes)` (read current bytes if present; if equal → `{"path":path,"written":False,"reason":"noop"}`; else `atomic_io.write_atomic(path, planned_bytes)` → `written:True`) and `_write_context(context_artifact, conflicts)` (dispatch on the plan's `action`: `create`/`update`/`adopt` → byte-compare + write; `noop` → skip; `conflict` → append the code to `conflicts`, write nothing). Ensure `planned_bytes` are `bytes` (UTF-8 encode the rendered strings). Map/index/context paths come from `build_plan`'s `artifacts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bin/context_graph && python3 -m unittest tests.test_apply -v`
Expected: PASS (all three).

- [ ] **Step 5: Add incomplete-apply / stale-lock fixture**

Add a test that fabricates a stale `.lock` with `operation:"apply"` and an old `acquired_at`, then asserts a subsequent `apply` either (a) contends and reports the owner metadata, or (b) after `lock.break_lock(cdir)` reconstructs full state and succeeds — proving retry is a clean re-derivation (design doc §12 "Incomplete-apply detection and safe retry"). Reuse the fabricated-lock pattern from `test_lock.py`.

- [ ] **Step 6: Commit**

```bash
git add bin/context_graph/apply.py bin/context_graph/tests/test_apply.py
git commit -m "feat(#185): apply writes atomically under lock with semantic no-op"
```

---

## Task 10: CLI — `apply` subcommand + `cmd_apply`

**Files:**
- Modify: `bin/context-graph.py`

**Interfaces:**
- Consumes: `context_graph.apply.apply`, the existing `_add_common_args`/`_emit`/`_parse_repo_roots` helpers, and the `cmd_confirm` handler shape (`context-graph.py:264`).
- Produces: `cmd_apply(args)` returning `0` on `ok` with no blocking conflicts, `1` otherwise; and an `apply` sub-parser registered in `main()` with `--repo-root` (repeatable) and `--adopt-context-md` (store_true), mirroring `preview`'s options.

- [ ] **Step 1: Write the failing CLI harness test**

Extend the existing CLI shell test (`bin/test-context-graph-cli.sh`) or add a Python test that invokes `main(["apply", "--notes-home", nh, "--project", slug])` on a throwaway notes-home and asserts exit 0 and that `index.json` now exists. Prefer the Python `main()` call for a fast, deterministic assertion; model it on how the existing CLI tests invoke `main`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bin/context_graph && python3 -m unittest tests.test_apply -v` (or the CLI test)
Expected: FAIL — `apply` is not a registered subcommand (`invalid choice: 'apply'`).

- [ ] **Step 3: Register the subcommand + handler**

In `main()` (after `p_confirm`, before `p_config`):

```python
p_apply = sub.add_parser(
    "apply", help="recompute, validate, and atomically write map/index/context (#185)")
_add_common_args(p_apply)
p_apply.add_argument(
    "--repo-root", action="append", default=[], metavar="ALIAS=PATH",
    help="repeatable; ALIAS must be a configured repository alias")
p_apply.add_argument("--adopt-context-md", action="store_true",
                     help="adopt a still-markerless context.md, refusing if it gained markers")
p_apply.set_defaults(func=cmd_apply)
```

Add the handler near `cmd_confirm`:

```python
def cmd_apply(args):
    repo_roots = _parse_repo_roots(args.repo_root)  # reuse preview's parser
    out = apply_mod.apply(args.notes_home, args.project,
                          repo_roots=repo_roots,
                          adopt_context_md=args.adopt_context_md)
    _emit(out, args.format)
    return 0 if out["ok"] and not out["conflicts"] else 1
```

Add `from context_graph import apply as apply_mod` (or extend the existing import block) at the top. Confirm the real helper name for parsing `--repo-root` (recon: `cmd_preview` uses one — reuse it verbatim, do not duplicate).

- [ ] **Step 4: Run test to verify it passes**

Run: the test from Step 1.
Expected: PASS (exit 0, `index.json` created).

- [ ] **Step 5: Commit**

```bash
git add bin/context-graph.py bin/context_graph/tests/
git commit -m "feat(#185): wire the apply subcommand into the CLI"
```

---

## Task 11: `config status` — orphaned-temp-file reporting

**Files:**
- Modify: `bin/context-graph.py` (`cmd_config_status`, `context-graph.py:130-135`)
- Modify: the config-status test (find it via `grep -rl cmd_config_status bin/context_graph/tests` or the CLI shell test)

**Interfaces:**
- Produces: `cmd_config_status` output gains an `orphaned_temp_files` list — any temp file matching `atomic_io`'s naming convention left in the project dir or `.bindle/context/` (a crash between temp write and `os.replace`). Reported as a diagnostic only; **never auto-deleted** (design doc §12 "Temporary files … orphan cleanup").

- [ ] **Step 1: Confirm the temp-file naming convention**

Read `atomic_io.write_atomic` (`atomic_io.py:13`) to get the exact `tempfile.mkstemp` prefix/suffix it uses in the target directory. The orphan scan must match that pattern precisely (otherwise it reports nothing or reports unrelated files).

- [ ] **Step 2: Write the failing test**

Create a fake orphan temp file (named per the convention from Step 1) under `.bindle/context/`, run `config status`, assert the file path appears under `orphaned_temp_files` and still exists on disk afterward (not deleted).

- [ ] **Step 3: Run test to verify it fails**

Expected: FAIL — `orphaned_temp_files` key absent.

- [ ] **Step 4: Implement the scan**

In `cmd_config_status`, glob the project dir and `.bindle/context/` for the temp pattern, add the sorted list to the emitted object. Delete nothing.

- [ ] **Step 5: Run test to verify it passes**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bin/context-graph.py bin/context_graph/tests/
git commit -m "feat(#185): config status reports orphaned temp files (never deletes)"
```

---

## Task 12: Capability inventory, full gates, and dogfood

**Files:**
- Modify: `capabilities.json`
- (Verification only) whole repo

- [ ] **Step 1: Stage everything, run the inventory check**

```bash
git add -A
make check
```

Expected: FAIL on unclassified files — the four new `bin/context_graph/*.py` modules and four new `tests/test_*.py` files (and any new doc) are not yet in `capabilities.json`. (`make check` scans git-tracked files, so `git add -A` first — the #29 FOOTGUN / #183 false-green.)

- [ ] **Step 2: Add `not_a_capability` rows**

Add one `not_a_capability` entry per new file to `capabilities.json` (mirror the six rows #183 added for its new library + test modules — same JSON shape, `reason` describing each). Update the existing `context-graph` capability row's description to mention the `apply` verb.

- [ ] **Step 3: Re-run the full gate suite**

```bash
make check
make test
pre-commit run --all-files
```

Expected: all green. If `make test` (the ~40 sub-script suite) surfaces a regression in an existing context-graph shell harness, fix it before proceeding. Run the unit suite explicitly too, both without and with `jsonschema` installed (mirror #183's two-run discipline for the schema-conformance tests):

```bash
cd bin/context_graph && python3 -m unittest discover -s tests -t . -v
```

- [ ] **Step 4: Manual dogfood against a throwaway notes-home**

Run the real cycle end-to-end against a `/tmp` notes-home with a stubbed GitHub adapter: `init` → write a `map.md` → `preview` → `propose`/`confirm` an edge → `confirm` an identity anchor → `apply` → inspect `index.json`, `context.md`, and the inserted `map.md` marker → run `apply` a second time and confirm zero writes (mtimes unchanged) → corrupt `context.md`'s markers and confirm `apply` refuses that file while still writing index/map. Capture the commands + observed output for the PR body.

- [ ] **Step 5: Final commit**

```bash
git add -A
make check   # confirm green on the fully-staged tree
git commit -m "chore(#185): classify new context-graph apply modules in the capability inventory"
```

---

## Self-Review

**Spec coverage** — every #185 acceptance criterion maps to a task:
- recompute + integrate #183/#184 → Task 8 (steps 1,3,5,6). first-apply anchor in first index → Task 8 step 1 test. generates no proposals/candidates → Task 8 (no append path exists). preserves `project_id` → Task 8 step 2. stale candidates not applied → Task 8 step 6 (`stale_illegal_judgment`, `judged_edge_missing_endpoint`). every #180 relationship materialized → Task 8 step 6 + Task 4 rendering. evidence edges survive + render → Task 4 test. endpoint legality revalidated at materialization → Task 8 step 6. approved anchors alter only the target line → Task 3. duplicate/malformed IDs prevent writes → Task 8 (validate_bundle) + Task 3 findings. absent context.md created / markerless refused → Tasks 5. managed markers unique+validated, user content byte-identical → Tasks 5/9. second unchanged apply zero writes → Task 9 test. no timestamp causes a write → Tasks 2/4 (no timestamp emitted) + Task 9 byte-compare. writes under notes home only → Global Constraints + `config` path helpers. per-file atomicity honest / interruption recoverable → Task 9 step 5. single-writer lock → Task 9. `make check`+`make test` pass → Task 12.
- Index-schema shape gap → Task 1. Orphan-temp/incomplete-apply visibility → Task 11 + Task 9 step 5.

**Placeholder scan:** no "TBD"/"handle edge cases" — each step names the exact behavior and shows code or a concrete rendering rule. The few "confirm the real signature" notes are deliberate: they point the implementer at the exact recon file:line to verify against before coding, not deferred design.

**Type consistency:** `build_plan` → `apply` artifact keys (`map`/`index`/`context`, `planned_bytes`, `planned_obj`, `plan`) are used identically in Tasks 8, 9, 10. `render_index` consumes the `final` graph shape produced in Task 8 step 7. `plan_context_md`/`plan_adopt_context_md` return `action`/`code`/`text` keys consumed by `_write_context` in Task 9. Marker constants `BEGIN`/`END` defined once (Task 4) and reused (Tasks 5, 6, 9 tests).

---

## Execution Handoff

Two decision callouts (index-schema extension; `config status` orphan reporting vs. a new `status` verb) are flagged in **File Structure** above — confirm both at plan review before execution, since each shapes the frozen contract.

**Two execution options:**
1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks. Best fit here: 12 well-bounded tasks with explicit interfaces.
2. **Inline Execution** — batch with checkpoints via superpowers:executing-plans.
