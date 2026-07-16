#!/usr/bin/env python3
"""Verify the source state for a tagged Bindle release."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


STATUS = {"passed", "failed", "unknown", "skipped"}
ARTIFACT_NAME = "bindle-release-provenance.json"
CHECKSUM_NAME = f"{ARTIFACT_NAME}.sha256"
TOOLS = ["git", "bash", "python3", "shellcheck", "shfmt"]
SEMVER_TAG = re.compile(
    r"^v(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


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


def required_commands(tag: str) -> dict[str, list[str]]:
    return {
        "version_state": [
            "python3", "bin/release-provenance.py", "verify-source",
            "--tag", tag,
        ],
        "release_integrity": [
            "python3",
            "skills/package-release-integrity/scripts/release_integrity.py",
            "publication-check", "--repo", ".", "--tag", tag,
        ],
        "make_check": ["make", "check"],
        "make_test": ["make", "test"],
    }


def _json_bytes(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON: duplicate object member {key!r}")
        result[key] = value
    return result


def _parse_json(text: str, label: str):
    try:
        return json.loads(text, object_pairs_hook=_json_object)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: invalid JSON ({exc})") from None


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, _json_bytes(document))


def collect_evidence(
    root: Path,
    tag: str,
    output: Path,
    runner=subprocess.run,
) -> bool:
    root = root.resolve()
    repository = _repository(root)
    commit_sha = git(root, "rev-parse", "HEAD")
    checks = []
    successful = True
    for check_id, command in required_commands(tag).items():
        error = None
        try:
            completed = runner(command, cwd=root, check=False)
            exit_code = completed.returncode
        except OSError as exc:
            exit_code = 127
            error = f"OSError: {exc}"
        passed = exit_code == 0
        successful = successful and passed
        check = {
            "id": check_id,
            "required": True,
            "command": command,
            "status": "passed" if passed else "failed",
            "exit_code": exit_code,
        }
        if error is not None:
            check["error"] = error
        checks.append(check)
    document = {
        "schema_version": 1,
        "repository": repository,
        "tag": tag,
        "commit_sha": commit_sha,
        "checks": checks,
    }
    _write_json(Path(output), document)
    return successful


def validate_evidence(evidence: dict, source: dict) -> dict:
    expected_top = {
        "schema_version", "repository", "tag", "commit_sha", "checks"
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_top:
        raise ValueError("evidence: expected exact top-level key set")
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        raise ValueError("evidence: unsupported schema_version")
    for field in ("repository", "tag", "commit_sha"):
        if evidence[field] != source[field]:
            raise ValueError(f"evidence: {field} mismatch")
    if not isinstance(evidence["checks"], list):
        raise ValueError("evidence: checks must be an array")

    commands = required_commands(source["tag"])
    seen = set()
    for check in evidence["checks"]:
        base_keys = {
            "id", "required", "command", "status", "exit_code"
        }
        if (
            not isinstance(check, dict)
            or set(check) not in (base_keys, base_keys | {"error"})
        ):
            raise ValueError("evidence: check has invalid key set")
        check_id = check["id"]
        if not isinstance(check_id, str) or check_id in seen:
            raise ValueError(f"evidence: duplicate or invalid check {check_id!r}")
        seen.add(check_id)
        if check["status"] not in STATUS:
            raise ValueError(f"evidence: invalid status for {check_id}")
        if check_id not in commands:
            raise ValueError(f"evidence: unknown check {check_id}")
        if "error" in check and (
            check["status"] != "failed"
            or not isinstance(check["error"], str)
            or not check["error"]
        ):
            raise ValueError(f"evidence: invalid error for {check_id}")
        if check["required"] is not True:
            raise ValueError(f"evidence: {check_id} must be required")
        if check["command"] != commands[check_id]:
            raise ValueError(f"evidence: command mismatch for {check_id}")
        if check["status"] != "passed":
            raise ValueError(f"evidence: {check_id} did not pass")
        if type(check["exit_code"]) is not int or check["exit_code"] != 0:
            raise ValueError(f"evidence: nonzero exit for {check_id}")
    missing = set(commands) - seen
    if missing:
        raise ValueError(
            "evidence: missing required checks: " + ", ".join(sorted(missing))
        )
    return evidence


def _tagged_json(root: Path, commit: str, path: str):
    return _parse_json(_tagged_file(root, commit, path), path)


def _capability_snapshot(root: Path, commit: str) -> list[dict]:
    data = _tagged_json(root, commit, "capabilities.json")
    capabilities = data.get("capabilities") if isinstance(data, dict) else None
    if not isinstance(capabilities, list):
        raise ValueError("capabilities.json: 'capabilities' must be an array")
    rows = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("capabilities.json: capability must be an object")
        rows.append({
            "name": capability.get("name"),
            "type": capability.get("type"),
            "provider": capability.get("provider"),
            "maturity": capability.get("maturity"),
            "version_introduced": capability.get("version_introduced"),
        })
    return sorted(rows, key=lambda row: row["name"] or "")


def _install_snapshot(root: Path, commit: str) -> list[dict]:
    rows = []
    for line in _tagged_file(root, commit, "install-manifest.tsv").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            raise ValueError("install-manifest.tsv: invalid row")
        provider, category, name, src, dest = parts
        rows.append({
            "provider": provider, "category": category, "name": name,
            "src": src, "dest": dest,
        })
    return sorted(
        rows, key=lambda row: (
            row["provider"], row["category"], row["name"]
        )
    )


def _changelog_section(root: Path, commit: str, version: str) -> str:
    lines = _tagged_file(root, commit, "CHANGELOG.md").splitlines()
    header = f"## [{version}]"
    start = next(
        (index for index, line in enumerate(lines)
         if line == header or line.startswith(f"{header} ")),
        None,
    )
    if start is None:
        raise ValueError(f"CHANGELOG.md: missing exact '{header}' section")
    end = next(
        (index for index in range(start + 1, len(lines))
         if lines[index].startswith("## [")),
        len(lines),
    )
    return "\n".join(lines[start:end]).rstrip("\n")


def _tool_versions(runner=subprocess.run) -> dict[str, str]:
    versions = {}
    for tool in TOOLS:
        try:
            completed = runner(
                [tool, "--version"], check=True, capture_output=True, text=True
            )
            versions[tool] = (
                completed.stdout.strip() or completed.stderr.strip() or "unknown"
            )
        except (OSError, subprocess.CalledProcessError):
            versions[tool] = "not installed"
    return versions


def _previous_version(root: Path, tag: str, commit: str) -> str:
    parent = f"{commit}^"
    candidates = [
        candidate
        for candidate in git(
            root, "tag", "--merged", parent, "--list", "v*"
        ).splitlines()
        if candidate != tag and _is_semver_tag(candidate)
    ]
    if not candidates:
        raise ValueError("previous version: no reachable SemVer tag")
    distances = {
        candidate: int(git(root, "rev-list", "--count", f"{candidate}..{parent}"))
        for candidate in candidates
    }
    nearest_distance = min(distances.values())
    nearest = sorted(
        candidate for candidate, distance in distances.items()
        if distance == nearest_distance
    )
    if len(nearest) != 1:
        raise ValueError(
            "previous version: tied nearest SemVer tags: " + ", ".join(nearest)
        )
    return nearest[0][1:]


def _is_semver_tag(tag: str) -> bool:
    match = SEMVER_TAG.fullmatch(tag)
    if match is None:
        return False
    prerelease = match.group("prerelease")
    if prerelease is None:
        return True
    return not any(
        len(identifier) > 1 and identifier.startswith("0")
        for identifier in prerelease.split(".")
        if identifier.isdigit()
    )


def _outside_repo(root: Path, output_dir: Path) -> Path:
    root = root.resolve()
    output_dir = output_dir.resolve()
    if output_dir == root or root in output_dir.parents:
        raise ValueError("output directory must be outside repository root")
    return output_dir


def _validate_asset_target(root: Path, target: Path) -> None:
    if not target.is_symlink():
        return
    resolved = target.resolve()
    if resolved == root or root in resolved.parents:
        raise ValueError(f"{target.name}: symlink target resolves inside repository")
    raise ValueError(f"{target.name}: asset target must not be a symlink")


def build_provenance(root: Path, tag: str, evidence: dict) -> dict:
    source = verify_source(root, tag)
    validated = validate_evidence(evidence, source)
    commit = source["commit_sha"]
    return {
        "schema_version": 1,
        "artifact_type": "bindle-release-provenance",
        **source,
        "previous_version": _previous_version(root, tag, commit),
        "changelog": _changelog_section(root, commit, source["version"]),
        "capabilities": _capability_snapshot(root, commit),
        "installed_surfaces": _install_snapshot(root, commit),
        "verification_evidence": validated,
        "tool_versions": _tool_versions(),
    }


def generate(
    root: Path, tag: str, evidence_path: Path, output_dir: Path
) -> tuple[Path, Path]:
    root = root.resolve()
    output_dir = _outside_repo(root, Path(output_dir))
    evidence = _parse_json(
        Path(evidence_path).read_text(encoding="utf-8"), "evidence"
    )
    document = build_provenance(root, tag, evidence)
    payload = _json_bytes(document)
    digest = hashlib.sha256(payload).hexdigest()
    checksum = f"{digest}  {ARTIFACT_NAME}\n".encode("ascii")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / ARTIFACT_NAME
    checksum_path = output_dir / CHECKSUM_NAME
    _validate_asset_target(root, artifact_path)
    _validate_asset_target(root, checksum_path)
    _atomic_write(artifact_path, payload)
    _atomic_write(checksum_path, checksum)
    return artifact_path, checksum_path


def verify_artifact(
    root: Path, tag: str, artifact_path: Path, checksum_path: Path
) -> dict:
    payload = Path(artifact_path).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    expected_checksum = f"{digest}  {ARTIFACT_NAME}\n".encode("ascii")
    if Path(checksum_path).read_bytes() != expected_checksum:
        raise ValueError("checksum: detached checksum or digest mismatch")
    document = _parse_json(payload.decode("utf-8"), "artifact")
    if payload != _json_bytes(document):
        raise ValueError("artifact: non-canonical JSON bytes")
    expected_keys = {
        "schema_version", "artifact_type", "repository", "tag",
        "tag_object_sha", "tagger_timestamp", "commit_sha", "version",
        "previous_version", "changelog", "capabilities",
        "installed_surfaces", "verification_evidence", "tool_versions",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ValueError("artifact: invalid schema key set")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("artifact: unsupported schema_version")
    if document["artifact_type"] != "bindle-release-provenance":
        raise ValueError("artifact: invalid artifact_type")
    source = verify_source(root, tag)
    for field, value in source.items():
        if document[field] != value:
            raise ValueError(f"artifact: {field} mismatch")
    validate_evidence(document["verification_evidence"], source)
    if document["previous_version"] != _previous_version(
        root, tag, source["commit_sha"]
    ):
        raise ValueError("artifact: previous_version mismatch")
    if document["changelog"] != _changelog_section(
        root, source["commit_sha"], source["version"]
    ):
        raise ValueError("artifact: changelog mismatch")
    if document["capabilities"] != _capability_snapshot(
        root, source["commit_sha"]
    ):
        raise ValueError("artifact: capabilities mismatch")
    if document["installed_surfaces"] != _install_snapshot(
        root, source["commit_sha"]
    ):
        raise ValueError("artifact: installed_surfaces mismatch")
    tool_versions = document["tool_versions"]
    if (
        not isinstance(tool_versions, dict)
        or set(tool_versions) != set(TOOLS)
        or any(not isinstance(value, str) for value in tool_versions.values())
    ):
        raise ValueError("artifact: invalid tool_versions")
    return document


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-source")
    verify.add_argument("--root", type=Path, default=_default_root())
    verify.add_argument("--tag", required=True)
    verify.add_argument("--json", action="store_true")
    collect = commands.add_parser("collect-evidence")
    collect.add_argument("--root", type=Path, default=_default_root())
    collect.add_argument("--tag", required=True)
    collect.add_argument("--output", type=Path, required=True)
    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("--root", type=Path, default=_default_root())
    generate_parser.add_argument("--tag", required=True)
    generate_parser.add_argument("--evidence", type=Path, required=True)
    generate_parser.add_argument("--output-dir", type=Path, required=True)
    artifact_verify = commands.add_parser("verify")
    artifact_verify.add_argument("--root", type=Path, default=_default_root())
    artifact_verify.add_argument("--tag", required=True)
    artifact_verify.add_argument("--artifact", type=Path, required=True)
    artifact_verify.add_argument("--checksum", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify-source":
            result = verify_source(args.root, args.tag)
            if args.json:
                print(json.dumps(result, sort_keys=True))
            else:
                for key, value in result.items():
                    print(f"{key}: {value}")
        elif args.command == "collect-evidence":
            if not collect_evidence(args.root, args.tag, args.output):
                return 1
        elif args.command == "generate":
            generate(args.root, args.tag, args.evidence, args.output_dir)
        elif args.command == "verify":
            verify_artifact(
                args.root, args.tag, args.artifact, args.checksum
            )
    except (ValueError, OSError, json.JSONDecodeError,
            subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
