#!/usr/bin/env python3
"""Publish a tagged release only through verified provenance and a safe draft."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


VIEW_FIELDS = "tagName,targetCommitish,name,body,isDraft,isPrerelease,assets"
ARTIFACT_NAME = "bindle-release-provenance.json"
CHECKSUM_NAME = f"{ARTIFACT_NAME}.sha256"
EXPECTED_ASSETS = {ARTIFACT_NAME, CHECKSUM_NAME}
REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")


class PublicationError(Exception):
    """A pre-publication invariant failed."""


def release_not_found(stderr: str) -> bool:
    """Recognize only gh's normalized exact missing-release classification."""
    return stderr in {
        "release not found",
        "release not found\n",
        "release not found\r\n",
    }


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError(f"release view: duplicate JSON member {key!r}")
        result[key] = value
    return result


def _run(argv, *, cwd=None, capture_output=False):
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=capture_output,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else f"exit {exc.returncode}"
        raise PublicationError(f"{' '.join(argv[:3])}: {detail}") from None
    except OSError as exc:
        raise PublicationError(f"{argv[0]}: {exc}") from None


def _source_state(root: Path, tag: str) -> dict:
    completed = _run(
        [
            "python3", "bin/release-provenance.py", "verify-source",
            "--tag", tag, "--json",
        ],
        cwd=root,
        capture_output=True,
    )
    try:
        source = json.loads(completed.stdout, object_pairs_hook=_json_object)
    except (json.JSONDecodeError, PublicationError) as exc:
        raise PublicationError(f"verify-source: invalid JSON ({exc})") from None
    if not isinstance(source, dict):
        raise PublicationError("verify-source: expected a JSON object")
    return source


def _release_view(repo: str, tag: str):
    argv = [
        "gh", "release", "view", tag,
        "--repo", repo, "--json", VIEW_FIELDS,
    ]
    try:
        completed = subprocess.run(
            argv, check=False, capture_output=True, text=True
        )
    except OSError as exc:
        raise PublicationError(f"gh: {exc}") from None
    if completed.returncode != 0:
        if completed.returncode == 1 and release_not_found(completed.stderr):
            return None
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise PublicationError(f"gh release view: {detail}")
    try:
        release = json.loads(
            completed.stdout, object_pairs_hook=_json_object
        )
    except (json.JSONDecodeError, PublicationError) as exc:
        raise PublicationError(f"release view: invalid JSON ({exc})") from None
    return release


def _validate_draft(release, *, tag: str, commit: str, body: str) -> bool:
    fields = {
        "tagName", "targetCommitish", "name", "body", "isDraft",
        "isPrerelease", "assets",
    }
    if not isinstance(release, dict) or set(release) != fields:
        raise PublicationError("release view: invalid field set")
    expected = {
        "tagName": tag,
        "targetCommitish": commit,
        "name": tag,
        "body": body,
        "isDraft": True,
        "isPrerelease": False,
    }
    for field, value in expected.items():
        if release[field] != value:
            raise PublicationError(f"release draft: {field} mismatch")
    assets = release["assets"]
    if not isinstance(assets, list):
        raise PublicationError("release draft: assets must be an array")
    names = []
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise PublicationError("release draft: invalid asset metadata")
        names.append(asset["name"])
    if len(names) != len(set(names)):
        raise PublicationError("release draft: duplicate asset name")
    name_set = set(names)
    if name_set not in (set(), EXPECTED_ASSETS):
        raise PublicationError("release draft: unsafe asset set")
    return name_set == EXPECTED_ASSETS


def _prepare(root: Path, repo: str, tag: str, temporary) -> None:
    temporary.validate()
    temporary_path = temporary.path
    source = _source_state(root, tag)
    if source.get("repository") != repo:
        raise PublicationError("repository argument does not match tagged source")
    if source.get("tag") != tag or not isinstance(source.get("commit_sha"), str):
        raise PublicationError("verify-source: inconsistent source state")
    commit = source["commit_sha"]

    temporary.validate()
    evidence = temporary_path / "evidence.json"
    upload = temporary_path / "upload"
    download = temporary_path / "download"
    upload.mkdir()
    download.mkdir()
    temporary.validate()
    _run(
        [
            "python3", "bin/release-provenance.py", "collect-evidence",
            "--tag", tag, "--output", str(evidence),
        ],
        cwd=root,
    )
    temporary.validate()
    _run(
        [
            "python3", "bin/release-provenance.py", "generate",
            "--tag", tag, "--evidence", str(evidence),
            "--output-dir", str(upload),
        ],
        cwd=root,
    )
    local_artifact = upload / ARTIFACT_NAME
    local_checksum = upload / CHECKSUM_NAME
    temporary.validate()
    _run(
        [
            "python3", "bin/release-provenance.py", "verify",
            "--tag", tag, "--artifact", str(local_artifact),
            "--checksum", str(local_checksum),
        ],
        cwd=root,
    )
    temporary.validate()
    local_digest = hashlib.sha256(local_artifact.read_bytes()).digest()
    try:
        document = json.loads(
            local_artifact.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, PublicationError) as exc:
        raise PublicationError(f"local artifact: invalid JSON ({exc})") from None
    body = document.get("changelog") if isinstance(document, dict) else None
    if not isinstance(body, str):
        raise PublicationError("local artifact: missing changelog")
    notes = temporary_path / "release-notes.md"
    notes.write_bytes(body.encode("utf-8"))

    temporary.validate()
    release = _release_view(repo, tag)
    clobber = False
    if release is None:
        temporary.validate()
        _run([
            "gh", "release", "create", tag, "--draft", "--verify-tag",
            "--target", commit, "--title", tag, "--notes-file", str(notes),
            "--repo", repo,
        ])
    else:
        clobber = _validate_draft(
            release, tag=tag, commit=commit, body=body
        )

    upload_argv = [
        "gh", "release", "upload", tag,
        str(local_artifact), str(local_checksum),
    ]
    if clobber:
        upload_argv.append("--clobber")
    upload_argv.extend(["--repo", repo])
    temporary.validate()
    _run(upload_argv)
    temporary.validate()
    _run([
        "gh", "release", "download", tag,
        "--pattern", ARTIFACT_NAME,
        "--pattern", CHECKSUM_NAME,
        "--dir", str(download), "--repo", repo,
    ])
    downloaded_artifact = download / ARTIFACT_NAME
    downloaded_checksum = download / CHECKSUM_NAME
    temporary.validate()
    try:
        downloaded_digest = hashlib.sha256(
            downloaded_artifact.read_bytes()
        ).digest()
    except OSError as exc:
        raise PublicationError(f"downloaded artifact: {exc}") from None
    if downloaded_digest != local_digest:
        raise PublicationError("downloaded artifact does not match uploaded JSON")
    temporary.validate()
    _run(
        [
            "python3", "bin/release-provenance.py", "verify",
            "--tag", tag, "--artifact", str(downloaded_artifact),
            "--checksum", str(downloaded_checksum),
        ],
        cwd=root,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent.parent)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    return parser


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _cleanup_temporary_entry(
    entry: Path, expected_identity=None
) -> bool:
    try:
        metadata = os.lstat(entry)
    except FileNotFoundError:
        return False
    matches = True
    if expected_identity is not None:
        matches = (
            stat.S_ISDIR(metadata.st_mode)
            and expected_identity == (metadata.st_dev, metadata.st_ino)
        )
    if stat.S_ISDIR(metadata.st_mode):
        shutil.rmtree(entry)
    else:
        os.unlink(entry)
    return matches


class PublicationTemporary:
    """A validated lease on the original lexical mkdtemp entry."""

    def __init__(self, path: Path, root: Path, metadata):
        self.path = path
        self.root = root
        self.identity = (metadata.st_dev, metadata.st_ino)

    def validate(self) -> None:
        try:
            metadata = os.lstat(self.path)
        except OSError as exc:
            raise PublicationError(f"temporary entry: {exc}") from None
        if not stat.S_ISDIR(metadata.st_mode):
            raise PublicationError("temporary entry must remain a real directory")
        if (metadata.st_dev, metadata.st_ino) != self.identity:
            raise PublicationError("temporary entry identity changed")
        try:
            canonical = self.path.resolve(strict=True)
        except OSError as exc:
            raise PublicationError(f"temporary entry: {exc}") from None
        if canonical != self.path or _inside(self.root, canonical):
            raise PublicationError(
                "temporary entry must remain canonical and outside repository"
            )

    def cleanup(self, *, require_identity=False) -> None:
        validation_error = None
        if require_identity:
            try:
                self.validate()
            except PublicationError as exc:
                validation_error = exc
        matched = _cleanup_temporary_entry(self.path, self.identity)
        try:
            os.lstat(self.path)
        except FileNotFoundError:
            pass
        else:
            _cleanup_temporary_entry(self.path)
            raise PublicationError("temporary entry reappeared during cleanup")
        if require_identity and (validation_error is not None or not matched):
            raise validation_error or PublicationError(
                "temporary entry identity changed before cleanup"
            )


def _temporary_directory(root: Path) -> PublicationTemporary:
    try:
        base = Path(tempfile.gettempdir()).resolve(strict=True)
    except OSError as exc:
        raise PublicationError(f"temporary base: {exc}") from None
    if not base.is_dir():
        raise PublicationError("temporary base must be a directory")
    if _inside(root, base):
        raise PublicationError("temporary base must be outside repository root")
    try:
        created = Path(tempfile.mkdtemp(
            prefix="bindle-publication.", dir=base
        ))
    except OSError as exc:
        raise PublicationError(f"temporary directory: {exc}") from None
    if (
        not created.is_absolute()
        or created.parent != base
        or not created.name.startswith("bindle-publication.")
    ):
        if created.is_absolute() and created.parent == base:
            _cleanup_temporary_entry(created)
        raise PublicationError("mkdtemp returned an unexpected lexical entry")
    try:
        metadata = os.lstat(created)
        temporary = PublicationTemporary(created, root, metadata)
        temporary.validate()
    except (OSError, PublicationError):
        _cleanup_temporary_entry(created)
        raise
    return temporary


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    if REPOSITORY.fullmatch(args.repo) is None:
        print("--repo must be OWNER/REPO", file=sys.stderr)
        return 1
    try:
        temporary = _temporary_directory(root)
    except (PublicationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # Ordinary failures clean up explicitly. An external terminating signal can
    # leave temporary evidence, but cannot advance the still-draft release.
    try:
        _prepare(root, args.repo, args.tag, temporary)
        temporary.cleanup(require_identity=True)
    except (PublicationError, OSError) as exc:
        cleanup_error = None
        try:
            temporary.cleanup()
        except (PublicationError, OSError) as cleanup_exc:
            cleanup_error = cleanup_exc
        print(str(exc), file=sys.stderr)
        if cleanup_error is not None:
            print(f"temporary cleanup: {cleanup_error}", file=sys.stderr)
        return 1
    os.execvp("gh", [
        "gh", "release", "edit", args.tag, "--draft=false", "--repo", args.repo,
    ])


if __name__ == "__main__":
    sys.exit(main())
