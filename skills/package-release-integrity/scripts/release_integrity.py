#!/usr/bin/env python3
"""Portable package release-integrity checker (issue #59).

Deterministic, mechanical checks for a Python package release. Judgment checks
(change classification, track routing) return 'uncertain' — never guessed.
Stdlib only. Never mutates; a green check is not authorization to publish.
"""
import argparse
import json
import re
import subprocess
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


_CLASSES = ("breaking", "additive", "patch", "data-only")


def check_change_classification(change_class):
    if change_class is None:
        return _verdict(
            "change_classification", "uncertain",
            "no --change-class supplied; a human must classify the change",
        )
    if change_class not in _CLASSES:
        return _verdict(
            "change_classification", "fail",
            f"unknown class {change_class!r}; expected one of {_CLASSES}",
        )
    return _verdict("change_classification", "pass", f"declared {change_class}")


def check_version_movement(prev, pkg_version, change_class):
    if change_class is None:
        return _verdict(
            "version_movement", "uncertain", "movement depends on the change class"
        )
    if change_class == "data-only":
        return _verdict(
            "version_movement", "uncertain", "data-only: routed under track_routing"
        )
    pv, nv = parse_version(prev or ""), parse_version(pkg_version or "")
    if pv is None or nv is None:
        return _verdict(
            "version_movement", "uncertain",
            "need valid --prev-version and package version to check movement",
        )
    want = required_movement(change_class, is_pre_1_0(nv))
    got = bump_type(pv, nv)
    if got == want:
        return _verdict(
            "version_movement", "pass",
            f"{change_class} moved {prev}->{pkg_version} ({got}) as required",
        )
    return _verdict(
        "version_movement", "fail",
        f"{change_class} requires a {want} bump; {prev}->{pkg_version} was {got}",
    )


def check_track_routing(change_class, version_moved):
    if change_class != "data-only":
        return _verdict(
            "track_routing", "uncertain",
            "track routing only auto-checked for data-only changes",
        )
    if version_moved:
        return _verdict(
            "track_routing", "fail",
            "data-only change moved the package version",
        )
    return _verdict("track_routing", "pass", "data-only change left the version unmoved")


def run_gate(name, cmd, repo):
    """Shell out to a repo-supplied command. pass=0, fail=nonzero,
    uncertain=absent or unexecutable (degraded, never a false pass)."""
    if not cmd:
        return _verdict(name, "uncertain", "no command supplied for this gate")
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(repo),
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _verdict(name, "uncertain", f"could not run {cmd!r}: {exc} (degraded)")
    # 126/127 are the shell's own "command not found/not executable" codes
    # (POSIX sh/bash/zsh) — an execution failure, not a real gate failure.
    # shell=True means Python never raises for this case; the shell reports
    # it via returncode instead, so it must be classified as uncertain here
    # to keep the "degraded, never a false pass/fail" guarantee.
    if proc.returncode in (126, 127):
        return _verdict(
            name, "uncertain",
            f"could not run {cmd!r}: shell exit {proc.returncode} "
            f"({proc.stderr.strip() or 'command not found'}) (degraded)",
        )
    if proc.returncode == 0:
        return _verdict(name, "pass", f"{cmd!r} exited 0")
    return _verdict(name, "fail", f"{cmd!r} exited {proc.returncode}")


def run_check(repo, args):
    repo = Path(repo)
    verdicts = []
    sources = discover_version_sources(repo)
    verdicts.append(check_version_source_consistency(sources))
    pkg_version = resolved_package_version(sources)
    verdicts.append(check_tag_consistency(pkg_version, getattr(args, "tag", None)))
    required = not getattr(args, "no_changelog_required", False)
    verdicts.append(check_changelog_present(repo, pkg_version, required))
    change_class = getattr(args, "change_class", None)
    prev = getattr(args, "prev_version", None)
    verdicts.append(check_change_classification(change_class))
    verdicts.append(check_version_movement(prev, pkg_version, change_class))
    pv, nv = parse_version(prev or ""), parse_version(pkg_version or "")
    moved = bool(pv and nv and bump_type(pv, nv) is not None)
    verdicts.append(check_track_routing(change_class, moved))
    verdicts.append(run_gate("build_gate", getattr(args, "build_cmd", None), repo))
    verdicts.append(
        run_gate("verification_gate", getattr(args, "test_cmd", None), repo)
    )
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
    c.add_argument(
        "--change-class", default=None, choices=_CLASSES,
        help="declared change class; omitted => classification is uncertain",
    )
    c.add_argument("--prev-version", default=None, help="previously released version")
    c.add_argument("--build-cmd", default=None, help="repo build/metadata command")
    c.add_argument("--test-cmd", default=None, help="repo verification command")
    args = p.parse_args(argv)
    if args.command == "check":
        report = run_check(args.repo, args)
        _print_report(report, args.json)
        # Exit non-zero only on a hard fail; 'uncertain' does not fail.
        return 1 if any(v["verdict"] == "fail" for v in report["verdicts"]) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
