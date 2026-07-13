# Install compatible shared Agent Skills for Codex — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bin/install.sh --provider codex` symlinks the two wave-1 Codex-eligible skills (`verify-then-commit`, `fork-pr-flow`) into the officially documented Codex Agent Skills home (`~/.agents/skills`), driven entirely by a `capabilities.json` metadata field — no hard-coded skill list — with `doctor.sh` diagnostics, generated docs, and a real Codex session confirming discovery + invocation.

**Architecture:** `capabilities.json`'s existing `provider.codex` enum gains real use: `"installed"` on a `type: skill` row means "symlink this skill for Codex too." `bin/check-inventory.py`'s manifest generator (`_install_row` → `_install_rows`) emits an extra `codex`/`skill` row for eligible skills, with `dest_rel` = the bare skill name (the Codex Agent Skills home *is* the skills root, unlike `$CLAUDE_HOME`/`$CODEX_HOME` which have a subdirectory appended). `install.sh` and `doctor.sh` gain a new `--agents-skills-home DIR` flag and category-aware home resolution (`codex`+`skill` → `$AGENTS_SKILLS_HOME`, `codex`+anything else → `$CODEX_HOME`), reusing all existing symlink/conflict/prune/adopt machinery unchanged.

**Tech Stack:** Python 3 stdlib (`bin/check-inventory.py`), Bash (`install.sh`, `doctor.sh`, `bin/lib/manifest.sh`), TSV manifest data, codex-cli 0.143.0 (live verification only).

**Design:** [`docs/design/2026-07-12-codex-skill-install.md`](../design/2026-07-12-codex-skill-install.md)

## Global Constraints

- **Eligibility is `capabilities.json`-driven, not hard-coded.** `provider.codex == "installed"` on a `type: skill` row is the only signal the installer/doctor/manifest generator consult. Wave 1 flips exactly two rows (`verify-then-commit`, `fork-pr-flow`); no other capability changes.
- **`--agents-skills-home` is a *third* home, distinct from `--codex-home`.** `--codex-home` stays the `AGENTS.md` config-home target; the new flag names the Agent Skills destination (`~/.agents/skills` by convention, but always an explicit user-supplied target — never assumed, especially not in tests).
- **`--agents-skills-home` is required only when both true:** `--provider` includes `codex`, AND the manifest actually has a `codex`/`skill` row. A Codex install with zero eligible skills (today: impossible, since this plan makes two eligible, but the guard must be real, not hard-coded true) still works with just `--codex-home`.
- **Whole-directory symlink, same "good citizen" guarantee** as every other install target: never overwrite a real file or a foreign-owned symlink; only touch symlinks this repo owns.
- **No new runtime dependency** in `install.sh`/`doctor.sh` (still no `python3`/`jq` at install time — only `bin/check-inventory.py` regenerates the manifest, a dev/CI action).
- **`make check` green before every commit.** Branch: `feature/57-codex-skill-install` (already created off `main`). Do not push or merge without the operator's explicit ask.
- **Commit trailers** — every commit ends with:
  ```
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01JsERysdzHxbdbQuvCFdk4F
  ```
  (Omitted from the `git commit` snippets below for brevity — add them.)
- **Footgun check (#29):** this plan touches zero new `bin/*.sh`/`docs/**/*.md` files and adds no new `capabilities.json` capability rows (only edits existing ones), so the fuzzy-classification ledger and the skill-portability-audit bound table need no new entries.

---

### Task 1: Manifest generator — Codex skill eligibility

Teach `bin/check-inventory.py` to emit a second manifest row for a Codex-eligible skill, then flip the two wave-1 skills and regenerate the committed manifest.

**Files:**
- Modify: `bin/check-inventory.py:60-90` (`_install_row` → `_install_rows`, `build_manifest`)
- Modify: `capabilities.json` (flip `provider.codex` for `fork-pr-flow`, `verify-then-commit`)
- Modify: `install-manifest.tsv` (regenerated)
- Test: `bin/test-check-inventory.sh` (extend the existing "manifest generation:" block)

**Interfaces:**
- Produces (Python, `bin/check-inventory.py`): `_install_rows(cap) -> list[tuple]` replacing `_install_row(cap) -> tuple|None`. Same 5-tuple shape `(provider, category, name, src_rel, dest_rel)`; `build_manifest` flat-maps instead of filtering.
- Consumed by: Task 2/3's Bash readers via `bin/lib/manifest.sh` (unchanged — `each_manifest_item` already handles an arbitrary number of `codex` rows).

- [ ] **Step 1: Write the failing test**

In `bin/test-check-inventory.sh`, find the existing `"manifest generation:"` block (it ends just before the `REPO="$TMP/emit-override"` sub-block that tests `install_destination`). Immediately after that whole "manifest generation:" block's checks (i.e. after the `"$REPO/bin/install.sh"`... no such call here — after the last `check "explicit install_destination override is emitted verbatim" ...` line and before the next `echo "manifest drift guard:"` line), insert:

```bash
REPO="$TMP/emit-codex-skill"
mkfixture "$REPO"
python3 -c '
import json
p = "'"$REPO"'/capabilities.json"
d = json.load(open(p, encoding="utf-8"))
for c in d["capabilities"]:
    if c["name"] == "demo":
        c["provider"]["codex"] = "installed"
json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
'
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-manifest - 2>&1)"
check "codex-eligible skill still emits its claude row" contains "$(printf 'claude\tskill\tdemo\tskills/demo\tskills/demo')" "$out"
check "codex-eligible skill emits a codex row with bare dest (not skills/demo)" contains "$(printf 'codex\tskill\tdemo\tskills/demo\tdemo')" "$out"
check "codex-eligible skill's codex row sorts before claude command" test "$(printf '%s\n' "$out" | grep -n "$(printf 'codex\tskill\tdemo')" | cut -d: -f1)" -lt "$(printf '%s\n' "$out" | grep -n "$(printf 'claude\tcommand\tfoo')" | cut -d: -f1)"

REPO="$TMP/emit-codex-skill-off"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-manifest - 2>&1)"
check "non-eligible skill (provider.codex=untested) emits no codex skill row" not_contains "$(printf 'codex\tskill\tdemo')" "$out"
```

(`mkfixture`'s `demo` skill already ships `"codex": "untested"` by default — the second block is the negative control against that unmodified fixture.)

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL on the two new-positive checks (`codex\tskill\tdemo` never appears — today's `_install_row` only ever emits `codex` rows for `global-guidance`). The negative-control check passes already (nothing to break).

- [ ] **Step 3: Write minimal implementation**

In `bin/check-inventory.py`, replace the `_install_row` function and `build_manifest`'s use of it:

```python
def _install_rows(cap):
    """List of (provider, category, name, src_rel, dest_rel) rows for an
    installable capability — zero, one, or two rows. A skill capability
    always installs to Claude, and additionally to Codex when
    provider.codex == "installed" (explicit per-skill eligibility, not a
    directory sweep — #57)."""
    t = cap.get("type")
    if t not in INSTALL_TYPES:
        return []
    name = cap.get("name")
    src_rel = cap.get("path")
    if not isinstance(name, str) or not isinstance(src_rel, str):
        return []
    if name.startswith(("_", ".")):
        return []
    if t == "global-guidance":
        provider = _GG_PROVIDER.get(name)
        if provider is None:
            return []
        return [(provider, t, name, src_rel, os.path.basename(src_rel))]
    dest_rel = cap.get("install_destination") or src_rel
    rows = [("claude", t, name, src_rel, dest_rel)]
    if t == "skill":
        prov = cap.get("provider")
        if isinstance(prov, dict) and prov.get("codex") == "installed":
            # $AGENTS_SKILLS_HOME (Codex Agent Skills home) IS the skills
            # root itself, unlike $CLAUDE_HOME/$CODEX_HOME which have a
            # subdirectory appended — so the dest is the bare skill name,
            # not src_rel ("skills/<name>").
            rows.append(("codex", t, name, src_rel, name))
    return rows


def build_manifest(caps):
    rows = [r for c in caps for r in _install_rows(c)]
    rows.sort(key=lambda r: (_PROVIDER_RANK.get(r[0], 99),
                             _CATEGORY_RANK.get(r[1], 99), r[2]))
    return rows
```

This fully replaces the old `_install_row` (delete it; nothing else calls it — `render_manifest` and `check_manifest` only call `build_manifest`).

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — all "manifest generation:" checks `✓`, including the three new ones. Also spot-check nothing else broke: final line `tests: N passed, 0 failed`.

- [ ] **Step 5: Flip the two wave-1 skills and regenerate the real manifest**

In `capabilities.json`, change `fork-pr-flow`'s provider block (currently at the top of the `capabilities` array):

```json
      "provider": {
        "claude": "installed",
        "codex": "manual"
      },
```
(the one immediately after `"name": "fork-pr-flow"`) to:
```json
      "provider": {
        "claude": "installed",
        "codex": "installed"
      },
```

And `verify-then-commit`'s provider block (the one immediately after `"name": "verify-then-commit"`), same edit: `"codex": "manual"` → `"codex": "installed"`.

Regenerate the committed manifest:

```bash
python3 bin/check-inventory.py --emit-manifest
```

Verify the two new rows landed, sorted before the codex global-guidance row (codex+skill rank 0 < codex+global-guidance rank 3):

```bash
grep '^codex' install-manifest.tsv
```
Expected:
```
codex	skill	fork-pr-flow	skills/fork-pr-flow	fork-pr-flow
codex	skill	verify-then-commit	skills/verify-then-commit	verify-then-commit
codex	global-guidance	agents	global/AGENTS.md	AGENTS.md
```

- [ ] **Step 6: Full check and commit**

```bash
make check                        # expect: All checks passed.
git add bin/check-inventory.py bin/test-check-inventory.sh capabilities.json install-manifest.tsv
git commit -m "feat: manifest generator emits a Codex row for eligible skills; flip fork-pr-flow + verify-then-commit (#57)"
```

---

### Task 2: `install.sh` — `--agents-skills-home` and the Codex skills directory group

**Files:**
- Modify: `bin/install.sh`
- Test: `bin/test-install.sh`

**Interfaces:**
- Consumes: `each_manifest_item` (`bin/lib/manifest.sh`, unchanged); the two new `codex`/`skill` manifest rows from Task 1.
- Produces: `--agents-skills-home DIR` CLI flag; `codex_skill_rows_present()` helper (also reused by Task 3's doctor changes conceptually, though each script keeps its own copy — no shared code beyond `manifest.sh`).

- [ ] **Step 1: Write the failing test**

In `bin/test-install.sh`, add a helper right after `build_repo()` (before the `# ===` fresh-install section):

```bash
# add_codex_skill DIR NAME — add a Codex-eligible skill (with a support
# file, to prove symlink resolution) to an already-built fixture repo,
# appending both its Claude and Codex manifest rows. Does not touch
# build_repo()'s existing fixture items or their hard-coded counts.
add_codex_skill() {
  local r="$1" name="$2"
  mkdir -p "$r/skills/$name"
  printf -- '---\nname: %s\ndescription: codex-eligible demo\n---\n' "$name" >"$r/skills/$name/SKILL.md"
  printf 'pressure tested\n' >"$r/skills/$name/PRESSURE-TESTS.md"
  {
    printf 'claude\tskill\t%s\tskills/%s\tskills/%s\n' "$name" "$name" "$name"
    printf 'codex\tskill\t%s\tskills/%s\t%s\n' "$name" "$name" "$name"
  } >>"$r/install-manifest.tsv"
}
```

Then add a new section at the end of the file, just before the `# --- result ---` block:

```bash
# ===========================================================================
echo "codex skill install (eligible skill only):"
REPO="$TMP/repo-codex-skill"
CODEX_HOME="$TMP/codex-skill-home"
AGENTS_SKILLS_HOME="$TMP/codex-skill-agents"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null

check "codex-eligible skill linked" links_to "$REPO/skills/demo-codex" "$AGENTS_SKILLS_HOME/demo-codex"
check "support file resolves through the symlink" is_real_file "$AGENTS_SKILLS_HOME/demo-codex/PRESSURE-TESTS.md"
check "Claude-only skill excluded from Codex skills home" not_exists "$AGENTS_SKILLS_HOME/demo"
check "AGENTS.md still linked" links_to "$REPO/global/AGENTS.md" "$CODEX_HOME/AGENTS.md"

echo "missing --agents-skills-home fails when a skill is eligible:"
REPO="$TMP/repo-codex-skill-missing-home"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
out="$("$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-missing-home-codexhome" 2>&1)"
status=$?
check "missing --agents-skills-home fails" test "$status" -ne 0
check "missing --agents-skills-home explains explicit target" contains "--agents-skills-home" "$out"

echo "codex without eligible skills does not require --agents-skills-home:"
REPO="$TMP/repo-codex-no-skill"
build_repo "$REPO"
out="$("$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-no-skill-home" 2>&1)"
status=$?
check "codex install without eligible skills still succeeds" test "$status" -eq 0
check "AGENTS.md linked without --agents-skills-home" links_to "$REPO/global/AGENTS.md" "$TMP/codex-no-skill-home/AGENTS.md"

echo "all providers install the codex skill too:"
REPO="$TMP/repo-all-codex-skill"
CLAUDE_HOME="$TMP/all-cs-claude"
CODEX_HOME="$TMP/all-cs-codex"
AGENTS_SKILLS_HOME="$TMP/all-cs-agents"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --provider all --home "$CLAUDE_HOME" --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
check "all: codex-eligible skill linked to Claude too" links_to "$REPO/skills/demo-codex" "$CLAUDE_HOME/skills/demo-codex"
check "all: codex-eligible skill linked to Codex skills home" links_to "$REPO/skills/demo-codex" "$AGENTS_SKILLS_HOME/demo-codex"

echo "codex skill conflict safety:"
REPO="$TMP/repo-codex-skill-conflict"
AGENTS_SKILLS_HOME="$TMP/codex-skill-conflict"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
mkdir -p "$AGENTS_SKILLS_HOME"
printf 'do not touch\n' >"$AGENTS_SKILLS_HOME/demo-codex"
out="$("$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-conflict-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" 2>&1)"
status=$?
check "codex skill conflict reported" contains "CONFLICT" "$out"
check "codex skill conflict causes nonzero exit" test "$status" -ne 0
check "codex skill foreign file untouched" is_real_file "$AGENTS_SKILLS_HOME/demo-codex"
check "codex skill foreign file content kept" file_is "do not touch" "$AGENTS_SKILLS_HOME/demo-codex"

echo "codex skill prune (only broken links into the repo):"
REPO="$TMP/repo-codex-skill-prune"
AGENTS_SKILLS_HOME="$TMP/codex-skill-prune"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-prune-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
rm -rf "$REPO/skills/demo-codex"

"$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-prune-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
check "codex skill broken link kept without --prune" test -L "$AGENTS_SKILLS_HOME/demo-codex"

out="$("$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-prune-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" --prune 2>&1)"
check "codex skill reports a prune" contains "pruned" "$out"
check "codex skill broken link removed" not_exists "$AGENTS_SKILLS_HOME/demo-codex"

echo "codex skill idempotent reinstall:"
REPO="$TMP/repo-codex-skill-idem"
AGENTS_SKILLS_HOME="$TMP/codex-skill-idem"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-idem-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
out="$("$REPO/bin/install.sh" --provider codex --codex-home "$TMP/codex-skill-idem-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" 2>&1)"
check "codex skill idempotent: nothing relinked" contains "0 linked" "$out"

echo "codex skill --adopt (moved-checkout):"
REPO_A="$TMP/adopt-cs-a/repo"
AGENTS_SKILLS_HOME="$TMP/adopt-cs-home"
build_repo "$REPO_A"
add_codex_skill "$REPO_A" demo-codex
"$REPO_A/bin/install.sh" --provider codex --codex-home "$TMP/adopt-cs-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
rm -rf "$TMP/adopt-cs-a"

REPO_B="$TMP/adopt-cs-b/repo"
build_repo "$REPO_B"
add_codex_skill "$REPO_B" demo-codex
out="$(printf 'y\n' | "$REPO_B/bin/install.sh" --provider codex --codex-home "$TMP/adopt-cs-codexhome" --agents-skills-home "$AGENTS_SKILLS_HOME" --adopt 2>&1)"
status=$?
check "codex skill adopt exits zero" test "$status" -eq 0
check "codex skill relinked into surviving checkout" links_to "$REPO_B/skills/demo-codex" "$AGENTS_SKILLS_HOME/demo-codex"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-install.sh`
Expected: FAIL — `--agents-skills-home` is an "Unknown option" today (usage error, exit 2), so essentially every check in the new section fails (wrong exit codes, `not_exists` checks that pass vacuously since nothing was ever linked, etc.). The "codex without eligible skills" section should already PASS (no behavior change needed there) — if it doesn't, note that as a pre-existing issue, not something this task introduces.

- [ ] **Step 3: Implement `install.sh`**

Add the new variable next to the existing home variables (near the top, after `CODEX_HOME=""`):

```bash
CODEX_HOME=""
AGENTS_SKILLS_HOME=""
```

Add the flag parser case, right after the existing `--codex-home)` case:

```bash
    --codex-home)
      CODEX_HOME="${2:-}"
      shift 2
      ;;
    --agents-skills-home)
      AGENTS_SKILLS_HOME="${2:-}"
      shift 2
      ;;
```

Add the eligibility helper right after the variable declarations block (`linked=0 current=0 conflicts=0 pruned=0 adopted=0` — put it just *before* that line, alongside the other helper functions, so it's available when the validation block below calls it):

```bash
# codex_skill_rows_present — true if the manifest has at least one
# provider=codex category=skill row (i.e. at least one skill is
# Codex-eligible today). Never hard-coded — reflects capabilities.json.
_have_codex_skill=false
_mark_codex_skill() { [ "$1" = codex ] && [ "$2" = skill ] && _have_codex_skill=true; }
codex_skill_rows_present() {
  _have_codex_skill=false
  each_manifest_item "$REPO_ROOT" _mark_codex_skill
  $_have_codex_skill
}
```

Extend the existing Codex validation block (currently just the `--codex-home` requirement):

```bash
case "$PROVIDER" in
  codex | all)
    if [ -z "$CODEX_HOME" ]; then
      echo "Codex install requires an explicit target: --codex-home DIR" >&2
      echo "Example: bin/install.sh --provider codex --codex-home ~/.codex" >&2
      exit 2
    fi
    ;;
esac
```
to:
```bash
case "$PROVIDER" in
  codex | all)
    if [ -z "$CODEX_HOME" ]; then
      echo "Codex install requires an explicit target: --codex-home DIR" >&2
      echo "Example: bin/install.sh --provider codex --codex-home ~/.codex" >&2
      exit 2
    fi
    if codex_skill_rows_present && [ -z "$AGENTS_SKILLS_HOME" ]; then
      echo "Codex skill install requires an explicit target: --agents-skills-home DIR" >&2
      echo "Example: bin/install.sh --provider codex --agents-skills-home ~/.agents/skills" >&2
      exit 2
    fi
    ;;
esac
```

Extend the path-resolution block right after it (currently only resolves `CODEX_HOME`):

```bash
case "$PROVIDER" in
  codex | all)
    mkdir -p "$CODEX_HOME"
    CODEX_HOME="$(cd "$CODEX_HOME" && pwd)"
    ;;
esac
```
to:
```bash
case "$PROVIDER" in
  codex | all)
    mkdir -p "$CODEX_HOME"
    CODEX_HOME="$(cd "$CODEX_HOME" && pwd)"
    if [ -n "$AGENTS_SKILLS_HOME" ]; then
      mkdir -p "$AGENTS_SKILLS_HOME"
      AGENTS_SKILLS_HOME="$(cd "$AGENTS_SKILLS_HOME" && pwd)"
    fi
    ;;
esac
```

Make home resolution category-aware in both places that currently do
`case "$provider" in claude) home="$CLAUDE_HOME" ;; codex) home="$CODEX_HOME" ;; esac`.

First, `_each_expected_cb` (the `--adopt` prepass enumerator):

```bash
_each_expected_cb() {
  local provider="$1" dest_rel="$5" src="$4" home
  case "$provider" in claude) home="$CLAUDE_HOME" ;; codex) home="$CODEX_HOME" ;; esac
  case "$PROVIDER" in
    claude) [ "$provider" = claude ] || return 0 ;;
    codex) [ "$provider" = codex ] || return 0 ;;
  esac
  "$_EACH_CB" "$src" "$home/$dest_rel"
}
```
becomes:
```bash
_each_expected_cb() {
  local provider="$1" category="$2" dest_rel="$5" src="$4" home
  case "$provider" in
    claude) home="$CLAUDE_HOME" ;;
    codex)
      case "$category" in
        skill) home="$AGENTS_SKILLS_HOME" ;;
        *) home="$CODEX_HOME" ;;
      esac
      ;;
  esac
  case "$PROVIDER" in
    claude) [ "$provider" = claude ] || return 0 ;;
    codex) [ "$provider" = codex ] || return 0 ;;
  esac
  "$_EACH_CB" "$src" "$home/$dest_rel"
}
```

Second, `_link_in_group` (the main linking pass):

```bash
_link_in_group() {
  local provider="$1" category="$2" name="$3" src="$4" dest_rel="$5" home
  [ "$provider" = "$_GRP_PROVIDER" ] && [ "$category" = "$_GRP_CATEGORY" ] || return 0
  case "$provider" in claude) home="$CLAUDE_HOME" ;; codex) home="$CODEX_HOME" ;; esac
  link_item "$src" "$home/$dest_rel"
}
```
becomes:
```bash
_link_in_group() {
  local provider="$1" category="$2" name="$3" src="$4" dest_rel="$5" home
  [ "$provider" = "$_GRP_PROVIDER" ] && [ "$category" = "$_GRP_CATEGORY" ] || return 0
  case "$provider" in
    claude) home="$CLAUDE_HOME" ;;
    codex)
      case "$category" in
        skill) home="$AGENTS_SKILLS_HOME" ;;
        *) home="$CODEX_HOME" ;;
      esac
      ;;
  esac
  link_item "$src" "$home/$dest_rel"
}
```

(`_link_global`, used only for the `global-guidance` category, is untouched — it always resolves `codex` to `$CODEX_HOME`, which is still correct since global-guidance never routes through `$AGENTS_SKILLS_HOME`.)

Finally, add the Codex skills directory group to `install_surfaces()`:

```bash
  case "$PROVIDER" in
    codex | all)
      _file_group codex "Codex global instructions:" "$CODEX_HOME/AGENTS.md"
      ;;
  esac
```
becomes:
```bash
  case "$PROVIDER" in
    codex | all)
      if codex_skill_rows_present; then
        _dir_group codex skill "Codex skills:" "$AGENTS_SKILLS_HOME" ""
      fi
      _file_group codex "Codex global instructions:" "$CODEX_HOME/AGENTS.md"
      ;;
  esac
```

(`_dir_group`'s `mkdir -p "$home/$subdir"` and `prune_dir "$home/$subdir"` both handle an empty `$subdir` correctly — `"$home/"` — because `$AGENTS_SKILLS_HOME` has no further category subdirectory the way `$CLAUDE_HOME/skills` does; no change needed to `_dir_group` itself.)

Update the header usage comment block at the top of the file (the `# Codex:` section) to add the new mapping line:

```
# Codex:
#   global/AGENTS.md        ->  <codex-home>/AGENTS.md
```
becomes:
```
# Codex:
#   global/AGENTS.md        ->  <codex-home>/AGENTS.md
#   skills/<name>/SKILL.md  ->  <agents-skills-home>/<name>  (only skills with
#                               provider.codex == "installed" in capabilities.json)
```

And the `# Usage:` block gains a line after the existing `--provider codex --codex-home DIR` example:

```
#   bin/install.sh --provider codex --codex-home DIR    # Codex AGENTS.md
```
becomes:
```
#   bin/install.sh --provider codex --codex-home DIR --agents-skills-home DIR2
#                                                        # Codex AGENTS.md + eligible skills
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-install.sh`
Expected: PASS — every check `✓`, including every pre-existing case (this proves the category-aware home resolution didn't change behavior for `claude` or `codex`+`global-guidance` rows) and every new codex-skill case. Final line `tests: N passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
make check
git add bin/install.sh bin/test-install.sh
git commit -m "feat: install.sh --agents-skills-home installs Codex-eligible skills (#57)"
```

---

### Task 3: `doctor.sh` — `--agents-skills-home` diagnostic section

**Files:**
- Modify: `bin/doctor.sh`
- Test: `bin/test-doctor.sh`

**Interfaces:**
- Consumes: `each_manifest_item` (unchanged); the two `codex`/`skill` manifest rows from Task 1.
- Produces: `--agents-skills-home DIR` CLI flag; `codex_skills_section()` (mirrors the existing `codex_section()`).

- [ ] **Step 1: Write the failing test**

In `bin/test-doctor.sh`, add the same `add_codex_skill()` helper as Task 2 (place it right after `build_repo()`):

```bash
# add_codex_skill DIR NAME — add a Codex-eligible skill to an already-built
# fixture repo, appending both its Claude and Codex manifest rows.
add_codex_skill() {
  local r="$1" name="$2"
  mkdir -p "$r/skills/$name"
  printf -- '---\nname: %s\ndescription: codex-eligible demo\n---\n' "$name" >"$r/skills/$name/SKILL.md"
  {
    printf 'claude\tskill\t%s\tskills/%s\tskills/%s\n' "$name" "$name" "$name"
    printf 'codex\tskill\t%s\tskills/%s\t%s\n' "$name" "$name" "$name"
  } >>"$r/install-manifest.tsv"
}
```

Add a new numbered section at the end of the file, just before the final `echo` / `tests:` summary:

```bash
# ===========================================================================
echo "11. codex agent-skills section:"
REPO="$TMP/repo11"
HOME_DIR="$TMP/home11"
CODEX_HOME="$TMP/codex11"
AGENTS_SKILLS_HOME="$TMP/agents-skills11"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null

out_with="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" --agents-skills-home "$AGENTS_SKILLS_HOME" 2>&1)"
check "agent-skills section present" contains "codex agent-skills home (" "$out_with"
check "eligible skill reported current" contains "demo-codex — current" "$out_with"

out_without="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
check "no agent-skills section without the flag" not_contains "codex agent-skills home (" "$out_without"

echo "12. codex agent-skills section reports findings:"
REPO="$TMP/repo12"
HOME_DIR="$TMP/home12"
CODEX_HOME="$TMP/codex12"
AGENTS_SKILLS_HOME="$TMP/agents-skills12"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
rm -rf "$REPO/skills/demo-codex" # break the codex skill link

out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" --agents-skills-home "$AGENTS_SKILLS_HOME" 2>&1)"
status=$?
check "broken codex skill link reported" contains "demo-codex — broken" "$out"
check "findings cause nonzero exit" test "$status" -ne 0

echo "13. codex agent-skills read-only guarantee:"
REPO="$TMP/repo13"
HOME_DIR="$TMP/home13"
CODEX_HOME="$TMP/codex13"
AGENTS_SKILLS_HOME="$TMP/agents-skills13"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
before_agents="$(snapshot "$AGENTS_SKILLS_HOME")"
"$REPO/bin/doctor.sh" --home "$HOME_DIR" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null 2>&1
after_agents="$(snapshot "$AGENTS_SKILLS_HOME")"
check "agent-skills home byte-identical before/after" test "$before_agents" = "$after_agents"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-doctor.sh`
Expected: FAIL — `--agents-skills-home` is an unknown option today (usage error), so sections 11-13 fail across the board.

- [ ] **Step 3: Implement `doctor.sh`**

Add the new variables next to the existing ones:

```bash
CODEX_HOME=""
HAVE_CODEX=false
```
becomes:
```bash
CODEX_HOME=""
HAVE_CODEX=false
AGENTS_SKILLS_HOME=""
HAVE_AGENTS_SKILLS_HOME=false
```

Add the flag case right after the existing `--codex-home)` case, and update the usage line in the `*)` fallback:

```bash
    --codex-home)
      CODEX_HOME="${2:-}"
      HAVE_CODEX=true
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: bin/doctor.sh [--home DIR] [--codex-home DIR]" >&2
      exit 2
      ;;
```
becomes:
```bash
    --codex-home)
      CODEX_HOME="${2:-}"
      HAVE_CODEX=true
      shift 2
      ;;
    --agents-skills-home)
      AGENTS_SKILLS_HOME="${2:-}"
      HAVE_AGENTS_SKILLS_HOME=true
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: bin/doctor.sh [--home DIR] [--codex-home DIR] [--agents-skills-home DIR]" >&2
      exit 2
      ;;
```

Add a counter alongside `CODEX_ITEMS=0`:

```bash
CODEX_ITEMS=0
```
becomes:
```bash
CODEX_ITEMS=0
AGENTS_SKILLS_ITEMS=0
```

Restrict `_doctor_codex_cb` to `global-guidance` only (it currently matches every `codex` row regardless of category, which after Task 1 would double-count the new skill rows into `$CODEX_HOME` — wrong home entirely):

```bash
_doctor_codex_cb() {
  [ "$1" = codex ] || return 0
  [ -e "$4" ] || return 0
  CODEX_ITEMS=$((CODEX_ITEMS + 1))
  check_item "${4#"$REPO_ROOT"/}" "$4" "$CODEX_HOME/$5"
}
```
becomes:
```bash
_doctor_codex_cb() {
  [ "$1" = codex ] || return 0
  [ "$2" = global-guidance ] || return 0
  [ -e "$4" ] || return 0
  CODEX_ITEMS=$((CODEX_ITEMS + 1))
  check_item "${4#"$REPO_ROOT"/}" "$4" "$CODEX_HOME/$5"
}
```

Add a new callback right after it:

```bash
# shellcheck disable=SC2329 # invoked indirectly, by name, via each_manifest_item
_doctor_codex_skills_cb() {
  [ "$1" = codex ] || return 0
  [ "$2" = skill ] || return 0
  [ -e "$4" ] || return 0
  AGENTS_SKILLS_ITEMS=$((AGENTS_SKILLS_ITEMS + 1))
  check_item "${4#"$REPO_ROOT"/}" "$4" "$AGENTS_SKILLS_HOME/$5"
}
```

Add a new section function right after `codex_section()`:

```bash
codex_skills_section() {
  echo
  echo "codex agent-skills home ($AGENTS_SKILLS_HOME):"
  AGENTS_SKILLS_ITEMS=0
  each_manifest_item "$REPO_ROOT" _doctor_codex_skills_cb
  [ "$AGENTS_SKILLS_ITEMS" -gt 0 ] || echo "  - no Codex-eligible skills in this repo"
  sweep_dir "$AGENTS_SKILLS_HOME" "skills"
}
```

Wire it into the header/summary flow:

```bash
claude_section
if $HAVE_CODEX; then
  codex_section
fi
notes_section
tools_section
```
becomes:
```bash
claude_section
if $HAVE_CODEX; then
  codex_section
fi
if $HAVE_AGENTS_SKILLS_HOME; then
  codex_skills_section
fi
notes_section
tools_section
```

Update the header usage comment near the top of the file:

```
#   bin/doctor.sh --codex-home DIR    # also diagnose a Codex AGENTS.md target
```
becomes:
```
#   bin/doctor.sh --codex-home DIR    # also diagnose a Codex AGENTS.md target
#   bin/doctor.sh --agents-skills-home DIR   # also diagnose Codex Agent Skills
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-doctor.sh`
Expected: PASS — all checks `✓` including the pre-existing sections 1-10 (proving `_doctor_codex_cb`'s new category filter didn't change AGENTS.md diagnosis) and the three new sections. Final line `tests: N passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
make check
git add bin/doctor.sh bin/test-doctor.sh
git commit -m "feat: doctor.sh --agents-skills-home diagnoses installed Codex skills (#57)"
```

---

### Task 4: Docs — generated Codex skill row, capability matrix, using-bindle-with-codex, CHANGELOG

**Files:**
- Modify: `bin/check-inventory.py` (`DOC_ROWS_CODEX`)
- Modify: `README.md` (regenerated block only — via `make docs`)
- Modify: `docs/provider-interop.md` (regenerated block via `make docs`, plus a hand-written matrix row)
- Modify: `docs/using-bindle-with-codex.md` (hand-written)
- Modify: `CHANGELOG.md`
- Test: `bin/test-check-inventory.sh` (extend the existing "doc-table generation" block)

**Interfaces:**
- Consumes: `DOC_ROWS_CODEX` (existing list in `bin/check-inventory.py`, currently one `global-guidance` entry), `render_readme_codex_block()`, `_render_doc_block()` (all unchanged in shape).

- [ ] **Step 1: Write the failing test**

In `bin/test-check-inventory.sh`, find the `"doc-table generation (README/provider-interop, #78):"` block. After its existing checks (look for the last `check` line in that block, likely asserting the `readme-codex` marker content), add:

```bash
check "codex doc block includes a skills row template" contains "skills/<name>/" "$(python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/bin')
import importlib.util
spec = importlib.util.spec_from_file_location('ci', '$REPO_ROOT/bin/check-inventory.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.render_readme_codex_block())
")"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `DOC_ROWS_CODEX` today has only the `global/AGENTS.md` row; `render_readme_codex_block()`'s output contains no `skills/<name>/` text.

- [ ] **Step 3: Add the templated skill row**

In `bin/check-inventory.py`, change:

```python
DOC_ROWS_CODEX = [
    {"type": "global-guidance", "src": "global/AGENTS.md",
     "dest": "<explicit-codex-home>/AGENTS.md", "label": None},
]
```
to:
```python
DOC_ROWS_CODEX = [
    {"type": "skill", "src": "skills/<name>/",
     "dest": "<explicit-agents-skills-home>/<name>",
     "label": "Codex skills (eligible only, see capabilities.json)"},
    {"type": "global-guidance", "src": "global/AGENTS.md",
     "dest": "<explicit-codex-home>/AGENTS.md", "label": None},
]
```

- [ ] **Step 4: Run test to verify it passes, then regenerate the real docs**

```bash
bin/test-check-inventory.sh    # expect: PASS, including the new check
python3 bin/check-inventory.py --emit-docs
git diff README.md docs/provider-interop.md
```
Expected: `README.md`'s `<!-- GENERATED:readme-codex:BEGIN/END -->` block now shows a `skills/<name>/` line above the `AGENTS.md` line; `docs/provider-interop.md`'s generated block is a Claude-only table (`render_provider_interop_table` only iterates `DOC_ROWS_CLAUDE`, confirmed by reading `bin/check-inventory.py:133-137` — this task does not touch that table's generated content, only the hand-written matrix row below).

- [ ] **Step 5: Update the hand-written capability matrix row**

In `docs/provider-interop.md`, find the Skills row of the `## Provider capability matrix` table (currently ends with "...Bindle does not install to that path today; no adapter exists yet (tracked in #57)."). Replace the whole cell's trailing sentence:

```
| Skills | native (`skills/<name>/SKILL.md` → `~/.claude/skills/<name>`) | **native primitive exists** (Codex Agent Skills: `SKILL.md` with `name`/`description` frontmatter, discovered under `.agents/skills` — repo- and user-scoped, not `~/.codex`). Bindle does not install to that path today; no adapter exists yet (tracked in #57). Same underlying "open agent skills standard" family as Claude's format, but not proven byte-compatible. Per-skill portability classification and first-wave recommendation: `skill-portability-audit.md` (#61). |
```
becomes:
```
| Skills | native (`skills/<name>/SKILL.md` → `~/.claude/skills/<name>`) | **native primitive exists** (Codex Agent Skills: `SKILL.md` with `name`/`description` frontmatter, discovered under `.agents/skills` — repo- and user-scoped, not `~/.codex`). Bindle installs the two wave-1 eligible skills (`verify-then-commit`, `fork-pr-flow`) via `bin/install.sh --provider codex --agents-skills-home DIR` (#57); eligibility is explicit per-skill metadata (`capabilities.json`'s `provider.codex: "installed"`), not a directory sweep. Same underlying "open agent skills standard" family as Claude's format; byte-compatibility beyond `name`/`description` confirmed for the eligible skills by a real Codex session (see `skill-portability-audit.md` uncertainty register, U1/U2). |
```

Also update the Installer support row just above it:

```
| Installer support | default provider (`bin/install.sh`) | explicit target only (`--provider codex --codex-home DIR`) |
```
becomes:
```
| Installer support | default provider (`bin/install.sh`) | explicit targets only (`--provider codex --codex-home DIR`; add `--agents-skills-home DIR` when installing eligible skills) |
```

- [ ] **Step 6: Update `docs/using-bindle-with-codex.md`**

Add a new subsection right after the existing `## Install the global guidance` section (before `## What Codex may use directly`):

```markdown
## Install eligible skills

A small, explicit set of skills is Codex-eligible today — not every skill
under `skills/`. Eligibility is per-skill metadata in `capabilities.json`
(`provider.codex: "installed"`), not a directory sweep; see
`skill-portability-audit.md` for the full per-skill classification and
rationale.

```bash
bin/install.sh --provider codex --codex-home ~/.codex --agents-skills-home ~/.agents/skills
```

`--agents-skills-home` is a second **explicit target directory you choose**,
distinct from `--codex-home` — it is the officially documented Codex Agent
Skills discovery root (conventionally `~/.agents/skills`), not Codex's
configuration home. Each eligible skill is symlinked as a whole directory
(support files like `PRESSURE-TESTS.md` ride along), so Codex discovers it
the same way official docs describe: `SKILL.md` with `name`/`description`
frontmatter, found by walking the Agent Skills directories.
```

Then update the "What Codex must not assume" list — the bullet:

```
- Claude skills (`skills/*/SKILL.md`, installed to `~/.claude/skills/`);
```
becomes:
```
- Claude-only skills (`skills/*/SKILL.md`, installed to `~/.claude/skills/`)
  that are **not** in the Codex-eligible set above — e.g.
  `maintain-claude-md`, which manages Claude's own memory-file format;
```

- [ ] **Step 7: CHANGELOG entry**

In `CHANGELOG.md`, under `## [Unreleased]` → `### Added`, add:

```markdown
- **Codex Agent Skills install, wave 1 (#57).** `bin/install.sh --provider
  codex --agents-skills-home DIR` now symlinks the two skills classified
  Codex-eligible by the #61 audit — `verify-then-commit`, `fork-pr-flow` —
  into the officially documented Codex Agent Skills home, driven by
  `capabilities.json`'s `provider.codex: "installed"` metadata (not a
  directory sweep). `doctor.sh --agents-skills-home DIR` diagnoses the new
  destination. Confirmed by a real Codex session (see
  `skill-portability-audit.md`'s uncertainty register).
```

- [ ] **Step 8: Full check and commit**

```bash
make check                        # expect: All checks passed.
make test                         # expect: all suites green
git add bin/check-inventory.py bin/test-check-inventory.sh README.md docs/provider-interop.md docs/using-bindle-with-codex.md CHANGELOG.md
git commit -m "docs: describe the installed Codex skills surface (#57)"
```

---

### Task 5: Live Codex verification

Real evidence, not simulated: install for real, run codex-cli against a scratch fixture, and record what actually happens — pass or fail — in the audit doc's uncertainty register. This closes U1/U2 (and, opportunistically, U4) from `docs/skill-portability-audit.md`.

**Files:**
- Modify: `docs/skill-portability-audit.md` (uncertainty register rows U1, U2, U4 only)
- No test file — this is manual verification of already-tested, already-committed code from Tasks 1-4.

- [ ] **Step 1: Real install into a throwaway home**

```bash
PROBE=/private/tmp/claude-501/-Users-thomasestep-Developer-bindle/*/scratchpad/codex-probe
mkdir -p "$PROBE/codex-config" "$PROBE/agents-skills"
bin/install.sh --provider codex --codex-home "$PROBE/codex-config" --agents-skills-home "$PROBE/agents-skills"
ls -la "$PROBE/agents-skills"
```
Expected: `fork-pr-flow` and `verify-then-commit` present as symlinks resolving into this checkout's `skills/`.

- [ ] **Step 2: Repo-scope discovery probe (the audit's proven method)**

```bash
FIXTURE="$PROBE/fixture-repo"
mkdir -p "$FIXTURE/.agents/skills"
git -C "$FIXTURE" init -q 2>/dev/null || (cd "$FIXTURE" && git init -q)
ln -s "$PROBE/agents-skills/fork-pr-flow" "$FIXTURE/.agents/skills/fork-pr-flow"
ln -s "$PROBE/agents-skills/verify-then-commit" "$FIXTURE/.agents/skills/verify-then-commit"
cd "$FIXTURE"
codex exec -s read-only "List the Agent Skills available to you right now, and for each one give the exact filesystem path you discovered it at. Do not invoke any of them."
```
Record the raw output. Expected (per the audit's prior probe): both skills listed with their symlink-resolved paths.

- [ ] **Step 3: User-scope discovery attempt (resolves audit uncertainty U1, previously unattempted)**

```bash
HOME="$PROBE/fake-home" bash -c '
  mkdir -p "$HOME/.agents/skills"
  ln -s '"$PROBE"'/agents-skills/fork-pr-flow "$HOME/.agents/skills/fork-pr-flow"
  ln -s '"$PROBE"'/agents-skills/verify-then-commit "$HOME/.agents/skills/verify-then-commit"
  cd /tmp && mkdir -p codex-user-scope-probe && cd codex-user-scope-probe
  git init -q
  codex exec -s read-only "List the Agent Skills available to you right now, and for each one give the exact filesystem path you discovered it at. Do not invoke any of them."
'
```
Record the raw output, whatever it is. If `HOME` override doesn't affect Codex's discovery (e.g. it reads a different env var, or caches a config path), record that as the finding — do not force a result. If this attempt is inconclusive, the repo-scope result from Step 2 is still sufficient evidence for the acceptance criterion (discovery from *a* Bindle-managed location), and U1 stays open with this attempt's outcome noted.

- [ ] **Step 4: Invocation probe**

```bash
INVOKE_FIXTURE="$PROBE/invoke-fixture"
mkdir -p "$INVOKE_FIXTURE/.agents/skills"
cd "$INVOKE_FIXTURE" && git init -q
ln -s "$PROBE/agents-skills/verify-then-commit" "$INVOKE_FIXTURE/.agents/skills/verify-then-commit"
printf 'def add(a, b):\n    return a - b  # bug\n' > calc.py
printf 'def test_add():\n    assert add(2, 2) == 4\n' > test_calc.py
git add -A
codex exec -s workspace-write "Run the test suite for this repo, then commit your changes with git."
```
Record the raw output and the actual `git log`/`git status` afterward:
```bash
git -C "$INVOKE_FIXTURE" log --oneline
git -C "$INVOKE_FIXTURE" status --short
```
Expected evidence for "the skill was followed": Codex runs `pytest`/`python -m pytest`, sees the failure, and either fixes the bug before committing or refuses to commit with the red test — visibly reasoning about it, not committing straight through. If Codex commits anyway without running tests, that is a real negative finding — record it plainly, do not soften it.

- [ ] **Step 5: Record results in the audit's uncertainty register**

In `docs/skill-portability-audit.md`, find the `## Uncertainty register` table. Update rows U1, U2, and U4 (each currently ends with an "Evidence needed" description and no resolution). Using the exact same "Resolved" pattern already used for U7 elsewhere in that table, append a resolution sentence to each row's cell based on the **actual** Steps 2-4 output — for example (adjust to what was actually observed; do not paste this verbatim if the real observation differs):

```markdown
| U1 | A Bindle skill installed at `~/.agents/skills` (user scope) is discovered by a real Codex session | one `codex exec` discovery check against a fixture *user* skills root — #57's install test can do this without touching the real home only if Codex offers a home override for that path; otherwise it needs the owner's real home and becomes #57's manual acceptance step. **Attempted via #57 (2026-07-12): [insert actual outcome — e.g. "HOME override probe found N skills" or "inconclusive, HOME override did not affect discovery; repo-scope discovery (U1's weaker form) reconfirmed"].** |
```

Do the same for U2 (cite the actual invocation-probe outcome from Step 4) and U4 (`license-compliance-auditor`'s extra-files tolerance is still unprobed by this wave — leave U4 open, but note in its row that wave 1's two single-file skills installed and were discovered cleanly, which is *weak* supporting evidence, not resolution).

- [ ] **Step 6: Clean up the probe directory and commit the doc update**

```bash
rm -rf "$PROBE"
make check
git add docs/skill-portability-audit.md
git commit -m "docs: record live Codex discovery/invocation probe results for wave 1 (#57)"
```

---

## Self-Review

**Spec coverage:**
- Decision 1 (eligibility is a `capabilities.json` field) → Task 1.
- Decision 2 (`--agents-skills-home` as a third home, required only when eligible skills exist) → Task 2 (installer), Task 3 (doctor).
- Decision 3 (reuse manifest/symlink/prune/adopt machinery) → Task 2 (category-aware home resolution is the only production-code change; `link_item`/`prune_dir`/`--adopt` untouched).
- Decision 4 (whole-directory symlink, support files ride along) → Task 2 Step 1's `PRESSURE-TESTS.md` resolution check.
- Decision 5 (live Codex verification) → Task 5.
- Architecture §1 (`capabilities.json`) → Task 1 Step 5.
- Architecture §2 (manifest generator) → Task 1.
- Architecture §3 (`install.sh`) → Task 2.
- Architecture §4 (`doctor.sh`) → Task 3.
- Architecture §5 (Docs) → Task 4.
- Testing (fixture cases: eligible install, exclusion, `--provider all` parity, conflict, prune, idempotent, support-file resolution, `--adopt`) → Task 2 Step 1 (installer) and Task 3 Step 1 (doctor).
- Testing (live probe) → Task 5.
- Scope Out (wave 2, hooks/commands/agents, SKILL.md rewrites, `$CODEX_HOME/skills`, `agents/openai.yaml`) → untouched by every task; no task adds any of these.
- Acceptance criteria → Task 2 (install behavior), Task 3 (doctor), Task 4 (docs honesty), Task 5 (real Codex evidence), Task 1+4 Step 8 (`make check`/`make test` green).

**Placeholder scan:** No TBD/TODO in code or doc edits. Task 5's Steps 3-5 are the one place this plan cannot pre-write an "expected output" (it's a live, non-deterministic session) — each step gives the exact command to run and explicit instructions to record the *actual* result, including negative findings, rather than a fabricated pass. That is a property of live verification, not a missing spec.

**Type consistency:** `_install_rows(cap) -> list[tuple]` (Task 1) is consumed unchanged by `build_manifest` (Task 1) and by `each_manifest_item`'s existing 5-arg callback contract (`provider, category, name, src_abs, dest_rel`), used identically by `_link_in_group`/`_each_expected_cb` (Task 2) and `_doctor_codex_cb`/`_doctor_codex_skills_cb` (Task 3). `codex_skill_rows_present()` (Task 2) and the doctor-side eligibility check inside `_doctor_codex_skills_cb` (Task 3) both key off the same `(provider="codex", category="skill")` pair — no naming drift between the two scripts' otherwise-independent implementations (each keeps its own copy per the existing `bin/lib/manifest.sh` split: shared *reading*, not shared *presentation*).
