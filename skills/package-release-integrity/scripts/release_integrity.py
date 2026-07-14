#!/usr/bin/env python3
"""Portable package release-integrity checker (issue #59).

Deterministic, mechanical checks for a Python package release. Judgment checks
(change classification, track routing) return 'uncertain' — never guessed.
Stdlib only. Never mutates; a green check is not authorization to publish.
"""
import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# change class -> required bump component, split by pre/post 1.0.
# Pre-1.0 (0.x): a breaking change bumps the MINOR; additive/fix bump PATCH.
# Post-1.0: standard semver.
_MOVEMENT = {
    False: {"breaking": "major", "additive": "minor", "patch": "patch"},
    True: {"breaking": "minor", "additive": "patch", "patch": "patch"},
}


def parse_version(s):
    """Parse an exact MAJOR.MINOR.PATCH string. Returns a tuple or None."""
    if s is None:
        return None
    m = SEMVER_RE.match(s.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def is_pre_1_0(ver):
    """True when the version is in the 0.x unstable series."""
    return ver[0] == 0


def bump_type(old, new):
    """Which single component increased old->new. None if no clean increase."""
    if new[0] > old[0]:
        return "major"
    if new[0] == old[0] and new[1] > old[1]:
        return "minor"
    if new[0] == old[0] and new[1] == old[1] and new[2] > old[2]:
        return "patch"
    return None


def required_movement(change_class, pre_1_0):
    """Required bump component for a change class. data-only -> None (no move)."""
    if change_class == "data-only":
        return None
    return _MOVEMENT[bool(pre_1_0)].get(change_class)


def _verdict(check, verdict, detail):
    return {"check": check, "verdict": verdict, "detail": detail}


def discover_version_sources(repo):
    """Find declared package versions. Maps a source label -> raw version str.

    Sources: pyproject.toml [project].version, [tool.poetry].version, and any
    top-level package `__init__.py` defining `__version__`.
    """
    repo = Path(repo)
    sources = {}
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text())
        proj = data.get("project", {}).get("version")
        if proj is not None:
            sources["pyproject:[project].version"] = proj
        poetry = data.get("tool", {}).get("poetry", {}).get("version")
        if poetry is not None:
            sources["pyproject:[tool.poetry].version"] = poetry
    # (["'])([^"']+)\1 — backreferenced quote; avoids a "]" + "(" adjacency
    # that the repo's file-wide link checker would misread as a broken link.
    ver_re = re.compile(r"""^__version__\s*=\s*(["'])([^"']+)\1""", re.M)
    for init in sorted(repo.glob("*/__init__.py")):
        m = ver_re.search(init.read_text())
        if m:
            sources[f"module:{init.relative_to(repo)}"] = m.group(2)
    return sources


def check_version_source_consistency(sources):
    if not sources:
        return _verdict(
            "version_source_consistency", "uncertain", "no version source found"
        )
    distinct = set(sources.values())
    if len(distinct) == 1:
        return _verdict(
            "version_source_consistency", "pass",
            f"all sources agree on {next(iter(distinct))}",
        )
    return _verdict(
        "version_source_consistency", "fail",
        "version sources disagree: "
        + ", ".join(f"{k}={v}" for k, v in sorted(sources.items())),
    )


def resolved_package_version(sources):
    """The agreed package version, or None if absent/conflicting."""
    distinct = set(sources.values())
    return next(iter(distinct)) if len(distinct) == 1 else None


def check_tag_consistency(pkg_version, tag):
    if tag is None:
        return _verdict("tag_consistency", "uncertain", "no --tag supplied")
    if pkg_version is None:
        return _verdict("tag_consistency", "uncertain", "no resolved package version")
    norm = tag[1:] if tag.startswith("v") else tag
    if norm == pkg_version:
        return _verdict("tag_consistency", "pass", f"tag {tag} == version {pkg_version}")
    return _verdict(
        "tag_consistency", "fail", f"tag {tag} (={norm}) != version {pkg_version}"
    )


def check_changelog_present(repo, pkg_version, required):
    changelog = Path(repo) / "CHANGELOG.md"
    if not changelog.is_file():
        verdict = "fail" if required else "uncertain"
        return _verdict("changelog_present", verdict, "CHANGELOG.md not found")
    text = changelog.read_text()
    if (pkg_version is not None and f"[{pkg_version}]" in text) or "[Unreleased]" in text:
        return _verdict(
            "changelog_present", "pass", f"section for {pkg_version} or [Unreleased]"
        )
    verdict = "fail" if required else "uncertain"
    return _verdict(
        "changelog_present", verdict, f"no section for {pkg_version} or [Unreleased]"
    )


def run_check(repo, args):
    repo = Path(repo)
    verdicts = []
    sources = discover_version_sources(repo)
    verdicts.append(check_version_source_consistency(sources))
    pkg_version = resolved_package_version(sources)
    verdicts.append(check_tag_consistency(pkg_version, getattr(args, "tag", None)))
    required = not getattr(args, "no_changelog_required", False)
    verdicts.append(check_changelog_present(repo, pkg_version, required))
    ready = all(v["verdict"] != "fail" for v in verdicts)
    return {"verdicts": verdicts, "ready": ready}


def _print_report(report, as_json):
    if as_json:
        print(json.dumps(report, indent=2))
        return
    for v in report["verdicts"]:
        print(f"{v['check']}: {v['verdict']} — {v['detail']}")
    print(f"ready: {report['ready']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Portable package release-integrity checker")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="run release-integrity checks on a repo")
    c.add_argument("--repo", default=".", help="path to the package repo")
    c.add_argument("--json", action="store_true", help="emit JSON")
    c.add_argument("--tag", default=None, help="proposed/existing release tag")
    c.add_argument(
        "--no-changelog-required", action="store_true",
        help="treat a missing changelog section as uncertain, not fail",
    )
    args = p.parse_args(argv)
    if args.command == "check":
        report = run_check(args.repo, args)
        _print_report(report, args.json)
        # Exit non-zero only on a hard fail; 'uncertain' does not fail.
        return 1 if any(v["verdict"] == "fail" for v in report["verdicts"]) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
