# license-compliance-auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable Claude Code capability that audits any repository for licensing compliance — a progressive-disclosure skill plus a `/license-audit` command, backed by deterministic Python helper scripts.

**Architecture:** A skill (`skills/license-compliance-auditor/`) owns the phase-ordered workflow in `SKILL.md`, heavy knowledge in `references/`, deterministic grunt work in `scripts/` (Python 3 stdlib-only), and fixtures/tests in `tests/`. Scripts do inventory, tool detection, mechanical normalization, report rendering, and issue-draft writing; the model owns all reconciliation, risk classification, and judgment. A thin `commands/license-audit.md` is the discoverable entrypoint. No legal conclusions anywhere.

**Tech Stack:** Bash (repo tooling), Python 3 stdlib-only (scripts + `unittest`), Markdown (skill/references/command). Design spec: [`docs/design/2026-07-05-license-compliance-auditor.md`](../design/2026-07-05-license-compliance-auditor.md).

## Global Constraints

- **Python 3, standard library only.** No `pip install`, no third-party imports. Scripts must run under `python3` with no environment setup.
- **Never install tools; never touch the network.** Detection is inspection-only. Missing coverage is reported with install hints, never guessed.
- **No legal conclusions anywhere** — scripts, references, reports. Use risk language ("likely obligation gap", "flag for review"), never "compliant/non-compliant". Every report carries the non-legal-advice disclaimer verbatim: `Automated license detection is a starting point, not legal advice.`
- **Repo hygiene gates (enforced by `make check` / pre-commit):** every tracked text file ends in exactly one newline and has no trailing whitespace (applies to `.py` too); every repo-relative markdown link target must resolve to a real file; `SKILL.md` needs `name:` (matching folder `license-compliance-auditor`) + `description:` frontmatter; `commands/*.md` needs `description:`; references/tests/scripts need no frontmatter.
- **Scripts with a shebang must be executable** (`chmod +x`) — a pre-commit hook enforces this. All `scripts/*.py` carry `#!/usr/bin/env python3` and are `chmod +x`.
- **SPDX everywhere feasible.** Emit SPDX ids/expressions or the literal `UNKNOWN`. Never invent a dual-license election.
- **Findings schema is the contract** (Task 1). Scripts and reports conform to it.
- **Fixtures are tiny synthetic trees** committed under `tests/fixtures/`, one directory per scenario.
- **The skill is not "done" until pressure-tested** (Task 12, RED→GREEN→REFACTOR). Until then it is marked a draft in the CHANGELOG.

---

### Task 1: Findings schema contract + skill directory scaffold

**Files:**
- Create: `skills/license-compliance-auditor/references/output-schema.md`

**Interfaces:**
- Produces: the canonical findings document shape consumed by `normalize_findings.py`, `render_report.py`, `issue_drafts.py` and produced for `license-compliance-findings.json`. Top-level keys: `schema_version` (str), `repo` (`{root, declared_license, declared_license_evidence[]}`), `coverage` (list of `{category, status, method?, tool?, note?, install_hint?}` where `status ∈ {checked, not-checked, partial}`), `findings` (list, shape below), `generated_by`, `disclaimer`.
- Each **finding**: `id` (`F-0001`), `type` (`dependency|vendored|submodule|spdx-header|font|asset|dataset|snippet|repo-license`), `item`, `path`, `version`, `ecosystem` (nullable), `source`, `license_expression` (SPDX id/expression or `UNKNOWN`), `usage`, `compatibility_risk` (risk enum), `unmet_obligation` (str or `none`), `evidence` (list of str), `confidence` (`high|medium|low`), `risk_level` (`critical|high|medium|low|info`), `review_notes` (str), `recommended_action` (str).

- [ ] **Step 1: Write `references/output-schema.md`**

Document three things: (a) the terminal report structure (from the design's Terminal UX), (b) the markdown report structure (executive summary → declared-license baseline → coverage → reconciliation table → human/legal review items → limitations → disclaimer), (c) the JSON findings schema exactly as the Interfaces block above, with one worked example finding. Include the reconciliation table column order verbatim: `item → type → path/package → version/source → license/SPDX expression → actual usage → compatibility risk vs repo license → unmet obligation → evidence → confidence → risk level → recommended action`. State that `risk_level` and `compatibility_risk` share the enum `critical|high|medium|low|info`.

- [ ] **Step 2: Verify hygiene**

Run: `bin/check.sh --content-only`
Expected: PASS (the new skill dir has no `SKILL.md` yet, so the frontmatter loop skips it; links in `output-schema.md`, if any, resolve).

- [ ] **Step 3: Commit**

```bash
git add skills/license-compliance-auditor/references/output-schema.md
git commit -m "feat(license-audit): define findings schema + report structure"
```

---

### Task 2: Fixtures + tests README

**Files:**
- Create: `skills/license-compliance-auditor/tests/README.md`
- Create: `skills/license-compliance-auditor/tests/fixtures/<scenario>/...` (14 tiny trees)

**Interfaces:**
- Produces: fixture repo trees used by both the deterministic script tests (Tasks 3–7) and the skill pressure-test (Task 12). Each fixture is a directory under `tests/fixtures/`.

- [ ] **Step 1: Create the 14 fixture trees**

One directory each; keep every file a few lines. Exact scenarios and their key files:

| Fixture dir | Key files / content |
|---|---|
| `mit-clean` | `LICENSE` (MIT text stub), `package.json` `{"license":"MIT","dependencies":{"left-pad":"1.3.0"}}` |
| `mit-with-gpl-dep` | `LICENSE` (MIT), `package.json` with a dep documented as GPL-3.0 in a sibling `deps-note.md` |
| `mit-with-agpl-dep` | `LICENSE` (MIT), `requirements.txt` listing an AGPL package name |
| `apache-missing-notice` | `LICENSE` (Apache-2.0 stub), a source file with `SPDX-License-Identifier: Apache-2.0`, **no** `NOTICE` |
| `ofl-font-missing-text` | `assets/fonts/DemoSans.ttf` (empty placeholder), **no** `OFL.txt` |
| `ofl-font-rfn` | `assets/fonts/DemoSans-Custom.ttf` + `OFL.txt` stub mentioning a Reserved Font Name |
| `ccby-image-no-attr` | `assets/img/photo.jpg` (placeholder), **no** attribution/`ATTRIBUTION.md` |
| `ccbync-asset-commercial` | `package.json` (private:false), `assets/img/art.png`, `assets/img/art.license` = `CC-BY-NC-4.0` |
| `dataset-unknown-license` | `data/records.csv` (placeholder), **no** license/source note |
| `vendored-separate-license` | `vendor/lib/LICENSE` (Apache-2.0), `vendor/lib/foo.c`; repo `LICENSE` = MIT |
| `spdx-header-mismatch` | repo `LICENSE` = MIT; `src/x.c` with `SPDX-License-Identifier: GPL-3.0-only` |
| `so-snippet-no-date` | `src/y.js` with a comment `// copied from https://stackoverflow.com/a/12345` and no date/license |
| `no-license-file` | `package.json` `{"name":"x"}` only; **no** `LICENSE` |
| `manifest-conflicts-license` | `LICENSE` = MIT; `package.json` `{"license":"GPL-3.0-only"}` |

Placeholder binary files (`.ttf`, `.jpg`, `.png`, `.csv`) may be empty or a one-line text stub — detection is by path/extension/adjacent files, not content.

- [ ] **Step 2: Write `tests/README.md`**

Document: how to run the deterministic tests (`python3 skills/license-compliance-auditor/scripts/selftest.py`), the fixture catalog (the 14 rows above with the behavior each should provoke), and the **skill pressure-test protocol** (dispatch a fresh agent at a fixture; assert correct risk classification, preserved uncertainty, graceful degradation when scanners are absent, and that it asks before creating issues).

- [ ] **Step 3: Verify hygiene + commit**

Run: `bin/check.sh --content-only`
Expected: PASS.

```bash
git add skills/license-compliance-auditor/tests
git commit -m "test(license-audit): add 14 fixture repos + tests README"
```

---

### Task 3: `detect_tools.py` (scanner detection, injectable `which`)

**Files:**
- Create: `skills/license-compliance-auditor/scripts/detect_tools.py`
- Create: `skills/license-compliance-auditor/scripts/selftest.py`
- Create: `skills/license-compliance-auditor/tests/test_detect_tools.py`
- Modify: `bin/check.sh` (add Python selftest section)

**Interfaces:**
- Produces: `detect(tools=TOOLS, managers=PACKAGE_MANAGERS, which=shutil.which) -> {"tools": {name: {"available": bool, "install_hint": str}}, "package_managers": {name: bool}}`. `which` is injectable for testing. Never installs.
- Produces: `selftest.py main()` discovers `tests/test_*.py` and returns 0/1.

- [ ] **Step 1: Write the failing test** — `tests/test_detect_tools.py`

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import detect_tools  # noqa: E402


class DetectToolsTest(unittest.TestCase):
    def test_reports_available_and_missing_with_hints(self):
        fake = {"scancode", "npm"}
        which = lambda name: "/usr/bin/" + name if name in fake else None
        out = detect_tools.detect(which=which)
        self.assertTrue(out["tools"]["scancode"]["available"])
        self.assertIn("install_hint", out["tools"]["scancode"])
        self.assertFalse(out["tools"]["reuse"]["available"])
        self.assertTrue(out["package_managers"]["npm"])
        self.assertFalse(out["package_managers"]["cargo"])

    def test_never_claims_missing_tool_available(self):
        out = detect_tools.detect(which=lambda name: None)
        self.assertFalse(any(t["available"] for t in out["tools"].values()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Write `scripts/selftest.py`**

```python
#!/usr/bin/env python3
"""Run all license-compliance-auditor script tests (stdlib unittest)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.normpath(os.path.join(HERE, "..", "tests"))


def main():
    sys.path.insert(0, HERE)
    sys.path.insert(0, TESTS)
    suite = unittest.defaultTestLoader.discover(TESTS, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python3 skills/license-compliance-auditor/scripts/selftest.py`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'detect_tools'`.

- [ ] **Step 4: Write `scripts/detect_tools.py`**

```python
#!/usr/bin/env python3
"""Detect available license/dependency scanners. Never installs anything."""
import json
import shutil
import sys

TOOLS = {
    "scancode": "pipx install scancode-toolkit",
    "reuse": "pipx install reuse",
    "licensee": "gem install licensee",
    "license-checker": "npm i -g license-checker-rseidelsohn",
    "pip-licenses": "pipx install pip-licenses",
    "cargo-license": "cargo install cargo-license",
    "go-licenses": "go install github.com/google/go-licenses@latest",
    "cyclonedx": "see https://cyclonedx.org/tool-center/",
}
PACKAGE_MANAGERS = [
    "npm", "pnpm", "yarn", "pip", "pip3", "poetry", "uv", "cargo", "go",
    "composer", "bundle", "mvn", "gradle", "dotnet",
]


def detect(tools=TOOLS, managers=PACKAGE_MANAGERS, which=shutil.which):
    return {
        "tools": {
            name: {"available": which(name) is not None, "install_hint": hint}
            for name, hint in tools.items()
        },
        "package_managers": {name: which(name) is not None for name in managers},
    }


def main(argv=None):
    print(json.dumps(detect(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Make scripts executable, run tests to verify pass**

```bash
chmod +x skills/license-compliance-auditor/scripts/detect_tools.py \
         skills/license-compliance-auditor/scripts/selftest.py
python3 skills/license-compliance-auditor/scripts/selftest.py
```
Expected: PASS (2 tests OK).

- [ ] **Step 6: Wire selftests into `bin/check.sh`**

Add this section immediately before the `# --- result ---` block (it runs in both full and `--content-only` mode, like the frontmatter check):

```bash
# --- 6. skill scripts (python selftests) -----------------------------------
echo "skill-scripts:"
lca_selftest="skills/license-compliance-auditor/scripts/selftest.py"
if [ -f "$lca_selftest" ]; then
  if command -v python3 >/dev/null 2>&1; then
    if python3 "$lca_selftest" >/dev/null 2>&1; then
      ok "license-compliance-auditor selftests pass"
    else
      problem "license-compliance-auditor selftests failed (run: python3 $lca_selftest)"
    fi
  else
    echo "  - python3 not installed; skipping script selftests"
  fi
fi
```

Then normalize shell formatting: `command -v shfmt >/dev/null && shfmt -i 2 -ci -w bin/check.sh`.

- [ ] **Step 7: Run full check + commit**

Run: `bin/check.sh`
Expected: PASS, including `✓ license-compliance-auditor selftests pass`.

```bash
git add skills/license-compliance-auditor/scripts/detect_tools.py \
        skills/license-compliance-auditor/scripts/selftest.py \
        skills/license-compliance-auditor/tests/test_detect_tools.py bin/check.sh
git commit -m "feat(license-audit): detect_tools.py + wire selftests into make check"
```

---

### Task 4: `inventory_repo.py` (repo inspection)

**Files:**
- Create: `skills/license-compliance-auditor/scripts/inventory_repo.py`
- Create: `skills/license-compliance-auditor/tests/test_inventory_repo.py`

**Interfaces:**
- Produces: `inventory(root) -> dict` with keys `root, license_files[], declared_license_candidates[{file,spdx}], manifests[], lockfiles[], ecosystems[], submodules[], vendored_dirs[], spdx_headers[{path,spdx}], provenance_markers[{path,line,marker}], fonts[{path}], assets{images[],audio[],video[],models[],data[]}`. Paths are repo-relative. Pure inspection; no network.

- [ ] **Step 1: Write the failing test** — `tests/test_inventory_repo.py`

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import inventory_repo  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class InventoryTest(unittest.TestCase):
    def test_finds_license_and_manifest_in_mit_clean(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "mit-clean"))
        self.assertIn("LICENSE", inv["license_files"])
        self.assertIn("package.json", inv["manifests"])
        self.assertIn("npm", inv["ecosystems"])
        self.assertTrue(any(c["spdx"] == "MIT"
                            for c in inv["declared_license_candidates"]))

    def test_flags_spdx_header_mismatch(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "spdx-header-mismatch"))
        self.assertTrue(any(h["spdx"] == "GPL-3.0-only"
                            for h in inv["spdx_headers"]))

    def test_flags_vendored_dir(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "vendored-separate-license"))
        self.assertTrue(any("vendor" in v for v in inv["vendored_dirs"]))

    def test_flags_stackoverflow_provenance(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "so-snippet-no-date"))
        self.assertTrue(any("stackoverflow" in m["marker"].lower()
                            for m in inv["provenance_markers"]))

    def test_finds_font(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "ofl-font-missing-text"))
        self.assertTrue(any(f["path"].endswith(".ttf") for f in inv["fonts"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/license-compliance-auditor/scripts/selftest.py`
Expected: FAIL — `No module named 'inventory_repo'`.

- [ ] **Step 3: Write `scripts/inventory_repo.py`**

```python
#!/usr/bin/env python3
"""Enumerate license-relevant files/dirs in a repo. Pure inspection; no network."""
import json
import os
import re
import sys

LICENSE_FILES = {"license", "licence", "copying", "notice", "authors",
                 "copyright", "unlicense"}
MANIFESTS = {"package.json", "pyproject.toml", "setup.py", "setup.cfg",
             "cargo.toml", "go.mod", "composer.json", "gemfile", "build.gradle",
             "pom.xml"}
LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock",
             "uv.lock", "cargo.lock", "go.sum", "composer.lock", "gemfile.lock",
             "requirements.txt"}
VENDOR_DIRS = {"vendor", "vendors", "third_party", "third-party", "external",
               "deps", "extern"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2", ".eot"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
MODEL_EXT = {".gltf", ".glb", ".obj", ".fbx", ".stl", ".blend", ".dae"}
DATA_EXT = {".csv", ".parquet", ".jsonl", ".geojson", ".sqlite", ".db"}
TEXT_SCAN_EXT = {".c", ".h", ".cpp", ".cc", ".py", ".js", ".ts", ".tsx", ".jsx",
                 ".go", ".rs", ".java", ".rb", ".php", ".css", ".scss"}
ECOSYSTEM_BY_MANIFEST = {
    "package.json": "npm", "pyproject.toml": "pip", "setup.py": "pip",
    "setup.cfg": "pip", "cargo.toml": "cargo", "go.mod": "go",
    "composer.json": "composer", "gemfile": "rubygems", "build.gradle": "gradle",
    "pom.xml": "maven",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".tox"}
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*(.+)")
PROVENANCE_RE = re.compile(
    r"(stackoverflow\.com|stackexchange\.com|gist\.github|codepen\.io|"
    r"jsfiddle\.net|copied from|adapted from)", re.I)
MAX_SCAN_BYTES = 200_000


def _read(path, limit=MAX_SCAN_BYTES):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read(limit)


def _spdx_from_manifest(path, name):
    try:
        text = _read(path)
    except OSError:
        return None
    patterns = {
        "package.json": r'"license"\s*:\s*"([^"]+)"',
        "composer.json": r'"license"\s*:\s*"([^"]+)"',
        "cargo.toml": r'license\s*=\s*"([^"]+)"',
        "pyproject.toml": r'license\s*=\s*["\']?([A-Za-z0-9.\-+ ]+)',
        "setup.cfg": r'license\s*=\s*([A-Za-z0-9.\-+ ]+)',
    }
    pat = patterns.get(name)
    if not pat:
        return None
    m = re.search(pat, text)
    return m.group(1).strip() if m else None


def inventory(root):
    root = os.path.abspath(root)
    inv = {
        "root": root, "license_files": [], "declared_license_candidates": [],
        "manifests": [], "lockfiles": [], "ecosystems": set(), "submodules": [],
        "vendored_dirs": [], "spdx_headers": [], "provenance_markers": [],
        "fonts": [], "assets": {"images": [], "audio": [], "video": [],
                                "models": [], "data": []},
    }
    gm = os.path.join(root, ".gitmodules")
    if os.path.isfile(gm):
        for m in re.finditer(r"path\s*=\s*(.+)", _read(gm)):
            inv["submodules"].append(m.group(1).strip())
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in list(dirnames):
            if d.lower() in VENDOR_DIRS:
                inv["vendored_dirs"].append(
                    os.path.relpath(os.path.join(dirpath, d), root))
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            low = fn.lower()
            stem, ext = os.path.splitext(low)
            if stem in LICENSE_FILES or low in LICENSE_FILES:
                inv["license_files"].append(rel)
            if low in MANIFESTS:
                inv["manifests"].append(rel)
                eco = ECOSYSTEM_BY_MANIFEST.get(low)
                if eco:
                    inv["ecosystems"].add(eco)
                spdx = _spdx_from_manifest(full, low)
                if spdx:
                    inv["declared_license_candidates"].append(
                        {"file": rel, "spdx": spdx})
            if low in LOCKFILES:
                inv["lockfiles"].append(rel)
            if ext in FONT_EXT:
                inv["fonts"].append({"path": rel})
            elif ext in IMAGE_EXT:
                inv["assets"]["images"].append(rel)
            elif ext in AUDIO_EXT:
                inv["assets"]["audio"].append(rel)
            elif ext in VIDEO_EXT:
                inv["assets"]["video"].append(rel)
            elif ext in MODEL_EXT:
                inv["assets"]["models"].append(rel)
            elif ext in DATA_EXT:
                inv["assets"]["data"].append(rel)
            if ext in TEXT_SCAN_EXT:
                try:
                    text = _read(full)
                except OSError:
                    continue
                for m in SPDX_RE.finditer(text):
                    inv["spdx_headers"].append(
                        {"path": rel, "spdx": m.group(1).strip()})
                for lineno, line in enumerate(text.splitlines(), 1):
                    if PROVENANCE_RE.search(line):
                        inv["provenance_markers"].append(
                            {"path": rel, "line": lineno,
                             "marker": line.strip()[:200]})
    inv["ecosystems"] = sorted(inv["ecosystems"])
    for k in ("license_files", "manifests", "lockfiles", "vendored_dirs"):
        inv[k].sort()
    return inv


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = argv[0] if argv else "."
    print(json.dumps(inventory(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable, run tests to verify pass**

```bash
chmod +x skills/license-compliance-auditor/scripts/inventory_repo.py
python3 skills/license-compliance-auditor/scripts/selftest.py
```
Expected: PASS (detect_tools + inventory tests).

- [ ] **Step 5: Commit**

```bash
git add skills/license-compliance-auditor/scripts/inventory_repo.py \
        skills/license-compliance-auditor/tests/test_inventory_repo.py
git commit -m "feat(license-audit): inventory_repo.py repo inspection"
```

---

### Task 5: `normalize_findings.py` (mechanical normalization)

**Files:**
- Create: `skills/license-compliance-auditor/scripts/normalize_findings.py`
- Create: `skills/license-compliance-auditor/tests/test_normalize_findings.py`

**Interfaces:**
- Consumes: a partial findings doc (model-assembled) — `{"findings": [ {partial finding} ]}`.
- Produces: `normalize(doc) -> doc` conforming to the Task 1 schema: assigns `id` (`F-0001`), canonicalizes `license_expression` via `canonical_spdx`, coerces `confidence`/`risk_level`/`compatibility_risk` to valid enums (defaults `low`/`medium`), wraps scalar `evidence` into a list, fills `unmet_obligation`/`review_notes`/`recommended_action` defaults, injects `schema_version`/`generated_by`/`disclaimer`. **Never invents a license election or legal conclusion.** Also exports `canonical_spdx(expr) -> str`.

- [ ] **Step 1: Write the failing test** — `tests/test_normalize_findings.py`

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import normalize_findings as nf  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_assigns_ids_and_defaults(self):
        out = nf.normalize({"findings": [{"item": "x", "type": "dependency"}]})
        f = out["findings"][0]
        self.assertEqual(f["id"], "F-0001")
        self.assertEqual(f["confidence"], "low")
        self.assertEqual(f["risk_level"], "medium")
        self.assertEqual(f["unmet_obligation"], "none")
        self.assertIn("not legal advice", out["disclaimer"])

    def test_canonicalizes_spdx_and_flags_ambiguous(self):
        self.assertEqual(nf.canonical_spdx("apache 2.0"), "Apache-2.0")
        self.assertIn("ambiguous", nf.canonical_spdx("BSD").lower())
        self.assertEqual(nf.canonical_spdx(None), "UNKNOWN")

    def test_evidence_scalar_becomes_list(self):
        out = nf.normalize({"findings": [{"item": "x", "evidence": "LICENSE"}]})
        self.assertEqual(out["findings"][0]["evidence"], ["LICENSE"])

    def test_never_invents_election_for_or_expression(self):
        out = nf.normalize({"findings": [
            {"item": "x", "license_expression": "MIT OR Apache-2.0"}]})
        self.assertEqual(out["findings"][0]["license_expression"],
                         "MIT OR Apache-2.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/license-compliance-auditor/scripts/selftest.py`
Expected: FAIL — `No module named 'normalize_findings'`.

- [ ] **Step 3: Write `scripts/normalize_findings.py`**

```python
#!/usr/bin/env python3
"""Normalize model-assembled findings to the stable schema. No legal inference."""
import json
import sys

RISK_LEVELS = {"critical", "high", "medium", "low", "info"}
CONFIDENCE = {"high", "medium", "low"}
SPDX_ALIASES = {
    "apache 2.0": "Apache-2.0", "apache-2": "Apache-2.0", "apache2": "Apache-2.0",
    "mit license": "MIT", "the mit license": "MIT",
    "bsd": "BSD (ambiguous — needs review)",
    "gpl": "GPL (ambiguous — needs review)",
    "gplv3": "GPL-3.0-only", "gplv2": "GPL-2.0-only",
    "cc-by": "CC-BY-4.0 (verify version)", "cc0": "CC0-1.0",
}


def canonical_spdx(expr):
    if not expr:
        return "UNKNOWN"
    return SPDX_ALIASES.get(expr.strip().lower(), expr.strip())


def normalize(doc):
    out = []
    for i, f in enumerate(doc.get("findings", []), 1):
        g = dict(f)
        g.setdefault("id", f"F-{i:04d}")
        g["license_expression"] = canonical_spdx(f.get("license_expression"))
        g["confidence"] = f.get("confidence") if f.get("confidence") in CONFIDENCE else "low"
        g["risk_level"] = f.get("risk_level") if f.get("risk_level") in RISK_LEVELS else "medium"
        cr = f.get("compatibility_risk")
        g["compatibility_risk"] = cr if cr in RISK_LEVELS else g["risk_level"]
        ev = g.get("evidence")
        g["evidence"] = ev if isinstance(ev, list) else ([ev] if ev else [])
        g.setdefault("unmet_obligation", "none")
        g.setdefault("review_notes", "")
        g.setdefault("recommended_action", "")
        out.append(g)
    doc = dict(doc)
    doc["findings"] = out
    doc.setdefault("schema_version", "1.0")
    doc.setdefault("generated_by", "license-compliance-auditor")
    doc.setdefault(
        "disclaimer",
        "Automated license detection is a starting point, not legal advice.")
    return doc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    src = json.load(open(argv[0])) if argv else json.load(sys.stdin)
    print(json.dumps(normalize(src), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable, run tests to verify pass**

```bash
chmod +x skills/license-compliance-auditor/scripts/normalize_findings.py
python3 skills/license-compliance-auditor/scripts/selftest.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/license-compliance-auditor/scripts/normalize_findings.py \
        skills/license-compliance-auditor/tests/test_normalize_findings.py
git commit -m "feat(license-audit): normalize_findings.py schema normalization"
```

---

### Task 6: `render_report.py` (terminal + markdown + JSON)

**Files:**
- Create: `skills/license-compliance-auditor/scripts/render_report.py`
- Create: `skills/license-compliance-auditor/tests/test_render_report.py`

**Interfaces:**
- Consumes: a normalized findings doc (Task 5 output).
- Produces: `render(doc, out_dir=".", write=True) -> str` (terminal text); when `write`, writes `license-compliance-report.md` + `license-compliance-findings.json` into `out_dir`. Also exports `terminal_report(doc) -> str` and `markdown_report(doc) -> str`. Findings sorted critical→info; terminal "Top findings" shows ≤5 critical/high.

- [ ] **Step 1: Write the failing test** — `tests/test_render_report.py`

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import render_report as rr  # noqa: E402

DOC = {
    "repo": {"declared_license": "MIT", "declared_license_evidence": ["LICENSE"]},
    "coverage": [{"category": "javascript-deps", "status": "checked"}],
    "findings": [
        {"item": "DemoSans", "type": "font", "path": "assets/fonts/DemoSans.ttf",
         "risk_level": "high", "unmet_obligation": "missing OFL.txt",
         "compatibility_risk": "high", "confidence": "medium",
         "evidence": ["no OFL.txt beside font"], "recommended_action": "add OFL.txt",
         "review_notes": "confirm OFL applies"},
        {"item": "left-pad", "type": "dependency", "path": "node_modules/left-pad",
         "risk_level": "info", "unmet_obligation": "none"},
    ],
}


class RenderTest(unittest.TestCase):
    def test_terminal_has_baseline_coverage_and_top_findings(self):
        term = rr.terminal_report(DOC)
        self.assertIn("Declared license: MIT", term)
        self.assertIn("javascript-deps", term)
        self.assertIn("DemoSans", term)
        self.assertIn("HIGH", term)

    def test_writes_md_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            rr.render(DOC, out_dir=d)
            md = open(os.path.join(d, "license-compliance-report.md")).read()
            self.assertIn("not legal advice", md.lower())
            self.assertIn("| Item |", md)
            data = json.load(open(os.path.join(d, "license-compliance-findings.json")))
            self.assertEqual(len(data["findings"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/license-compliance-auditor/scripts/selftest.py`
Expected: FAIL — `No module named 'render_report'`.

- [ ] **Step 3: Write `scripts/render_report.py`**

```python
#!/usr/bin/env python3
"""Render terminal + markdown reports from a normalized findings document."""
import json
import os
import sys

ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
DISCLAIMER = ("This report is generated by automated tooling. Automated license "
              "detection is a starting point, not legal advice. Risk levels and "
              "obligation notes are heuristics that require human/legal review.")


def _sorted(findings):
    return sorted(findings, key=lambda f: ORDER.get(f.get("risk_level"), 9))


def terminal_report(doc):
    repo = doc.get("repo", {})
    lines = ["License Compliance Audit", "Repo license baseline:",
             f"- Declared license: {repo.get('declared_license', 'UNKNOWN')}",
             "- Evidence: "
             + (", ".join(repo.get("declared_license_evidence", [])) or "none"),
             "Coverage:"]
    for c in doc.get("coverage", []):
        note = f" ({c['note']})" if c.get("note") else ""
        lines.append(f"- {c.get('category')}: {c.get('status')}{note}")
    tops = [f for f in _sorted(doc.get("findings", []))
            if f.get("risk_level") in ("critical", "high")][:5]
    lines.append("Top findings:")
    if tops:
        for i, f in enumerate(tops, 1):
            lines.append(f"{i}. {f.get('risk_level', '').upper()} — "
                         f"{f.get('item')}: {f.get('unmet_obligation')}")
    else:
        lines.append("- none at critical/high")
    lines += ["Full reports:", "- license-compliance-report.md",
              "- license-compliance-findings.json"]
    return "\n".join(lines)


def markdown_report(doc):
    repo = doc.get("repo", {})
    out = ["# License Compliance Report", "", f"> {DISCLAIMER}", "",
           "## Declared license baseline", "",
           f"- **License:** {repo.get('declared_license', 'UNKNOWN')}",
           "- **Evidence:** "
           + (", ".join(repo.get("declared_license_evidence", [])) or "none"),
           "", "## Coverage", ""]
    for c in doc.get("coverage", []):
        out.append(f"- **{c.get('category')}** — {c.get('status')}"
                   + (f" ({c['note']})" if c.get("note") else ""))
    out += ["", "## Reconciliation", "",
            "| Item | Type | Path/Pkg | Version | License | Usage | Risk vs repo "
            "| Unmet obligation | Confidence | Risk | Action |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in _sorted(doc.get("findings", [])):
        out.append("| " + " | ".join(str(f.get(k, "")) for k in (
            "item", "type", "path", "version", "license_expression", "usage",
            "compatibility_risk", "unmet_obligation", "confidence", "risk_level",
            "recommended_action")) + " |")
    out += ["", "## Human / legal review items", ""]
    review = [f"- **{f.get('item')}** — {f.get('review_notes')}"
              for f in doc.get("findings", []) if f.get("review_notes")]
    out += review or ["- none"]
    out += ["", "## Limitations", "",
            "- Detection is bounded by installed scanners; gaps are reported, "
            "not guessed.",
            "- Asset/font/dataset detection is heuristic, not content "
            "fingerprinting.", ""]
    return "\n".join(out)


def render(doc, out_dir=".", write=True):
    if write:
        with open(os.path.join(out_dir, "license-compliance-report.md"), "w") as fh:
            fh.write(markdown_report(doc) + "\n")
        with open(os.path.join(out_dir, "license-compliance-findings.json"), "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return terminal_report(doc)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    doc = json.load(open(argv[0]))
    out_dir = argv[1] if len(argv) > 1 else "."
    print(render(doc, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable, run tests to verify pass**

```bash
chmod +x skills/license-compliance-auditor/scripts/render_report.py
python3 skills/license-compliance-auditor/scripts/selftest.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/license-compliance-auditor/scripts/render_report.py \
        skills/license-compliance-auditor/tests/test_render_report.py
git commit -m "feat(license-audit): render_report.py terminal+md+json output"
```

---

### Task 7: `issue_drafts.py` (grouped local drafts; never calls gh)

**Files:**
- Create: `skills/license-compliance-auditor/scripts/issue_drafts.py`
- Create: `skills/license-compliance-auditor/tests/test_issue_drafts.py`

**Interfaces:**
- Consumes: a normalized findings doc.
- Produces: `write_drafts(doc, out_dir="license-compliance-issues") -> [paths]`; groups critical/high findings by `type`, writes one markdown draft per group with sections: title, suggested labels, highest risk, affected items, evidence, recommended action, human-review boundary, acceptance criteria. Also exports `group(findings) -> {type: [findings]}`. **Never** invokes `gh` or the network.

- [ ] **Step 1: Write the failing test** — `tests/test_issue_drafts.py`

```python
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import issue_drafts as idr  # noqa: E402

DOC = {"findings": [
    {"item": "DemoSans", "type": "font", "path": "assets/fonts/DemoSans.ttf",
     "risk_level": "high", "unmet_obligation": "missing OFL.txt",
     "evidence": ["no OFL.txt"], "recommended_action": "add OFL.txt"},
    {"item": "left-pad", "type": "dependency", "path": "n/left-pad",
     "risk_level": "info", "unmet_obligation": "none"},
]}


class IssueDraftsTest(unittest.TestCase):
    def test_only_groups_critical_high(self):
        groups = idr.group(DOC["findings"])
        self.assertIn("font", groups)
        self.assertNotIn("dependency", groups)  # info excluded

    def test_writes_grouped_draft_with_required_sections(self):
        with tempfile.TemporaryDirectory() as d:
            paths = idr.write_drafts(DOC, out_dir=d)
            self.assertEqual(len(paths), 1)
            text = open(paths[0]).read()
            for section in ("Suggested labels", "Affected items", "Evidence",
                            "Recommended action", "Human-review boundary",
                            "Acceptance criteria"):
                self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/license-compliance-auditor/scripts/selftest.py`
Expected: FAIL — `No module named 'issue_drafts'`.

- [ ] **Step 3: Write `scripts/issue_drafts.py`**

```python
#!/usr/bin/env python3
"""Write grouped local issue drafts from findings. Never calls gh or the network."""
import json
import os
import re
import sys

LABELS_BY_TYPE = {
    "dependency": ["license-compliance", "dependencies"],
    "vendored": ["license-compliance", "legal-review"],
    "submodule": ["license-compliance", "legal-review"],
    "font": ["license-compliance", "fonts"],
    "asset": ["license-compliance", "assets"],
    "dataset": ["license-compliance", "assets", "legal-review"],
    "snippet": ["license-compliance", "legal-review"],
    "spdx-header": ["license-compliance", "documentation"],
}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "issue"


def group(findings):
    groups = {}
    for f in findings:
        if f.get("risk_level") not in ("critical", "high"):
            continue
        groups.setdefault(f.get("type", "other"), []).append(f)
    return groups


def draft_markdown(group_type, items):
    labels = LABELS_BY_TYPE.get(group_type, ["license-compliance"])
    highest = "critical" if any(f.get("risk_level") == "critical"
                                for f in items) else "high"
    lines = [f"# License compliance: {group_type} findings", "",
             f"**Suggested labels:** {', '.join(labels)}",
             f"**Highest risk:** {highest}", "", "## Affected items", ""]
    for f in items:
        lines.append(f"- `{f.get('item')}` ({f.get('path')}) — "
                     f"{f.get('unmet_obligation')} [{f.get('risk_level')}]")
    lines += ["", "## Evidence", ""]
    for f in items:
        for e in f.get("evidence", []):
            lines.append(f"- {f.get('item')}: {e}")
    lines += ["", "## Recommended action", ""]
    for f in items:
        lines.append(f"- {f.get('item')}: {f.get('recommended_action')}")
    lines += ["", "## Human-review boundary", "",
              "This draft flags risk and likely obligation gaps; it is not legal "
              "advice. Confirm obligations with a qualified reviewer before acting.",
              "", "## Acceptance criteria", "",
              "- [ ] Each affected item resolved or explicitly accepted with rationale",
              "- [ ] Required license text / attribution added where applicable"]
    return "\n".join(lines)


def write_drafts(doc, out_dir="license-compliance-issues"):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for gtype, items in sorted(group(doc.get("findings", [])).items()):
        path = os.path.join(out_dir, f"{_slug(gtype)}.md")
        with open(path, "w") as fh:
            fh.write(draft_markdown(gtype, items) + "\n")
        written.append(path)
    return written


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    doc = json.load(open(argv[0]))
    out_dir = argv[1] if len(argv) > 1 else "license-compliance-issues"
    for p in write_drafts(doc, out_dir):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable, run tests to verify pass**

```bash
chmod +x skills/license-compliance-auditor/scripts/issue_drafts.py
python3 skills/license-compliance-auditor/scripts/selftest.py
```
Expected: PASS (all script tests).

- [ ] **Step 5: Commit**

```bash
git add skills/license-compliance-auditor/scripts/issue_drafts.py \
        skills/license-compliance-auditor/tests/test_issue_drafts.py
git commit -m "feat(license-audit): issue_drafts.py grouped local drafts"
```

---

### Task 8: Knowledge references

**Files:**
- Create: `skills/license-compliance-auditor/references/tool-map.md`
- Create: `skills/license-compliance-auditor/references/risk-taxonomy.md`
- Create: `skills/license-compliance-auditor/references/obligation-checklist.md`
- Create: `skills/license-compliance-auditor/references/font-license-cheatsheet.md`
- Create: `skills/license-compliance-auditor/references/asset-license-cheatsheet.md`
- Create: `skills/license-compliance-auditor/references/human-review-boundaries.md`

**Interfaces:**
- Produces: the on-demand knowledge SKILL.md points at. No frontmatter needed. Any repo-relative links must resolve.

- [ ] **Step 1: Write `tool-map.md`** — a table per ecosystem: ecosystem → scanner/command to try → what it emits → fallback when absent → install hint. Cover repo-wide (scancode, reuse, licensee, fosslight), JS/TS (license-checker, lockfile parsing), Python (pip-licenses, poetry/uv, metadata), Rust (cargo-license), Go (go-licenses), PHP (composer), Ruby (bundler), Java/Kotlin (maven/gradle reports), .NET (nuget). State the rule: **if a scanner is unavailable, record missing coverage + install hint — never guess.** Note optional CycloneDX SBOM emission where tooling exists.

- [ ] **Step 2: Write `risk-taxonomy.md`** — define the five levels verbatim (`critical`, `high`, `medium`, `low`, `info`) with the design's examples and escalation rules. State that compatibility conflicts between the declared license and detected obligations take the highest applicable severity, and list the "be especially careful" cases (permissive repo + copyleft dep; AGPL in a network service; LGPL statically linked/bundled; CC BY-SA / BY-NC / BY-ND assets; OFL fonts missing text or with RFN concerns; datasets under ODbL/CDLA/CC-BY/NC/SA/bespoke terms).

- [ ] **Step 3: Write `obligation-checklist.md`** — per-obligation checklist: attribution, NOTICE completeness, license-text inclusion, copyright-notice preservation, source-disclosure, copyleft/share-alike, LGPL linking, AGPL network-interaction, Apache-2.0 patent grant/retaliation, trademark/brand limits, CLA/DCO, dataset provenance/redistribution. Each: what to check, what evidence proves it met, how to phrase the gap as risk (not a conclusion).

- [ ] **Step 4: Write `font-license-cheatsheet.md`** — OFL (reserved-font-name rules, requirement to ship OFL text with redistributed fonts, web-embed vs redistribution), Apache/MIT fonts, proprietary/commercial (per-seat, web-embed limits), icon fonts, `@font-face`/Google Fonts/Adobe Fonts/`@fontsource/*`/`next/font` detection cues. What to flag (missing license text, unclear source, RFN modification, icon-font ambiguity).

- [ ] **Step 5: Write `asset-license-cheatsheet.md`** — Creative Commons family (CC0, BY, BY-SA, BY-NC, BY-NC-SA, BY-ND), ODbL, CDLA, public-domain/CC0, plus "free for personal use" and "non-commercial only" bespoke terms. Priorities: missing attribution, NC terms in commercial/public-distribution repos, share-alike, no-derivatives, unclear source, trademark/brand limits, missing license text/source URL, copied assets without provenance. State: public web availability ≠ redistribution permission.

- [ ] **Step 6: Write `human-review-boundaries.md`** — the authoritative non-legal-advice language. List exactly what MUST be escalated, never decided (the design's out-of-scope list: version-history license drift, cross-copyleft compatibility, whether a linking/deployment model triggers LGPL/GPL/AGPL, trademark/logo permission, snippet substantiality, bespoke/commercial-use permission, org commercial-use permission, anything constituting legal advice). State what the tool *can* say (risk classification, likely obligation gaps, evidence, confidence) vs. cannot (compliance verdicts).

- [ ] **Step 7: Verify hygiene + commit**

Run: `bin/check.sh --content-only`
Expected: PASS (links resolve; still no `SKILL.md`, so frontmatter loop skips).

```bash
git add skills/license-compliance-auditor/references
git commit -m "docs(license-audit): add knowledge references (tools, risk, obligations, fonts, assets, review boundaries)"
```

---

### Task 9: SKILL.md (operational workflow)

**Files:**
- Create: `skills/license-compliance-auditor/SKILL.md`

**Interfaces:**
- Consumes: all references + scripts.
- Produces: the installed skill (frontmatter `name: license-compliance-auditor` + `description:`).

- [ ] **Step 1: Write `SKILL.md`**

Frontmatter: `name: license-compliance-auditor`; `description:` third-person, starts with "Use when", triggering only on license-compliance audits (e.g. *"Use when auditing a repository for license compliance — reconciling the declared license against dependencies, vendored code, fonts, bundled assets, datasets, and copied snippets; classifying risk and obligation gaps; never giving legal conclusions."*).

Body (concise, operational — heavy detail stays in references):
- **Overview** — one-line core principle: orchestrate scanners + inspection, reconcile against the declared license, classify risk, preserve uncertainty, never conclude legality.
- **When to use / when not** — audits vs. a quick single-file license question.
- **Safe-execution rules** — never install tools; never touch the network to "resolve" a license; no legal conclusions; always report coverage gaps.
- **Workflow checklist** (the phases): preflight → dependency scan → vendored/submodules/SPDX headers → fonts → other assets → provenance gaps → obligation layer → risk classification → terminal report → written reports → optional issue workflow. At each phase, point to the relevant reference (e.g. "before dependency scanning read `references/tool-map.md`").
- **Scripts** — the exact commands: `python3 scripts/detect_tools.py`, `python3 scripts/inventory_repo.py <root>`, pipe model-assembled findings through `python3 scripts/normalize_findings.py`, then `python3 scripts/render_report.py findings.json <out_dir>`, and (only after confirmation) `python3 scripts/issue_drafts.py findings.json`.
- **Report outputs** — `license-compliance-report.md`, `license-compliance-findings.json`; schema in `references/output-schema.md`.
- **Options/flags** — include/exclude dev deps, SBOM, scan-only-deps/-assets/-fonts, strict CI mode (critical/high → nonzero exit), report-only.
- **Issue-creation gate** — never automatic; print report, then ask; on yes propose a grouped plan first; only create via `gh` after explicit confirmation and when `gh` is authed + a GitHub remote exists; otherwise write drafts to `license-compliance-issues/`.
- **Legal boundary** — link `references/human-review-boundaries.md`; every report carries the non-legal-advice disclaimer.
- **Progressive-disclosure pointers** — a short "read these references when…" map.

Use relative links to the reference files so the links check passes (a link whose target is `references/tool-map.md`, resolved relative to `SKILL.md`).

- [ ] **Step 2: Verify full check**

Run: `bin/check.sh`
Expected: PASS — frontmatter now validates the skill (`name` matches folder), links resolve, selftests still pass.

- [ ] **Step 3: Commit**

```bash
git add skills/license-compliance-auditor/SKILL.md
git commit -m "feat(license-audit): SKILL.md operational workflow"
```

---

### Task 10: `/license-audit` slash command

**Files:**
- Create: `commands/license-audit.md`

**Interfaces:**
- Consumes: the skill. Thin entrypoint only.

- [ ] **Step 1: Write `commands/license-audit.md`**

Frontmatter: `description: Audit this repo for license compliance (deps, vendored code, fonts, assets, datasets, snippets).` and `argument-hint: [--deps-only|--assets-only|--fonts-only|--strict|--include-dev|--sbom|--report-only]`.

Body: instruct the model to invoke the `license-compliance-auditor` skill, parse `$ARGUMENTS` into the documented modes (deps-only / assets-only / fonts-only / strict / include-dev / sbom / report-only), and follow the skill's terminal-first workflow — including the issue-creation confirmation gate. Keep it a pointer; no logic duplication.

- [ ] **Step 2: Verify + commit**

Run: `bin/check.sh --content-only`
Expected: PASS (command has `description:`).

```bash
git add commands/license-audit.md
git commit -m "feat(license-audit): add /license-audit slash command entrypoint"
```

---

### Task 11: CHANGELOG + install verification

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md` (optional: list the new skill/command if it maintains such a list)

**Interfaces:**
- Produces: release notes; verified install/symlink.

- [ ] **Step 1: Add CHANGELOG entry under `## [Unreleased]`**

Add under Added: `license-compliance-auditor skill + /license-audit command — portable repo license-compliance audit (deps, vendored code, fonts, assets, datasets, snippets), Python stdlib-only scripts, terminal-first reports, grouped issue drafts. **Draft until pressure-tested.**`

- [ ] **Step 2: Verify install links the new skill + command**

```bash
bin/install.sh --home "$(mktemp -d)"
```
Expected: output includes `linked license-compliance-auditor` and `linked license-audit.md`, no conflicts.

- [ ] **Step 3: Full check + install test + commit**

Run: `make check && make test`
Expected: PASS.

```bash
git add CHANGELOG.md README.md
git commit -m "docs(license-audit): changelog entry; mark skill draft pending pressure-test"
```

---

### Task 12: Pressure-test the skill (RED → GREEN → REFACTOR) — the "done" gate

**Files:**
- Modify: `skills/license-compliance-auditor/SKILL.md` / `references/*` (as the test surfaces gaps)
- Modify: `CHANGELOG.md` (drop the "Draft" marker once verified)

**Interfaces:** none (behavioral verification per superpowers:writing-skills).

- [ ] **Step 1: RED — baseline without the skill**

Dispatch a fresh subagent (no skill) at 2–3 fixtures (`ofl-font-missing-text`, `mit-with-agpl-dep`, `ccbync-asset-commercial`) asking "audit this repo for license compliance." Record how it fails: misses obligations, makes legal conclusions, or creates issues unprompted.

- [ ] **Step 2: GREEN — with the skill**

Dispatch a fresh subagent *with* the skill at the same fixtures. Verify it: detects the seeded issue, assigns a defensible risk level, preserves uncertainty (evidence + confidence + review notes), reports coverage gaps when scanners are absent, produces the terminal report + `.md`/`.json`, and **asks before creating issues** (never creates unprompted).

- [ ] **Step 3: REFACTOR — fix gaps**

If the agent overclaims, skips a phase, or misses the issue gate, tighten SKILL.md / references (not the scripts unless a bug surfaces). Re-run Step 2 until behavior is correct. Document the RED/GREEN outcomes in `tests/README.md`.

- [ ] **Step 4: Drop the draft marker + final commit**

Run: `make check && make test`
Expected: PASS.

```bash
git add -A
git commit -m "test(license-audit): pressure-test skill; mark ready (drop draft marker)"
```

---

## Self-Review

**Spec coverage:** shape (skill + command) → Tasks 9–10; full script suite → Tasks 3–7; Python stdlib-only → Global Constraints; findings schema/reports → Tasks 1, 6; references (7 incl. output-schema) → Tasks 1, 8; terminal-first UX → Task 6 + SKILL.md; GitHub-issue gate → Tasks 7, 9; legal boundaries → Tasks 8 (human-review-boundaries), 9; risk taxonomy → Task 8; 14 fixtures + tests → Task 2; graceful degradation → detect_tools + tool-map + SKILL.md rules; pressure-test → Task 12; `make check` integration → Task 3. No spec section is unmapped.

**Placeholder scan:** script/test steps carry complete code; reference/SKILL/command steps are content specs (required sections + must-include facts), not "add appropriate X" placeholders. Fixture contents are enumerated in the Task 2 table.

**Type consistency:** the finding keys defined in Task 1 (`id, type, item, path, version, ecosystem, source, license_expression, usage, compatibility_risk, unmet_obligation, evidence, confidence, risk_level, review_notes, recommended_action`) are used consistently by `normalize_findings` (Task 5), `render_report` (Task 6), and `issue_drafts` (Task 7). Function names are stable: `detect`, `inventory`, `normalize`/`canonical_spdx`, `render`/`terminal_report`/`markdown_report`, `group`/`write_drafts`/`draft_markdown`. `selftest.py` discovers `tests/test_*.py` — the test filenames match.
