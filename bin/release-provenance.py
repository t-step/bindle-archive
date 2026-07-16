#!/usr/bin/env python3
"""Verify the source state for a tagged Bindle release."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def annotated_tag(root: Path, tag: str) -> tuple[str, str]:
    ref = f"refs/tags/{tag}"
    if git(root, "cat-file", "-t", ref) != "tag":
        raise ValueError(f"{tag}: annotated tag required")
    fields = dict(
        line.split(" ", 1)
        for line in git(root, "cat-file", "-p", ref).splitlines()
        if line.startswith(("object ", "type "))
    )
    if fields.get("type") != "commit":
        raise ValueError(f"{tag}: tag must point directly to a commit")
    return git(root, "rev-parse", ref), fields["object"]


def _repository(root: Path) -> str:
    origin = git(root, "remote", "get-url", "origin")
    if origin.startswith("git@") and ":" in origin:
        repository = origin.split(":", 1)[1]
    else:
        parsed = urlparse(origin)
        repository = parsed.path.lstrip("/") if parsed.scheme else origin
    if repository.endswith(".git"):
        repository = repository[:-4]
    if repository.count("/") != 1:
        raise ValueError("origin: expected repository in OWNER/REPO form")
    return repository


def _tagged_file(root: Path, commit: str, path: str) -> str:
    try:
        return git(root, "show", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        raise ValueError(f"{path}: missing from tagged commit") from None


def _version(root: Path, commit: str) -> str:
    version = _tagged_file(root, commit, "version.txt").strip()
    if not version:
        raise ValueError("version.txt: empty")
    return version


def _release_please_version(root: Path, commit: str) -> str:
    data = json.loads(
        _tagged_file(root, commit, ".release-please-manifest.json")
    )
    version = data.get(".") if isinstance(data, dict) else None
    if not isinstance(version, str):
        raise ValueError(
            ".release-please-manifest.json: missing string root version"
        )
    return version


def _require_changelog_section(
    root: Path, commit: str, version: str
) -> None:
    header = f"## [{version}]"
    lines = _tagged_file(root, commit, "CHANGELOG.md").splitlines()
    if not any(line == header or line.startswith(f"{header} ") for line in lines):
        raise ValueError(f"CHANGELOG.md: missing exact '{header}' section")


def verify_source(root: Path, tag: str) -> dict:
    root = root.resolve()
    tag_object_sha, recorded_commit = annotated_tag(root, tag)
    peeled_commit = git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}")
    if recorded_commit != peeled_commit:
        raise ValueError(f"{tag}: recorded tag object does not match commit")
    if recorded_commit != git(root, "rev-parse", "HEAD"):
        raise ValueError(f"{tag}: tagged commit does not match HEAD")

    version = _version(root, recorded_commit)
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(f"{tag}: expected tag {expected_tag} from version.txt")

    release_please_version = _release_please_version(root, recorded_commit)
    if release_please_version != version:
        raise ValueError(
            ".release-please-manifest.json: root version "
            f"{release_please_version} does not match version.txt {version}"
        )
    _require_changelog_section(root, recorded_commit, version)

    tagger_timestamp = git(
        root,
        "for-each-ref",
        "--format=%(taggerdate:iso-strict)",
        f"refs/tags/{tag}",
    )
    if not tagger_timestamp:
        raise ValueError(f"{tag}: annotated tag has no tagger timestamp")
    return {
        "repository": _repository(root),
        "tag": tag,
        "tag_object_sha": tag_object_sha,
        "tagger_timestamp": tagger_timestamp,
        "commit_sha": recorded_commit,
        "version": version,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-source")
    verify.add_argument("--root", type=Path, default=_default_root())
    verify.add_argument("--tag", required=True)
    verify.add_argument("--json", action="store_true")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_source(args.root, args.tag)
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            for key, value in result.items():
                print(f"{key}: {value}")
    except (ValueError, OSError, json.JSONDecodeError,
            subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
