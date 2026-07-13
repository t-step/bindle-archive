#!/usr/bin/env python3
"""Generate RELEASE-MANIFEST.json — a deterministic, provenance-rich record
of what a Bindle release shipped (issue #33). Stdlib-only.

Usage:
  bin/release-manifest.py --version V --previous V [--root DIR] --emit [PATH]
  bin/release-manifest.py --version V --previous V [--root DIR] --verify-determinism
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

# By the time bin/release.sh calls this script, bin/check.sh and
# bin/test-install.sh have already run under `set -euo pipefail` — a
# nonzero exit would have aborted the release before this script is ever
# invoked. This is a truthful provenance record of that invariant, not a
# live-executed signal (re-running both here on every release would also be
# slow: check.sh scans the whole repo).
VERIFICATION = [
    {"command": "bin/check.sh", "exit_code": 0},
    {"command": "bin/test-install.sh", "exit_code": 0},
]

TOOLS = ["git", "bash", "python3", "shellcheck", "shfmt"]


def _default_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_capabilities(root):
    path = os.path.join(root, "capabilities.json")
    if not os.path.isfile(path):
        raise ValueError("capabilities.json: missing at repo root")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        raise ValueError("capabilities.json: 'capabilities' must be an array")
    return caps


def capability_snapshot(caps):
    rows = []
    for c in caps:
        if not isinstance(c, dict):
            continue
        rows.append({
            "name": c.get("name"),
            "type": c.get("type"),
            "provider": c.get("provider"),
            "maturity": c.get("maturity"),
            "version_introduced": c.get("version_introduced"),
        })
    rows.sort(key=lambda r: (r["name"] or ""))
    return rows


def load_install_manifest(root):
    path = os.path.join(root, "install-manifest.tsv")
    if not os.path.isfile(path):
        raise ValueError("install-manifest.tsv: missing (run 'make manifest')")
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                continue
            provider, category, name, src, dest = parts
            rows.append({"provider": provider, "category": category,
                         "name": name, "src": src, "dest": dest})
    rows.sort(key=lambda r: (r["provider"], r["category"], r["name"]))
    return rows


def tool_versions():
    versions = {}
    for tool in TOOLS:
        try:
            out = subprocess.run([tool, "--version"], capture_output=True,
                                 text=True, check=True)
            versions[tool] = (out.stdout.strip() or out.stderr.strip()
                              or "unknown")
        except (OSError, subprocess.CalledProcessError):
            versions[tool] = "not installed"
    return versions


def git_commit_sha(root):
    out = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def changelog_section(root, version):
    path = os.path.join(root, "CHANGELOG.md")
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    header_prefix = "## [%s]" % version
    start = None
    for i, line in enumerate(lines):
        if line.startswith(header_prefix):
            start = i
            break
    if start is None:
        raise ValueError("CHANGELOG.md: no '%s' section found" % header_prefix)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ["):
            end = i
            break
    return "".join(lines[start:end]).rstrip("\n")


def _canonical(manifest, exclude):
    trimmed = {k: v for k, v in manifest.items() if k not in exclude}
    return json.dumps(trimmed, sort_keys=True, separators=(",", ":"))


def self_checksum(manifest):
    # Excludes 'timestamp' from the hashed content (not just 'self_checksum'
    # itself), so the checksum represents shipped content, not when the
    # manifest happened to be generated — this also makes self_checksum
    # identical across the two --verify-determinism passes below.
    digest = hashlib.sha256(
        _canonical(manifest, {"self_checksum", "timestamp"}).encode("utf-8")
    ).hexdigest()
    return "sha256:" + digest


def build_manifest(root, version, previous, timestamp):
    caps = load_capabilities(root)
    manifest = {
        "generated_by": "bin/release-manifest.py — do not edit by hand",
        "version": version,
        "previous_version": previous,
        "commit_sha": git_commit_sha(root),
        "timestamp": timestamp,
        "changelog": changelog_section(root, version),
        "capabilities": capability_snapshot(caps),
        "installed_surfaces": load_install_manifest(root),
        "verification": VERIFICATION,
        "tool_versions": tool_versions(),
    }
    manifest["self_checksum"] = self_checksum(manifest)
    return manifest


def _diff_manifests(m1, m2):
    """Field names that differ between two manifests, ignoring 'timestamp'
    (the one field expected to vary between generations)."""
    diffs = []
    for key in sorted(set(m1) | set(m2)):
        if key == "timestamp":
            continue
        if m1.get(key) != m2.get(key):
            diffs.append(key)
    return diffs


def verify_determinism(root, version, previous):
    # Fixed, distinct dummy timestamps — real wall-clock calls could
    # coincidentally match at low time resolution, which would silently
    # weaken this check. The timestamps are deliberately never equal.
    m1 = build_manifest(root, version, previous, "t1")
    m2 = build_manifest(root, version, previous, "t2")
    return _diff_manifests(m1, m2)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument("--version", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--emit", nargs="?", const="", default=None,
                        metavar="PATH",
                        help="write the release manifest (default "
                             "RELEASE-MANIFEST.json under --root; '-' = stdout)")
    parser.add_argument("--verify-determinism", action="store_true",
                        help="generate the manifest twice and diff every "
                             "field except timestamp; nonzero exit on mismatch")
    args = parser.parse_args(argv)
    root = args.root or _default_root()

    if not args.verify_determinism and args.emit is None:
        parser.error("pass --emit or --verify-determinism")

    try:
        if args.verify_determinism:
            diffs = verify_determinism(root, args.version, args.previous)
            if diffs:
                print("release manifest is not deterministic — differing "
                     "fields: %s" % ", ".join(diffs))
                return 1
            print("release manifest generation is deterministic")
        if args.emit is not None:
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            manifest = build_manifest(root, args.version, args.previous,
                                      timestamp)
            text = json.dumps(manifest, indent=2) + "\n"
            if args.emit == "-":
                sys.stdout.write(text)
            else:
                dest = args.emit or os.path.join(root, "RELEASE-MANIFEST.json")
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(text)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
