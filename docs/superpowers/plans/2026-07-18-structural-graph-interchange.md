# Structural-Graph Interchange Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical versioned provider-neutral structural-graph JSON interchange (#227) and its reference reader, so the #141 projection engine can consume structural facts without importing any provider.

**Architecture:** A new `bin/structural_graph/` package with six single-responsibility modules — frozen vocabularies, redaction, hand-rolled validation, coverage tiling, single-document load, multi-document set load. It imports `context_graph.ids` and `context_graph.config` one-directionally and never the reverse. A JSON Schema mirrors the vocabularies for test-time conformance; a manifest-driven fixture corpus exercises every state.

**Tech Stack:** Python 3 stdlib only (`json`, `re`, `os`, `subprocess`, `unittest`). `jsonschema` is test-only, injected by the pre-commit hook. Bash for the test harness.

**Design spec:** `docs/superpowers/specs/2026-07-18-structural-graph-interchange-design.md`

## Global Constraints

Every task's requirements implicitly include all of these. They are house conventions verified against the existing `bin/context_graph/` package — deviating from any one of them will fail review.

- **No type hints, no dataclasses, no `enum.Enum`.** Every structure is a plain dict. Enumerated value sets are module-level tuples mirrored into JSON Schema `enum`.
- **Runtime validation is hand-rolled.** Never import `jsonschema` outside `bin/structural_graph/tests/`.
- **Findings are `{"code", "message", "index", "field"}` dicts.** No other keys. Never a `value` key.
- **Findings never contain an unredacted provider string.** Redaction runs before any finding is constructed.
- **Validators return finding lists and never raise.** Exceptions are reserved for caller error only.
- **The package writes nothing.** No `atomic_io.write_*` import anywhere in `bin/structural_graph/`.
- **Network access is never required or attempted.**
- **Determinism:** sorted keys, no timestamps in any output, repeated runs byte-identical.
- **Tests are stdlib `unittest`**, auto-discovered from `bin/structural_graph/tests/`, one `test_<module>.py` per module. Every test module starts with the path bootstrap shown in Task 1.
- **Every `bin/structural_graph/**/*.py` file needs a `not_a_capability` entry in `capabilities.json`** or `make check` fails. `bin/test-*.sh` is auto-excluded; `schemas/**` and `testdata/**` owe nothing.
- **`make check` must be green before every commit.** New files must be `git add`ed *before* running it — it scans tracked content only.
- **Branch discipline:** work stays on `feature/227-structural-graph-interchange`. Never commit to `main`, never `--no-verify`, never push.
- **Fixture authoring:** `private-ok` markers go on the same physical line as an offending string. Secret-shaped strings are bearer/API-key shaped (`ghp_`, `sk-`, `AKIA`) and **never PEM blocks** — `detect-private-key` honors neither `private-ok` nor the scanner skip list.
- **Files end in a newline, no trailing whitespace, LF endings.**

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `bin/structural_graph/__init__.py` | package marker (empty) |
| `bin/structural_graph/schema.py` | frozen vocabularies + anchor-field registry |
| `bin/structural_graph/redaction.py` | path normalization + secret redaction |
| `bin/structural_graph/validation.py` | hand-rolled structural validation, `E_SG_*` codes |
| `bin/structural_graph/coverage.py` | coverage tiling + `status_for` lookup |
| `bin/structural_graph/document.py` | single-document load pipeline |
| `bin/structural_graph/graphset.py` | multi-document set load + aggregation |
| `bin/structural_graph/tests/__init__.py` | test package marker (empty) |
| `bin/structural_graph/tests/test_*.py` | one per module, plus `test_schema_conformance.py` |
| `schemas/structural-graph/v1/document.schema.json` | JSON Schema mirror |
| `schemas/structural-graph/v1/invariant-coverage.json` | finding-code classification |
| `testdata/structural-graph/v1/manifest.json` | fixture registry |
| `testdata/structural-graph/v1/<category>/*.json` | fixture corpus, exactly one level deep |
| `bin/check-structural-graph-fixtures.py` | manifest-driven fixture runner |
| `bin/test-structural-graph.sh` | test harness |

**Modify:** `Makefile` (harness), `.pre-commit-config.yaml` (harness + `jsonschema`), `capabilities.json` (ledger entries), `bin/check-private-info.sh` (skip `redaction.py`), `.gitleaks.toml` (allowlist `redaction.py`).

---

### Task 1: Package skeleton, frozen vocabularies, and the test harness

Folds all scaffolding into the first task that needs it: without the harness nothing later can run a test.

**Files:**
- Create: `bin/structural_graph/__init__.py`, `bin/structural_graph/schema.py`, `bin/structural_graph/tests/__init__.py`
- Create: `bin/test-structural-graph.sh`
- Test: `bin/structural_graph/tests/test_schema.py`
- Modify: `Makefile`, `.pre-commit-config.yaml`, `capabilities.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `schema.SCHEMA_VERSION` (int), `schema.SUPPORTED_SCHEMA_VERSIONS` (tuple of int), `schema.SYMBOL_KINDS`, `schema.EDGE_TYPES`, `schema.CAPABILITIES`, `schema.COVERAGE_STATUSES`, `schema.DOCUMENT_STATUSES`, `schema.FRESHNESS_STATES`, `schema.ANCHOR_FIELDS` (all tuples of str), and `schema.is_anchor(field_path)` → bool.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_schema.py`:

```python
"""Unit tests for structural_graph.schema."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import schema


class TestVocabularies(unittest.TestCase):
    def test_supported_versions_contains_current(self):
        self.assertIn(schema.SCHEMA_VERSION, schema.SUPPORTED_SCHEMA_VERSIONS)

    def test_symbol_kinds_have_other_escape(self):
        self.assertIn("other", schema.SYMBOL_KINDS)

    def test_vocabularies_are_unique_nonempty_tuples(self):
        for name in (
            "SUPPORTED_SCHEMA_VERSIONS",
            "SYMBOL_KINDS",
            "EDGE_TYPES",
            "CAPABILITIES",
            "COVERAGE_STATUSES",
            "DOCUMENT_STATUSES",
            "FRESHNESS_STATES",
            "ANCHOR_FIELDS",
        ):
            value = getattr(schema, name)
            self.assertIsInstance(value, tuple, name)
            self.assertTrue(value, name)
            self.assertEqual(len(value), len(set(value)), name)

    def test_coverage_statuses_are_the_three_frozen_values(self):
        self.assertEqual(
            schema.COVERAGE_STATUSES,
            ("observed", "unsupported", "partial_parse_failure"),
        )


class TestIsAnchor(unittest.TestCase):
    def test_file_path_is_an_anchor(self):
        self.assertTrue(schema.is_anchor("files[].path"))

    def test_edge_endpoints_are_anchors(self):
        self.assertTrue(schema.is_anchor("edges[].source"))
        self.assertTrue(schema.is_anchor("edges[].target"))

    def test_coverage_prefix_is_an_anchor(self):
        self.assertTrue(schema.is_anchor("coverage[].path_prefix"))

    def test_diagnostics_are_not_anchors(self):
        self.assertFalse(schema.is_anchor("diagnostics[].message"))

    def test_optional_observations_are_never_anchors(self):
        self.assertFalse(
            schema.is_anchor("optional_provider_observations.routes[].path")
        )

    def test_unknown_field_is_not_an_anchor(self):
        self.assertFalse(schema.is_anchor("nope[].nothing"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_schema -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'structural_graph'`

- [ ] **Step 3: Write minimal implementation**

Create `bin/structural_graph/__init__.py` and `bin/structural_graph/tests/__init__.py` as empty files (zero bytes).

Create `bin/structural_graph/schema.py`:

```python
"""structural_graph.schema -- frozen vocabularies for the #227 interchange.

Owns the versioned value sets every other module in this package validates
against, plus the anchor-field registry that decides whether an
unnormalizable provider string fails a document closed or is redacted in
place (design spec, "Redaction").

Pure constants and pure membership lookup only: no filesystem access, no
network access, no validation beyond membership in a tuple. Cross-object
rules live in structural_graph.validation.

These tuples are mirrored into schemas/structural-graph/v1/document.schema.json
as JSON Schema "enum" values, the way context_graph.relationships mirrors
edge.schema.json. The mirror is asserted by the conformance tests; neither
copy may drift.
"""

SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = (1,)

# Normalized across providers. "other" is the mandatory escape: a provider
# that observes a construct with no normalized equivalent reports "other"
# rather than inventing a kind or dropping the symbol.
SYMBOL_KINDS = (
    "module",
    "class",
    "function",
    "method",
    "field",
    "constant",
    "type_alias",
    "interface",
    "other",
)

EDGE_TYPES = ("contains", "imports", "depends_on", "calls", "tests")

# Capability names are the unit coverage is declared against. A provider
# advertises the subset it supports; an unadvertised capability means the
# facts are unavailable, never observed-zero.
CAPABILITIES = (
    "contains",
    "imports",
    "depends_on",
    "calls",
    "tests",
    "has_export_visibility",
)

COVERAGE_STATUSES = ("observed", "unsupported", "partial_parse_failure")

DOCUMENT_STATUSES = (
    "loaded",
    "malformed",
    "unsupported_version",
    "deconfigured",
    "unavailable",
)

# Orthogonal to DOCUMENT_STATUSES: a stale document still loads.
FRESHNESS_STATES = ("current", "stale", "freshness_unknown")

# Dotted field paths whose values anchor a fact to the repository. An
# unnormalizable anchor makes the whole document malformed; every other
# string is redacted in place and its fact is kept.
ANCHOR_FIELDS = (
    "root",
    "files[].path",
    "symbols[].id",
    "symbols[].name",
    "symbols[].path",
    "edges[].source",
    "edges[].target",
    "coverage[].path_prefix",
)


def is_anchor(field_path):
    """True when field_path names an anchor field.

    Membership is exact against ANCHOR_FIELDS. Anything under
    optional_provider_observations is a provider conclusion, never an
    anchor, and is excluded by construction rather than by a prefix rule.
    """
    return field_path in ANCHOR_FIELDS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 9 tests, `OK`

- [ ] **Step 5: Create the test harness**

Create `bin/test-structural-graph.sh` (mode `755`):

```bash
#!/usr/bin/env bash
# Single test harness for bin/structural_graph/ (#227).
#
# Runs stdlib unittest discovery over the package's tests, then the
# manifest-driven fixture runner once it exists. Mirrors
# bin/test-context-graph-schema.sh.
set -euo pipefail

# Fixture tests shell out to git; git sets GIT_DIR in a pre-commit hook env
# and it overrides `git -C`, which would silently target the real repo.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

pass=0
fail=0

check() {
  local label="$1"
  shift
  if "$@" >/tmp/sg-check.$$ 2>&1; then
    echo "  ✓ $label"
    pass=$((pass + 1))
  else
    echo "  ✗ $label"
    sed 's/^/      /' /tmp/sg-check.$$
    fail=$((fail + 1))
  fi
  rm -f /tmp/sg-check.$$
}

echo "structural-graph:"
check "unit tests" python3 -m unittest discover -s bin/structural_graph/tests -t .

echo ""
if [ "$fail" -gt 0 ]; then
  echo "structural-graph: $fail check(s) failed, $pass passed"
  exit 1
fi
echo "structural-graph: all $pass check(s) passed"
```

- [ ] **Step 6: Wire the harness into the Makefile and pre-commit**

In `Makefile`, add to the `test` target's list alongside the other context-graph harnesses:

```make
	bash bin/test-structural-graph.sh
```

In `.pre-commit-config.yaml`, add a hook mirroring `bindle-test-context-graph-schema`. Both registrations are required: CI runs only `pre-commit run --all-files` and never `make test`, so a Makefile-only harness would not run in CI.

```yaml
      - id: bindle-test-structural-graph
        name: structural-graph interchange tests
        entry: bash bin/test-structural-graph.sh
        language: python
        additional_dependencies: ["jsonschema"]
        pass_filenames: false
        always_run: true
```

- [ ] **Step 7: Add ledger entries**

In `capabilities.json`, append to `not_a_capability`:

```json
    {
      "path": "bin/structural_graph/__init__.py",
      "reason": "package marker for the #227 structural-graph interchange library; consumed by the projection engine, not a standalone capability."
    },
    {
      "path": "bin/structural_graph/schema.py",
      "reason": "library module holding the frozen interchange vocabularies and anchor-field registry (#227); consumed by the structural_graph package, not a standalone capability."
    },
    {
      "path": "bin/structural_graph/tests/__init__.py",
      "reason": "test package marker for structural_graph; test infrastructure, not a capability an agent invokes."
    },
    {
      "path": "bin/structural_graph/tests/test_schema.py",
      "reason": "unit tests for structural_graph.schema; test infrastructure, not a capability an agent invokes."
    },
```

- [ ] **Step 8: Verify the full gate**

Run: `git add -A && make check && bash bin/test-structural-graph.sh`
Expected: `All checks passed.` then `structural-graph: all 1 check(s) passed`

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(#227): structural-graph package skeleton and frozen vocabularies

Adds bin/structural_graph/ with schema.py holding the interchange
vocabularies and the anchor-field registry, plus the test harness wired
into both the Makefile and pre-commit (CI runs pre-commit only)."
```

---

### Task 2: Redaction

**Files:**
- Create: `bin/structural_graph/redaction.py`
- Test: `bin/structural_graph/tests/test_redaction.py`
- Modify: `bin/check-private-info.sh`, `.gitleaks.toml`, `capabilities.json`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `redaction.normalize_path(value, root)` → repo-relative `str` or `None`; `redaction.redact(value)` → `(scrubbed_str, matched_names_tuple)`; `redaction.REDACTION_PATTERNS` (tuple of `(name, compiled_regex)`).

This task edits two privacy gates. `redaction.py` encodes the same home-directory pattern the scanners hunt for, exactly as `bin/check-private-info.sh` and `.gitleaks.toml` already self-exempt. Keep both edits minimal and reviewed.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_redaction.py`:

```python
"""Unit tests for structural_graph.redaction."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import redaction


class TestNormalizePath(unittest.TestCase):
    def test_plain_relative_path_passes_through(self):
        self.assertEqual(redaction.normalize_path("src/app.py", ""), "src/app.py")

    def test_leading_dot_slash_is_stripped(self):
        self.assertEqual(redaction.normalize_path("./src/app.py", ""), "src/app.py")

    def test_backslashes_become_forward_slashes(self):
        self.assertEqual(redaction.normalize_path("src\\app.py", ""), "src/app.py")

    def test_absolute_path_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("/etc/passwd", ""))

    def test_windows_drive_path_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("C:/repo/app.py", ""))

    def test_traversal_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("src/../../secret", ""))

    def test_query_string_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("src/app.py?raw=1", ""))

    def test_empty_value_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("", ""))

    def test_path_inside_root_is_kept(self):
        self.assertEqual(
            redaction.normalize_path("pkg/src/app.py", "pkg"), "pkg/src/app.py"
        )

    def test_path_outside_root_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("other/app.py", "pkg"))

    def test_root_itself_is_normalizable(self):
        self.assertEqual(redaction.normalize_path("pkg", "pkg"), "pkg")

    def test_sibling_with_shared_prefix_is_not_inside_root(self):
        self.assertIsNone(redaction.normalize_path("pkgother/app.py", "pkg"))


class TestRedact(unittest.TestCase):
    def test_clean_string_is_unchanged_and_matches_nothing(self):
        scrubbed, names = redaction.redact("parsed 12 symbols in src/app.py")
        self.assertEqual(scrubbed, "parsed 12 symbols in src/app.py")
        self.assertEqual(names, ())

    def test_home_directory_path_is_redacted(self):
        scrubbed, names = redaction.redact(
            "failed to open " + "/Users" + "/jane/repo/app.py"
        )
        self.assertNotIn("jane", scrubbed)
        self.assertIn("home-path", names)
        self.assertIn("[redacted:home-path]", scrubbed)

    def test_bearer_token_is_redacted(self):
        scrubbed, names = redaction.redact("auth failed for ghp_" + "A" * 36)
        self.assertNotIn("ghp_" + "A" * 36, scrubbed)
        self.assertIn("token", names)

    def test_aws_key_is_redacted(self):
        scrubbed, names = redaction.redact("key AKIA" + "B" * 16)
        self.assertNotIn("AKIA" + "B" * 16, scrubbed)
        self.assertIn("token", names)

    def test_multiple_patterns_all_reported_sorted(self):
        scrubbed, names = redaction.redact(
            "/Users" + "/jane/x and sk-" + "C" * 32
        )
        self.assertEqual(names, ("home-path", "token"))
        self.assertNotIn("jane", scrubbed)

    def test_redaction_is_idempotent(self):
        once, _ = redaction.redact("/Users" + "/jane/x")
        twice, names = redaction.redact(once)
        self.assertEqual(once, twice)
        self.assertEqual(names, ())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_redaction -v`
Expected: FAIL — `ImportError: cannot import name 'redaction'`

- [ ] **Step 3: Write minimal implementation**

Create `bin/structural_graph/redaction.py`:

```python
"""structural_graph.redaction -- path normalization and secret redaction.

A build gap, not a reuse. Nothing in bin/ relativizes a path or scrubs a
secret: bin/check-private-info.sh and .gitleaks.toml are detectors that
never rewrite content, and context_graph.evidence rejects an unsafe path
while echoing the raw value straight back to its caller.

Every provider string crosses this module before it reaches a fact, a
finding, a log line, or disk. Findings are built from redacted values only,
so a finding is structurally incapable of carrying a secret.

This module deliberately encodes the same home-directory pattern that
bin/check-private-info.sh scans for, so it carries a skip-list entry there
and an allowlist path in .gitleaks.toml -- the same self-exemption those
two files already hold.
"""

import re

REDACTED = "[redacted:%s]"

# Name -> pattern. Names appear in findings; the matched text never does.
REDACTION_PATTERNS = (
    ("home-path", re.compile(r"/Users/[A-Za-z][A-Za-z0-9._-]*")),
    ("home-path", re.compile(r"/home/[A-Za-z][A-Za-z0-9._-]*")),
    ("vault-path", re.compile(r"iCloud~md~obsidian|Mobile Documents/[^ ]*[Oo]bsidian")),  # private-ok: pattern literal, see the SKIP_FILES entry in Step 5
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("token", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("token", re.compile(r"AKIA[0-9A-Z]{16}")),
)


def normalize_path(value, root):
    """Return value as a repository-relative path, or None if unnormalizable.

    The interchange requires repository-relative paths. An absolute path, a
    Windows drive path, a traversal, or a query string has no safe relative
    form and is refused rather than guessed at -- callers turn a refused
    anchor into a malformed document.

    root bounds what the document may reference: "" means the whole
    repository. A path outside root is unnormalizable, so a document cannot
    smuggle facts about a subtree its coverage never tiled.
    """
    if not isinstance(value, str) or not value:
        return None
    if "?" in value:
        return None
    path = value.replace("\\", "/")
    if path.startswith("/"):
        return None
    if len(path) > 1 and path[1] == ":":
        return None
    if path.startswith("./"):
        path = path[2:]
    if not path:
        return None
    if ".." in path.split("/"):
        return None
    if root:
        if path != root and not path.startswith(root + "/"):
            return None
    return path


def redact(value):
    """Return (scrubbed, matched_names) for an incidental provider string.

    matched_names is a sorted tuple of distinct pattern names, suitable for
    a finding message. The matched text itself is never returned anywhere.
    Redaction is idempotent: a scrubbed string contains no further matches.
    """
    if not isinstance(value, str) or not value:
        return value, ()
    scrubbed = value
    names = set()
    for name, pattern in REDACTION_PATTERNS:
        replacement = REDACTED % name
        scrubbed, count = pattern.subn(replacement, scrubbed)
        if count:
            names.add(name)
    return scrubbed, tuple(sorted(names))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 27 tests, `OK`

- [ ] **Step 5: Exempt the module from the two scanners**

In `bin/check-private-info.sh`, add to the `SKIP_FILES` array (keep it literal and sorted with the existing entries):

```bash
  bin/structural_graph/redaction.py
```

In `.gitleaks.toml`, add to the `[allowlist]` `paths` list:

```toml
  '''bin/structural_graph/redaction\.py''',
```

Also pre-emptively allowlist the fixture corpus so it cannot become a latent blocker if gitleaks is ever wired into CI:

```toml
  '''testdata/structural-graph/v\d+/.*''',
```

- [ ] **Step 6: Add ledger entries**

In `capabilities.json`, append to `not_a_capability`:

```json
    {
      "path": "bin/structural_graph/redaction.py",
      "reason": "library module performing path normalization and secret redaction for the #227 interchange reader; consumed by the structural_graph package, not a standalone capability."
    },
    {
      "path": "bin/structural_graph/tests/test_redaction.py",
      "reason": "unit tests for structural_graph.redaction; test infrastructure, not a capability an agent invokes."
    },
```

- [ ] **Step 7: Verify the gate accepts the exemption**

Run: `git add -A && make check`
Expected: `All checks passed.` — in particular `private info: ✓ self-test passes; no private info in tracked files`. If the private-info check fails naming `redaction.py`, the `SKIP_FILES` entry is wrong; fix it rather than weakening the pattern.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(#227): path normalization and secret redaction

Adds structural_graph.redaction, the build gap the design spec identifies:
nothing in bin/ previously relativized a path or scrubbed a secret.

normalize_path refuses absolute, drive-letter, traversal, query-string, and
out-of-root paths rather than guessing. redact scrubs incidental strings and
returns pattern names only, never matched text, so findings cannot carry a
secret.

The module encodes the same home-directory pattern the private-info scanner
hunts for, so it takes a skip-list entry and a gitleaks allowlist path --
the same self-exemption those two files already hold."
```

---

### Task 3: Structural validation

**Files:**
- Create: `bin/structural_graph/validation.py`
- Test: `bin/structural_graph/tests/test_validation.py`
- Modify: `capabilities.json`

**Interfaces:**
- Consumes: `schema.SYMBOL_KINDS`, `schema.EDGE_TYPES`, `schema.CAPABILITIES`, `schema.COVERAGE_STATUSES`, `schema.SUPPORTED_SCHEMA_VERSIONS`.
- Produces: `validation.FINDING_CODES` (tuple of str); `validation.finding(code, message, index, field)` → dict; `validation.validate_document(doc)` → list of findings in deterministic order.

`validate_document` checks shape and vocabulary membership only. Coverage tiling is Task 4; binding membership, freshness, and redaction are Task 5. Keeping them apart is what makes each independently testable.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_validation.py`:

```python
"""Unit tests for structural_graph.validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import validation


def minimal_document():
    """A structurally valid document, used as the base for mutation."""
    return {
        "schema_version": 1,
        "binding_id": "repository-binding:" + "0" * 31 + "1",
        "source_commit": "a" * 40,
        "provider": {"name": "reference-json", "version": "1.0.0"},
        "capabilities": ["contains"],
        "root": "",
        "coverage": [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ],
        "files": [{"path": "src/app.py"}],
        "symbols": [
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"}
        ],
        "edges": [],
    }


def codes(findings):
    return [f["code"] for f in findings]


class TestValidDocument(unittest.TestCase):
    def test_minimal_document_has_no_findings(self):
        self.assertEqual(validation.validate_document(minimal_document()), [])


class TestFindingShape(unittest.TestCase):
    def test_finding_has_exactly_the_house_keys(self):
        doc = minimal_document()
        del doc["source_commit"]
        found = validation.validate_document(doc)[0]
        self.assertEqual(
            sorted(found.keys()), ["code", "field", "index", "message"]
        )

    def test_no_finding_carries_a_value_key(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "wildly-invalid"
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)

    def test_every_emitted_code_is_registered(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "nope"
        doc["edges"] = [{"type": "nope", "source": "sym-1", "target": "sym-2"}]
        for found in validation.validate_document(doc):
            self.assertIn(found["code"], validation.FINDING_CODES)


class TestShapeFindings(unittest.TestCase):
    def test_missing_schema_version(self):
        doc = minimal_document()
        del doc["schema_version"]
        self.assertIn("E_SG_MISSING_SCHEMA_VERSION", codes(validation.validate_document(doc)))

    def test_unsupported_schema_version(self):
        doc = minimal_document()
        doc["schema_version"] = 99
        self.assertIn(
            "E_SG_UNSUPPORTED_SCHEMA_VERSION", codes(validation.validate_document(doc))
        )

    def test_missing_required_field(self):
        doc = minimal_document()
        del doc["binding_id"]
        self.assertIn("E_SG_MISSING_FIELD", codes(validation.validate_document(doc)))

    def test_unknown_top_level_field_rejected(self):
        doc = minimal_document()
        doc["surprise"] = True
        self.assertIn("E_SG_UNKNOWN_FIELD", codes(validation.validate_document(doc)))

    def test_malformed_commit(self):
        doc = minimal_document()
        doc["source_commit"] = "not-a-sha"
        self.assertIn("E_SG_MALFORMED_COMMIT", codes(validation.validate_document(doc)))


class TestVocabularyFindings(unittest.TestCase):
    def test_unknown_symbol_kind(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "gadget"
        self.assertIn(
            "E_SG_UNKNOWN_SYMBOL_KIND", codes(validation.validate_document(doc))
        )

    def test_unknown_edge_type(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "teleports", "source": "sym-1", "target": "sym-1"}]
        self.assertIn("E_SG_UNKNOWN_EDGE_TYPE", codes(validation.validate_document(doc)))

    def test_unknown_capability(self):
        doc = minimal_document()
        doc["capabilities"] = ["telepathy"]
        self.assertIn("E_SG_UNKNOWN_CAPABILITY", codes(validation.validate_document(doc)))

    def test_unknown_coverage_status(self):
        doc = minimal_document()
        doc["coverage"][0]["status"] = "vibes"
        self.assertIn(
            "E_SG_UNKNOWN_COVERAGE_STATUS", codes(validation.validate_document(doc))
        )


class TestReferentialFindings(unittest.TestCase):
    def test_duplicate_symbol_id(self):
        doc = minimal_document()
        doc["symbols"].append(
            {"id": "sym-1", "name": "dup", "kind": "function", "path": "src/app.py"}
        )
        self.assertIn(
            "E_SG_DUPLICATE_SYMBOL_ID", codes(validation.validate_document(doc))
        )

    def test_dangling_edge_endpoint(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": "sym-1", "target": "ghost"}]
        self.assertIn(
            "E_SG_DANGLING_EDGE_ENDPOINT", codes(validation.validate_document(doc))
        )

    def test_coverage_declares_unadvertised_capability(self):
        doc = minimal_document()
        doc["coverage"].append(
            {"path_prefix": "", "capability": "calls", "status": "observed"}
        )
        self.assertIn(
            "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
            codes(validation.validate_document(doc)),
        )


class TestDeterminism(unittest.TestCase):
    def test_findings_are_stable_across_runs(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "gadget"
        doc["capabilities"] = ["telepathy"]
        first = validation.validate_document(doc)
        second = validation.validate_document(doc)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_validation -v`
Expected: FAIL — `ImportError: cannot import name 'validation'`

- [ ] **Step 3: Write minimal implementation**

Create `bin/structural_graph/validation.py`:

```python
"""structural_graph.validation -- hand-rolled structural validation (#227).

Returns finding lists and never raises, matching context_graph.validation.
Findings are {"code", "message", "index", "field"} dicts and never carry the
offending value: a finding that echoed a provider string back would be the
exact leak structural_graph.redaction exists to close.

Scope is shape and vocabulary membership. Coverage tiling lives in
structural_graph.coverage; binding membership, freshness, and redaction live
in structural_graph.document. Finding order is deterministic: checks run in
registration order, and within a check, by object index.
"""

import re

from structural_graph import schema

FINDING_CODES = (
    "E_SG_MISSING_SCHEMA_VERSION",
    "E_SG_UNSUPPORTED_SCHEMA_VERSION",
    "E_SG_MISSING_FIELD",
    "E_SG_UNKNOWN_FIELD",
    "E_SG_MALFORMED_BINDING_ID",
    "E_SG_MALFORMED_COMMIT",
    "E_SG_UNKNOWN_SYMBOL_KIND",
    "E_SG_UNKNOWN_EDGE_TYPE",
    "E_SG_UNKNOWN_CAPABILITY",
    "E_SG_UNKNOWN_COVERAGE_STATUS",
    "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
    "E_SG_DUPLICATE_SYMBOL_ID",
    "E_SG_DANGLING_EDGE_ENDPOINT",
    "E_SG_COVERAGE_GAP",
    "E_SG_COVERAGE_OVERLAP",
    "E_SG_FACT_OUTSIDE_ROOT",
    "E_SG_UNNORMALIZABLE_ANCHOR",
    "E_SG_BINDING_NOT_CONFIGURED",
)

_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "binding_id",
    "source_commit",
    "provider",
    "capabilities",
    "root",
    "coverage",
    "files",
    "symbols",
    "edges",
)

_KNOWN_TOP_LEVEL = _REQUIRED_TOP_LEVEL + ("optional_provider_observations", "diagnostics")

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def finding(code, message, index, field):
    """Build a house-shaped finding. Never accepts or stores a value."""
    return {"code": code, "message": message, "index": index, "field": field}


def version_findings(doc):
    """Return version-gate findings only. Public on purpose.

    structural_graph.document needs this standalone: the version gate must
    short-circuit before full validation runs, because a document from an
    unknown schema version cannot be meaningfully checked against v1 rules.
    validate_document calls it too, so the rule lives in exactly one place.
    """
    out = []
    if "schema_version" not in doc:
        out.append(
            finding(
                "E_SG_MISSING_SCHEMA_VERSION",
                "document has no schema_version",
                None,
                "schema_version",
            )
        )
    elif doc["schema_version"] not in schema.SUPPORTED_SCHEMA_VERSIONS:
        out.append(
            finding(
                "E_SG_UNSUPPORTED_SCHEMA_VERSION",
                "schema_version is outside the supported set",
                None,
                "schema_version",
            )
        )
    return out


def _shape_findings(doc):
    out = []
    for field in _REQUIRED_TOP_LEVEL:
        if field == "schema_version":
            continue
        if field not in doc:
            out.append(
                finding("E_SG_MISSING_FIELD", "required field is absent", None, field)
            )
    for field in sorted(doc):
        if field not in _KNOWN_TOP_LEVEL:
            out.append(
                finding("E_SG_UNKNOWN_FIELD", "unrecognized top-level field", None, field)
            )
    commit = doc.get("source_commit")
    if commit is not None and not (
        isinstance(commit, str) and _COMMIT_RE.match(commit)
    ):
        out.append(
            finding(
                "E_SG_MALFORMED_COMMIT",
                "source_commit is not a 40-character lowercase hex sha",
                None,
                "source_commit",
            )
        )
    return out


def _vocabulary_findings(doc):
    out = []
    for index, capability in enumerate(doc.get("capabilities") or []):
        if capability not in schema.CAPABILITIES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_CAPABILITY",
                    "capability is not in the normalized vocabulary",
                    index,
                    "capabilities[]",
                )
            )
    for index, symbol in enumerate(doc.get("symbols") or []):
        if symbol.get("kind") not in schema.SYMBOL_KINDS:
            out.append(
                finding(
                    "E_SG_UNKNOWN_SYMBOL_KIND",
                    "symbol kind is not in the normalized vocabulary",
                    index,
                    "symbols[].kind",
                )
            )
    for index, edge in enumerate(doc.get("edges") or []):
        if edge.get("type") not in schema.EDGE_TYPES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_EDGE_TYPE",
                    "edge type is not in the normalized vocabulary",
                    index,
                    "edges[].type",
                )
            )
    declared = set(doc.get("capabilities") or [])
    for index, entry in enumerate(doc.get("coverage") or []):
        if entry.get("status") not in schema.COVERAGE_STATUSES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_COVERAGE_STATUS",
                    "coverage status is not in the normalized vocabulary",
                    index,
                    "coverage[].status",
                )
            )
        if entry.get("capability") not in declared:
            out.append(
                finding(
                    "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
                    "coverage declares a capability the provider did not advertise",
                    index,
                    "coverage[].capability",
                )
            )
    return out


def _referential_findings(doc):
    out = []
    seen = set()
    for index, symbol in enumerate(doc.get("symbols") or []):
        symbol_id = symbol.get("id")
        if symbol_id in seen:
            out.append(
                finding(
                    "E_SG_DUPLICATE_SYMBOL_ID",
                    "symbol id appears more than once",
                    index,
                    "symbols[].id",
                )
            )
        seen.add(symbol_id)
    for index, edge in enumerate(doc.get("edges") or []):
        for field in ("source", "target"):
            if edge.get(field) not in seen:
                out.append(
                    finding(
                        "E_SG_DANGLING_EDGE_ENDPOINT",
                        "edge endpoint names no symbol in this document",
                        index,
                        "edges[]." + field,
                    )
                )
    return out


def validate_document(doc):
    """Return findings for a parsed document. [] means structurally valid."""
    if not isinstance(doc, dict):
        return [
            finding(
                "E_SG_MISSING_FIELD", "document is not a JSON object", None, None
            )
        ]
    out = []
    out.extend(version_findings(doc))
    out.extend(_shape_findings(doc))
    out.extend(_vocabulary_findings(doc))
    out.extend(_referential_findings(doc))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 45 tests, `OK`

- [ ] **Step 5: Add ledger entries and commit**

Append the two `not_a_capability` entries for `validation.py` and `test_validation.py` following the wording pattern from Task 2, then:

```bash
git add -A && make check && bash bin/test-structural-graph.sh
git commit -m "feat(#227): hand-rolled structural validation

Adds structural_graph.validation with the E_SG_* finding-code registry and
shape, vocabulary, and referential checks. Returns finding lists and never
raises; findings carry code/message/index/field only, never the offending
value."
```

---

### Task 4: Coverage tiling

**Files:**
- Create: `bin/structural_graph/coverage.py`
- Test: `bin/structural_graph/tests/test_coverage.py`
- Modify: `capabilities.json`

**Interfaces:**
- Consumes: `validation.finding`.
- Produces: `coverage.tiling_findings(root, capabilities, entries)` → list of findings; `coverage.status_for(entries, capability, path)` → status str or `None`.

**Container shapes are already guaranteed here.** `document.py` runs
`validate_document` first and returns `malformed` on any
`E_SG_MALFORMED_FIELD_SHAPE`, so by the time this module sees `entries` it is
a list of dicts. Do not re-guard element types — that check belongs in
`validation.py` and duplicating it would put the same rule in two places.

**Tiling is realized as root-anchored longest-prefix override.** Exhaustively tiling an unknown filesystem is not decidable from a document alone, so tiling means: for each advertised capability there is **exactly one** entry at `root`, plus zero or more strictly-nested entries with distinct prefixes. The root entry covers everything not otherwise claimed, which makes gaps structurally impossible; a duplicate prefix for one capability is the overlap case. `status_for` resolves by longest matching prefix.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_coverage.py`:

```python
"""Unit tests for structural_graph.coverage."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import coverage


def codes(findings):
    return [f["code"] for f in findings]


class TestTilingFindings(unittest.TestCase):
    def test_single_root_entry_per_capability_tiles(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "calls", "status": "unsupported"},
        ]
        self.assertEqual(
            coverage.tiling_findings("", ["contains", "calls"], entries), []
        )

    def test_nested_override_is_allowed(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {
                "path_prefix": "vendor",
                "capability": "contains",
                "status": "partial_parse_failure",
            },
        ]
        self.assertEqual(coverage.tiling_findings("", ["contains"], entries), [])

    def test_missing_root_entry_is_a_gap(self):
        entries = [
            {"path_prefix": "src", "capability": "contains", "status": "observed"}
        ]
        self.assertIn(
            "E_SG_COVERAGE_GAP",
            codes(coverage.tiling_findings("", ["contains"], entries)),
        )

    def test_capability_with_no_entry_at_all_is_a_gap(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ]
        self.assertIn(
            "E_SG_COVERAGE_GAP",
            codes(coverage.tiling_findings("", ["contains", "calls"], entries)),
        )

    def test_duplicate_prefix_for_one_capability_is_an_overlap(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "contains", "status": "unsupported"},
        ]
        self.assertIn(
            "E_SG_COVERAGE_OVERLAP",
            codes(coverage.tiling_findings("", ["contains"], entries)),
        )

    def test_same_prefix_for_different_capabilities_is_not_an_overlap(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "calls", "status": "observed"},
            {"path_prefix": "vendor", "capability": "contains", "status": "unsupported"},
            {"path_prefix": "vendor", "capability": "calls", "status": "unsupported"},
        ]
        self.assertEqual(
            coverage.tiling_findings("", ["contains", "calls"], entries), []
        )

    def test_entry_outside_root_is_a_gap(self):
        entries = [
            {"path_prefix": "pkg", "capability": "contains", "status": "observed"},
            {"path_prefix": "other", "capability": "contains", "status": "observed"},
        ]
        self.assertIn(
            "E_SG_COVERAGE_GAP",
            codes(coverage.tiling_findings("pkg", ["contains"], entries)),
        )

    def test_nonempty_root_tiles_from_its_own_prefix(self):
        entries = [
            {"path_prefix": "pkg", "capability": "contains", "status": "observed"}
        ]
        self.assertEqual(coverage.tiling_findings("pkg", ["contains"], entries), [])


class TestStatusFor(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {
                "path_prefix": "vendor",
                "capability": "contains",
                "status": "partial_parse_failure",
            },
            {
                "path_prefix": "vendor/deep",
                "capability": "contains",
                "status": "unsupported",
            },
        ]

    def test_root_status_applies_by_default(self):
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "src/app.py"), "observed"
        )

    def test_longest_prefix_wins(self):
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "vendor/lib.py"),
            "partial_parse_failure",
        )
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "vendor/deep/x.py"),
            "unsupported",
        )

    def test_prefix_matches_on_segment_boundary_only(self):
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "vendorish/x.py"),
            "observed",
        )

    def test_undeclared_capability_is_none_not_a_status(self):
        self.assertIsNone(coverage.status_for(self.entries, "calls", "src/app.py"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_coverage -v`
Expected: FAIL — `ImportError: cannot import name 'coverage'`

- [ ] **Step 3: Write minimal implementation**

Create `bin/structural_graph/coverage.py`:

```python
"""structural_graph.coverage -- coverage tiling and status lookup (#227).

Coverage is declared per (path_prefix, capability). Tiling is what makes
"unsupported" structurally distinct from "observed to be zero": a subtree a
provider could not parse must say so, and no path may fall outside every
entry.

Exhaustively tiling an unknown filesystem is not decidable from a document
alone, so tiling is realized as root-anchored longest-prefix override:
exactly one entry at root per advertised capability, plus zero or more
strictly-nested entries with distinct prefixes. The root entry covers
everything not otherwise claimed, so a gap is impossible by construction and
a repeated prefix within one capability is the overlap case.
"""

from structural_graph import validation


def _within(path, prefix):
    """True when path is prefix or lies under it on a segment boundary."""
    if prefix == "":
        return True
    return path == prefix or path.startswith(prefix + "/")


def tiling_findings(root, capabilities, entries):
    """Return findings for coverage that fails to tile root."""
    out = []
    entries = entries or []
    for capability in sorted(set(capabilities or [])):
        prefixes = [
            entry.get("path_prefix")
            for entry in entries
            if entry.get("capability") == capability
        ]
        if root not in prefixes:
            out.append(
                validation.finding(
                    "E_SG_COVERAGE_GAP",
                    "capability has no coverage entry at the document root",
                    None,
                    "coverage[].capability",
                )
            )
        seen = set()
        for index, entry in enumerate(entries):
            if entry.get("capability") != capability:
                continue
            prefix = entry.get("path_prefix")
            if prefix in seen:
                out.append(
                    validation.finding(
                        "E_SG_COVERAGE_OVERLAP",
                        "capability has more than one entry at the same prefix",
                        index,
                        "coverage[].path_prefix",
                    )
                )
            seen.add(prefix)
            if not _within(prefix, root):
                out.append(
                    validation.finding(
                        "E_SG_COVERAGE_GAP",
                        "coverage entry lies outside the document root",
                        index,
                        "coverage[].path_prefix",
                    )
                )
    return out


def status_for(entries, capability, path):
    """Return the coverage status for path under capability.

    Resolves by longest matching prefix. Returns None when the capability has
    no coverage at all -- the caller must treat that as unknown, never as an
    observed zero.
    """
    best_prefix = None
    best_status = None
    for entry in entries or []:
        if entry.get("capability") != capability:
            continue
        prefix = entry.get("path_prefix")
        if not _within(path, prefix):
            continue
        if best_prefix is None or len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_status = entry.get("status")
    return best_status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 57 tests, `OK`

- [ ] **Step 5: Add ledger entries and commit**

```bash
git add -A && make check && bash bin/test-structural-graph.sh
git commit -m "feat(#227): coverage tiling and longest-prefix status lookup

Realizes the design spec's tiling requirement as root-anchored longest-prefix
override: exactly one entry per advertised capability at root, plus strictly
nested overrides. Gaps become structurally impossible and an unsupported
subtree can never read as an observed zero."
```

---

### Task 5: Single-document load

**Files:**
- Create: `bin/structural_graph/document.py`
- Test: `bin/structural_graph/tests/test_document.py`
- Modify: `capabilities.json`

**Interfaces:**
- Consumes: `schema`, `redaction`, `validation`, `coverage`, plus `context_graph.ids.parse_typed_id` and a project config dict shaped like `context_graph.config`'s (`{"repositories": [{"binding_id", "local_checkout_path", ...}]}`).
- Produces: `document.load(path, cfg)` → result dict `{"status", "freshness", "findings", "facts"}`; `document.load_object(doc, cfg)` → same, for an already-parsed document.

The pipeline order is contractual: fail-closed precedes everything.

**That ordering is also what makes the anchor and redaction passes safe.**
`validate_document` runs before them and returns `malformed` on any
`E_SG_MALFORMED_FIELD_SHAPE`, so `_anchor_findings` can assume `files`,
`symbols`, `edges`, and `coverage` are lists of dicts. Do not re-guard element
types here — that rule lives in `validation.py`.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_document.py`:

```python
"""Unit tests for structural_graph.document."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import document

BINDING = "repository-binding:" + "0" * 31 + "1"
OTHER_BINDING = "repository-binding:" + "0" * 31 + "2"


def minimal_document():
    return {
        "schema_version": 1,
        "binding_id": BINDING,
        "source_commit": "a" * 40,
        "provider": {"name": "reference-json", "version": "1.0.0"},
        "capabilities": ["contains"],
        "root": "",
        "coverage": [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ],
        "files": [{"path": "src/app.py"}],
        "symbols": [
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"}
        ],
        "edges": [],
    }


def config(checkout=None):
    repo = {"alias": "main", "binding_id": BINDING, "provider": "github"}
    if checkout:
        repo["local_checkout_path"] = checkout
    return {"schema_version": 1, "repositories": [repo]}


class TestFailClosedOrder(unittest.TestCase):
    def test_unsupported_version_short_circuits_all_other_checks(self):
        doc = minimal_document()
        doc["schema_version"] = 99
        doc["symbols"][0]["kind"] = "also-invalid"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "unsupported_version")
        self.assertEqual(
            [f["code"] for f in result["findings"]],
            ["E_SG_UNSUPPORTED_SCHEMA_VERSION"],
        )
        self.assertIsNone(result["facts"])

    def test_structural_violation_is_malformed(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "gadget"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIsNone(result["facts"])


class TestBindingResolution(unittest.TestCase):
    def test_malformed_binding_id_is_malformed(self):
        doc = minimal_document()
        doc["binding_id"] = "not-a-binding"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_BINDING_ID", [f["code"] for f in result["findings"]]
        )

    def test_foreign_binding_id_is_deconfigured(self):
        doc = minimal_document()
        doc["binding_id"] = OTHER_BINDING
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "deconfigured")
        self.assertIn(
            "E_SG_BINDING_NOT_CONFIGURED", [f["code"] for f in result["findings"]]
        )


class TestCoverageIntegration(unittest.TestCase):
    def test_coverage_gap_is_malformed(self):
        doc = minimal_document()
        doc["coverage"] = []
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn("E_SG_COVERAGE_GAP", [f["code"] for f in result["findings"]])


class TestRedactionIntegration(unittest.TestCase):
    def test_unnormalizable_anchor_makes_document_malformed(self):
        doc = minimal_document()
        doc["files"][0]["path"] = "/etc/passwd"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_fact_outside_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = "pkg"
        doc["coverage"] = [
            {"path_prefix": "pkg", "capability": "contains", "status": "observed"}
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )

    def test_incidental_string_is_redacted_and_the_fact_survives(self):
        doc = minimal_document()
        doc["diagnostics"] = [
            {"message": "could not open " + "/Users" + "/jane/repo/x.py"}
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "loaded")
        self.assertNotIn("jane", json.dumps(result["facts"]))
        self.assertIn(
            "[redacted:home-path]", result["facts"]["diagnostics"][0]["message"]
        )
        self.assertEqual(len(result["facts"]["files"]), 1)

    def test_secret_in_a_symbol_name_anchor_is_malformed(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = "ghp_" + "A" * 36
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )

    def test_secret_in_an_edge_endpoint_anchor_is_malformed(self):
        doc = minimal_document()
        doc["symbols"].append(
            {
                "id": "/Users" + "/jane/x",
                "name": "other",
                "kind": "function",
                "path": "src/app.py",
            }
        )
        doc["edges"] = [
            {"type": "calls", "source": "sym-1", "target": "/Users" + "/jane/x"}
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )

    def test_no_finding_carries_an_unredacted_secret(self):
        doc = minimal_document()
        doc["files"][0]["path"] = "/Users" + "/jane/repo/x.py"
        result = document.load_object(doc, config())
        self.assertNotIn("jane", json.dumps(result["findings"]))


class TestFreshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git_repo(self):
        env = dict(os.environ)
        for var in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_COMMON_DIR",
        ):
            env.pop(var, None)
        subprocess.check_call(["git", "-C", self.tmp, "init", "-q"], env=env)
        subprocess.check_call(
            ["git", "-C", self.tmp, "config", "user.email", "t@example.com"], env=env
        )
        subprocess.check_call(
            ["git", "-C", self.tmp, "config", "user.name", "t"], env=env
        )
        open(os.path.join(self.tmp, "f.txt"), "w").write("x\n")
        subprocess.check_call(["git", "-C", self.tmp, "add", "f.txt"], env=env)
        subprocess.check_call(
            ["git", "-C", self.tmp, "commit", "-q", "-m", "init"], env=env
        )
        return subprocess.check_output(
            ["git", "-C", self.tmp, "rev-parse", "HEAD"], env=env
        ).decode().strip()

    def test_no_checkout_is_freshness_unknown(self):
        result = document.load_object(minimal_document(), config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["freshness"], "freshness_unknown")

    def test_matching_commit_is_current(self):
        head = self._git_repo()
        doc = minimal_document()
        doc["source_commit"] = head
        result = document.load_object(doc, config(checkout=self.tmp))
        self.assertEqual(result["freshness"], "current")

    def test_differing_commit_is_stale_but_still_loads(self):
        self._git_repo()
        doc = minimal_document()
        doc["source_commit"] = "b" * 40
        result = document.load_object(doc, config(checkout=self.tmp))
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["freshness"], "stale")
        self.assertIsNotNone(result["facts"])


class TestFileLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absent_file_is_unavailable(self):
        result = document.load(os.path.join(self.tmp, "nope.json"), config())
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["facts"])

    def test_unparseable_file_is_malformed(self):
        path = os.path.join(self.tmp, "bad.json")
        open(path, "w").write("{not json")
        result = document.load(path, config())
        self.assertEqual(result["status"], "malformed")

    def test_valid_file_loads(self):
        path = os.path.join(self.tmp, "good.json")
        open(path, "w").write(json.dumps(minimal_document()))
        result = document.load(path, config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["facts"]["binding_id"], BINDING)

    def test_load_writes_nothing(self):
        path = os.path.join(self.tmp, "good.json")
        open(path, "w").write(json.dumps(minimal_document()))
        before = sorted(os.listdir(self.tmp))
        document.load(path, config())
        self.assertEqual(sorted(os.listdir(self.tmp)), before)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_document -v`
Expected: FAIL — `ImportError: cannot import name 'document'`

- [ ] **Step 3: Write minimal implementation**

Create `bin/structural_graph/document.py`:

```python
"""structural_graph.document -- single-document load for the #227 interchange.

Runs a parsed document through a fixed pipeline and returns one explicit
state. The order is contractual: fail-closed precedes everything, because a
document from an unknown schema version cannot be meaningfully validated
against v1 rules and continuing would turn fail-closed into best-effort.

Load outcome and freshness are orthogonal. A stale document still loads --
FC-4 requires an outage to carry forward rather than delete -- so freshness
is a separate key, not a member of the status enum.

This module writes nothing. It reads the document and, when a checkout is
configured, git HEAD. No network access.
"""

import json
import os
import subprocess

from context_graph import ids
from structural_graph import coverage
from structural_graph import redaction
from structural_graph import schema
from structural_graph import validation


def _result(status, freshness, findings, facts):
    return {
        "status": status,
        "freshness": freshness,
        "findings": findings,
        "facts": facts,
    }


def _git_head(checkout):
    """Return HEAD at checkout, or None when it cannot be determined."""
    env = dict(os.environ)
    for var in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR",
    ):
        env.pop(var, None)
    try:
        out = subprocess.check_output(
            ["git", "-C", checkout, "rev-parse", "HEAD"],
            env=env,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.decode("utf-8").strip()


def _find_binding(cfg, binding_id):
    for repo in (cfg or {}).get("repositories") or []:
        if repo.get("binding_id") == binding_id:
            return repo
    return None


def _anchor_findings(doc):
    """Findings for anchors that cannot be normalized within the root."""
    out = []
    root = doc.get("root") or ""
    if redaction.normalize_path(root, "") is None and root != "":
        out.append(
            validation.finding(
                "E_SG_UNNORMALIZABLE_ANCHOR",
                "document root is not a safe repository-relative path",
                None,
                "root",
            )
        )
        return out
    checks = (
        ("files", "path", "files[].path"),
        ("symbols", "path", "symbols[].path"),
    )
    for collection, key, field in checks:
        for index, item in enumerate(doc.get(collection) or []):
            if redaction.normalize_path(item.get(key), root) is None:
                out.append(
                    validation.finding(
                        "E_SG_UNNORMALIZABLE_ANCHOR",
                        "anchor is not a safe repository-relative path within root",
                        index,
                        field,
                    )
                )
    for index, entry in enumerate(doc.get("coverage") or []):
        prefix = entry.get("path_prefix")
        if prefix == root:
            continue
        if redaction.normalize_path(prefix, root) is None:
            out.append(
                validation.finding(
                    "E_SG_UNNORMALIZABLE_ANCHOR",
                    "coverage prefix is not a safe path within root",
                    index,
                    "coverage[].path_prefix",
                )
            )
    # Anchors are exempt from redaction -- rewriting a symbol id would break
    # the edges that reference it. So a non-path anchor carrying a secret has
    # no safe outcome and fails the document closed instead.
    for collection, key, field in (
        ("symbols", "id", "symbols[].id"),
        ("symbols", "name", "symbols[].name"),
    ):
        for index, item in enumerate(doc.get(collection) or []):
            scrubbed, names = redaction.redact(item.get(key))
            if names:
                out.append(
                    validation.finding(
                        "E_SG_UNNORMALIZABLE_ANCHOR",
                        "anchor matches a secret pattern and cannot be redacted",
                        index,
                        field,
                    )
                )
    for index, edge in enumerate(doc.get("edges") or []):
        for key in ("source", "target"):
            scrubbed, names = redaction.redact(edge.get(key))
            if names:
                out.append(
                    validation.finding(
                        "E_SG_UNNORMALIZABLE_ANCHOR",
                        "anchor matches a secret pattern and cannot be redacted",
                        index,
                        "edges[]." + key,
                    )
                )
    return out


def _redact_incidental(doc):
    """Return a copy of doc with every non-anchor string redacted."""
    def walk(node, path):
        if isinstance(node, dict):
            return dict((k, walk(v, path + [k])) for k, v in node.items())
        if isinstance(node, list):
            return [walk(v, path + ["[]"]) for v in node]
        if isinstance(node, str):
            field = ".".join(path).replace(".[]", "[]")
            if schema.is_anchor(field):
                return node
            scrubbed, _ = redaction.redact(node)
            return scrubbed
        return node

    return walk(doc, [])


def load_object(doc, cfg):
    """Load an already-parsed document. Returns a result dict."""
    gate = validation.version_findings(doc if isinstance(doc, dict) else {})
    for found in gate:
        if found["code"] in (
            "E_SG_MISSING_SCHEMA_VERSION",
            "E_SG_UNSUPPORTED_SCHEMA_VERSION",
        ):
            return _result("unsupported_version", "freshness_unknown", [found], None)

    findings = validation.validate_document(doc)
    if findings:
        return _result("malformed", "freshness_unknown", findings, None)

    binding_id = doc.get("binding_id")
    try:
        parsed = ids.parse_typed_id(binding_id)
        shape_ok = parsed.get("type") == "repository_binding"
    except ids.MalformedIdError:
        shape_ok = False
    if not shape_ok:
        return _result(
            "malformed",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_MALFORMED_BINDING_ID",
                    "binding_id is not a well-formed repository-binding id",
                    None,
                    "binding_id",
                )
            ],
            None,
        )

    repo = _find_binding(cfg, binding_id)
    if repo is None:
        return _result(
            "deconfigured",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_BINDING_NOT_CONFIGURED",
                    "binding_id is not among the project's configured bindings",
                    None,
                    "binding_id",
                )
            ],
            None,
        )

    tiling = coverage.tiling_findings(
        doc.get("root") or "", doc.get("capabilities") or [], doc.get("coverage") or []
    )
    if tiling:
        return _result("malformed", "freshness_unknown", tiling, None)

    anchors = _anchor_findings(doc)
    if anchors:
        return _result("malformed", "freshness_unknown", anchors, None)

    facts = _redact_incidental(doc)

    checkout = repo.get("local_checkout_path")
    if not checkout:
        freshness = "freshness_unknown"
    else:
        head = _git_head(checkout)
        if head is None:
            freshness = "freshness_unknown"
        elif head == doc.get("source_commit"):
            freshness = "current"
        else:
            freshness = "stale"

    return _result("loaded", freshness, [], facts)


def load(path, cfg):
    """Load a document from disk. Never writes."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except FileNotFoundError:
        return _result(
            "unavailable",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_MISSING_FIELD", "document is not present", None, None
                )
            ],
            None,
        )
    except (ValueError, OSError):
        return _result(
            "malformed",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_MISSING_FIELD", "document is not readable JSON", None, None
                )
            ],
            None,
        )
    return load_object(doc, cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 76 tests, `OK`

- [ ] **Step 5: Add ledger entries and commit**

```bash
git add -A && make check && bash bin/test-structural-graph.sh
git commit -m "feat(#227): single-document load pipeline

Adds structural_graph.document with the contractual fail-closed pipeline:
version gate short-circuits, then structure, binding shape and membership,
coverage tiling, anchor normalization, redaction, freshness.

Load outcome and freshness are orthogonal keys so a stale document still
loads, per FC-4's carry-forward requirement. The module writes nothing."
```

---

### Task 6: Multi-document set load and aggregation

**Files:**
- Create: `bin/structural_graph/graphset.py`
- Test: `bin/structural_graph/tests/test_graphset.py`
- Modify: `capabilities.json`

**Interfaces:**
- Consumes: `document.load`, `coverage.status_for`.
- Produces: `graphset.load_set(cfg, paths_by_binding)` → `{"bindings": {...}, "facts": {...}, "findings": [...]}`; `graphset.aggregate_coverage(result, capability, path)` → `"observed"`, `"partial"`, or `"unknown"`.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_graphset.py`:

```python
"""Unit tests for structural_graph.graphset."""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import graphset

BINDING_A = "repository-binding:" + "0" * 31 + "1"
BINDING_B = "repository-binding:" + "0" * 31 + "2"


def doc_for(binding_id, capability="contains", status="observed"):
    return {
        "schema_version": 1,
        "binding_id": binding_id,
        "source_commit": "a" * 40,
        "provider": {"name": "reference-json", "version": "1.0.0"},
        "capabilities": [capability],
        "root": "",
        "coverage": [
            {"path_prefix": "", "capability": capability, "status": status}
        ],
        "files": [{"path": "src/app.py"}],
        "symbols": [
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"}
        ],
        "edges": [],
    }


def config():
    return {
        "schema_version": 1,
        "repositories": [
            {"alias": "a", "binding_id": BINDING_A, "provider": "github"},
            {"alias": "b", "binding_id": BINDING_B, "provider": "github"},
        ],
    }


class TestSetLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, doc):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc))
        return path

    def test_both_bindings_load(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_A]["status"], "loaded")
        self.assertEqual(result["bindings"][BINDING_B]["status"], "loaded")

    def test_same_path_in_two_bindings_stays_distinct(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertIn(BINDING_A + "::src/app.py", result["facts"]["files"])
        self.assertIn(BINDING_B + "::src/app.py", result["facts"]["files"])
        self.assertEqual(len(result["facts"]["files"]), 2)

    def test_same_symbol_id_in_two_bindings_stays_distinct(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(len(result["facts"]["symbols"]), 2)

    def test_one_binding_unavailable_does_not_invalidate_the_other(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: os.path.join(self.tmp, "missing.json"),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_A]["status"], "loaded")
        self.assertEqual(result["bindings"][BINDING_B]["status"], "unavailable")
        self.assertEqual(len(result["facts"]["files"]), 1)

    def test_configured_binding_with_no_document_is_unavailable(self):
        paths = {BINDING_A: self._write("a.json", doc_for(BINDING_A))}
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_B]["status"], "unavailable")

    def test_results_are_deterministic(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        first = graphset.load_set(config(), paths)
        second = graphset.load_set(config(), paths)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )


class TestAggregateCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, doc):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc))
        return path

    def test_all_observed_aggregates_to_observed(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "observed"
        )

    def test_one_unsupported_degrades_to_partial_never_zero(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write(
                "b.json", doc_for(BINDING_B, status="unsupported")
            ),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "partial"
        )

    def test_one_partial_parse_failure_degrades_to_partial(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write(
                "b.json", doc_for(BINDING_B, status="partial_parse_failure")
            ),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "partial"
        )

    def test_unavailable_binding_degrades_to_partial(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: os.path.join(self.tmp, "missing.json"),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "partial"
        )

    def test_capability_no_binding_declares_is_unknown(self):
        paths = {BINDING_A: self._write("a.json", doc_for(BINDING_A))}
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "calls", "src/app.py"), "unknown"
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_graphset -v`
Expected: FAIL — `ImportError: cannot import name 'graphset'`

- [ ] **Step 3: Write minimal implementation**

Create `bin/structural_graph/graphset.py`:

```python
"""structural_graph.graphset -- multi-document set load (#227).

One interchange document covers exactly one (binding, commit). A project
with several repository bindings therefore has a set of documents, and this
module loads them into one combined fact view.

Paths and symbol ids are binding-qualified as "<binding_id>::<value>" at
load, so an identical path in two repositories can never merge into one
fact. Aggregation propagates unavailable and unsupported as partial or
unknown and never sums them as zero: a capability nobody could observe is
not a capability observed to be empty.

A partial outage is contained. One binding failing to load leaves every
other binding's facts intact, per FC-4.
"""

from structural_graph import coverage
from structural_graph import document


def load_set(cfg, paths_by_binding):
    """Load one document per configured binding into a combined view.

    paths_by_binding maps binding_id -> document path. A configured binding
    with no entry, or whose document is absent, is reported unavailable.
    """
    bindings = {}
    files = {}
    symbols = {}
    edges = []
    findings = []

    configured = [
        repo.get("binding_id") for repo in (cfg or {}).get("repositories") or []
    ]
    for binding_id in sorted(b for b in configured if b):
        path = (paths_by_binding or {}).get(binding_id)
        if not path:
            bindings[binding_id] = {
                "status": "unavailable",
                "freshness": "freshness_unknown",
                "coverage": [],
                "capabilities": [],
            }
            continue
        result = document.load(path, cfg)
        facts = result["facts"] or {}
        bindings[binding_id] = {
            "status": result["status"],
            "freshness": result["freshness"],
            "coverage": facts.get("coverage") or [],
            "capabilities": facts.get("capabilities") or [],
        }
        for found in result["findings"]:
            entry = dict(found)
            entry["binding_id"] = binding_id
            findings.append(entry)
        if result["status"] != "loaded":
            continue
        for item in facts.get("files") or []:
            files[binding_id + "::" + item["path"]] = dict(item, binding_id=binding_id)
        for item in facts.get("symbols") or []:
            symbols[binding_id + "::" + item["id"]] = dict(item, binding_id=binding_id)
        for item in facts.get("edges") or []:
            edges.append(
                dict(
                    item,
                    binding_id=binding_id,
                    source=binding_id + "::" + item["source"],
                    target=binding_id + "::" + item["target"],
                )
            )

    return {
        "bindings": bindings,
        "facts": {"files": files, "symbols": symbols, "edges": edges},
        "findings": findings,
    }


def aggregate_coverage(result, capability, path):
    """Combine per-binding coverage for capability at path.

    Returns "observed" only when every participating binding observed it,
    "partial" when at least one observed and any other did not, and
    "unknown" when no binding could observe it at all. Never returns a
    count, and never treats unavailable as zero.
    """
    observed = 0
    degraded = 0
    for binding_id in sorted(result.get("bindings") or {}):
        info = result["bindings"][binding_id]
        if info["status"] != "loaded":
            degraded += 1
            continue
        if capability not in (info.get("capabilities") or []):
            degraded += 1
            continue
        status = coverage.status_for(info.get("coverage") or [], capability, path)
        if status == "observed":
            observed += 1
        else:
            degraded += 1
    if observed and not degraded:
        return "observed"
    if observed:
        return "partial"
    return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 87 tests, `OK`

- [ ] **Step 5: Add ledger entries and commit**

```bash
git add -A && make check && bash bin/test-structural-graph.sh
git commit -m "feat(#227): multi-document set load and coverage aggregation

Adds structural_graph.graphset. Paths and symbol ids are binding-qualified
at load so cross-repository collisions cannot merge, one binding's outage
leaves the others intact, and aggregation degrades to partial or unknown
rather than ever summing an unavailable capability as zero."
```

---

### Task 7: JSON Schema mirror and invariant coverage

**Files:**
- Create: `schemas/structural-graph/v1/document.schema.json`, `schemas/structural-graph/v1/invariant-coverage.json`
- Test: `bin/structural_graph/tests/test_schema_conformance.py`
- Modify: `capabilities.json`

**Interfaces:**
- Consumes: `schema` vocabularies, `validation.FINDING_CODES`.
- Produces: the schema files, consumed by Task 8's fixture runner and by #231's adapter as the published contract.

- [ ] **Step 1: Write the failing test**

Create `bin/structural_graph/tests/test_schema_conformance.py`:

```python
"""Conformance tests binding the hand-rolled validator to the JSON Schema.

jsonschema is test-only and optional; these tests skip when it is absent and
run under the pre-commit hook, which injects it.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import schema as sg_schema
from structural_graph import validation

try:
    import jsonschema

    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
SCHEMA_DIR = os.path.join(REPO_ROOT, "schemas", "structural-graph", "v1")


def load_json(name):
    with open(os.path.join(SCHEMA_DIR, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


class TestInvariantCoverage(unittest.TestCase):
    def test_every_finding_code_is_classified(self):
        coverage = load_json("invariant-coverage.json")
        classified = set(coverage["codes"])
        self.assertEqual(classified, set(validation.FINDING_CODES))

    def test_every_classification_is_a_known_value(self):
        coverage = load_json("invariant-coverage.json")
        for code, value in coverage["codes"].items():
            self.assertIn(value, ("schema-and-native", "native-only"), code)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestSchemaMirrorsVocabularies(unittest.TestCase):
    def setUp(self):
        self.document_schema = load_json("document.schema.json")

    def test_schema_version_is_pinned(self):
        self.assertEqual(
            self.document_schema["properties"]["schema_version"]["const"],
            sg_schema.SCHEMA_VERSION,
        )

    def test_symbol_kinds_mirror_exactly(self):
        enum = self.document_schema["properties"]["symbols"]["items"]["properties"][
            "kind"
        ]["enum"]
        self.assertEqual(tuple(enum), sg_schema.SYMBOL_KINDS)

    def test_edge_types_mirror_exactly(self):
        enum = self.document_schema["properties"]["edges"]["items"]["properties"][
            "type"
        ]["enum"]
        self.assertEqual(tuple(enum), sg_schema.EDGE_TYPES)

    def test_capabilities_mirror_exactly(self):
        enum = self.document_schema["properties"]["capabilities"]["items"]["enum"]
        self.assertEqual(tuple(enum), sg_schema.CAPABILITIES)

    def test_coverage_statuses_mirror_exactly(self):
        enum = self.document_schema["properties"]["coverage"]["items"]["properties"][
            "status"
        ]["enum"]
        self.assertEqual(tuple(enum), sg_schema.COVERAGE_STATUSES)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestSchemaRejectsWhatNativeRejects(unittest.TestCase):
    def setUp(self):
        self.validator = jsonschema.Draft7Validator(load_json("document.schema.json"))

    def _doc(self):
        return {
            "schema_version": 1,
            "binding_id": "repository-binding:" + "0" * 31 + "1",
            "source_commit": "a" * 40,
            "provider": {"name": "reference-json", "version": "1.0.0"},
            "capabilities": ["contains"],
            "root": "",
            "coverage": [
                {"path_prefix": "", "capability": "contains", "status": "observed"}
            ],
            "files": [{"path": "src/app.py"}],
            "symbols": [
                {
                    "id": "sym-1",
                    "name": "app",
                    "kind": "module",
                    "path": "src/app.py",
                }
            ],
            "edges": [],
        }

    def test_valid_document_passes_schema(self):
        self.assertEqual(list(self.validator.iter_errors(self._doc())), [])

    def test_unknown_symbol_kind_rejected(self):
        doc = self._doc()
        doc["symbols"][0]["kind"] = "gadget"
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_unknown_top_level_field_rejected(self):
        doc = self._doc()
        doc["surprise"] = True
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_malformed_commit_rejected(self):
        doc = self._doc()
        doc["source_commit"] = "nope"
        self.assertTrue(list(self.validator.iter_errors(doc)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest bin.structural_graph.tests.test_schema_conformance -v`
Expected: FAIL — `FileNotFoundError` for `invariant-coverage.json`

- [ ] **Step 3: Write the schema files**

Create `schemas/structural-graph/v1/document.schema.json`. Keep the `enum` arrays byte-identical to the tuples in `schema.py` — the conformance test compares them element by element.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://bindle/schemas/structural-graph/v1/document.schema.json",
  "title": "Structural-graph interchange document",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "binding_id",
    "source_commit",
    "provider",
    "capabilities",
    "root",
    "coverage",
    "files",
    "symbols",
    "edges"
  ],
  "properties": {
    "schema_version": { "const": 1 },
    "binding_id": { "type": "string", "pattern": "^repository-binding:[0-9a-f]{32}$" },
    "source_commit": { "type": "string", "pattern": "^[0-9a-f]{40}$" },
    "root": { "type": "string" },
    "provider": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "version"],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" }
      }
    },
    "capabilities": {
      "type": "array",
      "items": {
        "enum": [
          "contains",
          "imports",
          "depends_on",
          "calls",
          "tests",
          "has_export_visibility"
        ]
      }
    },
    "coverage": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["path_prefix", "capability", "status"],
        "properties": {
          "path_prefix": { "type": "string" },
          "capability": {
            "enum": [
              "contains",
              "imports",
              "depends_on",
              "calls",
              "tests",
              "has_export_visibility"
            ]
          },
          "status": {
            "enum": ["observed", "unsupported", "partial_parse_failure"]
          }
        }
      }
    },
    "files": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["path"],
        "properties": { "path": { "type": "string" } }
      }
    },
    "symbols": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "name", "kind", "path"],
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "path": { "type": "string" },
          "kind": {
            "enum": [
              "module",
              "class",
              "function",
              "method",
              "field",
              "constant",
              "type_alias",
              "interface",
              "other"
            ]
          },
          "is_exported": { "type": "boolean" }
        }
      }
    },
    "edges": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["type", "source", "target"],
        "properties": {
          "type": { "enum": ["contains", "imports", "depends_on", "calls", "tests"] },
          "source": { "type": "string" },
          "target": { "type": "string" }
        }
      }
    },
    "diagnostics": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["message"],
        "properties": { "message": { "type": "string" } }
      }
    },
    "optional_provider_observations": {
      "type": "object",
      "description": "Provider conclusions. Capability-gated hints, never authoritative, never anchors."
    }
  }
}
```

Create `schemas/structural-graph/v1/invariant-coverage.json`. Every code in `validation.FINDING_CODES` must appear exactly once.

```json
{
  "schema_version": 1,
  "description": "Classifies each E_SG_* finding code by whether the JSON Schema can also reject the responsible object, keeping the hand-rolled validator and the schema honest with each other.",
  "codes": {
    "E_SG_MISSING_SCHEMA_VERSION": "schema-and-native",
    "E_SG_UNSUPPORTED_SCHEMA_VERSION": "schema-and-native",
    "E_SG_MISSING_FIELD": "schema-and-native",
    "E_SG_UNKNOWN_FIELD": "schema-and-native",
    "E_SG_MALFORMED_BINDING_ID": "schema-and-native",
    "E_SG_MALFORMED_COMMIT": "schema-and-native",
    "E_SG_MALFORMED_FIELD_SHAPE": "schema-and-native",
    "E_SG_UNKNOWN_SYMBOL_KIND": "schema-and-native",
    "E_SG_UNKNOWN_EDGE_TYPE": "schema-and-native",
    "E_SG_UNKNOWN_CAPABILITY": "schema-and-native",
    "E_SG_UNKNOWN_COVERAGE_STATUS": "schema-and-native",
    "E_SG_COVERAGE_UNDECLARED_CAPABILITY": "native-only",
    "E_SG_DUPLICATE_SYMBOL_ID": "native-only",
    "E_SG_DANGLING_EDGE_ENDPOINT": "native-only",
    "E_SG_COVERAGE_GAP": "native-only",
    "E_SG_COVERAGE_OVERLAP": "native-only",
    "E_SG_FACT_OUTSIDE_ROOT": "native-only",
    "E_SG_UNNORMALIZABLE_ANCHOR": "native-only",
    "E_SG_BINDING_NOT_CONFIGURED": "native-only"
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pip install --quiet jsonschema && python3 -m unittest discover -s bin/structural_graph/tests -t . -v`
Expected: PASS — 96 tests, `OK`. Without `jsonschema` installed, the mirror and rejection classes skip and the invariant-coverage class still runs.

- [ ] **Step 5: Add ledger entry for the test module and commit**

```bash
git add -A && make check && bash bin/test-structural-graph.sh
git commit -m "feat(#227): JSON Schema mirror and invariant-coverage classification

Publishes schemas/structural-graph/v1/. The conformance tests assert the
schema enums mirror schema.py element for element and that every E_SG_* code
is classified, so the hand-rolled validator and the schema cannot drift."
```

---

### Task 8: Fixture corpus and manifest runner

**Files:**
- Create: `bin/check-structural-graph-fixtures.py`, `testdata/structural-graph/v1/manifest.json`, and fixtures under `core/`, `versions/`, `malformed/`, `bindings/`, `coverage/`, `freshness/`
- Modify: `bin/test-structural-graph.sh`, `capabilities.json`

**Interfaces:**
- Consumes: `document.load_object`, `graphset.load_set`.
- Produces: `bin/check-structural-graph-fixtures.py --manifest <path>` exiting 0 on success, non-zero with a per-fixture report on failure.

Fixtures live **exactly one category level deep** — anything nested deeper is invisible to glob-based discovery.

- [ ] **Step 1: Write the failing test — the manifest and first fixtures**

Create `testdata/structural-graph/v1/core/01-minimal.json`:

```json
{
  "schema_version": 1,
  "binding_id": "repository-binding:00000000000000000000000000000001",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider": { "name": "reference-json", "version": "1.0.0" },
  "capabilities": ["contains"],
  "root": "",
  "coverage": [
    { "path_prefix": "", "capability": "contains", "status": "observed" }
  ],
  "files": [{ "path": "src/app.py" }],
  "symbols": [
    { "id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py" }
  ],
  "edges": []
}
```

Create `testdata/structural-graph/v1/versions/10-unsupported-version.json` — the same document with `"schema_version": 99` and a deliberately invalid symbol kind, proving the version gate short-circuits:

```json
{
  "schema_version": 99,
  "binding_id": "repository-binding:00000000000000000000000000000001",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider": { "name": "reference-json", "version": "1.0.0" },
  "capabilities": ["contains"],
  "root": "",
  "coverage": [
    { "path_prefix": "", "capability": "contains", "status": "observed" }
  ],
  "files": [{ "path": "src/app.py" }],
  "symbols": [
    { "id": "sym-1", "name": "app", "kind": "gadget", "path": "src/app.py" }
  ],
  "edges": []
}
```

Create `testdata/structural-graph/v1/coverage/30-gap-missing-root.json` — coverage that never tiles the root:

```json
{
  "schema_version": 1,
  "binding_id": "repository-binding:00000000000000000000000000000001",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider": { "name": "reference-json", "version": "1.0.0" },
  "capabilities": ["contains"],
  "root": "",
  "coverage": [
    { "path_prefix": "src", "capability": "contains", "status": "observed" }
  ],
  "files": [{ "path": "src/app.py" }],
  "symbols": [
    { "id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py" }
  ],
  "edges": []
}
```

Create `testdata/structural-graph/v1/manifest.json`:

```json
{
  "schema_version": 1,
  "config": {
    "schema_version": 1,
    "repositories": [
      {
        "alias": "main",
        "binding_id": "repository-binding:00000000000000000000000000000001",
        "provider": "github"
      },
      {
        "alias": "second",
        "binding_id": "repository-binding:00000000000000000000000000000002",
        "provider": "github"
      }
    ]
  },
  "fixtures": [
    {
      "id": "1",
      "path": "core/01-minimal.json",
      "assertion": "load_status",
      "expect_status": "loaded",
      "expect_freshness": "freshness_unknown",
      "expect_codes": []
    },
    {
      "id": "10",
      "path": "versions/10-unsupported-version.json",
      "assertion": "load_status",
      "expect_status": "unsupported_version",
      "expect_freshness": "freshness_unknown",
      "expect_codes": ["E_SG_UNSUPPORTED_SCHEMA_VERSION"]
    },
    {
      "id": "30",
      "path": "coverage/30-gap-missing-root.json",
      "assertion": "load_status",
      "expect_status": "malformed",
      "expect_freshness": "freshness_unknown",
      "expect_codes": ["E_SG_COVERAGE_GAP"]
    }
  ]
}
```

- [ ] **Step 2: Run the runner to verify it fails**

Run: `python3 bin/check-structural-graph-fixtures.py --manifest testdata/structural-graph/v1/manifest.json`
Expected: FAIL — `python3: can't open file ... check-structural-graph-fixtures.py`

- [ ] **Step 3: Write the runner**

Create `bin/check-structural-graph-fixtures.py` (mode `755`):

```python
#!/usr/bin/env python3
"""Manifest-driven fixture runner for the #227 structural-graph interchange.

Contains no independent copy of validation, coverage, redaction, or load
logic: every assertion runs the real structural_graph modules, so a fixture
can never pass against a reimplementation that drifted from the library.

Mirrors bin/check-context-graph-fixtures.py in shape and exit contract.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from structural_graph import document
from structural_graph import graphset


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def assert_load_status(fixture, base, config):
    doc = load_json(os.path.join(base, fixture["path"]))
    result = document.load_object(doc, config)
    problems = []
    if result["status"] != fixture["expect_status"]:
        problems.append(
            "status %s, expected %s" % (result["status"], fixture["expect_status"])
        )
    expected_freshness = fixture.get("expect_freshness")
    if expected_freshness and result["freshness"] != expected_freshness:
        problems.append(
            "freshness %s, expected %s" % (result["freshness"], expected_freshness)
        )
    actual = sorted(set(f["code"] for f in result["findings"]))
    expected = sorted(set(fixture.get("expect_codes") or []))
    if actual != expected:
        problems.append("codes %s, expected %s" % (actual, expected))
    return problems


def assert_set_load(fixture, base, config):
    paths = dict(
        (binding, os.path.join(base, rel))
        for binding, rel in fixture["documents"].items()
    )
    result = graphset.load_set(config, paths)
    problems = []
    for binding, expected in (fixture.get("expect_binding_status") or {}).items():
        actual = result["bindings"].get(binding, {}).get("status")
        if actual != expected:
            problems.append(
                "binding %s status %s, expected %s" % (binding, actual, expected)
            )
    expected_files = fixture.get("expect_file_count")
    if expected_files is not None and len(result["facts"]["files"]) != expected_files:
        problems.append(
            "file count %d, expected %d"
            % (len(result["facts"]["files"]), expected_files)
        )
    return problems


def assert_aggregate_coverage(fixture, base, config):
    paths = dict(
        (binding, os.path.join(base, rel))
        for binding, rel in fixture["documents"].items()
    )
    result = graphset.load_set(config, paths)
    actual = graphset.aggregate_coverage(
        result, fixture["capability"], fixture["query_path"]
    )
    if actual != fixture["expect_aggregate"]:
        return ["aggregate %s, expected %s" % (actual, fixture["expect_aggregate"])]
    return []


ASSERTIONS = {
    "load_status": assert_load_status,
    "set_load": assert_set_load,
    "aggregate_coverage": assert_aggregate_coverage,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(args.manifest))
    manifest = load_json(args.manifest)
    config = manifest["config"]

    seen = set()
    failures = 0
    for fixture in manifest["fixtures"]:
        fixture_id = fixture["id"]
        if fixture_id in seen:
            print("  ✗ duplicate fixture id %s" % fixture_id)
            failures += 1
            continue
        seen.add(fixture_id)
        handler = ASSERTIONS.get(fixture["assertion"])
        if handler is None:
            print("  ✗ %s: unknown assertion %s" % (fixture_id, fixture["assertion"]))
            failures += 1
            continue
        problems = handler(fixture, base, config)
        if problems:
            failures += 1
            print("  ✗ %s (%s)" % (fixture_id, fixture["path"] if "path" in fixture else fixture["assertion"]))
            for problem in problems:
                print("      %s" % problem)

    total = len(manifest["fixtures"])
    if failures:
        print("fixtures: %d of %d failed" % (failures, total))
        return 1
    print("fixtures: all %d passed" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the runner to verify it passes**

Run: `python3 bin/check-structural-graph-fixtures.py --manifest testdata/structural-graph/v1/manifest.json`
Expected: `fixtures: all 3 passed`, exit 0

- [ ] **Step 5: Add the remaining fixtures**

Add these to `testdata/structural-graph/v1/` and register each in the manifest. Reuse `core/01-minimal.json` as the base document for each, changing only the field under test.

| Path | Change from base | Manifest assertion |
|---|---|---|
| `malformed/20-unknown-symbol-kind.json` | `symbols[0].kind` → `"gadget"` | `load_status`, `malformed`, `["E_SG_UNKNOWN_SYMBOL_KIND"]` |
| `malformed/21-dangling-edge.json` | `edges` → one `calls` edge to `"ghost"` | `load_status`, `malformed`, `["E_SG_DANGLING_EDGE_ENDPOINT"]` |
| `malformed/22-unknown-field.json` | add `"surprise": true` | `load_status`, `malformed`, `["E_SG_UNKNOWN_FIELD"]` |
| `bindings/40-foreign-binding.json` | `binding_id` → `repository-binding:` + 31 zeros + `9` | `load_status`, `deconfigured`, `["E_SG_BINDING_NOT_CONFIGURED"]` |
| `bindings/41-second-binding.json` | `binding_id` → `...0002`, same paths and symbol ids as base | used by set fixtures below |
| `coverage/31-overlap-duplicate-prefix.json` | two `contains` entries both at `""` | `load_status`, `malformed`, `["E_SG_COVERAGE_OVERLAP"]` |
| `coverage/32-partial-parse-failure.json` | add `{"path_prefix": "vendor", "capability": "contains", "status": "partial_parse_failure"}` | `load_status`, `loaded`, `[]` |
| `coverage/33-unsupported-capability.json` | `capabilities` → `["contains","calls"]`, coverage adds `calls` at `""` with `"unsupported"` | `load_status`, `loaded`, `[]` |
| `freshness/50-absent-document.json` | *no file created* — manifest points at a path that does not exist | `load_status`, `unavailable` |

Then add the multi-binding assertions to the manifest:

```json
    {
      "id": "60",
      "assertion": "set_load",
      "documents": {
        "repository-binding:00000000000000000000000000000001": "core/01-minimal.json",
        "repository-binding:00000000000000000000000000000002": "bindings/41-second-binding.json"
      },
      "expect_binding_status": {
        "repository-binding:00000000000000000000000000000001": "loaded",
        "repository-binding:00000000000000000000000000000002": "loaded"
      },
      "expect_file_count": 2
    },
    {
      "id": "61",
      "assertion": "set_load",
      "documents": {
        "repository-binding:00000000000000000000000000000001": "core/01-minimal.json",
        "repository-binding:00000000000000000000000000000002": "freshness/50-absent-document.json"
      },
      "expect_binding_status": {
        "repository-binding:00000000000000000000000000000001": "loaded",
        "repository-binding:00000000000000000000000000000002": "unavailable"
      },
      "expect_file_count": 1
    },
    {
      "id": "62",
      "assertion": "aggregate_coverage",
      "documents": {
        "repository-binding:00000000000000000000000000000001": "core/01-minimal.json",
        "repository-binding:00000000000000000000000000000002": "freshness/50-absent-document.json"
      },
      "capability": "contains",
      "query_path": "src/app.py",
      "expect_aggregate": "partial"
    }
```

Fixture 62 is the one that matters most: an unavailable binding degrades the aggregate to `partial`, never to an observed zero.

- [ ] **Step 6: Wire the runner into the harness**

In `bin/test-structural-graph.sh`, after the unit-test check:

```bash
check "fixture corpus" python3 bin/check-structural-graph-fixtures.py \
  --manifest testdata/structural-graph/v1/manifest.json

# Determinism: two runs must produce byte-identical output.
first="$(python3 bin/check-structural-graph-fixtures.py --manifest testdata/structural-graph/v1/manifest.json)"
second="$(python3 bin/check-structural-graph-fixtures.py --manifest testdata/structural-graph/v1/manifest.json)"
check "deterministic output" test "$first" = "$second"
```

- [ ] **Step 7: Verify and commit**

Run: `git add -A && make check && bash bin/test-structural-graph.sh`
Expected: `All checks passed.` then `structural-graph: all 3 check(s) passed`

```bash
git commit -m "feat(#227): fixture corpus and manifest-driven runner

Adds testdata/structural-graph/v1/ covering core loads, the version
short-circuit, malformed shapes, foreign bindings, coverage gaps and
overlaps, partial parse failure, absent documents, and multi-binding set
load.

The runner holds no copy of library logic; every assertion runs the real
modules."
```

---

### Task 9: Adversarial privacy fixtures and finding-payload purity

The regression test for the `evidence.normalize` defect. This task is the acceptance criterion #227 calls out as REQUIRED.

**Files:**
- Create: `testdata/structural-graph/v1/privacy/*.json`
- Modify: `testdata/structural-graph/v1/manifest.json`, `bin/check-structural-graph-fixtures.py`, `bin/structural_graph/tests/test_document.py`

**Interfaces:**
- Consumes: everything prior.
- Produces: a `redaction_purity` assertion kind proving no finding or fact anywhere in the corpus carries a secret.

**Authoring constraints — violating either blocks the commit with no escape:**
- `private-ok` markers go on the **same physical line** as the offending string.
- Secret-shaped strings are bearer/API-key shaped, **never PEM**.

- [ ] **Step 1: Write the failing fixtures**

Create `testdata/structural-graph/v1/privacy/70-absolute-path-anchor.json` — an absolute path in an **anchor**, which must make the document malformed:

```json
{
  "schema_version": 1,
  "binding_id": "repository-binding:00000000000000000000000000000001",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider": { "name": "reference-json", "version": "1.0.0" },
  "capabilities": ["contains"],
  "root": "",
  "coverage": [
    { "path_prefix": "", "capability": "contains", "status": "observed" }
  ],
  "files": [{ "path": "/Users/jane/private-ok/repo/src/app.py" }],
  "symbols": [
    { "id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py" }
  ],
  "edges": []
}
```

The `private-ok` marker is a **path segment**, not an extra key. `files[]` has `additionalProperties: false`, so a sibling `_note` key would fail JSON Schema — but the scanner only needs the literal `private-ok` somewhere on the same physical line, and a path segment satisfies that while leaving the fixture schema-valid. The path is still absolute, still matches the home-path pattern, and still fails `normalize_path`, so the test's intent is unchanged.

Create `testdata/structural-graph/v1/privacy/71-secret-in-diagnostic.json` — the secret is in an **incidental** field, so the fact must survive and the string must be scrubbed:

```json
{
  "schema_version": 1,
  "binding_id": "repository-binding:00000000000000000000000000000001",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider": { "name": "reference-json", "version": "1.0.0" },
  "capabilities": ["contains"],
  "root": "",
  "coverage": [
    { "path_prefix": "", "capability": "contains", "status": "observed" }
  ],
  "files": [{ "path": "src/app.py" }],
  "symbols": [
    { "id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py" }
  ],
  "edges": [],
  "diagnostics": [
    { "message": "auth failed with ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA reading /Users/jane/repo (private-ok: adversarial fixture)" }
  ]
}
```

Register both, plus the corpus-wide purity assertion:

```json
    {
      "id": "70",
      "path": "privacy/70-absolute-path-anchor.json",
      "assertion": "load_status",
      "expect_status": "malformed",
      "expect_freshness": "freshness_unknown",
      "expect_codes": ["E_SG_UNNORMALIZABLE_ANCHOR"]
    },
    {
      "id": "71",
      "path": "privacy/71-secret-in-diagnostic.json",
      "assertion": "load_status",
      "expect_status": "loaded",
      "expect_freshness": "freshness_unknown",
      "expect_codes": []
    },
    {
      "id": "72",
      "assertion": "redaction_purity"
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 bin/check-structural-graph-fixtures.py --manifest testdata/structural-graph/v1/manifest.json`
Expected: FAIL — `✗ 72: unknown assertion redaction_purity`

- [ ] **Step 3: Implement the purity assertion**

Add to `bin/check-structural-graph-fixtures.py`, above `ASSERTIONS`:

```python
SECRET_MARKERS = ("/Users/", "/home/", "ghp_", "sk-", "AKIA", "@")


def assert_redaction_purity(fixture, base, config):
    """No finding or fact anywhere in the corpus may carry a raw secret.

    This is the regression test for the context_graph.evidence defect, where
    an unsafe path was rejected and then echoed back verbatim in the result.
    """
    manifest = load_json(os.path.join(base, "manifest.json"))
    problems = []
    for entry in manifest["fixtures"]:
        if "path" not in entry:
            continue
        target = os.path.join(base, entry["path"])
        if not os.path.exists(target):
            continue
        result = document.load_object(load_json(target), config)
        for label in ("findings", "facts"):
            blob = json.dumps(result[label] or {})
            for marker in SECRET_MARKERS:
                if marker in blob:
                    problems.append(
                        "%s: %s contains unredacted marker %r"
                        % (entry["path"], label, marker)
                    )
    return problems
```

Register it: `"redaction_purity": assert_redaction_purity,` in `ASSERTIONS`.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 bin/check-structural-graph-fixtures.py --manifest testdata/structural-graph/v1/manifest.json`
Expected: `fixtures: all 15 passed`, exit 0

If fixture 70 reports an unredacted marker in `findings`, that is the real bug this task exists to catch — the anchor finding is leaking the path. Fix `document._anchor_findings` so the finding carries only `field` and `index`, never the value.

- [ ] **Step 5: Verify the privacy gate accepts the corpus**

Run: `git add -A && make check`
Expected: `All checks passed.` If the private-info scan flags a fixture, the `private-ok` marker is not on the same physical line as the offending string. Move it; do not weaken the scanner.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(#227): adversarial privacy fixtures and finding-payload purity

An absolute path in an anchor makes the document malformed; a secret in a
diagnostic is scrubbed while its fact survives. The corpus-wide purity
assertion proves no finding or fact carries a raw secret -- the regression
test for the evidence.normalize defect that rejects an unsafe path and then
echoes it back verbatim."
```

---

### Task 10: Documentation and issue close-out

**Files:**
- Modify: `CHANGELOG.md`, `capabilities.json` (verify complete)

- [ ] **Step 1: Verify every new file is ledgered**

Run:

```bash
python3 bin/check-inventory.py --root . --check-manifest --check-docs
```

Expected: `capability inventory OK`. If any `bin/structural_graph/**` file is reported unclassified, add its `not_a_capability` entry.

- [ ] **Step 2: Add the CHANGELOG entry**

Under the `Unreleased` heading's `### Added`:

```markdown
- Structural-graph interchange (#227): a versioned, provider-neutral local JSON
  format for raw structural facts, plus a reference reader that fails closed on
  unsupported versions, refuses unnormalizable anchors, redacts incidental
  provider strings, and degrades unsupported coverage to unknown rather than
  observed-zero. Library only — no CLI verb yet.
```

- [ ] **Step 3: Run the complete gate**

```bash
git add -A
make check
make test
bash bin/test-structural-graph.sh
```

Expected: all green.

- [ ] **Step 4: Commit and open the PR**

```bash
git commit -m "docs(#227): changelog entry for the structural-graph interchange"
```

Then open a PR to `main` whose body contains the literal phrase `Resolves #227` — prose alone does not close an issue on merge. **Do not push without asking the operator first.**

---

## Self-Review

**Spec coverage.** Every design-spec section maps to a task: architecture and module table → Tasks 1-6; redaction and the field-role split → Task 2 (module) and Task 5 (integration); data flow and pipeline order → Task 5; result shape → Task 5; aggregation → Task 6; persistence and exceptions → Task 5; testing and the two-layer validation bridge → Task 7; fixture corpus → Task 8; privacy fixtures → Task 9; gate obligations → distributed across every task, verified in Task 10.

**Known gap, deliberately left:** the spec's decision 3 describes coverage as "exhaustive tiling"; Task 4 realizes it as root-anchored longest-prefix override, because exhaustive tiling of an unknown filesystem is not decidable from a document alone. The realization satisfies the requirement — gaps become structurally impossible — but it is a narrowing of the spec's wording and is flagged for review rather than silently adopted.

**Type consistency.** `finding(code, message, index, field)` is used identically in `validation`, `coverage`, and `document`. `normalize_path(value, root)` and `redact(value)` keep their signatures across Tasks 2, 5. `status_for(entries, capability, path)` is called with that argument order in Task 6. Result-dict keys `status`/`freshness`/`findings`/`facts` are identical in Tasks 5, 6, 8, 9.

**Placeholder scan:** no TBD/TODO, no "add appropriate error handling", no "similar to Task N" — every code step carries complete code.
