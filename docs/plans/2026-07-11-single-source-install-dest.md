# Single-source install-destination mapping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `capabilities.json` the only hand-edited source of the type→install-destination mapping by generating a committed, Bash-readable TSV manifest that `install.sh`/`doctor.sh` consume, killing the 3× duplication without adding a runtime python/jq dependency.

**Architecture:** `bin/check-inventory.py` gains an `--emit-manifest` generator and a `--check-manifest` drift guard (run in `make check`). The generated `install-manifest.tsv` is read by a new shared bash reader `bin/lib/manifest.sh`, which replaces the three duplicated enumerators in `install.sh` (linking + `--adopt`) and `doctor.sh`. Item discovery, skip rules, and destination shape live only in the generator; scripts keep only their own presentation.

**Tech Stack:** Python 3 stdlib (generator/validator), Bash (installer, doctor, reader), TSV data file.

**Design:** [`docs/design/2026-07-11-single-source-install-dest.md`](../design/2026-07-11-single-source-install-dest.md)

## Global Constraints

- **No runtime dependency added to `install.sh`/`doctor.sh`.** They may read the committed TSV but must NOT invoke `python3` or `jq` to run. python3 is used only to *regenerate* the manifest (dev/CI).
- **`check-inventory.py` stays stdlib-only** (no new imports beyond the current `argparse json os re subprocess sys`).
- **Byte-identical output** from `install.sh` and `doctor.sh` for the populated case (all categories non-empty, as in every fixture and the real repo). The existing `bin/test-install.sh` and `bin/test-doctor.sh` suites are the safety net and must pass unchanged. (Benign, intentional difference: a category with *zero* items no longer prints its header — see Task 5.)
- **Installable types only:** `skill`, `agent`, `command`, `global-guidance`. `script` and `contract` are never installed.
- **Manifest is generated + committed:** first line is the banner `# GENERATED from capabilities.json — do not edit; run 'make manifest'`.
- **Footgun (#29):** any new `bin/*.sh` must be in `capabilities.json`'s `not_a_capability` ledger or `make check` fails. `bin/lib/manifest.sh` needs a ledger row (Task 3).
- **Commit style:** every commit ends with the repo's two trailers:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EQg6eYnGsgGU2Vhk6Q8DkT
  ```
  (Omitted from the `git commit` snippets below for brevity — add them.)
- **Branch:** `chore/79-single-source-install-dest`. `make check` green before every commit; do not push/merge without operator approval.

---

### Task 1: Manifest generator (`--emit-manifest`)

Add the projection from `capabilities.json` to TSV. Pure generation, no drift check yet.

**Files:**
- Modify: `bin/check-inventory.py` (add generator functions + `--emit-manifest` CLI)
- Test: `bin/test-check-inventory.sh` (new "manifest generation" block)

**Interfaces:**
- Produces (Python, module-level in `check-inventory.py`):
  - `INSTALL_TYPES = ("skill", "agent", "command", "global-guidance")`
  - `render_manifest(caps) -> str` — full manifest text (banner + rows + trailing `\n`)
  - `build_manifest(caps) -> list[tuple]` — sorted `(provider, category, name, src_rel, dest_rel)` rows
- CLI: `check-inventory.py --emit-manifest [PATH]` writes the manifest (default `install-manifest.tsv` under `--root`; `-` = stdout). Emission does NOT run validation (so `new.sh` can emit from a draft row).

- [ ] **Step 1: Write the failing test**

Add to `bin/test-check-inventory.sh` just before the final `echo` summary (the fixture `mkfixture` builds demo skill / foo command / claude+agents global-guidance):

```bash
echo "manifest generation:"
REPO="$TMP/emit"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-manifest - 2>&1)"
check "banner is first line" contains "# GENERATED from capabilities.json" "$out"
check "skill row emitted" contains "$(printf 'claude\tskill\tdemo\tskills/demo\tskills/demo')" "$out"
check "command row emitted" contains "$(printf 'claude\tcommand\tfoo\tcommands/foo.md\tcommands/foo.md')" "$out"
check "claude global row: dest is basename" contains "$(printf 'claude\tglobal-guidance\tclaude\tglobal/CLAUDE.md\tCLAUDE.md')" "$out"
check "codex global row: provider is codex" contains "$(printf 'codex\tglobal-guidance\tagents\tglobal/AGENTS.md\tAGENTS.md')" "$out"
check "no script/contract rows" not_contains "docs/skill-portability-audit.md" "$out"
# deterministic ordering: claude skill < claude command < claude global < codex global
check "codex row is last" test "$(printf '%s\n' "$out" | tail -1)" = "$(printf 'codex\tglobal-guidance\tagents\tglobal/AGENTS.md\tAGENTS.md')"

REPO="$TMP/emit-override"
mkfixture "$REPO"
python3 -c '
import json
p = "'"$REPO"'/capabilities.json"
d = json.load(open(p, encoding="utf-8"))
for c in d["capabilities"]:
    if c["name"] == "demo":
        c["install_destination"] = "skills/renamed-demo"
json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
'
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-manifest - 2>&1)"
check "explicit install_destination override is emitted verbatim" contains "$(printf 'claude\tskill\tdemo\tskills/demo\tskills/renamed-demo')" "$out"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `--emit-manifest` is an unrecognized argument (nonzero exit / argparse error in `$out`).

- [ ] **Step 3: Write minimal implementation**

In `bin/check-inventory.py`, add after the `SEMVER = ...` constant block (top of file):

```python
INSTALL_TYPES = ("skill", "agent", "command", "global-guidance")
_PROVIDER_RANK = {"claude": 0, "codex": 1}
_CATEGORY_RANK = {"skill": 0, "agent": 1, "command": 2, "global-guidance": 3}
# global-guidance name -> provider (mirrors the gg map in check_completeness_clean)
_GG_PROVIDER = {"claude": "claude", "agents": "codex"}
MANIFEST_BANNER = ("# GENERATED from capabilities.json — do not edit; "
                   "run 'make manifest'")


def _install_row(cap):
    """(provider, category, name, src_rel, dest_rel) for an installable
    capability, or None if its type is not installed or it is a _template."""
    t = cap.get("type")
    if t not in INSTALL_TYPES:
        return None
    name = cap.get("name")
    src_rel = cap.get("path")
    if not isinstance(name, str) or not isinstance(src_rel, str):
        return None
    if name.startswith(("_", ".")):
        return None
    if t == "global-guidance":
        provider = _GG_PROVIDER.get(name)
        if provider is None:
            return None
        dest_rel = os.path.basename(src_rel)
    else:
        provider = "claude"
        dest_rel = src_rel
    override = cap.get("install_destination")
    if override:
        dest_rel = override  # honored verbatim; latent (no row sets it today)
    return (provider, t, name, src_rel, dest_rel)


def build_manifest(caps):
    rows = [r for r in (_install_row(c) for c in caps) if r]
    rows.sort(key=lambda r: (_PROVIDER_RANK.get(r[0], 99),
                             _CATEGORY_RANK.get(r[1], 99), r[2]))
    return rows


def render_manifest(caps):
    lines = [MANIFEST_BANNER]
    lines += ["\t".join(row) for row in build_manifest(caps)]
    return "\n".join(lines) + "\n"
```

Then wire the CLI. In `main()`, extend the parser (after the existing `--root` arg):

```python
    parser.add_argument("--emit-manifest", nargs="?", const="", default=None,
                        metavar="PATH",
                        help="write the install manifest (default "
                             "install-manifest.tsv under --root; '-' = stdout)")
```

And, immediately after `dict_caps = [c for c in caps if isinstance(c, dict)]` is computed — BUT the emit path must run before the normal checks and return early. Restructure `main()`'s body so that right after `caps, ledger = load_inventory(root)` succeeds and `dict_caps` is built, insert:

```python
    if args.emit_manifest is not None:
        text = render_manifest(dict_caps)
        if args.emit_manifest == "-":
            sys.stdout.write(text)
        else:
            dest = args.emit_manifest or os.path.join(root, "install-manifest.tsv")
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(text)
        return 0
```

Concretely, `main()` becomes (showing the load + branch ordering):

```python
    try:
        caps, ledger = load_inventory(root)
        version = read_version(root)
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    dict_caps = [c for c in caps if isinstance(c, dict)]
    if args.emit_manifest is not None:
        text = render_manifest(dict_caps)
        if args.emit_manifest == "-":
            sys.stdout.write(text)
        else:
            dest = args.emit_manifest or os.path.join(root, "install-manifest.tsv")
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(text)
        return 0
    errors = []
    errors += check_schema(caps, version)
    errors += check_completeness_clean(dict_caps, root)
    errors += check_completeness_fuzzy(dict_caps, ledger, root)
    errors += check_paths(dict_caps, root)
    errors += check_crosschecks(dict_caps, root)
    errors += check_bound_table(dict_caps, root)
    # NOTE: later tasks append more checks here.
    ...
```

(`version` is unused on the emit path — that's fine; it is still read to fail fast on a missing VERSION.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — the new "manifest generation:" checks all `✓`, final line `tests: N passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat: check-inventory.py --emit-manifest generates install-manifest TSV (#79)"
```

---

### Task 2: Drift guard (`--check-manifest`) + commit the real manifest

Add the CI drift check and generate the committed `install-manifest.tsv` for this repo.

**Files:**
- Modify: `bin/check-inventory.py` (add `check_manifest` + `--check-manifest` CLI)
- Modify: `bin/check.sh:312` (pass `--check-manifest`)
- Create: `install-manifest.tsv` (generated, repo root)
- Test: `bin/test-check-inventory.sh` (new "manifest drift guard" block)

**Interfaces:**
- Consumes: `render_manifest` (Task 1)
- Produces: `check_manifest(caps, root) -> list[str]` errors; `--check-manifest` flag appends them to the validation run.

- [ ] **Step 1: Write the failing test**

Add to `bin/test-check-inventory.sh` after the Task 1 block:

```bash
echo "manifest drift guard:"
REPO="$TMP/manifest-ok"
mkfixture "$REPO"
python3 "$VALIDATOR" --root "$REPO" --emit-manifest >/dev/null
out="$(python3 "$VALIDATOR" --root "$REPO" --check-manifest 2>&1)"
status=$?
check "matching manifest passes --check-manifest" test "$status" -eq 0

REPO="$TMP/manifest-missing"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-manifest 2>&1)"
status=$?
check "missing manifest fails" test "$status" -ne 0
check "missing manifest names the fix" contains "install-manifest.tsv: missing" "$out"

REPO="$TMP/manifest-stale"
mkfixture "$REPO"
python3 "$VALIDATOR" --root "$REPO" --emit-manifest >/dev/null
printf 'claude\tskill\tbogus\tskills/bogus\tskills/bogus\n' >>"$REPO/install-manifest.tsv"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-manifest 2>&1)"
status=$?
check "stale manifest fails" test "$status" -ne 0
check "stale manifest names the fix" contains "install-manifest.tsv: stale" "$out"

REPO="$TMP/manifest-off"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "without --check-manifest, missing manifest is ignored" test "$status" -eq 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `--check-manifest` unrecognized.

- [ ] **Step 3: Write minimal implementation**

In `bin/check-inventory.py`, add after `render_manifest`:

```python
def check_manifest(caps, root):
    path = os.path.join(root, "install-manifest.tsv")
    want = render_manifest(caps)
    if not os.path.isfile(path):
        return ["install-manifest.tsv: missing — run 'make manifest'"]
    with open(path, encoding="utf-8") as fh:
        have = fh.read()
    if have != want:
        return ["install-manifest.tsv: stale — run 'make manifest'"]
    return []
```

Add the flag in `main()`'s parser:

```python
    parser.add_argument("--check-manifest", action="store_true",
                        help="also verify install-manifest.tsv matches the "
                             "inventory (drift guard)")
```

And append the check in `main()` after `check_bound_table`:

```python
    errors += check_bound_table(dict_caps, root)
    if args.check_manifest:
        errors += check_manifest(dict_caps, root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — "manifest drift guard:" checks all `✓`.

- [ ] **Step 5: Generate the real manifest and wire check.sh**

Generate the committed manifest for this repo:

```bash
python3 bin/check-inventory.py --emit-manifest
```

Then edit `bin/check.sh` line 312, changing:

```bash
  if inv_out="$(python3 bin/check-inventory.py --root . 2>&1)"; then
```
to:
```bash
  if inv_out="$(python3 bin/check-inventory.py --root . --check-manifest 2>&1)"; then
```

Verify the generated manifest looks right (expect skills alphabetical, then agents, then commands, then `claude` global, then `codex` AGENTS.md):

```bash
head -3 install-manifest.tsv; echo ...; tail -1 install-manifest.tsv
```
Expected: line 1 is the banner; line 2 a `claude<TAB>skill<TAB>...` row; last line `codex<TAB>global-guidance<TAB>agents<TAB>global/AGENTS.md<TAB>AGENTS.md`.

- [ ] **Step 6: Verify make check catches drift, then commit**

```bash
make check                                    # expect: All checks passed.
printf 'x\ty\tz\ta\tb\n' >> install-manifest.tsv
make check 2>&1 | grep -q "install-manifest.tsv: stale" && echo DRIFT-CAUGHT
git checkout install-manifest.tsv             # restore
make check                                    # green again
git add bin/check-inventory.py bin/check.sh bin/test-check-inventory.sh install-manifest.tsv
git commit -m "feat: manifest drift guard in make check + commit install-manifest.tsv (#79)"
```
Expected: `DRIFT-CAUGHT` prints; final `make check` is green.

---

### Task 3: Shared bash reader (`bin/lib/manifest.sh`) + ledger entry

**Files:**
- Create: `bin/lib/manifest.sh`
- Modify: `capabilities.json` (add `not_a_capability` row)
- Test: `bin/test-check-inventory.sh` already validates the ledger via `make check`; add a focused reader check to a new `bin/test-manifest-lib.sh` and register it in `Makefile` + `bin/check.sh` test list.

**Interfaces:**
- Produces (Bash): `each_manifest_item REPO_ROOT CALLBACK` — invokes `CALLBACK PROVIDER CATEGORY NAME SRC_ABS DEST_REL` for each data row in file order, skipping the `#` banner and blank lines. `SRC_ABS = REPO_ROOT/src_rel`.

- [ ] **Step 1: Write the failing test**

Create `bin/test-manifest-lib.sh`:

```bash
#!/usr/bin/env bash
#
# test-manifest-lib.sh — unit-test the shared manifest reader against a
# throwaway TSV. Nothing touches this repo's real install-manifest.tsv.
#
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=bin/lib/manifest.sh
source "$REPO_ROOT/bin/lib/manifest.sh"

pass=0 fail=0
check() { local d="$1"; shift; if "$@"; then printf '  ✓ %s\n' "$d"; pass=$((pass+1)); else printf '  ✗ %s\n' "$d"; fail=$((fail+1)); fi; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cat >"$TMP/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo

codex	global-guidance	agents	global/AGENTS.md	AGENTS.md
TSV

LINES=""
collect() { LINES="${LINES}${1}|${2}|${3}|${4}|${5}"$'\n'; }
each_manifest_item "$TMP" collect

echo "manifest reader:"
check "banner line skipped" not_grep "# GENERATED" "$LINES"
check "blank line skipped (exactly 2 rows)" test "$(printf '%s' "$LINES" | grep -c '|')" -eq 2
check "skill row: src is absolutized" grep_q "claude|skill|demo|$TMP/skills/demo|skills/demo" "$LINES"
check "codex row present" grep_q "codex|global-guidance|agents|$TMP/global/AGENTS.md|AGENTS.md" "$LINES"
check "missing manifest is a no-op" each_manifest_item "$TMP/nope" collect

grep_q() { grep -qF -- "$1" <<<"$2"; }
not_grep() { ! grep -qF -- "$1" <<<"$2"; }

echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
```

Note: define `grep_q`/`not_grep` BEFORE the `check` calls that use them — move those two function definitions above the `echo "manifest reader:"` line when writing the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-manifest-lib.sh`
Expected: FAIL — `bin/lib/manifest.sh` does not exist (source error).

- [ ] **Step 3: Write minimal implementation**

Create `bin/lib/manifest.sh`:

```bash
#!/usr/bin/env bash
#
# manifest.sh — shared reader for install-manifest.tsv (generated from
# capabilities.json by bin/check-inventory.py --emit-manifest). Sourced by
# install.sh and doctor.sh so the type->destination mapping and the item list
# live in exactly one place.
#
# each_manifest_item REPO_ROOT CALLBACK
#   For every data row, invokes:
#     CALLBACK PROVIDER CATEGORY NAME SRC_ABS DEST_REL
#   in file order. Skips the '#' banner and blank lines. SRC_ABS is
#   REPO_ROOT/<src_rel>; DEST_REL is relative to the provider home.
#   A missing manifest is a silent no-op (return 0).

each_manifest_item() {
  local repo_root="$1" cb="$2" manifest provider category name src_rel dest_rel
  manifest="$repo_root/install-manifest.tsv"
  [ -f "$manifest" ] || return 0
  while IFS=$'\t' read -r provider category name src_rel dest_rel; do
    case "$provider" in '' | '#'*) continue ;; esac
    "$cb" "$provider" "$category" "$name" "$repo_root/$src_rel" "$dest_rel"
  done <"$manifest"
}
```

Add the ledger row to `capabilities.json` `not_a_capability` (keep JSON valid, 2-space indent to match the file):

```json
    {
      "path": "bin/lib/manifest.sh",
      "reason": "shared bash reader for the generated install manifest; machinery consumed by install.sh/doctor.sh, not a capability an agent invokes."
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bin/test-manifest-lib.sh          # expect: tests: N passed, 0 failed
python3 bin/check-inventory.py --root . --check-manifest   # expect: OK (ledger accepts bin/lib/manifest.sh)
```
Expected: reader tests pass; inventory check exits 0 (the new `bin/*.sh` is ledgered, so the fuzzy gate is satisfied).

- [ ] **Step 5: Register the new test suite**

In `Makefile`, add `bin/test-manifest-lib.sh` to the `test:` target list (after `bin/test-check-inventory.sh`). In `bin/check.sh`, add it wherever the test suite discovers/lists `bin/test-*.sh` (grep `test-check-inventory` in `bin/check.sh` to find the list; if discovery is glob-based, no edit is needed — verify with `make check`).

- [ ] **Step 6: Commit**

```bash
make check                        # expect: All checks passed.
git add bin/lib/manifest.sh bin/test-manifest-lib.sh capabilities.json Makefile bin/check.sh
git commit -m "feat: bin/lib/manifest.sh shared reader + ledger row (#79)"
```

---

### Task 4: Rewire `doctor.sh` onto the reader

Doctor is read-only (no mkdir/prune interleaving), so it is the lower-risk consumer to convert first.

**Files:**
- Modify: `bin/doctor.sh` (source the reader; replace `claude_section`/`codex_section` item loops)
- Modify: `bin/test-doctor.sh` (fixture builder: add manifest + copy reader)

**Interfaces:**
- Consumes: `each_manifest_item` (Task 3); existing `check_item`, `sweep_dir`.

- [ ] **Step 1: Update the doctor fixture builder to fail-first**

In `bin/test-doctor.sh`, find the fixture builder (grep `mkdir -p` / the function that creates `skills/`, `agents/`, `commands/`, `global/`). Add, at the end of that builder, a copy of the reader and a matching manifest:

```bash
  mkdir -p "$r/bin/lib"
  cp "$REPO_ROOT/bin/lib/manifest.sh" "$r/bin/lib/manifest.sh"
  cat >"$r/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo
claude	agent	demo	agents/demo.md	agents/demo.md
claude	command	demo	commands/demo.md	commands/demo.md
claude	global-guidance	claude	global/CLAUDE.md	CLAUDE.md
codex	global-guidance	agents	global/AGENTS.md	AGENTS.md
TSV
```

Adjust the exact item names/paths to whatever `bin/test-doctor.sh`'s fixture actually creates (match its existing `skills/<x>`, `agents/<x>.md`, etc.). If the fixture omits AGENTS.md in some cases, omit the codex row there too.

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test-doctor.sh`
Expected: FAIL — `doctor.sh` still uses its own loops and does not source the reader, so nothing consumes the new manifest yet; but the immediate failure is that `doctor.sh` has not changed. (If it still passes here because doctor hasn't changed, that's expected — the RED signal for this task is Step 4's diff-nothing check; proceed to Step 3.)

- [ ] **Step 3: Rewire `doctor.sh`**

After the `REPO_ROOT=...` line near the top of `bin/doctor.sh`, add:

```bash
# shellcheck source=bin/lib/manifest.sh
source "$REPO_ROOT/bin/lib/manifest.sh"
```

Add two module-level callbacks (place them just above `claude_section`):

```bash
# _doctor_item PROVIDER CATEGORY NAME SRC DEST_REL — manifest callback that
# diagnoses one item for the given home. Label = the repo-relative source path,
# matching the labels doctor.sh printed before (skills/<n>, agents/<n>.md, ...).
_doctor_claude_cb() {
  [ "$1" = claude ] || return 0
  check_item "${4#"$REPO_ROOT"/}" "$4" "$CLAUDE_HOME/$5"
}
_doctor_codex_cb() {
  [ "$1" = codex ] || return 0
  CODEX_ITEMS=$((CODEX_ITEMS + 1))
  check_item "${4#"$REPO_ROOT"/}" "$4" "$CODEX_HOME/$5"
}
```

Replace the body of `claude_section()` — the three `for` loops and the `if [ -f .../global/CLAUDE.md ]` block — with a single reader call (keep the `echo` header and the three `sweep_dir` calls):

```bash
claude_section() {
  echo
  echo "claude home ($CLAUDE_HOME):"
  each_manifest_item "$REPO_ROOT" _doctor_claude_cb
  sweep_dir "$CLAUDE_HOME/skills" "skills"
  sweep_dir "$CLAUDE_HOME/agents" "agents"
  sweep_dir "$CLAUDE_HOME/commands" "commands"
}
```

Replace `codex_section()`:

```bash
codex_section() {
  echo
  echo "codex home ($CODEX_HOME):"
  CODEX_ITEMS=0
  each_manifest_item "$REPO_ROOT" _doctor_codex_cb
  [ "$CODEX_ITEMS" -gt 0 ] || echo "  - no global/AGENTS.md in this repo"
}
```

Add `CODEX_ITEMS=0` to the counter-init line near the top (alongside `current_count=0 ...`).

- [ ] **Step 4: Run to verify it passes**

```bash
bin/test-doctor.sh
```
Expected: PASS — all existing doctor checks `✓`, proving byte-identical classification/labels through the reader.

- [ ] **Step 5: Sanity-check real output is unchanged**

```bash
git stash                                   # temporarily restore pre-change doctor.sh? -- instead:
```
Simpler diff without stashing: capture current output, compare to the committed version's output:

```bash
bin/doctor.sh --home "$HOME/.claude" > /tmp/doctor.after 2>&1 || true
git show HEAD:bin/doctor.sh > /tmp/doctor.old.sh && chmod +x /tmp/doctor.old.sh
# (only if convenient; the test suite in Step 4 is the authoritative check)
```
If the real `~/.claude` is installed, `bin/doctor.sh` output should be identical to before. The test suite is the binding check; this step is a spot confirmation only.

- [ ] **Step 6: Commit**

```bash
make check
git add bin/doctor.sh bin/test-doctor.sh
git commit -m "refactor: doctor.sh reads install-manifest via shared reader (#79)"
```

---

### Task 5: Rewire `install.sh` onto the reader

Convert both the linking path (`install_claude`/`install_codex`) and the `--adopt` enumerator (`each_expected_item`). This is the highest-risk task — the streaming installer must reproduce headers, `mkdir`, and `--prune` sweeps in the current order.

**Files:**
- Modify: `bin/install.sh`
- Modify: `bin/test-install.sh` (fixture: add manifest + copy reader)

**Interfaces:**
- Consumes: `each_manifest_item` (Task 3); existing `link_item`, `prune_dir`, `prune_path`.

- [ ] **Step 1: Update the install fixture builder to fail-first**

In `bin/test-install.sh`, extend `build_repo()` (after it writes `global/AGENTS.md`):

```bash
  mkdir -p "$r/bin/lib"
  cp "$REPO_ROOT/bin/lib/manifest.sh" "$r/bin/lib/manifest.sh"
  cat >"$r/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo
claude	agent	demo	agents/demo.md	agents/demo.md
claude	command	demo	commands/demo.md	commands/demo.md
claude	global-guidance	claude	global/CLAUDE.md	CLAUDE.md
codex	global-guidance	agents	global/AGENTS.md	AGENTS.md
TSV
```

- [ ] **Step 2: Run to verify current state**

Run: `bin/test-install.sh`
Expected: PASS still (install.sh unchanged yet) — the fixture now carries a manifest the old code ignores. This sets up the fixture; the behavioral RED is that install.sh does not yet use it. Proceed.

- [ ] **Step 3: Rewire `install.sh` — source + streaming installer**

After the `REPO_ROOT=...` line, add:

```bash
# shellcheck source=bin/lib/manifest.sh
source "$REPO_ROOT/bin/lib/manifest.sh"
```

Add presentation helpers + the streaming callback (place above the `install_claude` definition):

```bash
_provider_label() { case "$1" in claude) printf Claude ;; codex) printf Codex ;; esac; }
_category_label() {
  case "$1" in
    skill) printf skills ;;
    agent) printf agents ;;
    command) printf commands ;;
    global-guidance) printf 'global instructions' ;;
  esac
}

# Streaming installer state: headers/mkdir emitted on category change; prune
# runs once per category in _finalize_group.
_CUR_KEY="" _CUR_PRUNE_DIR="" _CUR_PRUNE_PATH=""

_finalize_group() {
  [ -n "$_CUR_KEY" ] || return 0
  if $PRUNE; then
    if [ -n "$_CUR_PRUNE_DIR" ]; then
      prune_dir "$_CUR_PRUNE_DIR"
    elif [ -n "$_CUR_PRUNE_PATH" ]; then
      prune_path "$_CUR_PRUNE_PATH"
    fi
  fi
}

_install_cb() {
  local provider="$1" category="$2" name="$3" src="$4" dest_rel="$5" home sub
  case "$provider" in claude) home="$CLAUDE_HOME" ;; codex) home="$CODEX_HOME" ;; esac
  case "$PROVIDER" in
    claude) [ "$provider" = claude ] || return 0 ;;
    codex) [ "$provider" = codex ] || return 0 ;;
  esac
  local key="$provider/$category"
  if [ "$key" != "$_CUR_KEY" ]; then
    _finalize_group
    _CUR_KEY="$key"
    printf '%s %s:\n' "$(_provider_label "$provider")" "$(_category_label "$category")"
    case "$dest_rel" in
      */*)
        sub="${dest_rel%/*}"
        mkdir -p "$home/$sub"
        _CUR_PRUNE_DIR="$home/$sub" _CUR_PRUNE_PATH=""
        ;;
      *)
        _CUR_PRUNE_DIR="" _CUR_PRUNE_PATH="$home/$dest_rel"
        ;;
    esac
  fi
  link_item "$src" "$home/$dest_rel"
}

install_surfaces() {
  _CUR_KEY="" _CUR_PRUNE_DIR="" _CUR_PRUNE_PATH=""
  each_manifest_item "$REPO_ROOT" _install_cb
  _finalize_group
}
```

Replace `each_expected_item()` (the whole function) with a manifest-driven version. It must honor the `$PROVIDER` selection and call `cb "$src" "$dest_abs"`:

```bash
# each_expected_item CALLBACK — invoke CALLBACK "$src" "$dest" for every
# expected (src, dest) pair install_surfaces would link for the selected
# $PROVIDER, in manifest order. Read-only: no output, no mkdir. Used by --adopt.
_EACH_CB=""
_each_expected_cb() {
  local provider="$1" dest_rel="$5" src="$4" home
  case "$provider" in claude) home="$CLAUDE_HOME" ;; codex) home="$CODEX_HOME" ;; esac
  case "$PROVIDER" in
    claude) [ "$provider" = claude ] || return 0 ;;
    codex) [ "$provider" = codex ] || return 0 ;;
  esac
  "$_EACH_CB" "$src" "$home/$dest_rel"
}
each_expected_item() {
  _EACH_CB="$1"
  each_manifest_item "$REPO_ROOT" _each_expected_cb
}
```

Delete the now-dead `install_claude()` and `install_codex()` functions, and replace the final dispatch:

```bash
case "$PROVIDER" in
  claude)
    install_claude
    ;;
  codex)
    install_codex
    ;;
  all)
    install_claude
    install_codex
    ;;
esac
```
with:
```bash
install_surfaces
```

(The `$PROVIDER` filter now lives inside `_install_cb`, so a single `install_surfaces` call covers claude / codex / all.)

- [ ] **Step 4: Run to verify it passes**

```bash
bin/test-install.sh
```
Expected: PASS — every existing check `✓`, including the `--adopt`, `--prune`, conflict, and "4 already current" cases. This proves byte-identical linking + enumeration through the reader.

- [ ] **Step 5: Confirm the `--home` doc comment still holds**

The header comment block in `install.sh` (lines ~9-16) describes the type→dest mapping in prose; it is still accurate. No change needed, but re-read it to confirm it matches the manifest's derivation (skill dir, agent/command `.md`, `global/CLAUDE.md`→`CLAUDE.md`, `global/AGENTS.md`→`AGENTS.md`).

- [ ] **Step 6: Commit**

```bash
make check
git add bin/install.sh bin/test-install.sh
git commit -m "refactor: install.sh links + adopts via install-manifest reader (#79)"
```

---

### Task 6: Regenerate on scaffold, `make manifest`, and docs

Close the loop so adding a capability regenerates the manifest, and document the new artifact.

**Files:**
- Modify: `bin/new.sh` (regen after appending the row)
- Modify: `Makefile` (add `manifest` target)
- Modify: `docs/capability-inventory.md` (update the `install_destination` caveat; document `install-manifest.tsv`)
- Modify: `CHANGELOG.md`
- Test: `bin/test-check-inventory.sh` (extend the existing "new.sh appends a valid stub row" block to assert the manifest regenerates)

**Interfaces:**
- Consumes: `check-inventory.py --emit-manifest` (Task 1).

- [ ] **Step 1: Write the failing test**

In `bin/test-check-inventory.sh`, inside the existing "new.sh appends a valid stub row:" block, after the `bin/new.sh skill widget` invocation and its commit, add:

```bash
check "new.sh regenerated the manifest with the new skill" contains "$(printf 'claude\tskill\twidget\tskills/widget\tskills/widget')" "$(cat "$REPO/install-manifest.tsv")"
```

That fixture (`$TMP/newsh`) copies `bin/new.sh` and `bin/check-inventory.py` into the fixture — verify `check-inventory.py` is copied there too; if not, add `cp "$REPO_ROOT/bin/check-inventory.py" "$REPO/bin/check-inventory.py"` alongside the existing `cp .../new.sh` line so `new.sh` can invoke it.

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `new.sh` does not yet regenerate the manifest (file absent or lacks the `widget` row).

- [ ] **Step 3: Implement new.sh regen**

In `bin/new.sh`, after the inline python block that appends the capabilities.json row and prints "Added a draft capabilities.json row...", add:

```bash
  if [ -f capabilities.json ] && command -v python3 >/dev/null 2>&1 && [ -f bin/check-inventory.py ]; then
    python3 bin/check-inventory.py --emit-manifest >/dev/null 2>&1 &&
      echo "Regenerated install-manifest.tsv." ||
      echo "Note: could not regenerate install-manifest.tsv; run 'make manifest'." >&2
  fi
```

Place it so it runs only on the branch where a row was actually appended (inside the same guard that appended the row).

- [ ] **Step 4: Add the `make manifest` target**

In `Makefile`, add `manifest` to `.PHONY` and a target + help line:

```makefile
manifest:
	python3 bin/check-inventory.py --emit-manifest
	@echo "wrote install-manifest.tsv"
```
And in `help:`:
```makefile
	@echo "make manifest           regenerate install-manifest.tsv from capabilities.json"
```

- [ ] **Step 5: Update docs**

In `docs/capability-inventory.md`, update the `install_destination` row (currently: "optional `~/.claude/...`-style annotation; **not currently validated by CI**"). Replace with:

```markdown
| `install_destination` | no | authored | optional per-row override of the derived destination. Destinations are otherwise derived from `type` into the generated `install-manifest.tsv`, which `make check` drift-checks and `install.sh`/`doctor.sh` consume (see #79). |
```

Add a short paragraph (near where the file's outputs/consumers are described) documenting `install-manifest.tsv`:

```markdown
### `install-manifest.tsv` (generated)

`bin/check-inventory.py --emit-manifest` projects the installable capabilities
(`skill`/`agent`/`command`/`global-guidance`) into a committed tab-separated
manifest — `provider  category  name  src_rel  dest_rel`. `install.sh` and
`doctor.sh` read it via `bin/lib/manifest.sh`, so the type→destination mapping
lives only in the generator. `make check` regenerates it in memory and fails on
drift; run `make manifest` (or `bin/new.sh`, which regenerates automatically) to
refresh it. Never hand-edit it.
```

Also update the FOOTGUN note there (if present) to mention that adding a skill also refreshes the manifest (automatic via `new.sh` / `make manifest`).

In `CHANGELOG.md`, add under the current unreleased/next section:

```markdown
- **Single-sourced install destinations (#79).** `capabilities.json` is now the
  only hand-edited source of the type→install-destination mapping. A generated,
  committed `install-manifest.tsv` (drift-checked by `make check`) is consumed by
  `install.sh` and `doctor.sh` via `bin/lib/manifest.sh`, removing the mapping's
  3× duplication without adding a runtime python/jq dependency.
```

- [ ] **Step 6: Run tests and commit**

```bash
bin/test-check-inventory.sh       # expect: new.sh manifest-regen check passes
make manifest                     # ensure the committed manifest is fresh
make check                        # expect: All checks passed.
make test                         # expect: all suites green
git add bin/new.sh Makefile docs/capability-inventory.md CHANGELOG.md bin/test-check-inventory.sh install-manifest.tsv
git commit -m "feat: new.sh + make manifest regen; document install-manifest.tsv (#79)"
```

---

## Self-Review

**Spec coverage:**
- Manifest file (spec §Architecture 1) → Task 1 (generation), Task 2 (commit).
- Generator + drift guard (spec §Architecture 2) → Tasks 1, 2.
- Shared reader (spec §Architecture 3) → Task 3.
- `new.sh` regen (spec §Architecture 4) → Task 6.
- `install_destination` override (spec Decision 4) → Task 1 (`_install_row` override + test).
- Byte-identical output (spec §Byte-identical) → Tasks 4, 5 pass existing suites.
- Rewire install (linking + adopt) and doctor (spec §Scope In) → Tasks 4, 5.
- Ledger entry for `bin/lib/manifest.sh` (spec §Architecture 3 footgun) → Task 3.
- `make manifest` target (spec §defaults) → Task 6.
- Acceptance criteria (spec §Acceptance) → covered by Tasks 2 (drift), 4/5 (green suites), 6 (edit-only-json via new.sh).

**Placeholder scan:** No TBD/TODO; all code and commands are concrete. Fixture item names in Tasks 4-5 are marked "adjust to match the actual fixture" because those two test files' exact fixture item names must be read at implementation time — the implementer confirms them against the file (the shape is fully specified).

**Type consistency:** `each_manifest_item REPO_ROOT CALLBACK` with callback arity `(provider, category, name, src_abs, dest_rel)` is used identically in Tasks 3 (definition/test), 4 (doctor callbacks), and 5 (install callbacks). `render_manifest`/`build_manifest`/`check_manifest`/`_install_row` names are consistent across Tasks 1-2. Column order `provider  category  name  src_rel  dest_rel` is identical in the generator, the reader test, and both fixtures.
