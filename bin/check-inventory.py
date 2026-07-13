#!/usr/bin/env python3
"""Validate capabilities.json against the Bindle repo. Stdlib-only.

Usage: check-inventory.py [--root DIR]
Exits 0 if the inventory is consistent, 1 (with per-line diagnostics) otherwise.
"""
import argparse
import json
import os
import re
import subprocess
import sys

TYPES = {"skill", "command", "agent", "global-guidance", "script", "contract"}
PROVIDER_STATUS = {"installed", "manual", "untested", "unsupported", "n/a"}
MATURITY = {"draft", "documented", "tested"}
MUTATION_FLAGS = {"disk", "network", "external"}
REQUIRED = ["name", "type", "path", "description", "provider", "maturity",
            "mutation", "version_introduced"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

INSTALL_TYPES = ("skill", "agent", "command", "global-guidance")
_PROVIDER_RANK = {"claude": 0, "codex": 1}
_CATEGORY_RANK = {"skill": 0, "agent": 1, "command": 2, "global-guidance": 3}
# global-guidance name -> provider (mirrors the gg map in check_completeness_clean)
_GG_PROVIDER = {"claude": "claude", "agents": "codex"}
MANIFEST_BANNER = ("# GENERATED from capabilities.json — do not edit; "
                   "run 'make manifest'")

# Single source for README's "Provider support" blocks and
# provider-interop.md's Claude install-layout table (#78): one row per
# INSTALL_TYPES entry. `table_src` overrides `src` only where the two docs
# genuinely use different illustrative paths (README shows the skill's
# marker file; the table shows the bare directory). Trailers are the
# "(not installed)" project-guidance line each block ends with — not derived
# from any capabilities.json row, but part of the same generated fence so the
# markers can wrap a complete, renderable code block.
DOC_ROWS_CLAUDE = [
    {"type": "skill", "src": "skills/<name>/SKILL.md",
     "table_src": "skills/<name>/", "dest": "~/.claude/skills/<name>",
     "label": "Claude skills"},
    {"type": "agent", "src": "agents/<name>.md",
     "dest": "~/.claude/agents/<name>.md", "label": "Claude subagents"},
    {"type": "command", "src": "commands/<name>.md",
     "dest": "~/.claude/commands/<name>.md", "label": "Claude slash commands"},
    {"type": "global-guidance", "src": "global/CLAUDE.md",
     "dest": "~/.claude/CLAUDE.md", "label": "Claude global instructions"},
]
DOC_TRAILER_CLAUDE = {"src": "CLAUDE.md", "dest": "(not installed)",
                      "label": "Bindle project guidance for Claude"}
DOC_ROWS_CODEX = [
    {"type": "global-guidance", "src": "global/AGENTS.md",
     "dest": "<explicit-codex-home>/AGENTS.md", "label": None},
]
DOC_TRAILER_CODEX = {"src": "AGENTS.md", "dest": "(not installed)",
                     "label": "Bindle project guidance for Codex"}
DOC_MARKER_FMT = "<!-- GENERATED:%s:BEGIN -->", "<!-- GENERATED:%s:END -->"


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


def render_manifest(caps):
    lines = [MANIFEST_BANNER]
    lines += ["\t".join(row) for row in build_manifest(caps)]
    return "\n".join(lines) + "\n"


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


def _render_doc_block(rows, trailer):
    """A fenced ```-block: one aligned line per row, then the static trailer."""
    all_lines = rows + [trailer]
    w_src = max(len(r["src"]) for r in all_lines)
    w_dest = max(len(r["dest"]) for r in all_lines)
    lines = []
    for r in all_lines:
        arrow = "->" if r is not trailer else "  "
        line = "%-*s   %s  %-*s %s" % (w_src, r["src"], arrow, w_dest, r["dest"],
                                       r["label"] or "")
        lines.append(line.rstrip())
    return "```\n" + "\n".join(lines) + "\n```"


def render_readme_claude_block():
    return _render_doc_block(DOC_ROWS_CLAUDE, DOC_TRAILER_CLAUDE)


def render_readme_codex_block():
    return _render_doc_block(DOC_ROWS_CODEX, DOC_TRAILER_CODEX)


def render_provider_interop_table():
    lines = ["| Repo path | Claude install target |", "|---|---|"]
    for r in DOC_ROWS_CLAUDE:
        lines.append("| `%s` | `%s` |" % (r.get("table_src", r["src"]), r["dest"]))
    return "\n".join(lines)


DOC_TARGETS = [
    ("README.md", "readme-claude", render_readme_claude_block),
    ("README.md", "readme-codex", render_readme_codex_block),
    ("docs/provider-interop.md", "provider-interop-install-table",
     render_provider_interop_table),
]


def _replace_marked_region(text, marker_name, body):
    begin = "<!-- GENERATED:%s:BEGIN -->" % marker_name
    end = "<!-- GENERATED:%s:END -->" % marker_name
    if begin not in text or end not in text:
        raise ValueError("markers %s / %s not found" % (begin, end))
    pre, rest = text.split(begin, 1)
    _, post = rest.split(end, 1)
    return pre + begin + "\n" + body + "\n" + end + post


def check_doc_row_types():
    """DOC_ROWS_CLAUDE must cover exactly INSTALL_TYPES — a new install type
    needs a template row here before the docs can regenerate for it."""
    have = {r["type"] for r in DOC_ROWS_CLAUDE}
    want = set(INSTALL_TYPES)
    if have != want:
        return ["DOC_ROWS_CLAUDE types %s do not match INSTALL_TYPES %s — add "
                "a template row for the new type" % (sorted(have), sorted(want))]
    return []


def emit_docs(root):
    by_file = {}
    for rel, marker, render in DOC_TARGETS:
        by_file.setdefault(rel, []).append((marker, render()))
    for rel, marks in by_file.items():
        path = os.path.join(root, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for marker, body in marks:
            text = _replace_marked_region(text, marker, body)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def check_docs(root):
    errors = check_doc_row_types()
    by_file = {}
    for rel, marker, render in DOC_TARGETS:
        by_file.setdefault(rel, []).append((marker, render()))
    for rel, marks in by_file.items():
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            errors.append("%s: missing" % rel)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        want = text
        try:
            for marker, body in marks:
                want = _replace_marked_region(want, marker, body)
        except ValueError as exc:
            errors.append("%s: %s" % (rel, exc))
            continue
        if want != text:
            errors.append("%s: generated doc tables stale — run 'make docs'" % rel)
    return errors


def load_inventory(root):
    path = os.path.join(root, "capabilities.json")
    if not os.path.isfile(path):
        raise ValueError("capabilities.json: missing at repo root")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError("capabilities.json: invalid JSON (%s)" % exc)
    if not isinstance(data, dict):
        raise ValueError("capabilities.json: top level must be an object")
    caps = data.get("capabilities")
    ledger = data.get("not_a_capability", [])
    if not isinstance(caps, list):
        raise ValueError("capabilities.json: 'capabilities' must be an array")
    if not isinstance(ledger, list):
        raise ValueError("capabilities.json: 'not_a_capability' must be an array")
    return caps, ledger


def read_version(root):
    with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


def _semver_tuple(v):
    return tuple(int(x) for x in v.split("."))


def _next_release_tuples(version):
    """The single-bump-ahead versions that count as 'the next unreleased
    release' from `version` — next patch, next minor, or next major. Two or
    more bumps ahead is still out of bounds, regardless of which bump the
    next actual release turns out to be."""
    major, minor, patch = _semver_tuple(version)
    return {
        (major, minor, patch + 1),
        (major, minor + 1, 0),
        (major + 1, 0, 0),
    }


def check_schema(caps, version):
    errors = []
    seen = set()
    for i, cap in enumerate(caps):
        if not isinstance(cap, dict):
            errors.append("<row %d>: not an object" % i)
            continue
        label = cap.get("name", "<row %d>" % i)
        for field in REQUIRED:
            if field not in cap:
                errors.append("%s: missing required field '%s'" % (label, field))
        if cap.get("type") not in TYPES:
            errors.append("%s: invalid type '%s'" % (label, cap.get("type")))
        key = (cap.get("type"), cap.get("name"))
        if key in seen:
            errors.append("%s: duplicate (type, name) %s" % (label, key))
        seen.add(key)
        prov = cap.get("provider")
        if isinstance(prov, dict):
            for p in ("claude", "codex"):
                if prov.get(p) not in PROVIDER_STATUS:
                    errors.append("%s: provider.%s '%s' not in %s"
                                  % (label, p, prov.get(p), sorted(PROVIDER_STATUS)))
        else:
            errors.append("%s: provider must be an object with claude+codex" % label)
        if cap.get("maturity") not in MATURITY:
            errors.append("%s: invalid maturity '%s'" % (label, cap.get("maturity")))
        mut = cap.get("mutation")
        if not isinstance(mut, list) or any(m not in MUTATION_FLAGS for m in mut):
            errors.append("%s: mutation must be a subset of %s"
                          % (label, sorted(MUTATION_FLAGS)))
        vi = str(cap.get("version_introduced", ""))
        if not SEMVER.match(vi):
            errors.append("%s: version_introduced '%s' is not semver" % (label, vi))
        elif (_semver_tuple(vi) > _semver_tuple(version)
              and _semver_tuple(vi) not in _next_release_tuples(version)):
            errors.append("%s: version_introduced %s is ahead of the next "
                          "unreleased release from VERSION %s"
                          % (label, vi, version))
    return errors


def _bijection(type_name, inventory_names, fs_names):
    errors = []
    for missing in sorted(fs_names - inventory_names):
        errors.append("%s '%s' exists on disk but is missing from the inventory"
                      % (type_name, missing))
    for extra in sorted(inventory_names - fs_names):
        errors.append("%s '%s' is in the inventory but not found on disk"
                      % (type_name, extra))
    return errors


def check_completeness_clean(caps, root):
    errors = []

    def names_of(t):
        return {c.get("name") for c in caps if c.get("type") == t}

    fs_skills = set()
    skills_dir = os.path.join(root, "skills")
    if os.path.isdir(skills_dir):
        for entry in os.listdir(skills_dir):
            if entry.startswith(("_", ".")):
                continue
            if os.path.isfile(os.path.join(skills_dir, entry, "SKILL.md")):
                fs_skills.add(entry)
    errors += _bijection("skill", names_of("skill"), fs_skills)

    for t, d in (("command", "commands"), ("agent", "agents")):
        fs = set()
        dd = os.path.join(root, d)
        if os.path.isdir(dd):
            for entry in os.listdir(dd):
                if entry.startswith(("_", ".")) or not entry.endswith(".md"):
                    continue
                fs.add(entry[:-3])
        errors += _bijection(t, names_of(t), fs)

    gg = {"claude": "global/CLAUDE.md", "agents": "global/AGENTS.md"}
    fs_gg = {label for label, rel in gg.items()
             if os.path.isfile(os.path.join(root, rel))}
    errors += _bijection("global-guidance", names_of("global-guidance"), fs_gg)
    return errors


AUTO_EXCLUDE = [
    re.compile(r"^bin/test-.*\.sh$"),   # the test harness, never a capability
    re.compile(r"^docs/design/"),       # design specs
    re.compile(r"^docs/plans/"),        # implementation plans
]


def _tracked_under(root, subdir):
    """Tracked files under subdir (via git), so untracked scratch never trips
    the check. Returns [] if git is unavailable."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", subdir],
                             capture_output=True, text=True, check=True)
        return [line for line in out.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return []


def check_completeness_fuzzy(caps, ledger, root):
    errors = []
    inv_paths = {c.get("path") for c in caps
                 if c.get("type") in ("script", "contract")}
    led_paths = {e.get("path") for e in ledger}
    candidates = [p for p in _tracked_under(root, "bin")
                  if p.endswith((".sh", ".py"))]
    candidates += [p for p in _tracked_under(root, "docs") if p.endswith(".md")]
    for path in sorted(set(candidates)):
        if any(rx.search(path) for rx in AUTO_EXCLUDE):
            continue
        if path in inv_paths or path in led_paths:
            continue
        errors.append("%s: unclassified — add it to the inventory (type "
                      "script/contract) or to not_a_capability with a reason" % path)
    return errors


def check_paths(caps, root):
    errors = []
    for cap in caps:
        p = cap.get("path")
        if p and not os.path.exists(os.path.join(root, p)):
            errors.append("%s: path '%s' does not exist" % (cap.get("name"), p))
        for rel in cap.get("related_docs", []) or []:
            if not os.path.exists(os.path.join(root, rel)):
                errors.append("%s: related_docs '%s' does not exist"
                              % (cap.get("name"), rel))
    return errors


def _read_fm_value(path, key):
    """Read a single-line `key: value` from a leading --- frontmatter block."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^%s:\s*(.*)$" % re.escape(key), line)
        if m:
            return m.group(1).strip()
    return None


def _frontmatter_description(root, cap):
    t, p = cap.get("type"), cap.get("path")
    if t == "skill":
        f = os.path.join(root, p, "SKILL.md")
    elif t in ("command", "agent"):
        f = os.path.join(root, p)
    else:
        return None
    if not os.path.isfile(f):
        return None
    return _read_fm_value(f, "description")


def check_crosschecks(caps, root):
    errors = []
    for cap in caps:
        t = cap.get("type")
        if t in ("skill", "command", "agent"):
            fm = _frontmatter_description(root, cap)
            if fm is not None and fm != cap.get("description"):
                errors.append("%s: description does not match %s frontmatter"
                              % (cap.get("name"), t))
        if t == "skill" and cap.get("maturity") == "tested":
            pt = os.path.join(root, cap.get("path", ""), "PRESSURE-TESTS.md")
            if not os.path.isfile(pt):
                errors.append("%s: maturity 'tested' but no PRESSURE-TESTS.md"
                              % cap.get("name"))
    return errors


def _audit_skill_names(path):
    names = set()
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    in_table = False
    for line in lines:
        if line.strip().startswith("| Skill |"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            cell = line.split("|")[1].strip().strip("`").strip()
            if not cell or set(cell) <= set("-: "):
                continue  # separator row (|---|)
            if "/" in cell or cell.startswith("_"):
                continue  # not a bare skill name (e.g. the skills/_template/ row)
            names.add(cell)
    return names


def check_bound_table(caps, root):
    errors = []
    audit = os.path.join(root, "docs/skill-portability-audit.md")
    if not os.path.isfile(audit):
        errors.append("docs/skill-portability-audit.md: missing (bound table for "
                      "criterion c)")
        return errors
    inv = {c.get("name") for c in caps if c.get("type") == "skill"}
    tbl = _audit_skill_names(audit)
    for missing in sorted(inv - tbl):
        errors.append("skill '%s' in inventory but not in skill-portability-audit "
                      "table" % missing)
    for extra in sorted(tbl - inv):
        errors.append("skill '%s' in skill-portability-audit table but not in "
                      "inventory" % extra)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument("--emit-manifest", nargs="?", const="", default=None,
                        metavar="PATH",
                        help="write the install manifest (default "
                             "install-manifest.tsv under --root; '-' = stdout)")
    parser.add_argument("--check-manifest", action="store_true",
                        help="also verify install-manifest.tsv matches the "
                             "inventory (drift guard)")
    parser.add_argument("--emit-docs", action="store_true",
                        help="regenerate the marked blocks in README.md and "
                             "docs/provider-interop.md")
    parser.add_argument("--check-docs", action="store_true",
                        help="also verify README.md/provider-interop.md "
                             "generated blocks match (drift guard)")
    args = parser.parse_args(argv)
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        caps, ledger = load_inventory(root)
        version = read_version(root)
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    # Non-dict rows are already reported by check_schema below; drop them here
    # so the remaining checks (which assume dict rows) don't also crash on them.
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
    if args.emit_docs:
        emit_docs(root)
        print("wrote README.md + docs/provider-interop.md generated blocks")
        return 0
    errors = []
    errors += check_schema(caps, version)
    errors += check_completeness_clean(dict_caps, root)
    errors += check_completeness_fuzzy(dict_caps, ledger, root)
    errors += check_paths(dict_caps, root)
    errors += check_crosschecks(dict_caps, root)
    errors += check_bound_table(dict_caps, root)
    if args.check_manifest:
        errors += check_manifest(dict_caps, root)
    if args.check_docs:
        errors += check_docs(root)
    # NOTE: later tasks append more checks here.
    if errors:
        for e in errors:
            print(e)
        return 1
    print("capability inventory OK (%d capabilities, %d ledgered exclusions)"
          % (len(caps), len(ledger)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
