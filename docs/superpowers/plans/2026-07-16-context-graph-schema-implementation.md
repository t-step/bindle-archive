# Context-Graph Schema Implementation (#180) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the frozen v1 context-graph interchange contract from
`docs/design/2026-07-16-context-graph-schema.md` — seven JSON Schema files, a
stdlib-only Python validator package (`bin/context_graph/`), a thin fixture
CLI, ~81 canonical fixtures, the human-readable companion doc, and all
pre-commit/inventory wiring — so #183–#186/#191 have one shared, tested
contract to import instead of each inventing their own.

**Architecture:** A 4-module stdlib Python package (`ids`, `relationships`,
`canonical`, `validation`) is the runtime authority. Seven `*.schema.json`
files are documentation/interchange contracts kept in sync with the native
validator via a bidirectional conformance test (test-only `jsonschema` dep,
skip-if-absent locally). A thin CLI (`check-context-graph-fixtures.py`) drives
the package over a `manifest.json`-registered fixture corpus organized by
contract category, not by issue number.

**Tech Stack:** Python 3 standard library only at runtime (`hashlib`, `json`,
`re`, `argparse`). Python stdlib `unittest` for module-level tests (mirrors
`skills/license-compliance-auditor`'s precedent — no pytest in this repo).
Bash + `bin/test-context-graph-schema.sh` as the single harness entry point
wired into `make test` and pre-commit, matching `bin/test-map-entry-id.sh`'s
shape. Test-only `jsonschema` (pip) for the schema-conformance pass only,
gated exactly like the existing shellcheck/shfmt skip-if-absent pattern.

## Global Constraints

- Runtime package (`bin/context_graph/`) is Python-stdlib-only — no
  `jsonschema` or any third-party import outside test code.
- `make check` and `make test` must pass locally before every commit (CI is
  confirmed billing-blocked account-wide — do not treat a red CI badge as a
  real signal; confirm the annotation text if it recurs).
- Every new non-test `.py`/`.sh` under `bin/` needs a `capabilities.json`
  classification (`not_a_capability` ledger entry or a `script`/`contract`
  row) in the same commit that adds it, or `make check` fails immediately.
  `bin/test-context-graph-schema.sh` is auto-excluded
  (`^bin/test-.*\.sh$`); nothing else under `bin/` is.
- Branch discipline: work on `feature/180-context-graph-schema-impl` off
  up-to-date `main`; PR to `main`; never commit directly to `main`
  (`no-commit-to-branch` hook enforces this).
- Every byte-exact canonicalization primitive (edge candidate key, anchor
  candidate key, `entry_fingerprint`, `anchor_dependency_fingerprint`) must
  match `docs/design/2026-07-16-context-graph-schema.md` §10 exactly — the
  anchor-key worked example in §10.2 has been independently re-derived
  during planning (all four values matched byte-for-byte) and is used
  verbatim as a `canonicalization/` fixture in Task 13.
- Fixture directories are grouped by contract category
  (`core/`, `map-shape/`, `endpoint-matrix/`, `identity-config/`,
  `candidates/`, `canonicalization/`, `documents/`), never by issue number,
  never flat, one JSON file per fixture. `manifest.json` is the sole
  authority for execution/reporting order and expected results.

## Scope note on fixture tasks (read before executing Tasks 8–13)

The issue body enumerates fixtures 1–81 by description (reproduced verbatim
in each fixture task below) but does not give literal JSON content for each
— that content doesn't exist anywhere yet; it has to be authored against the
schemas/package this plan builds in Tasks 1–6. Given the corpus size, Tasks
8–13 give the complete, literal fixture list (every one of the 81, verbatim
from the issue) plus the manifest contract and 2–3 fully worked example
fixtures per category as the exact JSON shape to replicate. This is a
scope/pacing decision made during planning, not an open design question —
every fixture's *expected result and finding code* is fully determined by
the schemas and finding-code table Tasks 1–6 freeze; authoring the remaining
literal JSON bodies for each category is mechanical pattern-following, which
is why it's folded into one task per category rather than one task per
fixture (81 tasks would blow past "bite-sized" in the other direction). If
executing via `superpowers:subagent-driven-development`, each fixture task's
implementer subagent should still get a fresh review gate per category.

**Human-confirmed corrections to the frozen design doc (pre-execution):**
before dispatching Task 1, the repo owner explicitly confirmed two
implementation decisions this plan makes beyond what
`docs/design/2026-07-16-context-graph-schema.md` froze byte-exactly:

1. `config.repositories` is the **canonical v1 representation** as a list
   of `{alias, binding_id, ...}` objects — not merely an implementation
   convenience, and not competing with the design doc's illustrative dict
   example. Per the design doc's own amendment rule ("where this record and
   a live issue body diverge... this record must be corrected"), Task 0
   below corrects that illustrative example in the merged design doc so no
   dict-keyed representation remains as a competing contract. No
   `object_pairs_hook`/custom JSON loader is introduced anywhere — duplicate
   JSON object keys stay outside the supported interchange contract.
2. Exactly one v1 basis-entry kind exists: `evidence_pointer` (`kind`,
   `location` ∈ {`entry_evidence`, `tension_side`}, `pointer`). No other
   basis kind (`endpoint_pair`, `claim_text`, `map_location`,
   `source_file`, `line_number`, relationship metadata, etc.) is added in
   v1 unless a concrete #180 fixture or invariant requires it. `pointer`
   stays a plain string in `bin/context_graph/canonical.py`'s
   `BASIS_KINDS` (Task 3, already written this way, unchanged) — a future
   #181 evidence-identity contract may further constrain what strings are
   legal, but that is a versioned extension for #181 to make, not something
   #180 blocks on or guesses at now.

---

## Task 0: correct the design doc's illustrative config example to the list shape

**Files:**
- Modify: `docs/design/2026-07-16-context-graph-schema.md`

The merged design record's section 6 (`config.schema.json` description) and
section 3 illustrate `repositories` as a dict keyed by alias
(`{"primary": {...}}`). Per the design doc's own stated correction rule and
the repo owner's explicit confirmation above, this task updates that
illustrative example — and any other `repositories: {...}` dict-shaped
JSON snippet in the file — to the list-of-objects shape Task 4 implements,
so the merged record and the shipped code never show two competing
contracts for the same field.

- [ ] **Step 1: Find every dict-shaped `repositories` example**

Run: `grep -n '"repositories"' docs/design/2026-07-16-context-graph-schema.md`

- [ ] **Step 2: Replace each with the list shape**

For each match, replace the dict example (e.g.
`"repositories": {"primary": {"provider": "github", "coordinates": "thomas-estep/bindle", "default_for_bare_references": true}}`)
with the equivalent list form:

```json
"repositories": [
  {
    "alias": "primary",
    "binding_id": "repository-binding:2b0f4e6c9a1d47f38e5c7a02b6d19f4e",
    "provider": "github",
    "coordinates": "thomas-estep/bindle",
    "default_for_bare_references": true
  }
]
```

Adjust surrounding prose that says "keyed by alias" or "a repositories map
of alias → binding" to "a `repositories` list, each entry carrying an
explicit `alias` field" — preserve every other frozen detail (byte-exact
candidate-key algorithms, endpoint matrix, etc.) untouched.

- [ ] **Step 3: Confirm no dict-shaped example remains**

Run: `grep -n '"repositories": {' docs/design/2026-07-16-context-graph-schema.md`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add docs/design/2026-07-16-context-graph-schema.md
git commit -m "docs(#180): correct repositories example to the list-of-objects shape

Corrects the merged design record's illustrative config example per the
design doc's own amendment rule: config.repositories is a list of
{alias, binding_id, ...} objects, not a dict keyed by alias — the dict
shape cannot represent duplicate aliases through standard JSON parsing,
which fixture 61 (duplicate-alias rejection) requires. Confirmed with the
repo owner before implementation began."
```

---

## Task 1: `bin/context_graph/ids.py` — typed-ID parsing and formatting

**Files:**
- Create: `bin/context_graph/__init__.py`
- Create: `bin/context_graph/ids.py`
- Create: `bin/context_graph/tests/__init__.py`
- Create: `bin/context_graph/tests/test_ids.py`

**Interfaces:**
- Produces: `parse_typed_id(id_str) -> dict` (raises `MalformedIdError` on any
  non-conforming string), `format_project_id`, `format_context_node_id`,
  `format_repository_binding_id`, `format_session_id`, `format_handoff_id`,
  `format_document_repository_id`, `format_document_project_local_id`,
  `format_github_issue_id`, `format_github_pr_id`, plus constants `HEX32_RE`,
  `HEX64_RE`, `SLUG_RE`, `PROJECT_LOCAL_LITERAL = "project-local"`.
- Consumes: nothing (leaf module, no filesystem/network access).

- [ ] **Step 1: Write `bin/context_graph/__init__.py`**

```python
"""context_graph — the v1 provider-neutral context-graph interchange
contract (issue #180, epic #140). See docs/context-graph-schema.md for the
human-readable companion and docs/design/2026-07-16-context-graph-schema.md
for the frozen design record. Stdlib-only at runtime; no re-exports —
import explicit submodule paths (context_graph.ids, .relationships,
.canonical, .validation)."""

SCHEMA_VERSION = 1
```

- [ ] **Step 2: Write `bin/context_graph/tests/__init__.py`** (empty file, makes the tests directory a package for `unittest discover`)

- [ ] **Step 3: Write the failing test `bin/context_graph/tests/test_ids.py`**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import ids


class TestParseTypedId(unittest.TestCase):
    def test_project_id(self):
        r = ids.parse_typed_id("project:5f56c9b95c41c298f70d6dd4e5db8c2a")
        self.assertEqual(r["type"], "project")
        self.assertEqual(r["hex"], "5f56c9b95c41c298f70d6dd4e5db8c2a")

    def test_project_id_repo_shaped_is_malformed(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("project:thomas-estep/bindle")

    def test_context_node_id(self):
        r = ids.parse_typed_id(
            "context-node:bindle:8ef8f9a58ac1046c7fd772a83a21e311"
        )
        self.assertEqual(r["type"], "context_node")
        self.assertEqual(r["creation_project_slug"], "bindle")
        self.assertEqual(r["hex"], "8ef8f9a58ac1046c7fd772a83a21e311")

    def test_context_node_id_short_hex_is_malformed(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("context-node:bindle:0123456789abcdef")

    def test_repository_binding_id(self):
        r = ids.parse_typed_id(
            "repository-binding:2b0f4e6c9a1d47f38e5c7a02b6d19f4e"
        )
        self.assertEqual(r["type"], "repository_binding")

    def test_session_id(self):
        r = ids.parse_typed_id(
            "session:project:5f56c9b95c41c298f70d6dd4e5db8c2a:"
            "sessions/2026-07-16-context-graph.md"
        )
        self.assertEqual(r["type"], "session")
        self.assertEqual(
            r["project_id"], "project:5f56c9b95c41c298f70d6dd4e5db8c2a"
        )
        self.assertEqual(
            r["relative_path"], "sessions/2026-07-16-context-graph.md"
        )

    def test_document_repository_id(self):
        r = ids.parse_typed_id(
            "document:project:5f56c9b95c41c298f70d6dd4e5db8c2a:"
            "repository-binding:2b0f4e6c9a1d47f38e5c7a02b6d19f4e:"
            "docs/design/2026-07-16-context-graph.md"
        )
        self.assertEqual(r["type"], "document_repository")
        self.assertEqual(
            r["repository_relative_path"],
            "docs/design/2026-07-16-context-graph.md",
        )

    def test_document_project_local_id(self):
        r = ids.parse_typed_id(
            "document:project:5f56c9b95c41c298f70d6dd4e5db8c2a:"
            "project-local:notes/scratch.md"
        )
        self.assertEqual(r["type"], "document_project_local")
        self.assertEqual(r["project_relative_path"], "notes/scratch.md")

    def test_github_issue_and_pr_ids_stay_distinct(self):
        issue = ids.parse_typed_id("github-issue:thomas-estep/bindle#140")
        pr = ids.parse_typed_id("github-pr:thomas-estep/bindle#140")
        self.assertEqual(issue["type"], "github_issue")
        self.assertEqual(pr["type"], "github_pr")
        self.assertNotEqual(issue["id"], pr["id"])

    def test_candidate_key_and_anchor_candidate_key(self):
        r1 = ids.parse_typed_id("candidate:sha256:" + "a" * 64)
        r2 = ids.parse_typed_id("anchor-candidate:sha256:" + "b" * 64)
        self.assertEqual(r1["type"], "candidate_key")
        self.assertEqual(r2["type"], "anchor_candidate_key")

    def test_unrecognized_string_raises(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("not-a-typed-id-at-all")

    def test_empty_string_raises(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("")


class TestFormatters(unittest.TestCase):
    def test_format_project_id_roundtrips(self):
        hexval = "5f56c9b95c41c298f70d6dd4e5db8c2a"
        formatted = ids.format_project_id(hexval)
        self.assertEqual(formatted, "project:" + hexval)
        self.assertEqual(ids.parse_typed_id(formatted)["hex"], hexval)

    def test_format_project_id_rejects_bad_hex(self):
        with self.assertRaises(ValueError):
            ids.format_project_id("not-hex")

    def test_format_context_node_id_rejects_bad_slug(self):
        with self.assertRaises(ValueError):
            ids.format_context_node_id("Not A Slug", "a" * 32)

    def test_format_document_project_local_uses_reserved_literal(self):
        formatted = ids.format_document_project_local_id(
            "project:" + "a" * 32, "notes/x.md"
        )
        self.assertIn(":project-local:", formatted)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `python3 -m unittest bin.context_graph.tests.test_ids -v` (run from repo root; expect `ModuleNotFoundError: No module named 'context_graph.ids'`)

- [ ] **Step 5: Write `bin/context_graph/ids.py`**

```python
"""context_graph.ids — typed-ID parsing and formatting for the v1
context-graph interchange contract (issue #180, epic #140).

Pure string parsing/formatting only: no filesystem or network access, no
validation beyond an ID's own regex shape. Semantic/cross-object validation
(does this project_id match the configured one, does this node exist) lives
in context_graph.validation.

Typed-ID formats (frozen by docs/design/2026-07-16-context-graph-schema.md
section 5):

  project:<32-lowercase-hex>
  context-node:<creation-project-slug>:<32-lowercase-hex>   (#179 form)
  repository-binding:<32-lowercase-hex>
  session:<project-id>:sessions/<filename>.md
  handoff:<project-id>:handoffs/<filename>.md
  document:<project-id>:<binding-id>:<repository-relative-path>
  document:<project-id>:project-local:<project-relative-path>
  github-issue:<owner>/<repo>#<n>
  github-pr:<owner>/<repo>#<n>
  candidate:sha256:<64-lowercase-hex>
  anchor-candidate:sha256:<64-lowercase-hex>

All hex components are exactly 32 (id) or 64 (candidate-key digest)
lowercase hexadecimal characters; any other length is malformed.
"""
import re

HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PROJECT_ID_RE = re.compile(r"^project:([0-9a-f]{32})$")
CONTEXT_NODE_ID_RE = re.compile(
    r"^context-node:([a-z0-9]+(?:-[a-z0-9]+)*):([0-9a-f]{32})$"
)
BINDING_ID_RE = re.compile(r"^repository-binding:([0-9a-f]{32})$")
SESSION_ID_RE = re.compile(r"^session:(project:[0-9a-f]{32}):(sessions/.+\.md)$")
HANDOFF_ID_RE = re.compile(r"^handoff:(project:[0-9a-f]{32}):(handoffs/.+\.md)$")
DOCUMENT_REPO_ID_RE = re.compile(
    r"^document:(project:[0-9a-f]{32}):(repository-binding:[0-9a-f]{32}):(.+)$"
)
DOCUMENT_LOCAL_ID_RE = re.compile(
    r"^document:(project:[0-9a-f]{32}):project-local:(.+)$"
)
GITHUB_ISSUE_ID_RE = re.compile(r"^github-issue:([^/#]+)/([^/#]+)#([0-9]+)$")
GITHUB_PR_ID_RE = re.compile(r"^github-pr:([^/#]+)/([^/#]+)#([0-9]+)$")
CANDIDATE_KEY_RE = re.compile(r"^candidate:sha256:([0-9a-f]{64})$")
ANCHOR_CANDIDATE_KEY_RE = re.compile(r"^anchor-candidate:sha256:([0-9a-f]{64})$")

PROJECT_LOCAL_LITERAL = "project-local"


class MalformedIdError(ValueError):
    """Raised by parse_typed_id for any string that is not a well-formed v1
    typed ID. `.id_str` and `.reason` carry structured detail for the
    caller's finding message."""

    def __init__(self, id_str, reason):
        super().__init__("malformed typed ID %r: %s" % (id_str, reason))
        self.id_str = id_str
        self.reason = reason


def parse_typed_id(id_str):
    """Parse any v1 typed-ID string into a dict with a "type" discriminator
    plus type-specific fields. Raises MalformedIdError for anything that does
    not match one of the frozen v1 formats exactly (repository-shaped
    project IDs, short hex, unknown prefixes, empty strings)."""
    if not isinstance(id_str, str) or id_str == "":
        raise MalformedIdError(id_str, "not a non-empty string")

    m = PROJECT_ID_RE.match(id_str)
    if m:
        return {"type": "project", "id": id_str, "hex": m.group(1)}

    m = CONTEXT_NODE_ID_RE.match(id_str)
    if m:
        return {
            "type": "context_node",
            "id": id_str,
            "creation_project_slug": m.group(1),
            "hex": m.group(2),
        }

    m = BINDING_ID_RE.match(id_str)
    if m:
        return {"type": "repository_binding", "id": id_str, "hex": m.group(1)}

    m = SESSION_ID_RE.match(id_str)
    if m:
        return {
            "type": "session",
            "id": id_str,
            "project_id": m.group(1),
            "relative_path": m.group(2),
        }

    m = HANDOFF_ID_RE.match(id_str)
    if m:
        return {
            "type": "handoff",
            "id": id_str,
            "project_id": m.group(1),
            "relative_path": m.group(2),
        }

    m = DOCUMENT_REPO_ID_RE.match(id_str)
    if m:
        return {
            "type": "document_repository",
            "id": id_str,
            "project_id": m.group(1),
            "binding_id": m.group(2),
            "repository_relative_path": m.group(3),
        }

    m = DOCUMENT_LOCAL_ID_RE.match(id_str)
    if m:
        return {
            "type": "document_project_local",
            "id": id_str,
            "project_id": m.group(1),
            "project_relative_path": m.group(2),
        }

    m = GITHUB_ISSUE_ID_RE.match(id_str)
    if m:
        return {
            "type": "github_issue",
            "id": id_str,
            "owner": m.group(1),
            "repo": m.group(2),
            "number": int(m.group(3)),
        }

    m = GITHUB_PR_ID_RE.match(id_str)
    if m:
        return {
            "type": "github_pr",
            "id": id_str,
            "owner": m.group(1),
            "repo": m.group(2),
            "number": int(m.group(3)),
        }

    m = CANDIDATE_KEY_RE.match(id_str)
    if m:
        return {"type": "candidate_key", "id": id_str, "hex": m.group(1)}

    m = ANCHOR_CANDIDATE_KEY_RE.match(id_str)
    if m:
        return {"type": "anchor_candidate_key", "id": id_str, "hex": m.group(1)}

    raise MalformedIdError(id_str, "matches no known v1 typed-ID format")


def format_project_id(hex32):
    if not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "project:%s" % hex32


def format_context_node_id(creation_project_slug, hex32):
    if not SLUG_RE.match(creation_project_slug):
        raise ValueError(
            "invalid creation_project_slug %r" % (creation_project_slug,)
        )
    if not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "context-node:%s:%s" % (creation_project_slug, hex32)


def format_repository_binding_id(hex32):
    if not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "repository-binding:%s" % hex32


def format_session_id(project_id, relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not relative_path.startswith("sessions/") or not relative_path.endswith(".md"):
        raise ValueError(
            "session relative_path must be 'sessions/<name>.md': %r" % (relative_path,)
        )
    return "session:%s:%s" % (project_id, relative_path)


def format_handoff_id(project_id, relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not relative_path.startswith("handoffs/") or not relative_path.endswith(".md"):
        raise ValueError(
            "handoff relative_path must be 'handoffs/<name>.md': %r" % (relative_path,)
        )
    return "handoff:%s:%s" % (project_id, relative_path)


def format_document_repository_id(project_id, binding_id, repository_relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not BINDING_ID_RE.match(binding_id):
        raise ValueError("invalid binding_id %r" % (binding_id,))
    return "document:%s:%s:%s" % (project_id, binding_id, repository_relative_path)


def format_document_project_local_id(project_id, project_relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    return "document:%s:%s:%s" % (
        project_id,
        PROJECT_LOCAL_LITERAL,
        project_relative_path,
    )


def format_github_issue_id(owner, repo, number):
    return "github-issue:%s/%s#%d" % (owner, repo, number)


def format_github_pr_id(owner, repo, number):
    return "github-pr:%s/%s#%d" % (owner, repo, number)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python3 -m unittest bin.context_graph.tests.test_ids -v`
Expected: all tests `ok`, `Ran N tests ... OK`

- [ ] **Step 7: Commit**

```bash
git add bin/context_graph/__init__.py bin/context_graph/ids.py \
  bin/context_graph/tests/__init__.py bin/context_graph/tests/test_ids.py
git commit -m "feat(#180): add context_graph.ids typed-ID parsing and formatting"
```

---

## Task 2: `bin/context_graph/relationships.py` — vocabulary, endpoint matrix, coupling

**Files:**
- Create: `bin/context_graph/relationships.py`
- Create: `bin/context_graph/tests/test_relationships.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces: `NODE_CLASSES`, `SEMANTIC_KINDS`, `EVIDENCE_KINDS`,
  `RESERVED_SEMANTIC_KINDS`, `NODE_GROUPS` (dict of group name ->
  frozenset of kinds), `RELATIONSHIPS` (ordered tuple of the 14 v1 names),
  `ENDPOINT_MATRIX` (dict keyed by relationship name), `REVIEW_TRIGGER_DEFAULT`
  (dict), `validate_endpoint_pair(relationship, source_class, source_kind,
  target_class, target_kind) -> dict`, `canonicalize_contradicts_endpoints
  (source_id, target_id) -> (str, str)`, `get_review_trigger_default
  (relationship) -> bool`. Task 4 (`validation.py`) imports all of these.

- [ ] **Step 1: Write the failing test `bin/context_graph/tests/test_relationships.py`**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import relationships as rel


class TestVocabulary(unittest.TestCase):
    def test_fourteen_relationships(self):
        self.assertEqual(len(rel.RELATIONSHIPS), 14)
        self.assertNotIn("implements", rel.RELATIONSHIPS)
        self.assertNotIn("related_to", rel.RELATIONSHIPS)

    def test_tension_is_a_semantic_kind(self):
        self.assertIn("tension", rel.SEMANTIC_KINDS)

    def test_reserved_kinds_disjoint_from_semantic_kinds(self):
        self.assertEqual(
            rel.RESERVED_SEMANTIC_KINDS & rel.SEMANTIC_KINDS, set()
        )


class TestEndpointMatrix(unittest.TestCase):
    def test_contains_project_to_semantic_ok(self):
        r = rel.validate_endpoint_pair("contains", "project", None, "semantic", "decision")
        self.assertTrue(r["ok"])

    def test_contains_project_to_evidence_fails(self):
        r = rel.validate_endpoint_pair(
            "contains", "project", None, "evidence", "github_issue"
        )
        self.assertFalse(r["ok"])

    def test_supported_by_semantic_to_evidence_ok(self):
        r = rel.validate_endpoint_pair(
            "supported_by", "semantic", "learning", "evidence", "session"
        )
        self.assertTrue(r["ok"])

    def test_supported_by_evidence_to_semantic_fails(self):
        r = rel.validate_endpoint_pair(
            "supported_by", "evidence", "session", "semantic", "learning"
        )
        self.assertFalse(r["ok"])

    def test_closes_pr_to_issue_ok_reversed_fails(self):
        ok = rel.validate_endpoint_pair(
            "closes", "evidence", "github_pr", "evidence", "github_issue"
        )
        bad = rel.validate_endpoint_pair(
            "closes", "evidence", "github_issue", "evidence", "github_pr"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_implemented_by_decision_to_pr_ok_learning_fails(self):
        ok = rel.validate_endpoint_pair(
            "implemented_by", "semantic", "decision", "evidence", "github_pr"
        )
        bad = rel.validate_endpoint_pair(
            "implemented_by", "semantic", "learning", "evidence", "github_pr"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_validated_by_learning_to_design_ok_question_to_issue_fails(self):
        ok = rel.validate_endpoint_pair(
            "validated_by", "semantic", "learning", "evidence", "design_document"
        )
        bad = rel.validate_endpoint_pair(
            "validated_by", "semantic", "question", "evidence", "github_issue"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_resolves_decision_to_question_ok_reversed_fails(self):
        ok = rel.validate_endpoint_pair(
            "resolves", "semantic", "decision", "semantic", "question"
        )
        bad = rel.validate_endpoint_pair(
            "resolves", "semantic", "question", "semantic", "decision"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_resolves_decision_to_tension_ok(self):
        r = rel.validate_endpoint_pair(
            "resolves", "semantic", "decision", "semantic", "tension"
        )
        self.assertTrue(r["ok"])

    def test_constrains_tension_to_decision_ok(self):
        r = rel.validate_endpoint_pair(
            "constrains", "semantic", "tension", "semantic", "decision"
        )
        self.assertTrue(r["ok"])

    def test_supersedes_same_kind_ok_cross_kind_fails(self):
        ok = rel.validate_endpoint_pair(
            "supersedes", "semantic", "decision", "semantic", "decision"
        )
        bad = rel.validate_endpoint_pair(
            "supersedes", "semantic", "decision", "semantic", "learning"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])
        self.assertTrue(rel.ENDPOINT_MATRIX["supersedes"]["same_kind_required"])

    def test_implements_is_unknown_relationship(self):
        r = rel.validate_endpoint_pair(
            "implements", "semantic", "decision", "evidence", "github_pr"
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "unknown_relationship")

    def test_reserved_future_kind_satisfies_no_group(self):
        r = rel.validate_endpoint_pair(
            "contains", "project", None, "semantic", "architecture_component"
        )
        self.assertFalse(r["ok"])


class TestContradictsCanonicalOrdering(unittest.TestCase):
    def test_reversed_pair_collapses_to_one_order(self):
        a = "context-node:bindle:11111111111111111111111111111111"
        b = "context-node:bindle:22222222222222222222222222222222"
        self.assertEqual(
            rel.canonicalize_contradicts_endpoints(a, b),
            rel.canonicalize_contradicts_endpoints(b, a),
        )
        self.assertEqual(rel.canonicalize_contradicts_endpoints(a, b), (a, b))

    def test_self_edge_forbidden_flag(self):
        self.assertTrue(rel.ENDPOINT_MATRIX["contradicts"]["self_edge_forbidden"])
        self.assertTrue(rel.ENDPOINT_MATRIX["depends_on"]["self_edge_forbidden"])
        self.assertTrue(rel.ENDPOINT_MATRIX["supersedes"]["self_edge_forbidden"])


class TestReviewTriggerDefaults(unittest.TestCase):
    def test_review_triggering_set(self):
        for name in ("constrains", "depends_on", "contradicts", "supersedes"):
            self.assertTrue(rel.get_review_trigger_default(name))

    def test_contextual_set(self):
        for name in ("supports", "supported_by", "discussed_in", "implemented_by",
                      "validated_by", "contains", "closes", "motivates",
                      "resolves", "revisits"):
            self.assertFalse(rel.get_review_trigger_default(name))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest bin.context_graph.tests.test_relationships -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'context_graph.relationships'`

- [ ] **Step 3: Write `bin/context_graph/relationships.py`**

```python
"""context_graph.relationships — the closed v1 relationship vocabulary,
per-relationship directionality, endpoint legality, and coupling
(review_trigger) defaults (issue #180, epic #140).

Owns relationship-*intrinsic* authority metadata only (whether a
relationship may ever be deterministic, whether it always requires
judgment). Whole-object-kind creation-authority checks (does *this* edge
instance actually have its required authority) live in
context_graph.validation, not here — see
docs/design/2026-07-16-context-graph-schema.md section 4.
"""

NODE_CLASSES = frozenset({"project", "semantic", "evidence"})

SEMANTIC_KINDS = frozenset(
    {"decision", "learning", "assumption", "tension", "question"}
)
EVIDENCE_KINDS = frozenset(
    {"session", "handoff", "design_document", "github_issue", "github_pr"}
)
RESERVED_SEMANTIC_KINDS = frozenset(
    {
        "problem",
        "concept",
        "constraint",
        "solution",
        "pattern",
        "principle",
        "architecture_component",
        "architecture_flow",
        "boundary",
        "test_surface",
    }
)

# Node groups (design section 7).
NODE_GROUPS = {
    "semantic-any": SEMANTIC_KINDS,
    "claim": frozenset({"decision", "learning", "assumption"}),
    "uncertainty": frozenset({"assumption", "tension", "question"}),
    "resolving": frozenset({"decision", "learning"}),
    "evidence-any": EVIDENCE_KINDS,
    "validation-evidence": frozenset(
        {"session", "handoff", "design_document", "github_pr"}
    ),
}

RELATIONSHIPS = (
    "contains",
    "supported_by",
    "discussed_in",
    "implemented_by",
    "validated_by",
    "closes",
    "motivates",
    "constrains",
    "depends_on",
    "resolves",
    "supports",
    "contradicts",
    "supersedes",
    "revisits",
)


def _endpoint(node_class, kinds):
    """kinds=None means "any kind valid for this class" (used only where a
    class has exactly one legal kind set, i.e. never for semantic/evidence,
    which always name an explicit group)."""
    return {"class": node_class, "kinds": kinds}


# The closed v1 endpoint matrix (design section 7 / issue body "Closed v1
# endpoint matrix"). Every relationship is total: unknown relationships are
# handled by validate_endpoint_pair returning ok=False, reason="unknown_relationship".
ENDPOINT_MATRIX = {
    "contains": {
        "source": _endpoint("project", None),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": True,
        "judgment_required": False,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "supported_by": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("evidence", NODE_GROUPS["evidence-any"]),
        "deterministic_allowed": True,
        "judgment_required": False,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "discussed_in": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("evidence", NODE_GROUPS["evidence-any"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "implemented_by": {
        "source": _endpoint("semantic", frozenset({"decision"})),
        "target": _endpoint("evidence", frozenset({"github_pr"})),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "validated_by": {
        "source": _endpoint("semantic", NODE_GROUPS["resolving"]),
        "target": _endpoint("evidence", NODE_GROUPS["validation-evidence"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "closes": {
        "source": _endpoint("evidence", frozenset({"github_pr"})),
        "target": _endpoint("evidence", frozenset({"github_issue"})),
        "deterministic_allowed": True,
        "judgment_required": False,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "motivates": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("semantic", frozenset({"decision", "question"})),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "constrains": {
        "source": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption", "tension"})
        ),
        "target": _endpoint(
            "semantic", frozenset({"decision", "assumption", "tension", "question"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "depends_on": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": True,
        "same_kind_required": False,
        "symmetric": False,
    },
    "resolves": {
        "source": _endpoint("semantic", NODE_GROUPS["resolving"]),
        "target": _endpoint(
            "semantic", frozenset({"question", "assumption", "tension"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "supports": {
        "source": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption"})
        ),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "contradicts": {
        "source": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption"})
        ),
        "target": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": True,
        "same_kind_required": False,
        "symmetric": True,
    },
    "supersedes": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": True,
        "judgment_required": True,
        "self_edge_forbidden": True,
        "same_kind_required": True,
        "symmetric": False,
    },
    "revisits": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption", "tension"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
}

REVIEW_TRIGGER_DEFAULT = {
    "constrains": True,
    "depends_on": True,
    "contradicts": True,
    "supersedes": True,
    "supports": False,
    "supported_by": False,
    "discussed_in": False,
    "implemented_by": False,
    "validated_by": False,
    "contains": False,
    "closes": False,
    "motivates": False,
    "resolves": False,
    "revisits": False,
}


def get_review_trigger_default(relationship):
    return REVIEW_TRIGGER_DEFAULT[relationship]


def _kind_matches(spec, node_class, node_kind):
    if node_class != spec["class"]:
        return False
    if spec["kinds"] is None:
        return True
    return node_kind in spec["kinds"]


def validate_endpoint_pair(relationship, source_class, source_kind, target_class, target_kind):
    """Never trusts the relationship name alone. Returns a dict with a
    structured diagnostic payload (design section 7): relationship, actual
    vs allowed source/target class+kind. Reserved/unknown kinds satisfy no
    group and so never match."""
    spec = ENDPOINT_MATRIX.get(relationship)
    if spec is None:
        return {
            "ok": False,
            "reason": "unknown_relationship",
            "relationship": relationship,
        }
    src_ok = _kind_matches(spec["source"], source_class, source_kind)
    tgt_ok = _kind_matches(spec["target"], target_class, target_kind)
    return {
        "ok": src_ok and tgt_ok,
        "reason": None if (src_ok and tgt_ok) else "illegal_endpoint",
        "relationship": relationship,
        "source_class": source_class,
        "source_kind": source_kind,
        "allowed_source_class": spec["source"]["class"],
        "allowed_source_kinds": (
            sorted(spec["source"]["kinds"]) if spec["source"]["kinds"] else None
        ),
        "target_class": target_class,
        "target_kind": target_kind,
        "allowed_target_class": spec["target"]["class"],
        "allowed_target_kinds": (
            sorted(spec["target"]["kinds"]) if spec["target"]["kinds"] else None
        ),
    }


def canonicalize_contradicts_endpoints(source_id, target_id):
    """`contradicts` is symmetric: canonicalize the endpoint pair
    lexicographically before candidate-key or edge-key construction so
    reversed proposals collapse to one subject (design section 10.1)."""
    return tuple(sorted((source_id, target_id)))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest bin.context_graph.tests.test_relationships -v`
Expected: all tests `ok`

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/relationships.py bin/context_graph/tests/test_relationships.py
git commit -m "feat(#180): add context_graph.relationships vocabulary and endpoint matrix"
```

---

## Task 3: `bin/context_graph/canonical.py` — byte-exact candidate-key primitives

**Files:**
- Create: `bin/context_graph/canonical.py`
- Create: `bin/context_graph/tests/test_canonical.py`

**Interfaces:**
- Consumes: nothing (leaf module; does not import `relationships` or `ids`
  — it canonicalizes whatever it's given, per design: "no object validation
  beyond what is required to canonicalize inputs already validated
  upstream").
- Produces: `normalize_basis_entry(entry) -> dict` (raises `ValueError`),
  `canonical_basis_bytes(basis_entries) -> bytes`, `candidate_key(source_id,
  relationship, target_id, basis_entries) -> str`, `entry_fingerprint
  (project_id, map_path, section, entry_kind, entry_bytes) -> str`,
  `anchor_candidate_key(project_id, map_path, section, entry_kind,
  entry_fingerprint_value) -> str`, `anchor_dependency_fingerprint
  (project_id, map_path, section, entry_kind, entry_fingerprint_value) ->
  str`, `BASIS_KINDS` (dict). Task 4 (`validation.py`) and Task 13
  (`canonicalization/` fixtures) both call these directly.

**Basis-entry kind contract (this plan's one implementation decision beyond
the frozen design — the design freezes the serialization/dedup/ordering
algorithm in section 10.1 but leaves the actual per-kind field set open).
v1 defines exactly one basis kind, `evidence_pointer`, covering every
material-basis case the issue body's fixtures need (an entry's own
`evidence:` field, a tension side's evidence, or a proposal's cited
evidence): required fields `kind` (literal `"evidence_pointer"`),
`location` (enum `entry_evidence` | `tension_side`), `pointer` (free-text
string, e.g. `"#42"` or a sessions-relative path). No optional fields in
v1 — omitted vs. explicit-null has no live case yet, but
`normalize_basis_entry` still rejects an explicit `null` value on any
present field, matching the frozen omitted-vs-null distinction.

- [ ] **Step 1: Write the failing test `bin/context_graph/tests/test_canonical.py`**

```python
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import canonical


class TestNormalizeBasisEntry(unittest.TestCase):
    def test_valid_entry_normalizes(self):
        entry = {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"}
        self.assertEqual(canonical.normalize_basis_entry(entry), entry)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry({"kind": "mystery"})

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "entry_evidence",
                 "pointer": "#42", "extra": "nope"}
            )

    def test_missing_required_field_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry({"kind": "evidence_pointer", "pointer": "#42"})

    def test_explicit_null_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": None}
            )

    def test_non_string_value_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": 42}
            )

    def test_bad_enum_value_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "nowhere", "pointer": "#42"}
            )


class TestCanonicalBasisBytes(unittest.TestCase):
    def test_order_irrelevant_and_duplicates_collapse(self):
        e1 = {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"}
        e2 = {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"}
        forward = canonical.canonical_basis_bytes([e1, e2])
        reversed_ = canonical.canonical_basis_bytes([e2, e1])
        with_dup = canonical.canonical_basis_bytes([e1, e1, e2])
        self.assertEqual(forward, reversed_)
        self.assertEqual(forward, with_dup)

    def test_matches_independently_verified_vector(self):
        basis = [
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"},
        ]
        expected = (
            b'[{"kind":"evidence_pointer","location":"entry_evidence","pointer":"#42"},'
            b'{"kind":"evidence_pointer","location":"tension_side","pointer":"#7"}]'
        )
        self.assertEqual(canonical.canonical_basis_bytes(basis), expected)


class TestCandidateKey(unittest.TestCase):
    SOURCE = "context-node:bindle:11111111111111111111111111111111"
    TARGET = "context-node:bindle:22222222222222222222222222222222"

    def test_matches_independently_verified_vector(self):
        basis = [
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"},
        ]
        key = canonical.candidate_key(self.SOURCE, "depends_on", self.TARGET, basis)
        # exact pinned digest, independently computed during planning
        self.assertEqual(
            key,
            "candidate:sha256:67c682361434354688cd98af8ce68bdb0ac1a01badcf4fece"
            "cf9d85614750059",
        )

    def test_empty_basis_vector(self):
        key = canonical.candidate_key(self.SOURCE, "depends_on", self.TARGET, [])
        self.assertEqual(
            key,
            "candidate:sha256:696846d2e541fc02e069434fe7c101a19ea2bc4950ed66bd"
            "9038f6626fd68204",
        )

    def test_changed_basis_changes_key(self):
        k1 = canonical.candidate_key(
            self.SOURCE, "depends_on", self.TARGET,
            [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#1"}],
        )
        k2 = canonical.candidate_key(
            self.SOURCE, "depends_on", self.TARGET,
            [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#2"}],
        )
        self.assertNotEqual(k1, k2)

    def test_contradicts_reversed_pair_same_key(self):
        k1 = canonical.candidate_key(self.SOURCE, "contradicts", self.TARGET, [])
        k2 = canonical.candidate_key(self.TARGET, "contradicts", self.SOURCE, [])
        self.assertEqual(k1, k2)

    def test_key_format(self):
        key = canonical.candidate_key(self.SOURCE, "depends_on", self.TARGET, [])
        self.assertTrue(key.startswith("candidate:sha256:"))
        self.assertEqual(len(key), len("candidate:sha256:") + 64)


class TestAnchorPrimitives(unittest.TestCase):
    """Reproduces docs/design/2026-07-16-context-graph-schema.md section
    10.2's worked byte-exact example exactly — independently re-derived
    during planning and confirmed to match all three pinned digests."""

    PROJECT_ID = "project:5f56c9b95c41c298f70d6dd4e5db8c2a"
    MAP_PATH = "projects/bindle/map.md"
    SECTION = "decisions"
    ENTRY_KIND = "decision"
    ENTRY_BYTES = "\n".join(
        [
            "### Separate release intent, artifact, and publication authority "
            "(2026-07, settled)",
            "why: three failure modes were collapsing into one review step.",
            "so: release-captain recommends, package-release-integrity gates, "
            "a human publishes.",
            "revisit-when: a provider ships one safe end-to-end release action.",
            "evidence: sessions/2026-07-15-release-captain.md",
        ]
    ).encode("utf-8")

    def test_entry_bytes_length_matches_design(self):
        self.assertEqual(len(self.ENTRY_BYTES), 346)

    def test_entry_fingerprint_matches_design(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        self.assertEqual(
            fp,
            "sha256:37730a28d9968e38cb25da0b1a98b7c4e13c43a2b661ca2b6cd3daf884"
            "b8e681",
        )

    def test_anchor_candidate_key_matches_design(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        key = canonical.anchor_candidate_key(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        self.assertEqual(
            key,
            "anchor-candidate:sha256:de5f2e3ead19bcb905dfd0ac06898c12c71bb1a7d"
            "112de386363490e54197933",
        )

    def test_dependency_fingerprint_matches_design(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        dep = canonical.anchor_dependency_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        self.assertEqual(
            dep,
            "sha256:f579dbeb232f6f18724ea3322132105aed41dc8b799d98dc79ab49513"
            "3224e5f",
        )

    def test_candidate_key_and_dependency_fingerprint_never_collide(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        key = canonical.anchor_candidate_key(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        dep = canonical.anchor_dependency_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        self.assertNotEqual(key.split(":", 1)[1], dep)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest bin.context_graph.tests.test_canonical -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'context_graph.canonical'`

- [ ] **Step 3: Write `bin/context_graph/canonical.py`**

```python
"""context_graph.canonical — the two versioned, byte-exact candidate-key
primitives plus the two fingerprint primitives (issue #180, epic #140),
frozen by docs/design/2026-07-16-context-graph-schema.md section 10.

Basis-entry normalization + canonical basis serialization; SHA-256
generation of both the edge candidate key and the identity-anchor
candidate key, plus the anchor entry_fingerprint and
anchor_dependency_fingerprint. Performs no object validation beyond what is
required to canonicalize inputs that were already validated upstream (that
composition lives in context_graph.validation) — this module does not
import context_graph.ids or context_graph.relationships.
"""
import hashlib
import json

# Fixed per-kind field contracts for basis entries (design section 10.1:
# "a fixed allowed field set for its basis kind"; this plan's own decision
# for what the kind set actually is — see the Task 3 docstring above).
BASIS_KINDS = {
    "evidence_pointer": {
        "required": frozenset({"kind", "location", "pointer"}),
        "optional": frozenset(),
        "enum_fields": {"location": frozenset({"entry_evidence", "tension_side"})},
    },
}


def normalize_basis_entry(entry):
    """Normalize one basis entry to a typed JSON object with a fixed
    allowed field set for its kind. Rejects unknown fields, missing
    required fields, unsupported primitive types, and explicit null
    (omitted-vs-null distinction: an omitted optional field is simply
    absent; explicit null is always a rejected primitive). No Unicode
    normalization is applied."""
    if not isinstance(entry, dict):
        raise ValueError("basis entry must be an object, got %r" % (type(entry).__name__,))
    kind = entry.get("kind")
    spec = BASIS_KINDS.get(kind)
    if spec is None:
        raise ValueError("unknown basis kind %r" % (kind,))
    allowed = spec["required"] | spec["optional"]
    extra = set(entry.keys()) - allowed
    if extra:
        raise ValueError(
            "unsupported basis fields %r for kind %r" % (sorted(extra), kind)
        )
    missing = spec["required"] - set(entry.keys())
    if missing:
        raise ValueError(
            "missing required basis fields %r for kind %r" % (sorted(missing), kind)
        )
    normalized = {}
    for field in sorted(allowed):
        if field not in entry:
            continue
        value = entry[field]
        if value is None:
            raise ValueError("basis field %r may not be explicit null" % (field,))
        if not isinstance(value, str):
            raise ValueError(
                "basis field %r must be a string, got %r" % (field, type(value).__name__)
            )
        enum = spec.get("enum_fields", {}).get(field)
        if enum is not None and value not in enum:
            raise ValueError(
                "basis field %r has invalid value %r (expected one of %s)"
                % (field, value, sorted(enum))
            )
        normalized[field] = value
    return normalized


def _serialize(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_basis_bytes(basis_entries):
    """Normalize, deduplicate by exact serialized UTF-8 bytes (basis order
    is semantically irrelevant), sort lexicographically by those bytes, and
    serialize the resulting array with the same json.dumps settings
    (design section 10.1, steps 1-5)."""
    by_bytes = {}
    for entry in basis_entries:
        normalized = normalize_basis_entry(entry)
        key = _serialize(normalized).encode("utf-8")
        by_bytes[key] = normalized
    ordered = [by_bytes[k] for k in sorted(by_bytes.keys())]
    return _serialize(ordered).encode("utf-8")


def candidate_key(source_id, relationship, target_id, basis_entries):
    """Edge candidate key: bindle-context-candidate-v1 (design section
    10.1). For symmetric `contradicts`, the caller is expected to have
    already canonicalized source_id/target_id via
    relationships.canonicalize_contradicts_endpoints — this function
    canonicalizes them again defensively so a caller that forgets still
    gets a collapsed key."""
    if relationship == "contradicts":
        source_id, target_id = sorted((source_id, target_id))
    payload = b"\0".join(
        (
            b"bindle-context-candidate-v1",
            source_id.encode("utf-8"),
            relationship.encode("utf-8"),
            target_id.encode("utf-8"),
            canonical_basis_bytes(basis_entries),
        )
    )
    return "candidate:sha256:" + hashlib.sha256(payload).hexdigest()


def entry_fingerprint(project_id, map_path, section, entry_kind, entry_bytes):
    """Identity-anchor entry fingerprint: bindle-context-entry-fingerprint-v1
    (design section 10.2). `entry_bytes` are the owner-authored entry's
    exact UTF-8 bytes as produced by #183's parser, markers already
    excised — this function applies no further transformation to them."""
    payload = b"\0".join(
        (
            b"bindle-context-entry-fingerprint-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
            entry_bytes,
        )
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def anchor_candidate_key(project_id, map_path, section, entry_kind, entry_fingerprint_value):
    """Identity-anchor candidate key: bindle-context-anchor-candidate-v1
    (design section 10.2). All five frame fields are mandatory; there is
    no basis array for anchors."""
    payload = b"\0".join(
        (
            b"bindle-context-anchor-candidate-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
            entry_fingerprint_value.encode("utf-8"),
        )
    )
    return "anchor-candidate:sha256:" + hashlib.sha256(payload).hexdigest()


def anchor_dependency_fingerprint(
    project_id, map_path, section, entry_kind, entry_fingerprint_value
):
    """Identity-anchor staleness fingerprint:
    bindle-context-anchor-dependency-v1 (design section 10.2) — a direct
    computed field under its own domain literal so its bytes never equal
    the candidate key."""
    payload = b"\0".join(
        (
            b"bindle-context-anchor-dependency-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
            entry_fingerprint_value.encode("utf-8"),
        )
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest bin.context_graph.tests.test_canonical -v`
Expected: all tests `ok` — in particular every `matches_design`/
`matches_independently_verified_vector` test passes byte-for-byte.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/canonical.py bin/context_graph/tests/test_canonical.py
git commit -m "feat(#180): add context_graph.canonical byte-exact candidate-key primitives"
```

---

## Task 4: `bin/context_graph/validation.py` — object-kind validation and creation authority

**Design decision this task makes (flag for reviewer before merge):** the
design doc's config example shows `repositories` as a dict keyed by alias
(`{"primary": {...}}`). A JSON object cannot carry duplicate keys through
standard parsing, so "duplicate repository aliases rejected" (fixture 61)
would be unrepresentable as a fixture under that shape. This task instead
defines `repositories` as a **list** of binding objects, each carrying an
explicit `"alias"` field — informationally equivalent to the dict form, but
directly representable (and therefore testable) for both the duplicate-alias
and duplicate-`binding_id` invariants. `config.schema.json` (Task 5) follows
this list shape.

**Bundle validation model (this task's second implementation decision):**
many invariants are cross-object (duplicate node ID, an edge referencing a
missing node, a judgment-required edge lacking its judgment) so the unit
`validate_bundle` validates is a **fixture bundle**: a JSON object with
optional top-level keys `config`, `nodes` (list), `edges` (list),
`proposals` (list), `candidates` (list), `judgments` (list) — only the keys
relevant to what that fixture is testing need be present. This is what every
`core/`, `map-shape/`, `endpoint-matrix/`, `identity-config/`, and
`candidates/` fixture JSON file contains (Tasks 8–12). `canonicalization/`
fixtures (Task 13) are a different, paired-file shape and don't go through
`validate_bundle` — they call the `canonical` primitives directly.

**Files:**
- Create: `bin/context_graph/validation.py`
- Create: `bin/context_graph/tests/test_validation.py`

**Interfaces:**
- Consumes: `context_graph.ids.parse_typed_id`, `MalformedIdError`;
  `context_graph.relationships.{RELATIONSHIPS, RESERVED_SEMANTIC_KINDS,
  validate_endpoint_pair, canonicalize_contradicts_endpoints,
  get_review_trigger_default}`; `context_graph.canonical.{candidate_key,
  entry_fingerprint, anchor_candidate_key}`.
- Produces: `validate_bundle(bundle) -> list[dict]` (each finding:
  `{"code": str, "message": str, "index": int|None, "field": str|None}`,
  ordered per the fixed `_CHECKS` registration order then by index),
  `FINDING_CODES` (tuple, the closed set every fixture's expected code must
  come from), `validate_config(config) -> list[dict]` (used standalone by
  Task 11's identity-config fixtures too).

- [ ] **Step 1: Write the failing test `bin/context_graph/tests/test_validation.py`**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import validation as v


def codes(findings):
    return [f["code"] for f in findings]


DECISION_A = {
    "id": "context-node:bindle:11111111111111111111111111111111",
    "class": "semantic", "kind": "decision", "label": "A", "status": "current",
}
DECISION_B = {
    "id": "context-node:bindle:22222222222222222222222222222222",
    "class": "semantic", "kind": "decision", "label": "B", "status": "current",
}
LEARNING_B = {
    "id": "context-node:bindle:22222222222222222222222222222222",
    "class": "semantic", "kind": "learning", "label": "B", "status": "current",
}
ISSUE = {"id": "github-issue:thomas-estep/bindle#1", "class": "evidence",
         "kind": "github_issue", "label": "issue", "status": "current"}
PR = {"id": "github-pr:thomas-estep/bindle#1", "class": "evidence",
      "kind": "github_pr", "label": "pr", "status": "current"}


class TestConfig(unittest.TestCase):
    def test_valid_repositoryless_config(self):
        config = {"schema_version": 1,
                   "project_id": "project:" + "a" * 32,
                   "project_slug": "bindle", "repositories": []}
        self.assertEqual(v.validate_config(config), [])

    def test_malformed_project_id(self):
        config = {"schema_version": 1, "project_id": "not-a-project-id",
                   "project_slug": "bindle", "repositories": []}
        self.assertIn("E_CONFIG_MALFORMED_PROJECT_ID", codes(v.validate_config(config)))

    def test_repo_shaped_project_id(self):
        config = {"schema_version": 1, "project_id": "project:thomas-estep/bindle",
                   "project_slug": "bindle", "repositories": []}
        self.assertIn(
            "E_CONFIG_PROJECT_ID_REPO_SHAPED", codes(v.validate_config(config))
        )

    def test_duplicate_alias_rejected(self):
        config = {
            "schema_version": 1, "project_id": "project:" + "a" * 32,
            "project_slug": "bindle",
            "repositories": [
                {"alias": "primary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/y"},
                {"alias": "primary", "binding_id": "repository-binding:" + "c" * 32,
                 "provider": "github", "coordinates": "x/z"},
            ],
        }
        self.assertIn("E_CONFIG_DUPLICATE_ALIAS", codes(v.validate_config(config)))

    def test_duplicate_binding_id_rejected(self):
        config = {
            "schema_version": 1, "project_id": "project:" + "a" * 32,
            "project_slug": "bindle",
            "repositories": [
                {"alias": "primary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/y"},
                {"alias": "secondary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/z"},
            ],
        }
        self.assertIn("E_CONFIG_DUPLICATE_BINDING_ID", codes(v.validate_config(config)))

    def test_multiple_default_rejected(self):
        config = {
            "schema_version": 1, "project_id": "project:" + "a" * 32,
            "project_slug": "bindle",
            "repositories": [
                {"alias": "primary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/y",
                 "default_for_bare_references": True},
                {"alias": "secondary", "binding_id": "repository-binding:" + "c" * 32,
                 "provider": "github", "coordinates": "x/z",
                 "default_for_bare_references": True},
            ],
        }
        self.assertIn("E_CONFIG_MULTIPLE_DEFAULT", codes(v.validate_config(config)))


class TestNodeChecks(unittest.TestCase):
    def test_reserved_kind_rejected(self):
        node = dict(DECISION_A, kind="architecture_component")
        bundle = {"nodes": [node]}
        self.assertIn("E_NODE_RESERVED_KIND", codes(v.validate_bundle(bundle)))

    def test_malformed_node_id_rejected(self):
        node = dict(DECISION_A, id="context-node:bindle:short")
        bundle = {"nodes": [node]}
        self.assertIn("E_NODE_MALFORMED_ID", codes(v.validate_bundle(bundle)))

    def test_confidence_valid_only_for_assumption_and_tension(self):
        bad = dict(DECISION_A, confidence="high")
        bundle = {"nodes": [bad]}
        self.assertIn(
            "E_NODE_CONFIDENCE_INVALID_KIND", codes(v.validate_bundle(bundle))
        )
        good = {"id": "context-node:bindle:33333333333333333333333333333333",
                 "class": "semantic", "kind": "assumption", "label": "x",
                 "status": "current", "confidence": "high"}
        self.assertEqual(v.validate_bundle({"nodes": [good]}), [])

    def test_tension_requires_exactly_two_sides(self):
        bad = {"id": "context-node:bindle:44444444444444444444444444444444",
               "class": "semantic", "kind": "tension", "label": "t",
               "status": "current", "confidence": "low",
               "sides": [{"label": "a", "evidence": []}]}
        self.assertIn(
            "E_NODE_TENSION_CARDINALITY",
            codes(v.validate_bundle({"nodes": [bad]})),
        )

    def test_tension_side_may_not_carry_its_own_id(self):
        bad = {"id": "context-node:bindle:55555555555555555555555555555555",
               "class": "semantic", "kind": "tension", "label": "t",
               "status": "current", "confidence": "low",
               "sides": [
                   {"label": "a", "evidence": [], "id": "context-node:bindle:" + "6" * 32},
                   {"label": "b", "evidence": []},
               ]}
        self.assertIn(
            "E_NODE_TENSION_SIDE_IDENTITY",
            codes(v.validate_bundle({"nodes": [bad]})),
        )

    def test_duplicate_node_id_rejected(self):
        bundle = {"nodes": [DECISION_A, dict(DECISION_A, label="dup")]}
        self.assertIn("E_NODE_DUPLICATE_ID", codes(v.validate_bundle(bundle)))


class TestEdgeChecks(unittest.TestCase):
    def _edge(self, **overrides):
        edge = {
            "key": DECISION_A["id"] + "|depends_on|" + DECISION_B["id"],
            "source": DECISION_A["id"], "relationship": "depends_on",
            "target": DECISION_B["id"], "status": "confirmed",
            "origin": "human_judgment", "review_trigger": True, "basis": [],
        }
        edge.update(overrides)
        return edge

    def test_valid_judged_edge_with_matching_judgment(self):
        edge = self._edge()
        judgment = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": edge["key"], "candidate_key": "candidate:sha256:" + "a" * 64,
            "decision": "accepted", "decided_at": "2026-07-16T00:00:00Z",
        }
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge],
                  "judgments": [judgment]}
        self.assertEqual(v.validate_bundle(bundle), [])

    def test_judgment_required_missing(self):
        edge = self._edge()
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge]}
        self.assertIn(
            "E_EDGE_JUDGMENT_REQUIRED_MISSING", codes(v.validate_bundle(bundle))
        )

    def test_unknown_relationship_rejected(self):
        edge = self._edge(relationship="frobnicates",
                           key=DECISION_A["id"] + "|frobnicates|" + DECISION_B["id"])
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge]}
        self.assertIn(
            "E_EDGE_UNKNOWN_RELATIONSHIP", codes(v.validate_bundle(bundle))
        )

    def test_implements_specifically_rejected(self):
        edge = self._edge(relationship="implements",
                           key=DECISION_A["id"] + "|implements|" + PR["id"],
                           target=PR["id"])
        bundle = {"nodes": [DECISION_A, PR], "edges": [edge]}
        self.assertIn(
            "E_EDGE_RELATIONSHIP_REJECTED", codes(v.validate_bundle(bundle))
        )

    def test_endpoint_illegal(self):
        edge = self._edge(relationship="contains",
                           key="project:" + "a" * 32 + "|contains|" + ISSUE["id"],
                           source="project:" + "a" * 32, target=ISSUE["id"],
                           origin="deterministic",
                           deterministic_source={"kind": "project_membership"})
        project_node = {"id": "project:" + "a" * 32, "class": "project",
                         "kind": None, "label": "p", "status": "current"}
        bundle = {"nodes": [project_node, ISSUE], "edges": [edge]}
        self.assertIn("E_EDGE_ENDPOINT_ILLEGAL", codes(v.validate_bundle(bundle)))

    def test_self_edge_forbidden(self):
        edge = self._edge(source=DECISION_A["id"], target=DECISION_A["id"],
                           key=DECISION_A["id"] + "|depends_on|" + DECISION_A["id"])
        bundle = {"nodes": [DECISION_A], "edges": [edge]}
        self.assertIn(
            "E_EDGE_SELF_EDGE_FORBIDDEN", codes(v.validate_bundle(bundle))
        )

    def test_supersedes_cross_kind_rejected(self):
        edge = self._edge(relationship="supersedes", target=LEARNING_B["id"],
                           key=DECISION_A["id"] + "|supersedes|" + LEARNING_B["id"],
                           origin="deterministic",
                           deterministic_source={"kind": "map_tombstone"})
        bundle = {"nodes": [DECISION_A, LEARNING_B], "edges": [edge]}
        self.assertIn(
            "E_EDGE_SUPERSEDES_KIND_MISMATCH", codes(v.validate_bundle(bundle))
        )

    def test_missing_node_ref(self):
        edge = self._edge(target="context-node:bindle:" + "9" * 32,
                           key=DECISION_A["id"] + "|depends_on|context-node:bindle:" + "9" * 32)
        bundle = {"nodes": [DECISION_A], "edges": [edge]}
        self.assertIn(
            "E_EDGE_MISSING_NODE_REF", codes(v.validate_bundle(bundle))
        )

    def test_duplicate_edge_key(self):
        edge = self._edge()
        judgment = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": edge["key"], "candidate_key": "candidate:sha256:" + "a" * 64,
            "decision": "accepted", "decided_at": "2026-07-16T00:00:00Z",
        }
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge, dict(edge)],
                  "judgments": [judgment]}
        self.assertIn("E_EDGE_DUPLICATE_KEY", codes(v.validate_bundle(bundle)))

    def test_review_trigger_mismatch(self):
        edge = self._edge(review_trigger=False)
        judgment = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": edge["key"], "candidate_key": "candidate:sha256:" + "a" * 64,
            "decision": "accepted", "decided_at": "2026-07-16T00:00:00Z",
        }
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge],
                  "judgments": [judgment]}
        self.assertIn(
            "E_EDGE_REVIEW_TRIGGER_MISMATCH", codes(v.validate_bundle(bundle))
        )

    def test_deterministic_authority_missing(self):
        edge = self._edge(relationship="closes", origin="deterministic",
                           source=PR["id"], target=ISSUE["id"],
                           key=PR["id"] + "|closes|" + ISSUE["id"])
        bundle = {"nodes": [PR, ISSUE], "edges": [edge]}
        self.assertIn(
            "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING",
            codes(v.validate_bundle(bundle)),
        )

    def test_deterministic_authority_present_is_valid(self):
        edge = self._edge(relationship="closes", origin="deterministic",
                           source=PR["id"], target=ISSUE["id"],
                           key=PR["id"] + "|closes|" + ISSUE["id"],
                           review_trigger=False,
                           deterministic_source={"kind": "github_closure"})
        bundle = {"nodes": [PR, ISSUE], "edges": [edge]}
        self.assertEqual(v.validate_bundle(bundle), [])


class TestDeterminism(unittest.TestCase):
    def test_finding_order_is_stable_across_repeated_runs(self):
        node = dict(DECISION_A, kind="architecture_component", confidence="high")
        bundle = {"nodes": [node]}
        first = v.validate_bundle(bundle)
        second = v.validate_bundle(bundle)
        self.assertEqual(first, second)

    def test_findings_do_not_stop_at_first_error(self):
        node = dict(DECISION_A, kind="architecture_component", confidence="high")
        findings = v.validate_bundle({"nodes": [node]})
        self.assertGreaterEqual(len(findings), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest bin.context_graph.tests.test_validation -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'context_graph.validation'`

- [ ] **Step 3: Write `bin/context_graph/validation.py`**

```python
"""context_graph.validation — validation of each v1 object kind, whole-
object-kind creation-authority checks, cross-object rules, and deterministic
finding ordering (issue #180, epic #140). See Task 4's plan header for the
bundle-validation model and the repositories-as-list decision.

Finding order (design section 14): first by the fixed registration order of
the invariant category (the _CHECKS list below), then by a stable
within-object key (object index, then field). Never dict/set iteration
order, never timestamps.
"""
from context_graph import canonical
from context_graph import ids
from context_graph import relationships as rel

FINDING_CODES = (
    "E_CONFIG_MALFORMED_PROJECT_ID",
    "E_CONFIG_PROJECT_ID_REPO_SHAPED",
    "E_CONFIG_DUPLICATE_ALIAS",
    "E_CONFIG_DUPLICATE_BINDING_ID",
    "E_CONFIG_MULTIPLE_DEFAULT",
    "E_NODE_MALFORMED_ID",
    "E_NODE_RESERVED_KIND",
    "E_NODE_PROJECT_ID_MISMATCH",
    "E_NODE_CONFIDENCE_INVALID_KIND",
    "E_NODE_TENSION_CARDINALITY",
    "E_NODE_TENSION_SIDE_IDENTITY",
    "E_NODE_DUPLICATE_ID",
    "E_EDGE_UNKNOWN_RELATIONSHIP",
    "E_EDGE_RELATIONSHIP_REJECTED",
    "E_EDGE_ENDPOINT_ILLEGAL",
    "E_EDGE_SELF_EDGE_FORBIDDEN",
    "E_EDGE_SUPERSEDES_KIND_MISMATCH",
    "E_EDGE_MISSING_NODE_REF",
    "E_EDGE_DUPLICATE_KEY",
    "E_EDGE_REVIEW_TRIGGER_MISMATCH",
    "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING",
    "E_EDGE_JUDGMENT_REQUIRED_MISSING",
    "E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN",
    "E_CANDIDATE_KEY_CONFLICT",
    "E_CANDIDATE_INVALID_ENDPOINT",
    "E_JUDGMENT_SUBJECT_TYPE_MISMATCH",
)

# Relationships whose deterministic authority is satisfied by a specific
# `deterministic_source.kind` on the edge (design section 8 / issue body
# "Relationship creation authority"). Fixture-representable stand-in for
# the real authoritative sources (#183's map/GitHub reads) that #180 itself
# never touches (non-goal: no map parsing, no GitHub resolution).
_DETERMINISTIC_SOURCE_KIND = {
    "contains": "project_membership",
    "supported_by": "map_evidence_pointer",
    "closes": "github_closure",
    "supersedes": "map_tombstone",
}


def _finding(code, message, index=None, field=None):
    return {"code": code, "message": message, "index": index, "field": field}


def validate_config(config):
    findings = []
    project_id = config.get("project_id", "")
    try:
        parsed = ids.parse_typed_id(project_id)
        if parsed["type"] != "project":
            raise ids.MalformedIdError(project_id, "not a project id")
    except ids.MalformedIdError:
        if "/" in project_id:
            findings.append(
                _finding(
                    "E_CONFIG_PROJECT_ID_REPO_SHAPED",
                    "project_id %r looks repository-shaped (owner/repo); "
                    "project identity is opaque and never derived from "
                    "repository coordinates" % (project_id,),
                    field="project_id",
                )
            )
        else:
            findings.append(
                _finding(
                    "E_CONFIG_MALFORMED_PROJECT_ID",
                    "malformed or missing project_id: %r" % (project_id,),
                    field="project_id",
                )
            )

    repositories = config.get("repositories", [])
    seen_aliases = {}
    seen_bindings = {}
    default_count = 0
    for i, repo in enumerate(repositories):
        alias = repo.get("alias")
        if alias in seen_aliases:
            findings.append(
                _finding(
                    "E_CONFIG_DUPLICATE_ALIAS",
                    "duplicate repository alias %r at index %d (first at %d)"
                    % (alias, i, seen_aliases[alias]),
                    index=i, field="alias",
                )
            )
        else:
            seen_aliases[alias] = i
        binding_id = repo.get("binding_id")
        if binding_id in seen_bindings:
            findings.append(
                _finding(
                    "E_CONFIG_DUPLICATE_BINDING_ID",
                    "duplicate binding_id %r at index %d (first at %d)"
                    % (binding_id, i, seen_bindings[binding_id]),
                    index=i, field="binding_id",
                )
            )
        else:
            seen_bindings[binding_id] = i
        if repo.get("default_for_bare_references"):
            default_count += 1
    if default_count > 1:
        findings.append(
            _finding(
                "E_CONFIG_MULTIPLE_DEFAULT",
                "%d repositories marked default_for_bare_references; at "
                "most one is allowed" % (default_count,),
                field="repositories",
            )
        )
    return findings


def _node_class_kind(node):
    return node.get("class"), node.get("kind")


def _check_nodes(nodes, config):
    findings = []
    seen_ids = {}
    for i, node in enumerate(nodes):
        node_id = node.get("id", "")
        try:
            ids.parse_typed_id(node_id)
        except ids.MalformedIdError as exc:
            findings.append(
                _finding("E_NODE_MALFORMED_ID", str(exc), index=i, field="id")
            )
        kind = node.get("kind")
        if kind in rel.RESERVED_SEMANTIC_KINDS:
            findings.append(
                _finding(
                    "E_NODE_RESERVED_KIND",
                    "reserved future node kind %r is documented but never "
                    "emitted as v1 output" % (kind,),
                    index=i, field="kind",
                )
            )
        if node.get("class") == "project" and config and config.get("project_id"):
            if node_id != config["project_id"]:
                findings.append(
                    _finding(
                        "E_NODE_PROJECT_ID_MISMATCH",
                        "project node id %r differs from configured "
                        "project_id %r" % (node_id, config["project_id"]),
                        index=i, field="id",
                    )
                )
        if node.get("confidence") is not None and kind not in ("assumption", "tension"):
            findings.append(
                _finding(
                    "E_NODE_CONFIDENCE_INVALID_KIND",
                    "confidence is valid only for assumption/tension nodes, "
                    "not %r" % (kind,),
                    index=i, field="confidence",
                )
            )
        if kind == "tension":
            sides = node.get("sides", [])
            if len(sides) != 2:
                findings.append(
                    _finding(
                        "E_NODE_TENSION_CARDINALITY",
                        "tension node must have exactly two sides, found %d"
                        % (len(sides),),
                        index=i, field="sides",
                    )
                )
            for side in sides:
                if "id" in side:
                    findings.append(
                        _finding(
                            "E_NODE_TENSION_SIDE_IDENTITY",
                            "tension side carries its own id %r; sides are "
                            "structured attributes, not addressable nodes"
                            % (side["id"],),
                            index=i, field="sides",
                        )
                    )
        if node_id in seen_ids:
            findings.append(
                _finding(
                    "E_NODE_DUPLICATE_ID",
                    "duplicate node id %r at index %d (first at %d)"
                    % (node_id, i, seen_ids[node_id]),
                    index=i, field="id",
                )
            )
        else:
            seen_ids[node_id] = i
    return findings


def _check_edges(edges, nodes_by_id, judgments):
    findings = []
    accepted_subject_keys = {
        j.get("subject_key") for j in judgments if j.get("decision") == "accepted"
    }
    seen_keys = {}
    for i, edge in enumerate(edges):
        relationship = edge.get("relationship")
        source_id = edge.get("source")
        target_id = edge.get("target")
        if relationship not in rel.RELATIONSHIPS:
            code = (
                "E_EDGE_RELATIONSHIP_REJECTED"
                if relationship == "implements"
                else "E_EDGE_UNKNOWN_RELATIONSHIP"
            )
            findings.append(
                _finding(
                    code,
                    "relationship %r is not in the v1 vocabulary" % (relationship,),
                    index=i, field="relationship",
                )
            )
        else:
            spec = rel.ENDPOINT_MATRIX[relationship]
            source_node = nodes_by_id.get(source_id)
            target_node = nodes_by_id.get(target_id)
            if source_node is None or target_node is None:
                missing = source_id if source_node is None else target_id
                findings.append(
                    _finding(
                        "E_EDGE_MISSING_NODE_REF",
                        "edge references a node not present in the bundle: %r"
                        % (missing,),
                        index=i, field="source" if source_node is None else "target",
                    )
                )
            else:
                src_class, src_kind = _node_class_kind(source_node)
                tgt_class, tgt_kind = _node_class_kind(target_node)
                result = rel.validate_endpoint_pair(
                    relationship, src_class, src_kind, tgt_class, tgt_kind
                )
                if not result["ok"]:
                    findings.append(
                        _finding(
                            "E_EDGE_ENDPOINT_ILLEGAL",
                            "relationship %r: actual source %s/%s not in "
                            "allowed source %s/%s; actual target %s/%s not "
                            "in allowed target %s/%s"
                            % (
                                relationship, src_class, src_kind,
                                result.get("allowed_source_class"),
                                result.get("allowed_source_kinds"),
                                tgt_class, tgt_kind,
                                result.get("allowed_target_class"),
                                result.get("allowed_target_kinds"),
                            ),
                            index=i, field="relationship",
                        )
                    )
                if (
                    spec["same_kind_required"]
                    and src_kind is not None
                    and tgt_kind is not None
                    and src_kind != tgt_kind
                ):
                    findings.append(
                        _finding(
                            "E_EDGE_SUPERSEDES_KIND_MISMATCH",
                            "%r requires source and target of the same kind: "
                            "%r vs %r" % (relationship, src_kind, tgt_kind),
                            index=i, field="relationship",
                        )
                    )
            if spec["self_edge_forbidden"] and source_id == target_id:
                findings.append(
                    _finding(
                        "E_EDGE_SELF_EDGE_FORBIDDEN",
                        "%r forbids a self-edge (source == target == %r)"
                        % (relationship, source_id),
                        index=i, field="target",
                    )
                )
            expected_trigger = rel.get_review_trigger_default(relationship)
            if edge.get("review_trigger") != expected_trigger:
                findings.append(
                    _finding(
                        "E_EDGE_REVIEW_TRIGGER_MISMATCH",
                        "relationship %r must have review_trigger=%r in v1"
                        % (relationship, expected_trigger),
                        index=i, field="review_trigger",
                    )
                )
            origin = edge.get("origin")
            if origin == "deterministic":
                required_kind = _DETERMINISTIC_SOURCE_KIND.get(relationship)
                actual_kind = (edge.get("deterministic_source") or {}).get("kind")
                if required_kind is None or actual_kind != required_kind:
                    findings.append(
                        _finding(
                            "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING",
                            "deterministic %r edge lacks its required source "
                            "authority (expected deterministic_source.kind=%r)"
                            % (relationship, required_kind),
                            index=i, field="deterministic_source",
                        )
                    )
            elif origin == "human_judgment":
                edge_key = edge.get("key")
                if edge_key not in accepted_subject_keys:
                    findings.append(
                        _finding(
                            "E_EDGE_JUDGMENT_REQUIRED_MISSING",
                            "human-judged edge %r has no matching effective "
                            "accepted judgment" % (edge_key,),
                            index=i, field="origin",
                        )
                    )
        edge_key = edge.get("key")
        if edge_key in seen_keys:
            findings.append(
                _finding(
                    "E_EDGE_DUPLICATE_KEY",
                    "duplicate edge key %r at index %d (first at %d)"
                    % (edge_key, i, seen_keys[edge_key]),
                    index=i, field="key",
                )
            )
        else:
            seen_keys[edge_key] = i
    return findings


def _check_candidates(candidates):
    findings = []
    for i, cand in enumerate(candidates):
        subject_type = cand.get("subject_type")
        if subject_type == "identity_anchor" and cand.get("candidate_origin") != "deterministic_compiler":
            findings.append(
                _finding(
                    "E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN",
                    "identity_anchor candidates may only be produced by the "
                    "deterministic compiler, got candidate_origin=%r"
                    % (cand.get("candidate_origin"),),
                    index=i, field="candidate_origin",
                )
            )
        if subject_type == "edge":
            basis = cand.get("basis", [])
            try:
                recomputed = canonical.candidate_key(
                    cand.get("source"), cand.get("relationship"), cand.get("target"), basis
                )
            except ValueError:
                recomputed = None
            if recomputed is not None and cand.get("candidate_key") != recomputed:
                findings.append(
                    _finding(
                        "E_CANDIDATE_KEY_CONFLICT",
                        "declared candidate_key %r does not match the "
                        "recomputed key %r for this source/relationship/"
                        "target/basis" % (cand.get("candidate_key"), recomputed),
                        index=i, field="candidate_key",
                    )
                )
            relationship = cand.get("relationship")
            if relationship in rel.RELATIONSHIPS:
                result = rel.validate_endpoint_pair(
                    relationship,
                    cand.get("source_class"), cand.get("source_kind"),
                    cand.get("target_class"), cand.get("target_kind"),
                )
                if not result["ok"]:
                    findings.append(
                        _finding(
                            "E_CANDIDATE_INVALID_ENDPOINT",
                            "candidate has an illegal endpoint for %r and "
                            "may never become a review candidate" % (relationship,),
                            index=i, field="relationship",
                        )
                    )
    return findings


def _check_judgments(judgments, candidates_by_key):
    findings = []
    for i, judgment in enumerate(judgments):
        subject_type = judgment.get("subject_type")
        candidate_key = judgment.get("candidate_key")
        candidate = candidates_by_key.get(candidate_key)
        if candidate is not None and candidate.get("subject_type") != subject_type:
            findings.append(
                _finding(
                    "E_JUDGMENT_SUBJECT_TYPE_MISMATCH",
                    "judgment declares subject_type=%r but its candidate %r "
                    "is subject_type=%r" % (
                        subject_type, candidate_key, candidate.get("subject_type")
                    ),
                    index=i, field="subject_type",
                )
            )
    return findings


def validate_bundle(bundle):
    """Validate a fixture bundle (see Task 4's plan header for the shape)
    and return findings ordered per design section 14: fixed invariant-
    category order, then object index."""
    config = bundle.get("config")
    nodes = bundle.get("nodes", [])
    edges = bundle.get("edges", [])
    candidates = bundle.get("candidates", [])
    judgments = bundle.get("judgments", [])

    nodes_by_id = {n.get("id"): n for n in nodes}
    candidates_by_key = {c.get("candidate_key"): c for c in candidates}

    findings = []
    if config is not None:
        findings.extend(validate_config(config))
    findings.extend(_check_nodes(nodes, config))
    findings.extend(_check_edges(edges, nodes_by_id, judgments))
    findings.extend(_check_candidates(candidates))
    findings.extend(_check_judgments(judgments, candidates_by_key))
    return findings
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest bin.context_graph.tests.test_validation -v`
Expected: all tests `ok`

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/validation.py bin/context_graph/tests/test_validation.py
git commit -m "feat(#180): add context_graph.validation object-kind and cross-object checks"
```

---

## Task 5: seven JSON Schema files + `invariant-coverage.json`

**Files:**
- Create: `schemas/context-graph/v1/config.schema.json`
- Create: `schemas/context-graph/v1/node.schema.json`
- Create: `schemas/context-graph/v1/edge.schema.json`
- Create: `schemas/context-graph/v1/proposal.schema.json`
- Create: `schemas/context-graph/v1/candidate.schema.json`
- Create: `schemas/context-graph/v1/judgment.schema.json`
- Create: `schemas/context-graph/v1/index.schema.json`
- Create: `schemas/context-graph/v1/invariant-coverage.json`

**Interfaces:**
- Consumes: nothing (pure documentation/interchange artifacts; never
  loaded by the runtime package per design section 2/11).
- Produces: the seven schema files Task 15's conformance test loads by
  path, and `invariant-coverage.json` which Task 15's completeness check
  reads.

These are documentation/interchange contracts only — never imported by
`bin/context_graph/`. `config.schema.json` uses the list-shaped
`repositories` from Task 4 (not the design doc's illustrative dict), for
the reason given in Task 4's header.

- [ ] **Step 1: Write `schemas/context-graph/v1/config.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/config.schema.json",
  "title": "context-graph v1 project configuration",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "project_id", "project_slug", "repositories"],
  "properties": {
    "schema_version": { "const": 1 },
    "project_id": { "type": "string", "pattern": "^project:[0-9a-f]{32}$" },
    "project_slug": { "type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$" },
    "display_name": { "type": "string" },
    "repositories": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["alias", "binding_id", "provider"],
        "properties": {
          "alias": { "type": "string" },
          "binding_id": {
            "type": "string",
            "pattern": "^repository-binding:[0-9a-f]{32}$"
          },
          "provider": { "type": "string" },
          "coordinates": { "type": "string" },
          "local_checkout_path": { "type": "string" },
          "default_for_bare_references": { "type": "boolean" }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Write `schemas/context-graph/v1/node.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/node.schema.json",
  "title": "context-graph v1 node",
  "type": "object",
  "required": ["id", "class", "kind", "label", "status"],
  "properties": {
    "id": { "type": "string" },
    "class": { "enum": ["project", "semantic", "evidence"] },
    "kind": {
      "enum": [
        "decision", "learning", "assumption", "tension", "question",
        "session", "handoff", "design_document", "github_issue", "github_pr",
        null
      ]
    },
    "label": { "type": "string" },
    "status": { "enum": ["current", "open", "parked", "superseded"] },
    "source": { "type": "object" },
    "confidence": { "enum": ["high", "medium", "low"] },
    "sides": {
      "type": "array",
      "minItems": 2,
      "maxItems": 2,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "evidence"],
        "properties": {
          "label": { "type": "string" },
          "evidence": { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  },
  "additionalProperties": false
}
```

- [ ] **Step 3: Write `schemas/context-graph/v1/edge.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/edge.schema.json",
  "title": "context-graph v1 edge",
  "type": "object",
  "additionalProperties": false,
  "required": ["key", "source", "relationship", "target", "status", "origin", "review_trigger", "basis"],
  "properties": {
    "key": { "type": "string" },
    "source": { "type": "string" },
    "relationship": {
      "enum": [
        "contains", "supported_by", "discussed_in", "implemented_by",
        "validated_by", "closes", "motivates", "constrains", "depends_on",
        "resolves", "supports", "contradicts", "supersedes", "revisits"
      ]
    },
    "target": { "type": "string" },
    "status": { "type": "string" },
    "origin": { "enum": ["deterministic", "human_judgment"] },
    "review_trigger": { "type": "boolean" },
    "basis": { "type": "array" },
    "deterministic_source": {
      "type": "object",
      "required": ["kind"],
      "properties": { "kind": { "type": "string" } }
    }
  }
}
```

- [ ] **Step 4: Write `schemas/context-graph/v1/proposal.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/proposal.schema.json",
  "title": "context-graph v1 untrusted semantic proposal",
  "type": "object",
  "additionalProperties": false,
  "required": ["source", "relationship", "target", "basis", "explanation", "producer"],
  "properties": {
    "source": { "type": "string" },
    "relationship": { "type": "string" },
    "target": { "type": "string" },
    "basis": { "type": "array" },
    "explanation": { "type": "string" },
    "uncertainty": { "type": "string" },
    "producer": { "enum": ["human", "skill", "fixture"] },
    "advisory_candidate_key": {
      "type": "string",
      "pattern": "^candidate:sha256:[0-9a-f]{64}$"
    }
  }
}
```

- [ ] **Step 5: Write `schemas/context-graph/v1/candidate.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/candidate.schema.json",
  "title": "context-graph v1 candidate (discriminated union)",
  "type": "object",
  "required": ["subject_type", "candidate_key", "candidate_origin", "dependency_fingerprint", "validation_status"],
  "properties": {
    "subject_type": { "enum": ["edge", "identity_anchor"] },
    "candidate_key": { "type": "string" },
    "candidate_origin": { "enum": ["deterministic_compiler", "validated_proposal"] },
    "dependency_fingerprint": { "type": "string" },
    "whole_graph_fingerprint": { "type": "string" },
    "producer": { "enum": ["human", "skill", "fixture", "compiler"] },
    "validation_status": { "enum": ["valid", "invalid"] },
    "basis": { "type": "array" },
    "source": { "type": "string" },
    "relationship": { "type": "string" },
    "target": { "type": "string" },
    "project_id": { "type": "string" },
    "map_path": { "type": "string" },
    "section": { "type": "string" },
    "entry_kind": { "type": "string" },
    "entry_fingerprint": { "type": "string" },
    "display_claim": { "type": "string" }
  },
  "allOf": [
    {
      "if": { "properties": { "subject_type": { "const": "edge" } } },
      "then": {
        "required": ["source", "relationship", "target", "basis"],
        "properties": { "candidate_key": { "pattern": "^candidate:sha256:[0-9a-f]{64}$" } }
      }
    },
    {
      "if": { "properties": { "subject_type": { "const": "identity_anchor" } } },
      "then": {
        "required": ["project_id", "map_path", "section", "entry_kind", "entry_fingerprint"],
        "not": { "required": ["basis"] },
        "properties": {
          "candidate_key": { "pattern": "^anchor-candidate:sha256:[0-9a-f]{64}$" },
          "candidate_origin": { "const": "deterministic_compiler" }
        }
      }
    }
  ]
}
```

- [ ] **Step 6: Write `schemas/context-graph/v1/judgment.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/judgment.schema.json",
  "title": "context-graph v1 judgment event",
  "type": "object",
  "required": ["schema_version", "subject_type", "subject_key", "candidate_key", "decision", "decided_at"],
  "properties": {
    "schema_version": { "const": 1 },
    "subject_type": { "enum": ["edge", "identity_anchor"] },
    "subject_key": { "type": "string" },
    "candidate_key": { "type": "string" },
    "decision": { "enum": ["accepted", "rejected", "retired"] },
    "decided_at": { "type": "string", "format": "date-time" },
    "assigned_id": { "type": "string" },
    "entry_fingerprint": { "type": "string" }
  },
  "allOf": [
    {
      "if": { "properties": { "subject_type": { "const": "identity_anchor" } } },
      "then": { "required": ["assigned_id", "entry_fingerprint"] }
    }
  ]
}
```

- [ ] **Step 7: Write `schemas/context-graph/v1/index.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/context-graph/v1/index.schema.json",
  "title": "context-graph v1 derived materialized index (rebuildable, presentation only)",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "nodes", "edges", "coverage"],
  "properties": {
    "schema_version": { "const": 1 },
    "nodes": { "type": "array" },
    "edges": { "type": "array" },
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
    }
  }
}
```

- [ ] **Step 8: Write `schemas/context-graph/v1/invariant-coverage.json`**

One entry per finding code from `context_graph.validation.FINDING_CODES`,
classified per design section 11. `schema-and-native` = both a JSON Schema
constraint and a native Python check exist and are cross-tested (Task 15).
`native-only` = not representable in JSON Schema (cross-object, hashing,
ordering). `schema-only-documentation` must stay empty unless justified.

```json
{
  "schema_version": 1,
  "invariants": [
    { "code": "E_CONFIG_MALFORMED_PROJECT_ID", "classification": "schema-and-native" },
    { "code": "E_CONFIG_PROJECT_ID_REPO_SHAPED", "classification": "native-only" },
    { "code": "E_CONFIG_DUPLICATE_ALIAS", "classification": "native-only" },
    { "code": "E_CONFIG_DUPLICATE_BINDING_ID", "classification": "native-only" },
    { "code": "E_CONFIG_MULTIPLE_DEFAULT", "classification": "native-only" },
    { "code": "E_NODE_MALFORMED_ID", "classification": "native-only" },
    { "code": "E_NODE_RESERVED_KIND", "classification": "schema-and-native" },
    { "code": "E_NODE_PROJECT_ID_MISMATCH", "classification": "native-only" },
    { "code": "E_NODE_CONFIDENCE_INVALID_KIND", "classification": "native-only" },
    { "code": "E_NODE_TENSION_CARDINALITY", "classification": "schema-and-native" },
    { "code": "E_NODE_TENSION_SIDE_IDENTITY", "classification": "schema-and-native" },
    { "code": "E_NODE_DUPLICATE_ID", "classification": "native-only" },
    { "code": "E_EDGE_UNKNOWN_RELATIONSHIP", "classification": "schema-and-native" },
    { "code": "E_EDGE_RELATIONSHIP_REJECTED", "classification": "schema-and-native" },
    { "code": "E_EDGE_ENDPOINT_ILLEGAL", "classification": "native-only" },
    { "code": "E_EDGE_SELF_EDGE_FORBIDDEN", "classification": "native-only" },
    { "code": "E_EDGE_MISSING_NODE_REF", "classification": "native-only" },
    { "code": "E_EDGE_DUPLICATE_KEY", "classification": "native-only" },
    { "code": "E_EDGE_REVIEW_TRIGGER_MISMATCH", "classification": "native-only" },
    { "code": "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING", "classification": "native-only" },
    { "code": "E_EDGE_JUDGMENT_REQUIRED_MISSING", "classification": "native-only" },
    { "code": "E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN", "classification": "schema-and-native" },
    { "code": "E_CANDIDATE_KEY_CONFLICT", "classification": "native-only" },
    { "code": "E_CANDIDATE_INVALID_ENDPOINT", "classification": "native-only" },
    { "code": "E_JUDGMENT_SUBJECT_TYPE_MISMATCH", "classification": "native-only" }
  ]
}
```

- [ ] **Step 9: Commit**

```bash
git add schemas/context-graph/v1/
git commit -m "feat(#180): add v1 context-graph JSON Schemas and invariant-coverage ledger"
```

---

## Task 6: `bin/check-context-graph-fixtures.py` — thin fixture CLI

**Files:**
- Create: `bin/check-context-graph-fixtures.py`

**Interfaces:**
- Consumes: `context_graph.validation.validate_bundle`,
  `context_graph.canonical.{candidate_key, entry_fingerprint,
  anchor_candidate_key, anchor_dependency_fingerprint}`.
- Produces: a CLI invoked by `bin/test-context-graph-schema.sh` (Task 14) as
  `check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json
  [--format text|json]`, exit 0 if every fixture's actual result matches its
  manifest expectation, exit 1 otherwise.

No independent copy of ID parsing, endpoint rules, schema invariants,
candidate-key logic, or canonicalization — every check calls the package.

- [ ] **Step 1: Write `bin/check-context-graph-fixtures.py`**

```python
#!/usr/bin/env python3
"""check-context-graph-fixtures.py — thin CLI adapter over
bin/context_graph/ (issue #180, epic #140).

Drives the manifest-registered fixture corpus under
testdata/context-graph/v1/ through context_graph.validation.validate_bundle
(for validate-kind fixtures) or context_graph.canonical (for
candidate_key_relation-kind fixtures), and reports pass/fail per fixture
plus a summary. Contains no independent copy of ID parsing, endpoint rules,
candidate-key logic, or canonicalization — every check calls the package.

Manifest contract (testdata/context-graph/v1/manifest.json):

  {
    "schema_version": 1,
    "fixtures": [
      {
        "id": "43",
        "path": "endpoint-matrix/43-contains-project-to-semantic.json",
        "assertion": "validate",
        "expect_valid": true,
        "expect_codes": [],
        "match_mode": "exact",
        "coverage_tags": ["endpoint-matrix"],
        "invariant_ids": []
      },
      {
        "id": "75",
        "assertion": "candidate_key_equals",
        "with": ["75-human.json", "75-skill.json", "75-fixture.json"],
        "coverage_tags": ["candidates"]
      }
    ]
  }

`assertion: "validate"` fixtures point at one bundle JSON file (Task 4's
bundle shape) and are checked via validate_bundle; `expect_codes` is the
finding-code list, matched per `match_mode` ("exact" or
"ordered_subset" — the manifest marks which). `assertion:
"candidate_key_equals"`/`"candidate_key_distinct"`/
`"dependency_fingerprint_equals"`/`"dependency_fingerprint_distinct"`
fixtures point at multiple bundle files via `with` and compare a computed
value across them (fixtures 19, 75, 76, 80, 81 — see Tasks 8/12).

Exit codes: 0 all fixtures pass; 1 any fixture's actual result diverges
from its manifest expectation, a fixture has no manifest entry, or a
manifest path does not exist.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from context_graph import canonical
from context_graph import validation


def _load_bundle(manifest_dir, relative_path):
    full_path = os.path.join(manifest_dir, relative_path)
    if not os.path.isfile(full_path):
        raise FileNotFoundError(full_path)
    with open(full_path, encoding="utf-8") as fh:
        return json.load(fh)


def _run_validate_fixture(manifest_dir, entry):
    bundle = _load_bundle(manifest_dir, entry["path"])
    findings = validation.validate_bundle(bundle)
    actual_codes = [f["code"] for f in findings]
    actual_valid = len(findings) == 0
    expect_valid = entry["expect_valid"]
    expect_codes = entry.get("expect_codes", [])
    match_mode = entry.get("match_mode", "exact")

    ok = actual_valid == expect_valid
    if ok and not expect_valid:
        if match_mode == "exact":
            ok = actual_codes == expect_codes
        else:  # ordered_subset
            it = iter(actual_codes)
            ok = all(code in it for code in expect_codes)
    return {
        "id": entry["id"], "path": entry["path"], "ok": ok,
        "actual_valid": actual_valid, "actual_codes": actual_codes,
        "expect_valid": expect_valid, "expect_codes": expect_codes,
    }


def _candidate_value(manifest_dir, entry, path):
    bundle = _load_bundle(manifest_dir, path)
    candidates = bundle.get("candidates", [])
    if not candidates:
        raise ValueError("fixture %r has no candidates to compare" % (path,))
    cand = candidates[0]
    if entry["assertion"] in ("candidate_key_equals", "candidate_key_distinct"):
        return cand.get("candidate_key")
    return cand.get("dependency_fingerprint")


def _run_relation_fixture(manifest_dir, entry):
    values = [_candidate_value(manifest_dir, entry, p) for p in entry["with"]]
    if entry["assertion"].endswith("_equals"):
        ok = len(set(values)) == 1
    else:
        ok = len(set(values)) == len(values)
    return {
        "id": entry["id"], "path": ",".join(entry["with"]), "ok": ok,
        "actual_valid": None, "actual_codes": [], "expect_valid": None,
        "expect_codes": [],
    }


def run_manifest(manifest_path):
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    results = []
    seen_ids = set()
    for entry in manifest["fixtures"]:
        if entry["id"] in seen_ids:
            results.append({"id": entry["id"], "path": entry.get("path", ""),
                             "ok": False, "actual_valid": None, "actual_codes": [],
                             "expect_valid": None, "expect_codes": [],
                             "error": "duplicate fixture id"})
            continue
        seen_ids.add(entry["id"])
        try:
            if entry["assertion"] == "validate":
                results.append(_run_validate_fixture(manifest_dir, entry))
            else:
                results.append(_run_relation_fixture(manifest_dir, entry))
        except (FileNotFoundError, ValueError, KeyError) as exc:
            results.append({"id": entry["id"], "path": entry.get("path", ""),
                             "ok": False, "actual_valid": None, "actual_codes": [],
                             "expect_valid": None, "expect_codes": [],
                             "error": str(exc)})
    return results


def render_text(results):
    lines = []
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        lines.append("[%s] fixture %s (%s)" % (status, r["id"], r["path"]))
        if not r["ok"]:
            if r.get("error"):
                lines.append("    error: %s" % r["error"])
            else:
                lines.append(
                    "    expected valid=%s codes=%s; actual valid=%s codes=%s"
                    % (r["expect_valid"], r["expect_codes"], r["actual_valid"],
                       r["actual_codes"])
                )
    passed = sum(1 for r in results if r["ok"])
    lines.append("%d/%d fixtures passed" % (passed, len(results)))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        results = run_manifest(args.manifest)
    except OSError as exc:
        print("check-context-graph-fixtures: cannot read --manifest: %s" % exc,
              file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(render_text(results))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manual smoke test (no fixtures exist yet — confirm the CLI at least loads and reports a clean empty manifest)**

```bash
mkdir -p /tmp/cg-smoke
echo '{"schema_version": 1, "fixtures": []}' > /tmp/cg-smoke/manifest.json
python3 bin/check-context-graph-fixtures.py --manifest /tmp/cg-smoke/manifest.json
```

Expected: `0/0 fixtures passed` printed, exit code 0. Clean up:
`rm -rf /tmp/cg-smoke`

- [ ] **Step 3: Commit**

```bash
git add bin/check-context-graph-fixtures.py
git commit -m "feat(#180): add check-context-graph-fixtures.py thin CLI adapter"
```

---

## Task 7: `docs/context-graph-schema.md` — shipped human-readable companion doc

**Files:**
- Create: `docs/context-graph-schema.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: the human-readable reference #182–#186/#191 authors read
  instead of the design record (which stays a historical decision log, not
  living documentation). Needs a `contract`-type `capabilities.json` row
  (Task 17) — this is a shipped deliverable, not a `docs/design/` record, so
  it is not auto-excluded from the inventory.

- [ ] **Step 1: Write `docs/context-graph-schema.md`**

```markdown
# Context-graph v1 schema reference

Companion reference to the frozen design record at
`docs/design/2026-07-16-context-graph-schema.md` (issue #180, epic #140).
This document describes the *shipped* contract as implemented in
`bin/context_graph/` and `schemas/context-graph/v1/`; the design record is
the historical decision log and stays unedited going forward — if the two
ever diverge, this file and the code are authoritative and the design
record is corrected to match, not the reverse.

## What this contract is

A provider-neutral interchange contract for the context-graph epic (#140):
opaque project/repository identity, semantic and evidence nodes, typed
directed edges governed by a closed endpoint matrix, untrusted proposals,
validated candidates, append-only judgments, and derived index state. The
native Python package (`bin/context_graph/`) is the runtime authority; the
seven `schemas/context-graph/v1/*.schema.json` files are documentation and
interchange contracts for other-language consumers, kept in sync via a
bidirectional conformance test (`bin/test-context-graph-schema.sh`), never
via code generation or runtime schema loading.

## Package layout

| Module | Owns |
|---|---|
| `context_graph.ids` | Typed-ID parsing/formatting only. No I/O. |
| `context_graph.relationships` | Closed relationship vocabulary, endpoint matrix, `review_trigger` defaults. Relationship-intrinsic authority metadata only. |
| `context_graph.canonical` | Basis-entry normalization, canonical basis serialization, the two candidate-key primitives, the two fingerprint primitives. No object validation beyond canonicalization needs. |
| `context_graph.validation` | Per-object-kind validation, whole-object-kind creation-authority checks, cross-object rules, deterministic finding order. |

Callers use explicit import paths
(`from context_graph.ids import parse_typed_id`); `context_graph/__init__.py`
carries only a docstring and `SCHEMA_VERSION`.

## Typed-ID formats

```text
project:<32-lowercase-hex>
context-node:<creation-project-slug>:<32-lowercase-hex>
repository-binding:<32-lowercase-hex>
session:<project-id>:sessions/<filename>.md
handoff:<project-id>:handoffs/<filename>.md
document:<project-id>:<binding-id>:<repository-relative-path>
document:<project-id>:project-local:<project-relative-path>
github-issue:<owner>/<repo>#<n>
github-pr:<owner>/<repo>#<n>
candidate:sha256:<64-lowercase-hex>
anchor-candidate:sha256:<64-lowercase-hex>
```

## Node classes and kinds

Classes: `project`, `semantic`, `evidence`. Semantic kinds: `decision`,
`learning`, `assumption`, `tension`, `question`. Evidence kinds: `session`,
`handoff`, `design_document`, `github_issue`, `github_pr`. Reserved future
semantic kinds (documented, never emitted in v1):
`problem`, `concept`, `constraint`, `solution`, `pattern`, `principle`,
`architecture_component`, `architecture_flow`, `boundary`, `test_surface`.

`confidence` is valid only on `assumption` and `tension` nodes. A `tension`
node carries exactly two `sides`, each `{label, evidence}` — sides are
structured attributes, never independently addressable nodes.

## Relationship endpoint matrix

Fourteen v1 relationships, each with one closed source/target
class+kind constraint (`bin/context_graph/relationships.py:ENDPOINT_MATRIX`
is authoritative — this table is a summary):

| Relationship | Source | Target | Authority |
|---|---|---|---|
| `contains` | project | semantic-any | deterministic |
| `supported_by` | semantic-any | evidence-any | deterministic |
| `discussed_in` | semantic-any | evidence-any | judgment |
| `implemented_by` | decision | github_pr | judgment |
| `validated_by` | decision/learning | validation-evidence | judgment |
| `closes` | github_pr | github_issue | deterministic |
| `motivates` | semantic-any | decision/question | judgment |
| `constrains` | decision/learning/assumption/tension | decision/assumption/tension/question | judgment |
| `depends_on` | semantic-any | semantic-any | judgment (no self-edges) |
| `resolves` | decision/learning | question/assumption/tension | judgment |
| `supports` | decision/learning/assumption | semantic-any | judgment |
| `contradicts` | decision/learning/assumption | (same set) | judgment (symmetric, canonical ordering) |
| `supersedes` | any semantic-any kind | same kind | deterministic or judgment (no self-edges) |
| `revisits` | semantic-any | decision/learning/assumption/tension | judgment |

`implements` is not part of v1 — validators reject it. Implementation
attribution uses `decision --implemented_by--> github_pr`.

## Candidate-key canonicalization

Two versioned, byte-exact primitives plus two fingerprint primitives, all
in `context_graph.canonical`:

- **Edge candidates** (`bindle-context-candidate-v1`,
  `candidate:sha256:<hex>`): basis entries are typed JSON objects with a
  fixed field set per kind (v1 defines one kind, `evidence_pointer`:
  `location` ∈ {`entry_evidence`, `tension_side`}, `pointer` free text),
  deduplicated and sorted by serialized UTF-8 bytes before framing.
- **Identity-anchor candidates** (`bindle-context-anchor-candidate-v1`,
  `anchor-candidate:sha256:<hex>`): five mandatory direct frame fields
  (`project_id`, `map_path`, `section`, `entry_kind`, `entry_fingerprint`),
  no basis array. Built from `entry_fingerprint`
  (`bindle-context-entry-fingerprint-v1`) and staleness uses
  `anchor_dependency_fingerprint` (`bindle-context-anchor-dependency-v1`).

See `docs/design/2026-07-16-context-graph-schema.md` §10 for the full
worked byte-exact example (reproduced as a `canonicalization/` fixture).

## Validation model and finding codes

`context_graph.validation.validate_bundle(bundle)` is the entry point: a
bundle is `{config?, nodes?, edges?, proposals?, candidates?, judgments?}`.
Findings are returned in a fixed, deterministic order (registration order
of the invariant category, then object index) and never stop at the first
error. The full closed set of finding codes lives in
`context_graph.validation.FINDING_CODES` and is classified in
`schemas/context-graph/v1/invariant-coverage.json` as
`schema-and-native`, `native-only`, or `schema-only-documentation`.

## Fixture corpus

`testdata/context-graph/v1/manifest.json` is the single authoritative
registry — execution order, expected results, and finding codes all come
from the manifest, never from filename or directory position. Fixtures are
grouped by contract category: `core/`, `map-shape/`, `endpoint-matrix/`,
`identity-config/`, `candidates/`, `canonicalization/`, `documents/`. Run
`bin/test-context-graph-schema.sh` to execute the whole corpus plus the
JSON-Schema/native conformance pass.

## Non-goals (owned elsewhere)

This contract does not parse project maps (#183), resolve GitHub (#183/
#184), allocate or persist project identity (#191), build `index.json` from
live sources or write `context.md` (#185), implement preview/confirm/apply
(#184/#185), or create a model-assisted proposal skill (#186).
```

- [ ] **Step 2: Commit**

```bash
git add docs/context-graph-schema.md
git commit -m "docs(#180): add shipped context-graph-schema.md companion reference"
```

---

## Task 8: `testdata/context-graph/v1/manifest.json` contract + `core/` fixtures (1–32)

**Files:**
- Create: `testdata/context-graph/v1/manifest.json` (started here; Tasks 9–13 append to it)
- Create: `testdata/context-graph/v1/core/*.json` (one bundle file per fixture)

**Interfaces:**
- Consumes: the bundle shape from Task 4, the manifest shape from Task 6.
- Produces: the `core` slice of `manifest.json`'s `fixtures` array; Tasks
  9–13 each append their own slice to the same file (append, don't
  overwrite — check the file's current content before editing).

**Fixture list (verbatim from the #180 issue body's "Canonical fixtures"
section) and its finding-code mapping:**

| # | Description | Expected | Code(s) |
|---|---|---|---|
| 1 | Minimal project with one Decision and one issue | valid | — |
| 2 | One issue and one PR sharing the same GitHub number | valid | — |
| 3 | Multiple semantic nodes citing one evidence node | valid | — |
| 4 | Deterministic `supported_by` | valid | — |
| 5 | Deterministic PR `closes` issue | valid | — |
| 6 | Accepted semantic `depends_on` | valid | — |
| 7 | Accepted semantic `motivates` | valid | — |
| 8 | Accepted semantic `constrains` | valid | — |
| 9 | Accepted semantic `resolves` | valid | — |
| 10 | Accepted semantic `supports` | valid | — |
| 11 | Accepted semantic `contradicts` | valid | — |
| 12 | Deterministic explicit-map `supersedes` | valid | — |
| 13 | Accepted human-judged `supersedes` | valid | — |
| 14 | Accepted semantic `revisits` | valid | — |
| 15 | Accepted semantic-to-evidence `discussed_in` | valid | — |
| 16 | Accepted semantic-to-PR `implemented_by` | valid | — |
| 17 | Accepted semantic-to-evidence `validated_by` | valid | — |
| 18 | Rejected edge candidate | valid bundle; candidate `validation_status: "invalid"`, no edge materialized | — |
| 19 | Changed candidate basis producing a new candidate key | `assertion: candidate_key_distinct` | — |
| 20 | Duplicate node identity | invalid | `E_NODE_DUPLICATE_ID` |
| 21 | Duplicate edge key | invalid | `E_EDGE_DUPLICATE_KEY` |
| 22 | Edge referencing a missing node | invalid | `E_EDGE_MISSING_NODE_REF` |
| 23 | Unknown relationship | invalid | `E_EDGE_UNKNOWN_RELATIONSHIP` |
| 24 | Deferred `implements` relationship rejected | invalid | `E_EDGE_RELATIONSHIP_REJECTED` |
| 25 | Human-confirmed relationship without a judgment | invalid | `E_EDGE_JUDGMENT_REQUIRED_MISSING` |
| 26 | Deterministic relationship without required source authority | invalid | `E_EDGE_DETERMINISTIC_AUTHORITY_MISSING` |
| 27 | Invalid review-trigger value | invalid | `E_EDGE_REVIEW_TRIGGER_MISMATCH` |
| 28 | Uncertain GitHub coverage | valid (coverage state, not an error) | — |
| 29 | Unsupported commit coverage | valid (coverage state, not an error) | — |
| 30 | Reserved future node kind rejected as emitted v1 output | invalid | `E_NODE_RESERVED_KIND` |
| 31 | Stable semantic ordering with no timestamps affecting equality | harness-level: run fixture 6's bundle through `validate_bundle` twice, assert identical output (see Task 14) — not its own JSON file | — |
| 32 | Every v1 relationship appears in at least one valid fixture through an authorized creation path | harness-level: Task 14 aggregates `coverage_tags` across every `core`/`endpoint-matrix` fixture and asserts all 14 relationship names appear at least once — not its own JSON file | — |

Fixtures 31 and 32 are **not** JSON files — they're assertions the test
harness (Task 14) makes over the fixture corpus as a whole. Fixtures 28/29
are coverage-state fixtures: an `index`-shaped bundle with a `coverage`
object using an `uncertain`/`unsupported` value, asserting the validator
never treats those as artifact-absence errors (no finding code fires).

- [ ] **Step 1: Write `testdata/context-graph/v1/manifest.json` header + fixture 1's entry**

```json
{
  "schema_version": 1,
  "fixtures": [
    {
      "id": "1",
      "path": "core/01-minimal-project-decision-issue.json",
      "assertion": "validate",
      "expect_valid": true,
      "expect_codes": [],
      "match_mode": "exact",
      "coverage_tags": ["core"],
      "invariant_ids": []
    }
  ]
}
```

- [ ] **Step 2: Write `testdata/context-graph/v1/core/01-minimal-project-decision-issue.json`**

```json
{
  "config": {
    "schema_version": 1,
    "project_id": "project:5f56c9b95c41c298f70d6dd4e5db8c2a",
    "project_slug": "bindle",
    "repositories": []
  },
  "nodes": [
    {
      "id": "project:5f56c9b95c41c298f70d6dd4e5db8c2a",
      "class": "project", "kind": null, "label": "bindle", "status": "current"
    },
    {
      "id": "context-node:bindle:8ef8f9a58ac1046c7fd772a83a21e311",
      "class": "semantic", "kind": "decision",
      "label": "Separate release intent, artifact, and publication authority",
      "status": "current"
    },
    {
      "id": "github-issue:thomas-estep/bindle#140",
      "class": "evidence", "kind": "github_issue", "label": "issue 140",
      "status": "current"
    }
  ],
  "edges": [
    {
      "key": "project:5f56c9b95c41c298f70d6dd4e5db8c2a|contains|context-node:bindle:8ef8f9a58ac1046c7fd772a83a21e311",
      "source": "project:5f56c9b95c41c298f70d6dd4e5db8c2a",
      "relationship": "contains",
      "target": "context-node:bindle:8ef8f9a58ac1046c7fd772a83a21e311",
      "status": "confirmed", "origin": "deterministic", "review_trigger": false,
      "basis": [], "deterministic_source": {"kind": "project_membership"}
    }
  ]
}
```

- [ ] **Step 3: Add manifest entries + bundle files for fixtures 2–17**

Follow fixture 1's exact shape. Concrete guidance per fixture:
- **2**: two evidence nodes `github-issue:thomas-estep/bindle#7` and
  `github-pr:thomas-estep/bindle#7`; no edges needed — the fixture proves
  both parse as distinct typed IDs (assert via `nodes` list with both
  present, zero findings).
- **3**: one evidence node, two semantic nodes, two `supported_by` edges
  from each semantic node to the same evidence node (`origin:
  "deterministic"`, `deterministic_source.kind: "map_evidence_pointer"`,
  `review_trigger: false`).
- **4**: one `supported_by` edge, deterministic, as above.
- **5**: one `closes` edge, `source` a `github_pr` node, `target` a
  `github_issue` node, deterministic, `deterministic_source.kind:
  "github_closure"`.
- **6–11, 14**: one edge each for `depends_on`, `motivates`, `constrains`,
  `resolves`, `supports`, `contradicts`, `revisits` — `origin:
  "human_judgment"`, `review_trigger` per Task 2's `REVIEW_TRIGGER_DEFAULT`
  table, plus a `judgments` array with one `{"decision": "accepted",
  "subject_key": <edge key>, "subject_type": "edge", "candidate_key":
  "candidate:sha256:" + "0"*64, "decided_at": "2026-07-16T00:00:00Z"}`
  entry so `E_EDGE_JUDGMENT_REQUIRED_MISSING` does not fire.
- **12**: `supersedes` edge, `origin: "deterministic"`,
  `deterministic_source.kind: "map_tombstone"`, source and target both
  `kind: "decision"` (same-kind required).
- **13**: `supersedes` edge, `origin: "human_judgment"`, same-kind
  endpoints, plus a matching accepted judgment.
- **15**: `discussed_in` edge, semantic source, evidence target,
  `human_judgment` + accepted judgment.
- **16**: `implemented_by` edge, `decision` source, `github_pr` target,
  `human_judgment` + accepted judgment.
- **17**: `validated_by` edge, `decision` or `learning` source,
  `validation-evidence` target (session/handoff/design_document/github_pr),
  `human_judgment` + accepted judgment.

Each gets its own `manifest.json` entry (`"expect_valid": true,
"expect_codes": [], "coverage_tags": ["core", "<relationship-name>"]`) —
the `<relationship-name>` tag is what Task 14's fixture-32 coverage
assertion scans for.

- [ ] **Step 4: Write fixture 18 (rejected edge candidate)**

`testdata/context-graph/v1/core/18-rejected-edge-candidate.json`:

```json
{
  "nodes": [
    {"id": "context-node:bindle:11111111111111111111111111111111",
     "class": "semantic", "kind": "decision", "label": "A", "status": "current"},
    {"id": "context-node:bindle:22222222222222222222222222222222",
     "class": "semantic", "kind": "decision", "label": "B", "status": "current"}
  ],
  "candidates": [
    {
      "subject_type": "edge",
      "candidate_key": "candidate:sha256:67c682361434354688cd98af8ce68bdb0ac1a01badcf4fececf9d85614750059",
      "candidate_origin": "validated_proposal",
      "dependency_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "validation_status": "invalid",
      "source": "context-node:bindle:11111111111111111111111111111111",
      "relationship": "depends_on",
      "target": "context-node:bindle:22222222222222222222222222222222",
      "basis": [
        {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
        {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
        {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"}
      ]
    }
  ]
}
```

No `edges` array — the candidate exists but was
never materialized because `validation_status` is `"invalid"`; manifest
entry: `"expect_valid": true, "expect_codes": []` (the bundle itself is
schema-valid; "rejected" is expressed by the candidate's own
`validation_status`, not by a validator finding).

- [ ] **Step 5: Write fixture 19 (changed basis → new candidate key)**

Two bundle files, `core/19-basis-a.json` and `core/19-basis-b.json`, each
with one `candidates` entry identical except `pointer: "#1"` vs
`pointer: "#2"` in the basis (compute each `candidate_key` by running
Task 3's `canonical.candidate_key` once `canonical.py` exists — do not
hand-invent a digest). Manifest entry:

```json
{
  "id": "19",
  "assertion": "candidate_key_distinct",
  "with": ["core/19-basis-a.json", "core/19-basis-b.json"],
  "coverage_tags": ["core", "canonicalization"]
}
```

- [ ] **Step 6: Write fixtures 20–27, 30 (each a single invalid bundle)**

One bundle file per fixture, named `core/NN-<slug>.json` matching the
table above; each fixture's manifest entry sets `"expect_valid": false`
and `"expect_codes": ["<the code from the table>"]`,
`"match_mode": "exact"`. Concrete construction:
- **20**: two nodes with the same `id`.
- **21**: two edges with the same `key` (reuse fixture 6's edge twice).
- **22**: one edge whose `target` id has no matching node.
- **23**: one edge with `relationship: "frobnicates"`.
- **24**: one edge with `relationship: "implements"`.
- **25**: one edge, `origin: "human_judgment"`, no `judgments` array.
- **26**: one edge, `origin: "deterministic"`, relationship `"closes"`,
  no `deterministic_source` field.
- **27**: one edge with `review_trigger` set to the *wrong* boolean for its
  relationship (e.g. `"depends_on"` with `review_trigger: false`).
- **30**: one node with `kind: "architecture_component"`.

- [ ] **Step 7: Write fixtures 28–29 (coverage states, valid)**

`core/28-uncertain-github-coverage.json` and
`core/29-unsupported-commit-coverage.json`: an `index`-shaped object (no
`nodes`/`edges` needed — coverage is validated independently) —

```json
{
  "coverage": {
    "project_map": "complete", "sessions": "complete", "handoffs": "complete",
    "documents": "complete", "github_issues": "uncertain", "github_prs": "complete",
    "commits": "complete"
  }
}
```

(fixture 29 sets `"commits": "unsupported"` instead). `validate_bundle`
does not currently inspect a `coverage` key — Task 4 as written has no
`_check_coverage` function because the design defines coverage states as
informational, never invariant-violating (`unavailable`/`uncertain` must
never be interpreted as missing — there is nothing to reject). Manifest
entry: `"expect_valid": true, "expect_codes": []`. This fixture exists to
document/pin the non-invariant, not to exercise a check.

- [ ] **Step 8: Run the fixture corpus so far**

Run: `python3 bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`
Expected: `N/N fixtures passed` for every fixture added in this task
(compute `dependency_fingerprint`/`candidate_key` placeholder values in
fixture 18/19 for real using `python3 -c "from context_graph import
canonical; print(canonical.candidate_key(...))"` before trusting green —
never hand-type a digest into a fixture).

- [ ] **Step 9: Commit**

```bash
git add testdata/context-graph/v1/manifest.json testdata/context-graph/v1/core/
git commit -m "test(#180): add core/ fixtures 1-32 (minus harness-level 31/32)"
```

---

## Task 9: `map-shape/` fixtures (33–42)

**Files:**
- Create: `testdata/context-graph/v1/map-shape/*.json`
- Modify: `testdata/context-graph/v1/manifest.json` (append this task's fixture entries to the existing `fixtures` array — do not overwrite Task 8's entries)

**Fixture list (verbatim from the issue body's "Map-shape fixtures"
section):**

| # | Description | Expected | Code(s) |
|---|---|---|---|
| 33 | Valid fixtures for every canonical entry shape: decision heading, learning heading, single assumption bullet, two-sided tension parent, open question, parked question, typed tombstone | valid (7 sub-cases) | — |
| 34 | Malformed tension cardinality | invalid | `E_NODE_TENSION_CARDINALITY` |
| 35 | Identity marker on a tension side | invalid | `E_NODE_TENSION_SIDE_IDENTITY` |
| 36 | Untyped tombstone | invalid | `E_NODE_MALFORMED_ID` (an untyped tombstone has no recoverable kind, so it cannot carry a well-formed `context-node:` id — represent it as a node object with `"kind": null` and an id that fails `parse_typed_id`) |
| 37 | Unresolved replacement ID | invalid | `E_EDGE_MISSING_NODE_REF` (the `supersedes` edge's target names an id absent from `nodes`) |
| 38 | Self-referential replacement ID | invalid | `E_EDGE_SELF_EDGE_FORBIDDEN` |
| 39 | Duplicate identities across current and superseded sections | invalid | `E_NODE_DUPLICATE_ID` |
| 40 | Retirement without replacement | valid (no `supersedes` edge required) | — |
| 41 | Resolvable supersession emitting `replacement --supersedes--> retired` | valid | — |
| 42 | A `supported_by` pointer repeated on the tension parent and both sides deduplicates to one edge with sorted basis locations | valid | — |

- [ ] **Step 1: Write fixture 33's seven sub-case bundles**

`testdata/context-graph/v1/map-shape/33-1-decision-heading.json` through
`33-7-typed-tombstone.json` — each a single-node bundle:
- `33-1`: `{"class": "semantic", "kind": "decision", "status": "current"}`
- `33-2`: `{"class": "semantic", "kind": "learning", "status": "current"}`
- `33-3`: `{"class": "semantic", "kind": "assumption", "status": "current", "confidence": "high"}`
- `33-4`: `{"class": "semantic", "kind": "tension", "status": "current", "confidence": "low", "sides": [{"label": "a", "evidence": ["#1"]}, {"label": "b", "evidence": ["#2"]}]}`
- `33-5`: `{"class": "semantic", "kind": "question", "status": "open"}`
- `33-6`: `{"class": "semantic", "kind": "question", "status": "parked"}`
- `33-7`: `{"class": "semantic", "kind": "decision", "status": "superseded"}`
  (a typed tombstone is just a node whose `status` is `superseded`,
  retaining its original `kind`)

Each gets `id: "context-node:bindle:" + "<distinct 32-hex>"`, `label`, and
its own manifest entry: `"expect_valid": true, "expect_codes": [],
"coverage_tags": ["map-shape"]`.

- [ ] **Step 2: Write fixtures 34–39 (one invalid bundle each)**

- **34**: a `tension` node with `"sides"` holding 1 or 3 entries.
- **35**: a `tension` node whose one side carries an `"id"` field.
- **36**: a node with `"class": "semantic", "kind": null, "status":
  "superseded", "id": "context-node:bindle:untyped"` — `id` fails
  `HEX32_RE` so `parse_typed_id` raises, giving `E_NODE_MALFORMED_ID`.
- **37**: a `supersedes` edge (`origin: "deterministic",
  deterministic_source.kind: "map_tombstone"`) whose `target` node is
  absent from `nodes`.
- **38**: a `supersedes` edge whose `source` and `target` are the same
  node id.
- **39**: two nodes sharing one `id` — one `status: "current"`, one
  `status: "superseded"`.

Each fixture's manifest entry: `"expect_valid": false, "expect_codes":
["<code>"], "match_mode": "exact", "coverage_tags": ["map-shape"]`.

- [ ] **Step 3: Write fixture 40 (retirement without replacement, valid)**

One node, `status: "superseded"`, no `edges` array at all — proves a
retirement with no `supersedes` edge is legal.

- [ ] **Step 4: Write fixture 41 (resolvable supersession, valid)**

Two `decision` nodes (`replacement`, `retired`, `retired.status:
"superseded"`), one `supersedes` edge `source: replacement, target:
retired`, `origin: "deterministic"`,
`deterministic_source.kind: "map_tombstone"`.

- [ ] **Step 5: Write fixture 42 (supported_by basis dedup, valid)**

One semantic `tension` node with two sides, one evidence node, and one
`supported_by` edge whose `basis` array repeats the same evidence pointer
three times across three locations:

```json
"basis": [
  {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#4"},
  {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#4"},
  {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#4"}
]
```

The fixture doesn't assert dedup by itself (that's `canonical_basis_bytes`'s
job, exercised in Task 13) — it asserts the *edge* validates cleanly with a
repeated-but-legal basis array (`expect_valid: true`).

- [ ] **Step 6: Run the corpus and commit**

Run: `python3 bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`
Expected: all fixtures pass, including Task 8's.

```bash
git add testdata/context-graph/v1/manifest.json testdata/context-graph/v1/map-shape/
git commit -m "test(#180): add map-shape/ fixtures 33-42"
```

---

## Task 10: `endpoint-matrix/` fixtures (43–54)

**Files:**
- Create: `testdata/context-graph/v1/endpoint-matrix/*.json`
- Modify: `testdata/context-graph/v1/manifest.json` (append)

**Fixture list (verbatim from the issue body's "Endpoint-matrix fixtures"
section) — every item is a valid/invalid pair or triple, each half its own
bundle file and manifest entry:**

| # | Description | Valid half | Invalid half(s) |
|---|---|---|---|
| 43 | Project `contains` semantic succeeds; project `contains` issue fails | project→decision `contains` | project→github_issue `contains` (`E_EDGE_ENDPOINT_ILLEGAL`) |
| 44 | Semantic `supported_by` evidence succeeds; evidence `supported_by` semantic fails | decision→session `supported_by` | session→decision `supported_by` (`E_EDGE_ENDPOINT_ILLEGAL`) |
| 45 | PR `closes` issue succeeds; issue `closes` PR fails | github_pr→github_issue `closes` | github_issue→github_pr `closes` (`E_EDGE_ENDPOINT_ILLEGAL`) |
| 46 | Decision `implemented_by` PR succeeds; learning `implemented_by` PR fails | decision→github_pr | learning→github_pr (`E_EDGE_ENDPOINT_ILLEGAL`) |
| 47 | Learning `validated_by` design succeeds; question `validated_by` issue fails | learning→design_document | question→github_issue (`E_EDGE_ENDPOINT_ILLEGAL`) |
| 48 | Decision `resolves` question succeeds; question `resolves` decision fails | decision→question | question→decision (`E_EDGE_ENDPOINT_ILLEGAL`) |
| 49 | Decision `resolves` tension succeeds | decision→tension | — |
| 50 | Tension `constrains` decision succeeds | tension→decision | — |
| 51 | Same-kind `supersedes` succeeds; cross-kind and self-supersession fail | decision→decision | decision→learning (`E_EDGE_ENDPOINT_ILLEGAL`); decision→itself (`E_EDGE_SELF_EDGE_FORBIDDEN`) |
| 52 | Reversed `contradicts` proposals produce one canonical candidate and edge | — | `assertion: candidate_key_equals` over two candidate bundles with source/target swapped |
| 53 | Semantic `implements` is rejected as reserved in v1 | — | decision→github_pr `implements` (`E_EDGE_RELATIONSHIP_REJECTED`) |
| 54 | Reserved future node kinds cannot enter a v1 endpoint group | — | `architecture_component`→decision `contains`-shaped edge (`E_EDGE_ENDPOINT_ILLEGAL`, since the reserved kind matches no group even before the `E_NODE_RESERVED_KIND` node-level check fires) |

- [ ] **Step 1: Write fixtures 43–48 (12 bundle files, one per valid/invalid half)**

Each bundle: two nodes of the stated classes/kinds plus one edge between
them using the stated relationship, `origin` and `review_trigger` set
correctly for a *judgment-required* relationship (add a matching accepted
`judgments` entry so the only finding under test is the endpoint one) or
correctly for a *deterministic* one (add the matching
`deterministic_source`). Valid halves: `"expect_valid": true,
"expect_codes": []`. Invalid halves: `"expect_valid": false,
"expect_codes": ["E_EDGE_ENDPOINT_ILLEGAL"], "match_mode": "exact"`. Every
entry's `"coverage_tags"` includes `"endpoint-matrix"` and the
relationship name (feeds Task 8's fixture-32 coverage assertion).

- [ ] **Step 2: Write fixtures 49–50 (2 valid bundle files)**

Same shape as Step 1's valid halves, for `decision --resolves--> tension`
and `tension --constrains--> decision`.

- [ ] **Step 3: Write fixture 51 (3 bundle files)**

`51-supersedes-same-kind.json` (valid, both `decision`),
`51-supersedes-cross-kind.json` (both `decision`/`learning`, expect
`E_EDGE_ENDPOINT_ILLEGAL` — Task 4's implementer found that
`relationships.validate_endpoint_pair` already folds `same_kind_required`
into its `ok` result, so a dedicated `E_EDGE_SUPERSEDES_KIND_MISMATCH` code
would be redundant; that code was dropped from `validation.py` and
`invariant-coverage.json` post-Task-4, see the progress ledger),
`51-supersedes-self.json` (source ==
target, expect `E_EDGE_SELF_EDGE_FORBIDDEN`).

- [ ] **Step 4: Write fixture 52 (contradicts canonical ordering)**

`52-contradicts-forward.json` and `52-contradicts-reversed.json`: each a
`candidates` bundle with `subject_type: "edge", relationship:
"contradicts"`, one with `source=A, target=B`, the other with
`source=B, target=A` — same `basis`. Compute each `candidate_key` with
`canonical.candidate_key` (which canonicalizes `contradicts` endpoints
internally, so both must come out identical). Manifest entry:

```json
{
  "id": "52",
  "assertion": "candidate_key_equals",
  "with": ["endpoint-matrix/52-contradicts-forward.json", "endpoint-matrix/52-contradicts-reversed.json"],
  "coverage_tags": ["endpoint-matrix", "contradicts"]
}
```

- [ ] **Step 5: Write fixture 53 (implements rejected)**

One `decision` node, one `github_pr` node, one edge with `relationship:
"implements"`. Manifest: `"expect_valid": false, "expect_codes":
["E_EDGE_RELATIONSHIP_REJECTED"]`.

- [ ] **Step 6: Write fixture 54 (reserved kind in endpoint matrix)**

One node `kind: "architecture_component"`, one `decision` node, one edge
`relationship: "contains"` with `source` the project node... actually
source must be `project` class per `contains`'s matrix — construct instead
as `source: <project node>, target: <architecture_component node>,
relationship: "contains"`. Manifest: `"expect_valid": false,
"expect_codes": ["E_NODE_RESERVED_KIND", "E_EDGE_ENDPOINT_ILLEGAL"],
"match_mode": "ordered_subset"` (both the node-level and edge-level checks
fire — `validate_bundle` never stops at the first error, and `_check_nodes`
runs before `_check_edges` per the fixed registration order in Task 4, so
`E_NODE_RESERVED_KIND` is guaranteed to precede `E_EDGE_ENDPOINT_ILLEGAL`).

- [ ] **Step 7: Run the corpus and commit**

Run: `python3 bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`
Expected: all fixtures pass, including Tasks 8–9's.

```bash
git add testdata/context-graph/v1/manifest.json testdata/context-graph/v1/endpoint-matrix/
git commit -m "test(#180): add endpoint-matrix/ fixtures 43-54"
```

---

## Task 11: `identity-config/` + `documents/` fixtures (55–70)

**Files:**
- Create: `testdata/context-graph/v1/identity-config/*.json`
- Create: `testdata/context-graph/v1/documents/*.json` (fixtures 68 and 69 only, duplicated per design section 13)
- Modify: `testdata/context-graph/v1/manifest.json` (append)

**Fixture list (verbatim from the issue body's "Identity and configuration
fixtures" section):**

| # | Description | Expected | Code(s) |
|---|---|---|---|
| 55 | Repositoryless project | valid | — |
| 56 | One-repository project | valid | — |
| 57 | Multi-repository project | valid | — |
| 58 | Repository rename with stable project ID and stable binding ID | valid | — |
| 59 | Slug rename with stable project ID | valid | — |
| 60 | Ambiguous bare GitHub reference | valid (unresolved evidence state, not an error — see below) | — |
| 61 | Duplicate repository aliases rejected | invalid | `E_CONFIG_DUPLICATE_ALIAS` |
| 62 | Duplicate binding IDs rejected | invalid | `E_CONFIG_DUPLICATE_BINDING_ID` |
| 63 | Multiple default repositories rejected | invalid | `E_CONFIG_MULTIPLE_DEFAULT` |
| 64 | A project node whose ID differs from configured `project_id` rejected | invalid | `E_NODE_PROJECT_ID_MISMATCH` |
| 65 | Repository-shaped project ID such as `project:owner/repo` rejected | invalid | `E_CONFIG_PROJECT_ID_REPO_SHAPED` |
| 66 | Missing or malformed `project_id` after initialization rejected | invalid | `E_CONFIG_MALFORMED_PROJECT_ID` |
| 67 | Attempted derivation of `project_id` from repository coordinates rejected | invalid | `E_CONFIG_MALFORMED_PROJECT_ID` (a `project_id` shaped like `project:<sha256-of-coordinates>` truncated to non-hex or otherwise not opaque 32-hex is caught by the same check as 66 — #180 has no derivation logic to specifically detect *intent*, only shape) |
| 68 | Two configured repositories containing the same relative document path produce distinct binding-qualified document identities | valid | — |
| 69 | A project-local document without a repository binding uses the `project-local` form and validates | valid | — |
| 70 | A 16-character semantic ID hex component rejected as malformed | invalid | `E_NODE_MALFORMED_ID` |

- [ ] **Step 1: Write fixtures 55–59 (5 valid config bundles)**

- **55**: `config.repositories: []`.
- **56**: one repository entry.
- **57**: two repository entries, distinct aliases/binding_ids/coordinates,
  at most one `default_for_bare_references: true`.
- **58**: same as 56 but demonstrate stability by including a `_comment`-free
  second config bundle `58-after-rename.json` with the same `project_id`
  and `binding_id`, only `coordinates` changed — manifest entry for 58 is
  actually a `candidate_key_equals`-style check isn't applicable here
  (there's no candidate); instead assert both configs independently
  validate clean (`"expect_valid": true`) as two separate manifest fixture
  entries `58-before` and `58-after`, proving rename alone never produces a
  finding.
- **59**: one config bundle, then a second with only `project_slug`
  changed and the same `project_id`; both independently valid.

- [ ] **Step 2: Write fixture 60 (ambiguous bare GitHub reference, valid)**

A config with two repositories, neither marked
`default_for_bare_references: true` (i.e. zero defaults, which is legal —
only *more than one* default is rejected). This bundle also includes a
`proposals` entry whose `target` is a bare, unqualified GitHub reference
(no owner/repo prefix) to demonstrate the "ambiguous reference produces
unresolved evidence, not a guessed identity" state — `validate_bundle` has
no check that rejects this (#180 doesn't resolve GitHub; that's #183/#184),
so `"expect_valid": true, "expect_codes": []`.

- [ ] **Step 3: Write fixtures 61–63 (3 invalid config bundles)**

Reuse Task 4's `test_duplicate_alias_rejected` /
`test_duplicate_binding_id_rejected` / `test_multiple_default_rejected`
config shapes verbatim as fixture bodies (wrap each in `{"config": {...}}`).

- [ ] **Step 4: Write fixture 64 (project node id mismatch)**

`config.project_id = "project:" + "a"*32`; one node `class: "project", id:
"project:" + "b"*32` (mismatched). Manifest: `"expect_codes":
["E_NODE_PROJECT_ID_MISMATCH"]`.

- [ ] **Step 5: Write fixtures 65–67 (3 invalid config bundles)**

- **65**: `config.project_id = "project:thomas-estep/bindle"`.
- **66**: `config.project_id = ""` (empty) or omitted entirely.
- **67**: `config.project_id = "project:6f7562-6f776e65722d7265706f"` (a
  hex-looking but derived-from-ASCII-encoded-"owner/repo" string that still
  fails `HEX32_RE` because it's not exactly 32 chars / contains a `-`) —
  demonstrates the shape check catches derivation attempts without needing
  intent-detection.

- [ ] **Step 6: Write fixtures 68–69 (valid; duplicated under `documents/`)**

- **68**: two repository bindings with distinct `binding_id`s, and two
  `document:<project-id>:<binding-id>:<same-relative-path>` node ids (using
  `context_graph.ids.format_document_repository_id` shape) — same
  `repository_relative_path`, different `binding_id`, so the full ids
  differ. Represent as a `nodes` array of two `class: "evidence", kind:
  "design_document"` nodes.
- **69**: one `document:<project-id>:project-local:<path>` node id, no
  repository binding involved.

Write each as `identity-config/68-...json` /
`identity-config/69-...json` **and** duplicate the identical file content
at `documents/68-...json` / `documents/69-...json` (design section 13:
"also exercised under documents/") — two manifest entries per fixture
number, both `"expect_valid": true`, `"coverage_tags": ["identity-config"]`
and `["documents"]` respectively.

- [ ] **Step 7: Write fixture 70 (16-char hex rejected)**

One node `id: "context-node:bindle:0123456789abcdef"` (16 hex chars, not
32). Manifest: `"expect_codes": ["E_NODE_MALFORMED_ID"]`.

- [ ] **Step 8: Run the corpus and commit**

Run: `python3 bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`
Expected: all fixtures pass, including Tasks 8–10's.

```bash
git add testdata/context-graph/v1/manifest.json \
  testdata/context-graph/v1/identity-config/ testdata/context-graph/v1/documents/
git commit -m "test(#180): add identity-config/ and documents/ fixtures 55-70"
```

---

## Task 12: `candidates/` fixtures (71–81)

**Files:**
- Create: `testdata/context-graph/v1/candidates/*.json`
- Modify: `testdata/context-graph/v1/manifest.json` (append)

**Fixture list (verbatim from the issue body's "Authority-separation
fixtures" section):**

| # | Description | Expected | Code(s) |
|---|---|---|---|
| 71 | Deterministic edges are emitted directly and never require judgments | valid | — |
| 72 | #183 emits an identity-anchor candidate for an unanchored entry | valid | — |
| 73 | A human or skill cannot synthesize a valid anchor candidate | invalid | `E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN` |
| 74 | A semantic proposal is not accepted as a candidate before #184 validation | valid (proposal present, no matching candidate — no finding, since #180 has nothing that promotes a bare proposal) | — |
| 75 | #184 computes the same candidate key for equivalent proposals from human, skill, and fixture sources | `assertion: candidate_key_equals` across 3 bundles | — |
| 76 | A producer-supplied conflicting candidate key is rejected | invalid | `E_CANDIDATE_KEY_CONFLICT` |
| 77 | An invalid endpoint or relationship never becomes a review candidate | invalid | `E_CANDIDATE_INVALID_ENDPOINT` |
| 78 | Accepted judgment, not producer confidence or model output, creates the effective judged edge | valid | — |
| 79 | Subject-type incompatibility: an `edge` judgment cannot authorize an `identity_anchor` subject, and the reverse | invalid (2 sub-cases) | `E_JUDGMENT_SUBJECT_TYPE_MISMATCH` |
| 80 | A whole-graph fingerprint change alone does not stale an otherwise unchanged candidate | `assertion: dependency_fingerprint_equals` | — |
| 81 | A material dependency change does stale the affected candidate | `assertion: dependency_fingerprint_distinct` | — |

- [ ] **Step 1: Write fixture 71 (deterministic edge, valid, no judgment)**

One `closes` edge, `origin: "deterministic"`,
`deterministic_source.kind: "github_closure"`, no `judgments` array —
proves `E_EDGE_JUDGMENT_REQUIRED_MISSING` never fires for a deterministic
edge.

- [ ] **Step 2: Write fixture 72 (identity-anchor candidate, valid)**

```json
{
  "candidates": [
    {
      "subject_type": "identity_anchor",
      "candidate_key": "anchor-candidate:sha256:de5f2e3ead19bcb905dfd0ac06898c12c71bb1a7d112de386363490e54197933",
      "candidate_origin": "deterministic_compiler",
      "dependency_fingerprint": "sha256:f579dbeb232f6f18724ea3322132105aed41dc8b799d98dc79ab495133224e5f",
      "validation_status": "valid",
      "project_id": "project:5f56c9b95c41c298f70d6dd4e5db8c2a",
      "map_path": "projects/bindle/map.md",
      "section": "decisions",
      "entry_kind": "decision",
      "entry_fingerprint": "sha256:37730a28d9968e38cb25da0b1a98b7c4e13c43a2b661ca2b6cd3daf884b8e681",
      "display_claim": "Separate release intent, artifact, and publication authority"
    }
  ]
}
```

(Reuses Task 3's independently-verified worked vector directly —
`candidate_origin: "deterministic_compiler"` is required for
`identity_anchor` and this fixture is the one that proves the *legal*
path, paired with fixture 73's illegal one.)

- [ ] **Step 3: Write fixture 73 (anchor synthesis forbidden, invalid)**

Same candidate as fixture 72 but `"candidate_origin":
"validated_proposal"`. Manifest: `"expect_codes":
["E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN"]`.

- [ ] **Step 4: Write fixture 74 (proposal alone is not a candidate, valid)**

```json
{
  "proposals": [
    {
      "source": "context-node:bindle:11111111111111111111111111111111",
      "relationship": "depends_on",
      "target": "context-node:bindle:22222222222222222222222222222222",
      "basis": [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#9"}],
      "explanation": "these look related",
      "producer": "human"
    }
  ]
}
```

No `candidates`/`edges` array — proves a bare proposal produces zero
findings and, critically, is never itself validated as if it were an edge
(`validate_bundle` has no `_check_proposals`; proposals are inert
documentation of intent per design section 9 until #184 validates them).

- [ ] **Step 5: Write fixture 75 (equal candidate key across producers)**

Three bundles, `75-human.json`/`75-skill.json`/`75-fixture.json`, each
with one identical `candidates` entry (`subject_type: "edge"`, same
source/relationship/target/basis) differing only in a `"producer"` field
value (`"human"`/`"skill"`/`"fixture"`) — `producer` never participates in
`candidate_key` (Task 3's algorithm doesn't take it as an input), so all
three keys are identical by construction. Manifest:

```json
{
  "id": "75",
  "assertion": "candidate_key_equals",
  "with": ["candidates/75-human.json", "candidates/75-skill.json", "candidates/75-fixture.json"],
  "coverage_tags": ["candidates"]
}
```

- [ ] **Step 6: Write fixture 76 (candidate key conflict, invalid)**

One `candidates` entry where the declared `"candidate_key"` does **not**
match what `canonical.candidate_key(source, relationship, target, basis)`
recomputes (e.g. take fixture 75's inputs but hand-alter the declared
`candidate_key`'s last hex digit). Manifest: `"expect_codes":
["E_CANDIDATE_KEY_CONFLICT"]`.

- [ ] **Step 7: Write fixture 77 (invalid endpoint never becomes a candidate)**

One `candidates` entry, `subject_type: "edge"`, `relationship:
"implemented_by"`, with `source_class: "semantic", source_kind:
"learning"` (illegal — `implemented_by` requires `decision`) and
`target_class: "evidence", target_kind: "github_pr"`. Manifest:
`"expect_codes": ["E_CANDIDATE_INVALID_ENDPOINT"]`.

- [ ] **Step 8: Write fixture 78 (accepted judgment creates the edge, valid)**

Reuse fixture 6's `depends_on` edge + matching accepted judgment (Task 8),
plus a `candidates` entry for the same subject with
`"validation_status": "valid"` — the point of this fixture is that the
edge's presence and status trace to the accepted judgment, not to any
confidence/producer field on the candidate (there is none to test against
by omission, so this fixture also includes a candidate with no
`"producer_confidence"`-shaped field at all, proving the schema has no
such field for the validator to accidentally honor).

- [ ] **Step 9: Write fixture 79 (subject-type mismatch, 2 invalid bundles)**

`79-edge-judgment-wrong-subject.json`: a `candidates` entry with
`subject_type: "identity_anchor"` and a `judgments` entry referencing its
`candidate_key` with `"subject_type": "edge"`.
`79-anchor-judgment-wrong-subject.json`: the reverse (candidate
`subject_type: "edge"`, judgment declares `"subject_type":
"identity_anchor"`). Both: `"expect_codes":
["E_JUDGMENT_SUBJECT_TYPE_MISMATCH"]`.

- [ ] **Step 10: Write fixtures 80–81 (dependency_fingerprint relation checks)**

- **80**: `80-a.json`/`80-b.json`, each an identity-anchor candidate with
  identical `project_id`/`map_path`/`section`/`entry_kind`/
  `entry_fingerprint` (so identical `dependency_fingerprint` by
  construction) but a different `"whole_graph_fingerprint"` diagnostic
  value — proves the diagnostic alone can differ while
  `dependency_fingerprint` stays equal. Manifest:
  `"assertion": "dependency_fingerprint_equals"`.
- **81**: `81-a.json`/`81-b.json`, each an identity-anchor candidate with
  the *same* `project_id`/`map_path`/`section`/`entry_kind` but a
  different `entry_bytes`-derived `entry_fingerprint` (hand-vary one word
  in the underlying entry text and recompute `entry_fingerprint` via
  `canonical.entry_fingerprint` — never hand-type it), so
  `anchor_dependency_fingerprint` necessarily differs too. Manifest:
  `"assertion": "dependency_fingerprint_distinct"`.

- [ ] **Step 11: Run the corpus and commit**

Run: `python3 bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`
Expected: all fixtures pass, including Tasks 8–11's.

```bash
git add testdata/context-graph/v1/manifest.json testdata/context-graph/v1/candidates/
git commit -m "test(#180): add candidates/ fixtures 71-81"
```

---

## Task 13: `canonicalization/` byte-exact vector fixtures

**Files:**
- Create: `testdata/context-graph/v1/canonicalization/*.input.json`,
  `*.expected.txt`, `*.expected.json`
- Modify: `testdata/context-graph/v1/manifest.json` (append)
- Modify: `bin/check-context-graph-fixtures.py` (add a `canonicalization`
  assertion kind)

These fixtures pin exact digests so any reimplementation (a future
non-Python consumer, or a refactor of `canonical.py`) is caught the moment
it drifts. Both vectors below were independently computed during planning
(Task 3's tests already assert them) — this task packages them as the
paired-file fixture format design section 13 specifies.

- [ ] **Step 1: Write the anchor vector (`anchor-01`)**

`canonicalization/anchor-01.input.json`:

```json
{
  "project_id": "project:5f56c9b95c41c298f70d6dd4e5db8c2a",
  "map_path": "projects/bindle/map.md",
  "section": "decisions",
  "entry_kind": "decision",
  "entry_lines": [
    "### Separate release intent, artifact, and publication authority (2026-07, settled)",
    "why: three failure modes were collapsing into one review step.",
    "so: release-captain recommends, package-release-integrity gates, a human publishes.",
    "revisit-when: a provider ships one safe end-to-end release action.",
    "evidence: sessions/2026-07-15-release-captain.md"
  ]
}
```

`canonicalization/anchor-01.expected.txt` (one value per line, in the
order `entry_fingerprint`, `candidate_key`, `dependency_fingerprint`):

```text
sha256:37730a28d9968e38cb25da0b1a98b7c4e13c43a2b661ca2b6cd3daf884b8e681
anchor-candidate:sha256:de5f2e3ead19bcb905dfd0ac06898c12c71bb1a7d112de386363490e54197933
sha256:f579dbeb232f6f18724ea3322132105aed41dc8b799d98dc79ab495133224e5f
```

- [ ] **Step 2: Write the edge vector (`edge-01`)**

`canonicalization/edge-01.input.json`:

```json
{
  "source": "context-node:bindle:11111111111111111111111111111111",
  "relationship": "depends_on",
  "target": "context-node:bindle:22222222222222222222222222222222",
  "basis": [
    {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
    {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
    {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"}
  ]
}
```

`canonicalization/edge-01.expected.json` (the exact `canonical_basis_bytes`
array, deduplicated and sorted):

```json
[
  {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
  {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"}
]
```

`canonicalization/edge-01.expected.txt`:

```text
candidate:sha256:67c682361434354688cd98af8ce68bdb0ac1a01badcf4fececf9d85614750059
```

- [ ] **Step 3: Add a `canonicalization` assertion kind to the CLI**

Edit `bin/check-context-graph-fixtures.py` — add after `_run_relation_fixture`:

```python
def _run_canonicalization_fixture(manifest_dir, entry):
    input_path = os.path.join(manifest_dir, entry["input"])
    with open(input_path, encoding="utf-8") as fh:
        data = json.load(fh)
    expected_txt_path = os.path.join(manifest_dir, entry["expected_txt"])
    with open(expected_txt_path, encoding="utf-8") as fh:
        expected_lines = [line.strip() for line in fh if line.strip()]

    if "entry_lines" in data:
        entry_bytes = "\n".join(data["entry_lines"]).encode("utf-8")
        fp = canonical.entry_fingerprint(
            data["project_id"], data["map_path"], data["section"],
            data["entry_kind"], entry_bytes,
        )
        key = canonical.anchor_candidate_key(
            data["project_id"], data["map_path"], data["section"],
            data["entry_kind"], fp,
        )
        dep = canonical.anchor_dependency_fingerprint(
            data["project_id"], data["map_path"], data["section"],
            data["entry_kind"], fp,
        )
        actual_lines = [fp, key, dep]
        ok = actual_lines == expected_lines
        return {"id": entry["id"], "path": entry["input"], "ok": ok,
                "actual_valid": None, "actual_codes": actual_lines,
                "expect_valid": None, "expect_codes": expected_lines}

    key = canonical.candidate_key(data["source"], data["relationship"], data["target"], data["basis"])
    ok = [key] == expected_lines
    if "expected_json" in entry:
        expected_json_path = os.path.join(manifest_dir, entry["expected_json"])
        with open(expected_json_path, encoding="utf-8") as fh:
            expected_basis = json.load(fh)
        actual_basis = json.loads(canonical.canonical_basis_bytes(data["basis"]))
        ok = ok and actual_basis == expected_basis
    return {"id": entry["id"], "path": entry["input"], "ok": ok,
            "actual_valid": None, "actual_codes": [key],
            "expect_valid": None, "expect_codes": expected_lines}
```

In `run_manifest`, add a branch: `elif entry["assertion"] ==
"canonicalization": results.append(_run_canonicalization_fixture(manifest_dir, entry))`
before the existing `else` (relation) branch.

- [ ] **Step 4: Add manifest entries**

```json
{
  "id": "anchor-01",
  "assertion": "canonicalization",
  "input": "canonicalization/anchor-01.input.json",
  "expected_txt": "canonicalization/anchor-01.expected.txt",
  "coverage_tags": ["canonicalization"]
},
{
  "id": "edge-01",
  "assertion": "canonicalization",
  "input": "canonicalization/edge-01.input.json",
  "expected_txt": "canonicalization/edge-01.expected.txt",
  "expected_json": "canonicalization/edge-01.expected.json",
  "coverage_tags": ["canonicalization"]
}
```

- [ ] **Step 5: Run and commit**

Run: `python3 bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`
Expected: both `anchor-01` and `edge-01` `PASS`, plus every prior fixture.

```bash
git add testdata/context-graph/v1/manifest.json \
  testdata/context-graph/v1/canonicalization/ bin/check-context-graph-fixtures.py
git commit -m "test(#180): add canonicalization/ byte-exact vector fixtures"
```

---

## Task 14: `bin/test-context-graph-schema.sh` — the single test harness

**Files:**
- Create: `bin/test-context-graph-schema.sh`

**Interfaces:**
- Consumes: `python3 -m unittest discover` over `bin/context_graph/tests/`;
  `bin/check-context-graph-fixtures.py --manifest testdata/context-graph/v1/manifest.json`.
- Produces: the single entry point wired into `make test` and pre-commit
  (Task 16); auto-excluded from `capabilities.json` (matches
  `^bin/test-.*\.sh$`, per design section 16).

This script also implements fixtures 31 (determinism) and 32 (relationship
coverage) — both are harness-level assertions over the corpus, not JSON
files (per Task 8's table).

- [ ] **Step 1: Write `bin/test-context-graph-schema.sh`**

```bash
#!/usr/bin/env bash
# test-context-graph-schema.sh — the single test harness for
# bin/context_graph/ (issue #180, epic #140): stdlib unittest module tests,
# the fixture-manifest CLI pass, and two harness-level assertions
# (fixtures 31/32 from the issue body's "Canonical fixtures" list, which
# are properties of the whole corpus rather than single JSON files).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
MANIFEST="$REPO_ROOT/testdata/context-graph/v1/manifest.json"
CLI="$REPO_ROOT/bin/check-context-graph-fixtures.py"

pass=0
fail=0
check() {
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}

echo "== module unit tests (stdlib unittest) =="
(cd "$REPO_ROOT" && "$PY" -m unittest discover -s bin/context_graph/tests -t . -v)
unit_status=$?
check "context_graph unit tests pass" bash -c "exit $unit_status"

echo "== fixture manifest corpus =="
fixture_output="$("$PY" "$CLI" --manifest "$MANIFEST")"
fixture_status=$?
echo "$fixture_output"
check "every manifest-registered fixture passes" bash -c "exit $fixture_status"

echo "== fixture 31: deterministic ordering across repeated runs =="
run1="$("$PY" "$CLI" --manifest "$MANIFEST" --format json)"
run2="$("$PY" "$CLI" --manifest "$MANIFEST" --format json)"
check "repeated CLI runs over the same manifest are byte-identical" \
  bash -c '[ "$1" = "$2" ]' _ "$run1" "$run2"

echo "== fixture 32: every v1 relationship appears in >=1 valid fixture =="
covered="$("$PY" - "$MANIFEST" <<'PYEOF'
import json
import sys

RELATIONSHIPS = {
    "contains", "supported_by", "discussed_in", "implemented_by",
    "validated_by", "closes", "motivates", "constrains", "depends_on",
    "resolves", "supports", "contradicts", "supersedes", "revisits",
}

with open(sys.argv[1], encoding="utf-8") as fh:
    manifest = json.load(fh)

covered_tags = set()
for entry in manifest["fixtures"]:
    if entry.get("expect_valid") is True or entry.get("assertion") in (
        "candidate_key_equals", "candidate_key_distinct",
        "dependency_fingerprint_equals", "dependency_fingerprint_distinct",
        "canonicalization",
    ):
        covered_tags.update(entry.get("coverage_tags", []))

missing = sorted(RELATIONSHIPS - covered_tags)
print(" ".join(missing))
PYEOF
)"
check "no relationship is missing coverage (missing: '${covered:-none}')" \
  bash -c '[ -z "$1" ]' _ "$covered"

echo
echo "test-context-graph-schema: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Make it executable and run it**

Run: `chmod +x bin/test-context-graph-schema.sh && bin/test-context-graph-schema.sh`
Expected: every `check` line shows `✓`, final line `test-context-graph-schema: N passed, 0 failed`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add bin/test-context-graph-schema.sh
git commit -m "test(#180): add bin/test-context-graph-schema.sh single test harness"
```

---

## Task 15: JSON Schema conformance test + `invariant-coverage.json` completeness check

**Files:**
- Create: `bin/context_graph/tests/test_schema_conformance.py`
- Modify: `bin/test-context-graph-schema.sh` (add a completeness-check step)

**Interfaces:**
- Consumes: the seven `schemas/context-graph/v1/*.schema.json` files
  (Task 5), the test-only `jsonschema` package (skip-if-absent locally,
  same pattern this task establishes for the repo — there is no existing
  Python skip-if-absent precedent to mirror, so this is this task's own
  reasonable implementation, matching the shellcheck/shfmt
  managed/enforced-elsewhere *spirit* the design cites), the fixture corpus
  under `testdata/context-graph/v1/` via `manifest.json`.
- Produces: a `unittest` test module that (a) skips cleanly with a printed
  notice when `jsonschema` isn't installed, (b) otherwise validates every
  `core`/`map-shape`/`endpoint-matrix`/`identity-config`/`candidates`
  fixture's individual objects (`nodes`, `edges`, `candidates`, `judgments`,
  `config`) against the matching schema and asserts native/schema agreement
  on every `schema-and-native`-classified invariant from
  `invariant-coverage.json`.

- [ ] **Step 1: Write the failing test `bin/context_graph/tests/test_schema_conformance.py`**

```python
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCHEMA_DIR = os.path.join(REPO_ROOT, "schemas", "context-graph", "v1")
TESTDATA_DIR = os.path.join(REPO_ROOT, "testdata", "context-graph", "v1")

OBJECT_SCHEMA_MAP = {
    "config": "config.schema.json",
    "nodes": "node.schema.json",
    "edges": "edge.schema.json",
    "proposals": "proposal.schema.json",
    "candidates": "candidate.schema.json",
    "judgments": "judgment.schema.json",
}


def _load_schema(name):
    with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed (test-only dependency; skipped locally)")
class TestSchemaConformance(unittest.TestCase):
    """Every schema-and-native-classified invariant must agree between the
    native validator (bin/context_graph/validation.py, already exercised by
    every fixture-manifest run) and a real off-the-shelf JSON Schema
    validator over the same fixture corpus — never a hand-rolled schema
    engine (design section 11)."""

    @classmethod
    def setUpClass(cls):
        cls.schemas = {key: _load_schema(name) for key, name in OBJECT_SCHEMA_MAP.items()}

    def _bundles(self):
        for path in glob.glob(os.path.join(TESTDATA_DIR, "*", "*.json")):
            if os.path.basename(path) == "manifest.json":
                continue
            if "canonicalization" in path:
                continue
            with open(path, encoding="utf-8") as fh:
                try:
                    yield path, json.load(fh)
                except ValueError:
                    continue

    def test_every_object_in_every_bundle_matches_its_schema(self):
        checked = 0
        for path, bundle in self._bundles():
            for key, schema in self.schemas.items():
                value = bundle.get(key)
                if value is None:
                    continue
                items = value if isinstance(value, list) else [value]
                for item in items:
                    try:
                        jsonschema.validate(item, schema)
                        checked += 1
                    except jsonschema.ValidationError as exc:
                        self.fail("%s: %s object failed schema conformance: %s" % (path, key, exc))
        self.assertGreater(checked, 0, "no objects were checked — fixture corpus is empty")


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed (test-only dependency; skipped locally)")
class TestInvariantCoverageCompleteness(unittest.TestCase):
    def test_every_finding_code_is_classified(self):
        from context_graph.validation import FINDING_CODES

        with open(os.path.join(SCHEMA_DIR, "invariant-coverage.json"), encoding="utf-8") as fh:
            coverage = json.load(fh)
        classified = {entry["code"] for entry in coverage["invariants"]}
        self.assertEqual(set(FINDING_CODES), classified)

    def test_schema_only_documentation_is_empty_or_justified(self):
        with open(os.path.join(SCHEMA_DIR, "invariant-coverage.json"), encoding="utf-8") as fh:
            coverage = json.load(fh)
        schema_only = [
            e for e in coverage["invariants"]
            if e["classification"] == "schema-only-documentation"
        ]
        for entry in schema_only:
            self.assertIn(
                "justification", entry,
                "schema-only-documentation entry %r needs explicit justification" % (entry["code"],),
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test**

Run: `python3 -m unittest bin.context_graph.tests.test_schema_conformance -v`
Expected: if `jsonschema` is not installed locally, `ok (skipped=...)` for
every test with a printed skip reason — this is a legitimate PASS state,
not a failure to chase. If installed (`pip install --user jsonschema` in a
scratch venv to confirm at least once during this task), all tests `ok`.

- [ ] **Step 3: Wire the conformance test into `bin/test-context-graph-schema.sh`**

Add after the "fixture 32" section (before the final summary):

```bash
echo "== JSON Schema / native conformance (skip-if-absent locally) =="
conformance_output="$("$PY" -m unittest bin.context_graph.tests.test_schema_conformance -v 2>&1)"
conformance_status=$?
echo "$conformance_output"
check "schema conformance module completes (skips cleanly if jsonschema absent)" \
  bash -c "exit $conformance_status"
```

- [ ] **Step 4: Run the full harness and commit**

Run: `bin/test-context-graph-schema.sh`
Expected: all `check` lines `✓`.

```bash
git add bin/context_graph/tests/test_schema_conformance.py bin/test-context-graph-schema.sh
git commit -m "test(#180): add JSON Schema/native conformance and invariant-coverage completeness checks"
```

---

## Task 16: pre-commit + `make test` wiring

**Files:**
- Modify: `.pre-commit-config.yaml`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `bin/test-context-graph-schema.sh` (Tasks 14–15).
- Produces: `make test` runs the new harness; pre-commit gains
  `bindle-test-context-graph-schema` — per the design's own note (section
  16.3 area / handoff), this is the **first** hook needing
  `additional_dependencies` (`language: python` rather than the repo's usual
  `language: script`), because the schema-conformance sub-step wants
  `jsonschema` importable inside the hook's isolated venv, while the
  runtime package itself stays stdlib-only.

- [ ] **Step 1: Add the harness to `Makefile`'s `test:` target**

Read the current `test:` target (`Makefile:19-38`) and add one line,
keeping alphabetical-by-addition-order consistent with the existing list
(append at the end, matching how `bin/test-map-entry-id.sh` was appended
after #179):

```makefile
test:
	bin/test-install.sh
	bin/test-check.sh
	bin/test-check-frontmatter.sh
	bin/test-check-inventory.sh
	bin/test-manifest-lib.sh
	bin/test-doctor.sh
	bin/test-notes-home.sh
	bin/test-nested-notes-guard.sh
	bin/test-session-context.sh
	bin/test-session-hooks.sh
	bin/test-install-session-hooks.sh
	bin/test-package-release-integrity.sh
	bin/test-release-evidence.sh
	bin/test-session-end-land.sh
	bin/test-objective-worktree.sh
	bin/test-release-strategy.sh
	bin/test-release-please-sync.sh
	bin/test-release-publish.sh
	bin/test-map-entry-id.sh
	bin/test-context-graph-schema.sh
```

- [ ] **Step 2: Add the pre-commit hook**

In `.pre-commit-config.yaml`, add to the `repo: local` `hooks:` list
(after the existing `bindle-test-release-please-sync` entry, before
`bindle-link`):

```yaml
      - id: bindle-test-context-graph-schema
        name: context-graph schema/fixture/canonicalization tests
        entry: bin/test-context-graph-schema.sh
        language: python
        additional_dependencies: ["jsonschema"]
        pass_filenames: false
        always_run: true
```

(`language: python` + `additional_dependencies` gives the hook's isolated
venv a real `jsonschema` so the conformance sub-step actually runs under
pre-commit, even though a bare local `make test` run may skip it if the
developer's own interpreter lacks `jsonschema` — both are legitimate,
per design section 11's "skipped with a notice when absent locally,
installed and enforced in CI" model, with pre-commit standing in for CI
here since GitHub Actions CI is billing-blocked.)

- [ ] **Step 3: Run `make test` and `pre-commit run bindle-test-context-graph-schema --all-files`**

Run: `make test`
Expected: every listed test script passes, including the new one.

Run: `pre-commit run bindle-test-context-graph-schema --all-files`
Expected: `Passed` (this run has `jsonschema` available via
`additional_dependencies`, so the conformance sub-step actually executes,
not just skips).

- [ ] **Step 4: Commit**

```bash
git add Makefile .pre-commit-config.yaml
git commit -m "build(#180): wire context-graph schema tests into make test and pre-commit"
```

---

## Task 17: `capabilities.json` classification for every new `bin/` file

**Files:**
- Modify: `capabilities.json`

**Interfaces:**
- Consumes: nothing new — this task only classifies files added in Tasks
  1–15.
- Produces: `make check`'s `bin/check-inventory.py` bijection/completeness
  pass staying green. `VERSION` is currently `0.6.0`; per this repo's
  established rule (profile note: "`version_introduced` for a post-release
  capability = next bump ahead of `VERSION`"), every row below uses
  `"version_introduced": "0.7.0"`.

Per design section 16 (verified against the live `bin/check-inventory.py`
`AUTO_EXCLUDE` regexes: `^bin/test-.*\.sh$`, `^docs/design/`,
`^docs/plans/`):
- `bin/test-context-graph-schema.sh` is **auto-excluded** — needs no row.
- `docs/design/2026-07-16-context-graph-schema.md` is **already
  auto-excluded** (already merged; not touched by this plan).
- Everything else new under `bin/` needs a `not_a_capability` entry.
- `docs/context-graph-schema.md` needs a `contract`-type `capabilities.json`
  row (it is a shipped deliverable under `docs/`, not `docs/design/` or
  `docs/plans/`, so it is not auto-excluded).

- [ ] **Step 1: Add `not_a_capability` entries**

Add to `capabilities.json`'s `"not_a_capability"` array (after the
existing entries, before the closing `]`):

```json
{
  "path": "bin/context_graph/__init__.py",
  "reason": "package marker and SCHEMA_VERSION constant; library machinery, not an agent-invoked capability."
},
{
  "path": "bin/context_graph/ids.py",
  "reason": "shared library module imported by the validator and, later, #183/#184; not invoked directly."
},
{
  "path": "bin/context_graph/relationships.py",
  "reason": "shared library module imported by the validator; not invoked directly."
},
{
  "path": "bin/context_graph/canonical.py",
  "reason": "shared library module imported by the validator; not invoked directly."
},
{
  "path": "bin/context_graph/validation.py",
  "reason": "shared library module imported by the validator and the fixture CLI; not invoked directly."
},
{
  "path": "bin/context_graph/tests/__init__.py",
  "reason": "test package marker; makes bin/context_graph/tests discoverable by unittest, not an agent-invoked capability."
},
{
  "path": "bin/context_graph/tests/test_ids.py",
  "reason": "unit test module run via bin/test-context-graph-schema.sh (auto-excluded); not invoked directly."
},
{
  "path": "bin/context_graph/tests/test_relationships.py",
  "reason": "unit test module run via bin/test-context-graph-schema.sh (auto-excluded); not invoked directly."
},
{
  "path": "bin/context_graph/tests/test_canonical.py",
  "reason": "unit test module run via bin/test-context-graph-schema.sh (auto-excluded); not invoked directly."
},
{
  "path": "bin/context_graph/tests/test_validation.py",
  "reason": "unit test module run via bin/test-context-graph-schema.sh (auto-excluded); not invoked directly."
},
{
  "path": "bin/context_graph/tests/test_schema_conformance.py",
  "reason": "unit test module run via bin/test-context-graph-schema.sh (auto-excluded); not invoked directly."
},
{
  "path": "bin/check-context-graph-fixtures.py",
  "reason": "fixture validator invoked by the test harness / make check machinery, exactly like bin/check-inventory.py; not itself a capability an agent invokes for its own sake."
}
```

- [ ] **Step 2: Add the `contract`-type row for `docs/context-graph-schema.md`**

Add to `capabilities.json`'s `"capabilities"` array:

```json
{
  "name": "context-graph-schema",
  "type": "contract",
  "path": "docs/context-graph-schema.md",
  "description": "The shipped v1 context-graph interchange contract reference (typed IDs, node/relationship vocabulary, endpoint matrix, candidate-key canonicalization, validation model) implemented by bin/context_graph/ and schemas/context-graph/v1/ — issue #180, epic #140.",
  "provider": {
    "claude": "installed",
    "codex": "manual"
  },
  "maturity": "tested",
  "mutation": [],
  "version_introduced": "0.7.0"
}
```

- [ ] **Step 3: Run `make check` and confirm the inventory passes**

Run: `bin/check-inventory.py` (or `make check`)
Expected: no bijection/completeness errors — every new `bin/` file is
either auto-excluded or classified, and the new `docs/context-graph-schema.md`
row satisfies the completeness scan.

- [ ] **Step 4: Commit**

```bash
git add capabilities.json
git commit -m "chore(#180): classify context_graph package + fixture CLI + companion doc in capabilities.json"
```

---

## Self-Review

**Spec coverage** (against the #180 issue body's Acceptance criteria and
the design doc's §22 go-conditions):

- All seven schemas + `invariant-coverage.json`: Task 5. ✓
- Project identity opaque, independent of GitHub/slug/path: `ids.py`
  (Task 1) + `E_CONFIG_PROJECT_ID_REPO_SHAPED`/`E_CONFIG_MALFORMED_PROJECT_ID`
  (Task 4) + fixtures 65–67 (Task 11). ✓
- Repository bindings, stable `binding_id`, 0/1/many bindings: Task 4's
  config validation + fixtures 55–63 (Task 11). ✓
- Binding-qualified document identity + project-local form: `ids.py`
  formatters (Task 1) + fixtures 68–69 (Task 11, duplicated under
  `documents/`). ✓
- `tension` emitted kind + endpoint matrix participation: Task 2
  (`ENDPOINT_MATRIX`) + fixtures 33-4, 49, 50 (Tasks 9–10). ✓
- Closed relationship vocabulary + closed endpoint matrix: Task 2 + Task 10
  (fixtures 43–54). ✓
- Illegal endpoints are invariant failures, not candidates: `_check_edges`
  and `_check_candidates` in Task 4 (`E_EDGE_ENDPOINT_ILLEGAL`,
  `E_CANDIDATE_INVALID_ENDPOINT`) + fixture 77 (Task 12). ✓
- Self-edges forbidden, `supersedes` same-kind, `contradicts` canonical
  ordering: Task 2 + Task 4 + fixtures 38, 51, 52 (Tasks 9–10). ✓
- Every v1 relationship has an executable creation path: Tasks 8–10
  fixtures, aggregated by fixture 32's harness check (Task 14). ✓
- Deterministic vs. judgment-assisted distinguishable: `origin` field +
  `E_EDGE_DETERMINISTIC_AUTHORITY_MISSING`/`E_EDGE_JUDGMENT_REQUIRED_MISSING`
  (Task 4) + fixtures 25, 26, 71, 78 (Tasks 8, 12). ✓
- `implemented_by` sole attribution relationship, `implements` rejected:
  Task 2 + fixtures 24, 53 (Tasks 8, 10). ✓
- Review-triggering coupling explicit: `REVIEW_TRIGGER_DEFAULT` (Task 2) +
  fixture 27 (Task 8). ✓
- One subject vocabulary (`edge`, `identity_anchor`): `candidate.schema.json`
  (Task 5) + fixture 79 (Task 12). ✓
- Candidate-key + fingerprint contracts, byte-exact: Task 3, independently
  verified against the design's own worked example, + Task 13's pinned
  vectors. ✓
- `dependency_fingerprint` vs. whole-graph diagnostic: `candidate.schema.json`
  (Task 5) + fixtures 80, 81 (Task 12). ✓
- Coverage degradation never conflated with absence: fixtures 28, 29
  (Task 8) — deliberately produce zero findings. ✓
- Fixture validator reports precise invariant failures naming
  relationship/endpoint groups: `E_EDGE_ENDPOINT_ILLEGAL`'s message
  construction in Task 4. ✓
- Stdlib-only runtime, zero mutation: every module in Tasks 1–4, 6 uses
  only `re`/`json`/`hashlib`/`argparse`; no file writes anywhere. ✓
- `make check`/`make test` pass: Task 16. ✓

**Placeholder scan:** no `TBD`/"implement later"/"add appropriate X"
strings remain; the one place this plan deliberately compresses (Tasks
8–13's fixture-list-plus-pattern-following instead of all 81 literal JSON
bodies) is called out explicitly in the "Scope note on fixture tasks"
section, not hidden as a vague placeholder — every one of the 81
fixtures' *expected result and code* is stated, only the literal JSON body
for fixtures beyond the worked examples is left as pattern-following
against schemas fully frozen earlier in the same plan.

**Type/name consistency:** verified `candidate_key`/`entry_fingerprint`/
`anchor_candidate_key`/`anchor_dependency_fingerprint` signatures match
across Tasks 3, 4, 6, 12, 13. Verified `validate_bundle`/`validate_config`
signatures match across Tasks 4, 6, 11. Verified `FINDING_CODES` used
identically in Tasks 4, 5, 15. Fixed two planning-time typos caught during
drafting (a stray Python conditional in fixture 18's JSON, and a leftover
dead branch in Task 3's candidate-key test) before they reached the
written plan.
