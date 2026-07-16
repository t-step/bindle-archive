#!/usr/bin/env bash
# Exercise the fail-closed GitHub Release draft publication state machine.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR="$REPO_ROOT/bin/release-publication.py"
PY="$(command -v python3)"

if [ ! -f "$ORCHESTRATOR" ]; then
  echo "FAIL: bin/release-publication.py does not exist" >&2
  exit 1
fi

"$PY" - "$REPO_ROOT" "$ORCHESTRATOR" <<'PY'
import hashlib
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

repo_root = Path(sys.argv[1])
orchestrator = Path(sys.argv[2])
python = sys.executable
owner_repo = "example/bindle"
tag = "v0.5.1"
body = "## [0.5.1] - 2026-07-15\n\n- Current."
asset_names = {
    "bindle-release-provenance.json",
    "bindle-release-provenance.json.sha256",
}

class BlockScalar(str):
    def __new__(cls, value, style):
        scalar = super().__new__(cls, value)
        scalar.style = style
        return scalar


def _line(lines, index):
    raw = lines[index]
    prefix = raw[:len(raw) - len(raw.lstrip(" \t"))]
    assert "\t" not in prefix, "tabs in YAML indentation are unsupported"
    return len(prefix), raw[len(prefix):]


def _next_content(lines, index):
    while index < len(lines):
        _, content = _line(lines, index)
        if content and not content.startswith("#"):
            return index
        index += 1
    return index


def _strip_inline_comment(value):
    quote = None
    escaped = False
    for index, char in enumerate(value):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            if char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    continue
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    assert quote is None, "unterminated quoted YAML scalar"
    return value.rstrip()


def _scalar(value):
    value = _strip_inline_comment(value.strip())
    assert value, "empty inline YAML scalar"
    assert not value.startswith(("[", "{", "&", "*", "!")), (
        f"unsupported YAML scalar: {value!r}"
    )
    if value.startswith('"'):
        decoded = json.loads(value)
        assert isinstance(decoded, str), "quoted YAML scalar must be a string"
        return decoded
    if value.startswith("'"):
        assert value.endswith("'") and len(value) >= 2, (
            "unterminated single-quoted YAML scalar"
        )
        return value[1:-1].replace("''", "'")
    return value


def _key_value(content):
    key, separator, value = content.partition(":")
    assert separator and key and key.strip() == key, (
        f"unsupported YAML mapping entry: {content!r}"
    )
    assert all(char.isalnum() or char in "_.-" for char in key), (
        f"unsupported YAML key: {key!r}"
    )
    return key, value.lstrip()


def _value(lines, index, indent, text):
    if text in (">", ">-", ">+", "|", "|-", "|+"):
        cursor = index + 1
        raw_block = []
        while cursor < len(lines):
            child_indent, child = _line(lines, cursor)
            if child and child_indent <= indent:
                break
            raw_block.append(lines[cursor])
            cursor += 1
        nonblank = [line for line in raw_block if line.strip()]
        assert nonblank, "empty YAML block scalar"
        block_indent = min(len(line) - len(line.lstrip(" "))
                           for line in nonblank)
        assert block_indent > indent, "invalid YAML block indentation"
        parts = [line[block_indent:].strip() for line in raw_block
                 if line.strip()]
        return BlockScalar(" ".join(parts), text), cursor
    if text:
        return _scalar(text), index + 1
    cursor = _next_content(lines, index + 1)
    assert cursor < len(lines), "missing nested YAML value"
    child_indent, _ = _line(lines, cursor)
    assert child_indent > indent, "nested YAML value is not indented"
    return _node(lines, cursor, child_indent)


def _mapping(lines, index, indent):
    result = {}
    cursor = index
    while True:
        cursor = _next_content(lines, cursor)
        if cursor >= len(lines):
            return result, cursor
        current_indent, content = _line(lines, cursor)
        if current_indent < indent:
            return result, cursor
        assert current_indent == indent and not content.startswith("-"), (
            f"unsupported YAML mapping structure on line {cursor + 1}"
        )
        key, text = _key_value(content)
        assert key not in result, f"duplicate YAML key: {key}"
        result[key], cursor = _value(lines, cursor, indent, text)


def _sequence(lines, index, indent):
    result = []
    cursor = index
    while True:
        cursor = _next_content(lines, cursor)
        if cursor >= len(lines):
            return result, cursor
        current_indent, content = _line(lines, cursor)
        if current_indent < indent:
            return result, cursor
        assert current_indent == indent and content.startswith("- "), (
            f"unsupported YAML sequence structure on line {cursor + 1}"
        )
        item = content[2:].strip()
        if ":" not in item:
            result.append(_scalar(item))
            cursor += 1
            continue
        key, text = _key_value(item)
        value, cursor = _value(lines, cursor, indent + 2, text)
        mapping = {key: value}
        continuation = _next_content(lines, cursor)
        if continuation < len(lines):
            continuation_indent, _ = _line(lines, continuation)
            if continuation_indent > indent:
                assert continuation_indent == indent + 2, (
                    "unsupported YAML sequence-item indentation"
                )
                extra, cursor = _mapping(lines, continuation, indent + 2)
                assert not mapping.keys() & extra.keys(), (
                    "duplicate YAML sequence-item key"
                )
                mapping.update(extra)
        result.append(mapping)


def _node(lines, index, indent):
    _, content = _line(lines, index)
    if content.startswith("- "):
        return _sequence(lines, index, indent)
    return _mapping(lines, index, indent)


def _parse_workflow(workflow):
    lines = workflow.splitlines()
    first = _next_content(lines, 0)
    assert first < len(lines), "empty release workflow"
    indent, _ = _line(lines, first)
    assert indent == 0, "top-level YAML must begin at column zero"
    document, cursor = _node(lines, first, indent)
    assert _next_content(lines, cursor) == len(lines), (
        "unsupported trailing YAML document content"
    )
    assert isinstance(document, dict), "workflow must be a YAML mapping"
    return document


def _exact_mapping(value, keys, path):
    assert isinstance(value, dict), f"{path} must be a mapping"
    assert set(value) == set(keys), (
        f"{path} keys must be exactly {sorted(keys)!r}; got {sorted(value)!r}"
    )
    return value


def assert_release_workflow(workflow):
    document = _parse_workflow(workflow)
    trigger = _exact_mapping(document.get("on"), {"push"}, "on")
    push = _exact_mapping(trigger["push"], {"tags"}, "on.push")
    assert push["tags"] == ["v*"], "on.push.tags must be exactly ['v*']"
    assert _exact_mapping(document.get("permissions"), {"contents"},
                          "permissions") == {"contents": "write"}
    jobs = _exact_mapping(document.get("jobs"), {"release"}, "jobs")
    release = _exact_mapping(jobs["release"], {"runs-on", "steps"},
                             "jobs.release")
    assert release["runs-on"] == "ubuntu-latest"
    steps = release["steps"]
    assert isinstance(steps, list) and len(steps) == 2, (
        "jobs.release.steps must contain exactly checkout and publication"
    )

    forbidden = (
        "gh release create", "gh release edit", "gh release upload",
        "gh release download", "RELEASE-MANIFEST.json",
        "bin/release-provenance.py", "bin/release-evidence.py", "awk -v",
        "sha256sum", "shasum", "openssl dgst",
    )
    executable = []
    for step in steps:
        if isinstance(step, dict):
            executable.extend(step[key] for key in ("uses", "run")
                              if isinstance(step.get(key), str))
    found = [fragment for fragment in forbidden
             if any(fragment in value for value in executable)]
    assert not found, f"forbidden executable release fragments: {found!r}"

    checkout = _exact_mapping(steps[0], {"uses", "with"},
                              "jobs.release.steps[0]")
    assert checkout["uses"] == "actions/checkout@v7"
    assert _exact_mapping(checkout["with"], {"fetch-depth"},
                          "jobs.release.steps[0].with") == {"fetch-depth": "0"}

    publish = _exact_mapping(steps[1], {"name", "env", "run"},
                             "jobs.release.steps[1]")
    assert publish["name"] == "Verify and publish tagged release provenance"
    assert _exact_mapping(publish["env"], {"GH_TOKEN"},
                          "jobs.release.steps[1].env") == {
                              "GH_TOKEN": "${{ github.token }}"}
    assert isinstance(publish["run"], BlockScalar)
    assert publish["run"].style.startswith(">"), (
        "publication command must use a folded YAML scalar"
    )
    expected = ('python3 bin/release-publication.py '
                '--repo "$GITHUB_REPOSITORY" --tag "$GITHUB_REF_NAME"')
    assert " ".join(publish["run"].split()) == expected, (
        "publication command must be the exact orchestrator argv"
    )


workflow = (repo_root / ".github/workflows/release.yml").read_text()
assert_release_workflow(workflow)


workflow_regression_failures = []


def expect_invalid(label, candidate):
    try:
        assert_release_workflow(candidate)
    except AssertionError:
        return
    workflow_regression_failures.append(f"{label}: invalid workflow accepted")


unrelated_checkout = workflow.replace(
    "jobs:\n", "x-documentation: |-\n"
    "  - uses: actions/checkout@v7\n"
    "jobs:\n",
).replace(
    "      - uses: actions/checkout@v7",
    "      - uses: actions/checkout@v6",
)
expect_invalid("unrelated checkout text", unrelated_checkout)

commented_fetch_depth = workflow.replace(
    "          fetch-depth: 0",
    "          fetch-depth: 1 #          fetch-depth: 0",
)
expect_invalid("commented fetch depth", commented_fetch_depth)

extra_publisher = workflow.replace(
    "      - name: Verify and publish tagged release provenance",
    "      - uses: softprops/action-gh-release@v2\n"
    "      - name: Verify and publish tagged release provenance",
)
expect_invalid("extra uses publisher", extra_publisher)

equivalent_formatting = workflow.replace("- 'v*'", '- "v*"').replace(
    "fetch-depth: 0", 'fetch-depth: "0"'
).replace(
    "          python3 bin/release-publication.py\n"
    '          --repo "$GITHUB_REPOSITORY"\n',
    "          python3 bin/release-publication.py --repo\n"
    '          "$GITHUB_REPOSITORY"\n',
)
equivalent_formatting = equivalent_formatting.replace(
    "name: Release", "# gh release create in prose is harmless\nname: Release"
)
try:
    assert_release_workflow(equivalent_formatting)
except AssertionError as error:
    workflow_regression_failures.append(
        f"equivalent formatting rejected: {error}"
    )

unrelated_prose = workflow.replace(
    "name: Release",
    "x-documentation: >-\n"
    "  Historical prose mentions gh release create and RELEASE-MANIFEST.json.\n"
    "name: Release",
)
try:
    assert_release_workflow(unrelated_prose)
except AssertionError as error:
    workflow_regression_failures.append(f"unrelated prose rejected: {error}")
assert not workflow_regression_failures, workflow_regression_failures


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def commit(repo, message):
    run(["git", "-C", str(repo), "add", "-A"])
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-07-15T12:34:56Z",
               GIT_COMMITTER_DATE="2026-07-15T12:34:56Z")
    run(["git", "-C", str(repo), "-c", "user.email=test@example.com",
         "-c", "user.name=Bindle Test", "commit", "-q", "-m", message],
        env=env)


def fixture(path):
    path.mkdir()
    (path / "bin").mkdir()
    (path / "skills/package-release-integrity/scripts").mkdir(parents=True)
    shutil.copy2(repo_root / "bin/release-provenance.py",
                 path / "bin/release-provenance.py")
    check = "#!/usr/bin/env python3\nraise SystemExit(0)\n"
    for relative in ("skills/package-release-integrity/scripts/release_integrity.py",):
        target = path / relative
        target.write_text(check)
        target.chmod(0o755)
    (path / "Makefile").write_text("check:\n\t@true\ntest:\n\t@true\n")
    run(["git", "-C", str(path), "init", "-q"])
    run(["git", "-C", str(path), "symbolic-ref", "HEAD", "refs/heads/main"])
    run(["git", "-C", str(path), "remote", "add", "origin",
         "git@github.com:example/bindle.git"])
    (path / "capabilities.json").write_text(
        '{"capabilities":[{"name":"demo","type":"skill",'
        '"provider":{"claude":"installed","codex":"untested"},'
        '"maturity":"tested","version_introduced":"0.5.0"}]}\n')
    (path / "install-manifest.tsv").write_text(
        "# generated\nclaude\tskill\tdemo\tskills/demo\tskills/demo\n")
    (path / "version.txt").write_text("0.5.0\n")
    (path / ".release-please-manifest.json").write_text('{".": "0.5.0"}\n')
    (path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.5.0] - 2026-07-01\n\n- Previous.\n")
    commit(path, "previous")
    run(["git", "-C", str(path), "tag", "v0.5.0"])
    (path / "version.txt").write_text("0.5.1\n")
    (path / ".release-please-manifest.json").write_text('{".": "0.5.1"}\n')
    (path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n" + body
        + "\n\n## [0.5.0] - 2026-07-01\n\n- Previous.\n")
    commit(path, "current")
    env = dict(os.environ, GIT_COMMITTER_DATE="2026-07-15T12:34:56Z")
    run(["git", "-C", str(path), "-c", "user.email=test@example.com",
         "-c", "user.name=Bindle Test", "tag", "-a", tag, "-m", tag], env=env)
    return run(["git", "-C", str(path), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip()


fake_gh = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import sys

state_path = Path(os.environ["GH_STATE"])
log_path = Path(os.environ["GH_LOG"])
state = json.loads(state_path.read_text())
argv = ["gh", *sys.argv[1:]]
with log_path.open("a") as handle:
    handle.write(json.dumps(argv) + "\n")

expected_repo = os.environ["GH_EXPECTED_REPO"]
expected_tag = os.environ["GH_EXPECTED_TAG"]

def persist_and_fail():
    state_path.write_text(json.dumps(state))
    raise SystemExit(9)

verb = argv[2]
if verb == "view":
    assert argv == ["gh", "release", "view", expected_tag, "--repo",
                    expected_repo, "--json",
                    "tagName,targetCommitish,name,body,isDraft,isPrerelease,assets"]
    if state["inspection_error"] in ("auth", "network"):
        print(state["inspection_error"] + " failure", file=sys.stderr)
        raise SystemExit(2)
    if state["inspection_error"] == "parsing":
        print("{")
        raise SystemExit(0)
    if state["release"] is None:
        print("release not found", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(state["release"]))
elif verb == "create":
    target = argv[7]
    notes_path = Path(argv[11])
    assert argv == ["gh", "release", "create", expected_tag, "--draft",
                    "--verify-tag", "--target", target, "--title",
                    expected_tag, "--notes-file", str(notes_path), "--repo",
                    expected_repo]
    assert notes_path.name == "release-notes.md"
    assert notes_path.parent.name.startswith("bindle-publication.")
    if state["failure"] == "create":
        persist_and_fail()
    notes_bytes = notes_path.read_bytes()
    state["created_notes_hex"] = notes_bytes.hex()
    state["release"] = {
        "tagName": expected_tag, "targetCommitish": target,
        "name": expected_tag, "body": notes_bytes.decode(), "isDraft": True,
        "isPrerelease": False, "assets": [],
    }
elif verb == "upload":
    files = [Path(argv[4]), Path(argv[5])]
    suffix = ["--clobber", "--repo", expected_repo] \
        if "--clobber" in argv else ["--repo", expected_repo]
    assert argv == ["gh", "release", "upload", expected_tag,
                    str(files[0]), str(files[1]), *suffix]
    assert [item.name for item in files] == [
        "bindle-release-provenance.json",
        "bindle-release-provenance.json.sha256"]
    assert files[0].parent == files[1].parent
    assert files[0].parent.name == "upload"
    if state["failure"] == "upload_first":
        persist_and_fail()
    if "--clobber" in suffix:
        replacing = {item.name for item in files}
        state["release"]["assets"] = [
            item for item in state["release"]["assets"]
            if item["name"] not in replacing]
    for index, source in enumerate(files):
        shutil.copy2(source, Path(state["assets_dir"]) / source.name)
        state["release"]["assets"].append({"name": source.name})
        if index == 0 and state["failure"] == "upload_second":
            persist_and_fail()
elif verb == "download":
    destination = Path(argv[9])
    patterns = [argv[5], argv[7]]
    assert argv == ["gh", "release", "download", expected_tag,
                    "--pattern", "bindle-release-provenance.json",
                    "--pattern", "bindle-release-provenance.json.sha256",
                    "--dir", str(destination), "--repo", expected_repo]
    assert destination.name == "download"
    for index, name in enumerate(patterns):
        if index == 0 and state["failure"] == "download_json":
            persist_and_fail()
        shutil.copy2(Path(state["assets_dir"]) / name, destination / name)
        if index == 0 and state["failure"] == "download_checksum":
            persist_and_fail()
    corruption = state["download_corruption"]
    if corruption == "json":
        (destination / "bindle-release-provenance.json").write_text("corrupt\n")
    elif corruption == "checksum":
        (destination / "bindle-release-provenance.json.sha256").write_text("corrupt\n")
elif verb == "edit":
    assert argv == ["gh", "release", "edit", expected_tag, "--draft=false",
                    "--repo", expected_repo]
    if state["failure"] == "edit":
        persist_and_fail()
    state["release"]["isDraft"] = False
else:
    raise AssertionError(argv)
state_path.write_text(json.dumps(state))
'''


with tempfile.TemporaryDirectory(prefix="bindle-publication-test.") as tmp_text:
    tmp = Path(tmp_text)
    source = tmp / "source"
    commit_sha = fixture(source)
    bindir = tmp / "path"
    bindir.mkdir()
    (bindir / "gh").write_text(fake_gh)
    (bindir / "gh").chmod(0o755)
    base_env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")

    def invoke(initial_release, *, corruption=None, inspection=None,
               failure=None):
        case = tmp / f"case-{len(list(tmp.glob('case-*')))}"
        case.mkdir()
        assets = case / "assets"
        assets.mkdir()
        state_path = case / "state.json"
        log_path = case / "gh.log"
        log_path.write_text("")
        state = {"release": initial_release, "assets_dir": str(assets),
                 "download_corruption": corruption,
                 "inspection_error": inspection, "failure": failure,
                 "created_notes_hex": None}
        state_path.write_text(json.dumps(state))
        env = dict(base_env, GH_STATE=str(state_path), GH_LOG=str(log_path),
                   GH_ASSETS=str(assets), TMPDIR=str(case),
                   GH_EXPECTED_REPO=owner_repo, GH_EXPECTED_TAG=tag)
        completed = subprocess.run(
            [python, str(orchestrator), "--root", str(source),
             "--repo", owner_repo, "--tag", tag], env=env,
            capture_output=True, text=True)
        final_state = json.loads(state_path.read_text())
        logs = [json.loads(line) for line in log_path.read_text().splitlines()]
        leftovers = sorted(item.name for item in case.iterdir()
                           if item.name.startswith("bindle-publication."))
        return completed, final_state, logs, leftovers

    final = ["gh", "release", "edit", tag, "--draft=false", "--repo", owner_repo]
    view = ["gh", "release", "view", tag, "--repo", owner_repo, "--json",
            "tagName,targetCommitish,name,body,isDraft,isPrerelease,assets"]

    def assert_commands(logs, verbs, *, clobber=False):
        assert [call[2] for call in logs] == verbs
        assert logs[0] == view
        for call in logs[1:]:
            verb = call[2]
            if verb == "create":
                notes_path = Path(call[11])
                assert notes_path.name == "release-notes.md"
                assert notes_path.parent.name.startswith("bindle-publication.")
                assert call == ["gh", "release", "create", tag, "--draft",
                                "--verify-tag", "--target", commit_sha,
                                "--title", tag, "--notes-file", str(notes_path),
                                "--repo", owner_repo]
            elif verb == "upload":
                artifact, checksum = Path(call[4]), Path(call[5])
                assert artifact.name == "bindle-release-provenance.json"
                assert checksum.name == "bindle-release-provenance.json.sha256"
                assert artifact.parent == checksum.parent
                assert artifact.parent.name == "upload"
                suffix = ["--clobber", "--repo", owner_repo] \
                    if clobber else ["--repo", owner_repo]
                assert call == ["gh", "release", "upload", tag,
                                str(artifact), str(checksum), *suffix]
            elif verb == "download":
                destination = Path(call[9])
                assert destination.name == "download"
                assert call == ["gh", "release", "download", tag,
                                "--pattern", "bindle-release-provenance.json",
                                "--pattern",
                                "bindle-release-provenance.json.sha256",
                                "--dir", str(destination), "--repo", owner_repo]
            elif verb == "edit":
                assert call == final

    result, state, logs, leftovers = invoke(None)
    assert result.returncode == 0, result.stderr
    assert {key: state["release"][key] for key in (
        "tagName", "targetCommitish", "name", "body", "isPrerelease"
    )} == {"tagName": tag, "targetCommitish": commit_sha, "name": tag,
           "body": body, "isPrerelease": False}
    assert state["release"]["isDraft"] is False
    assert state["created_notes_hex"] == body.encode().hex()
    assert [item["name"] for item in state["release"]["assets"]] == sorted(asset_names)
    assert_commands(logs, ["view", "create", "upload", "download", "edit"])
    assert logs[-1] == final
    assert leftovers == []

    matching = {"tagName": tag, "targetCommitish": commit_sha, "name": tag,
                "body": body, "isDraft": True, "isPrerelease": False,
                "assets": []}
    result, state, logs, _ = invoke(matching)
    assert result.returncode == 0, result.stderr
    assert_commands(logs, ["view", "upload", "download", "edit"])
    assert not any(call[2] == "create" for call in logs)
    assert logs[-1] == final

    exact = dict(matching, assets=[{"name": name} for name in sorted(asset_names)])
    result, state, logs, _ = invoke(exact)
    assert result.returncode == 0, result.stderr
    assert_commands(logs, ["view", "upload", "download", "edit"],
                    clobber=True)
    uploads = [call for call in logs if call[2] == "upload"]
    assert len(uploads) == 1 and "--clobber" in uploads[0]
    assert [item["name"] for item in state["release"]["assets"]] == sorted(asset_names)
    assert logs[-1] == final

    invalid = []
    invalid.append(dict(matching, assets=[{"name": "bindle-release-provenance.json"}]))
    invalid.append(dict(matching, assets=[{"name": "bindle-release-provenance.json"},
                                          {"name": "bindle-release-provenance.json"}]))
    invalid.append(dict(matching, assets=[{"name": "unexpected.txt"}]))
    for field, value in (("tagName", "v9.9.9"), ("targetCommitish", "0" * 40),
                         ("name", "wrong"), ("body", "wrong"),
                         ("isPrerelease", True), ("isDraft", False)):
        invalid.append(dict(matching, **{field: value}))
    for release in invalid:
        result, state, logs, leftovers = invoke(release)
        assert result.returncode != 0
        assert state["release"] == release
        assert list(Path(state["assets_dir"]).iterdir()) == []
        assert_commands(logs, ["view"])
        assert not any(call[2] in ("upload", "edit") for call in logs), (release, logs)
        assert leftovers == []

    for corruption in ("json", "checksum"):
        result, state, logs, leftovers = invoke(matching, corruption=corruption)
        assert result.returncode != 0
        assert state["release"]["isDraft"] is True
        assert_commands(logs, ["view", "upload", "download"])
        assert sorted(item.name for item in Path(state["assets_dir"]).iterdir()) \
            == sorted(asset_names)
        assert not any(call[2] == "edit" for call in logs)
        assert leftovers == []

    for inspection in ("auth", "network", "parsing"):
        result, state, logs, leftovers = invoke(None, inspection=inspection)
        assert result.returncode != 0
        assert state["release"] is None
        assert_commands(logs, ["view"])
        assert not any(call[2] in ("create", "upload", "edit") for call in logs)
        assert leftovers == []

    failure_cases = [
        ("create", None, None, []),
        ("upload_first", matching, matching, []),
        ("upload_second", matching,
         dict(matching, assets=[{"name": "bindle-release-provenance.json"}]),
         ["bindle-release-provenance.json"]),
        ("download_json", matching,
         dict(matching, assets=[{"name": name} for name in sorted(asset_names)]),
         sorted(asset_names)),
        ("download_checksum", matching,
         dict(matching, assets=[{"name": name} for name in sorted(asset_names)]),
         sorted(asset_names)),
    ]
    for failure, initial, expected_release, expected_files in failure_cases:
        result, state, logs, leftovers = invoke(initial, failure=failure)
        assert result.returncode != 0
        assert state["release"] == expected_release, (failure, state["release"])
        if state["release"] is not None:
            assert state["release"]["isDraft"] is True
        assert sorted(item.name for item in Path(state["assets_dir"]).iterdir()) \
            == expected_files
        expected_verbs = {
            "create": ["view", "create"],
            "upload_first": ["view", "upload"],
            "upload_second": ["view", "upload"],
            "download_json": ["view", "upload", "download"],
            "download_checksum": ["view", "upload", "download"],
        }[failure]
        assert_commands(logs, expected_verbs)
        assert not any(call[2] == "edit" for call in logs)
        assert leftovers == []

    result, state, logs, leftovers = invoke(matching, failure="edit")
    assert result.returncode != 0
    assert state["release"]["isDraft"] is True
    assert_commands(logs, ["view", "upload", "download", "edit"])
    assert logs[-1] == final
    assert leftovers == []

spec = importlib.util.spec_from_file_location("release_publication", orchestrator)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.release_not_found("release not found\n") is True
for message in (" release not found\n", "release not found: v0.5.1\n",
                "authentication required\n", "network error\n", ""):
    assert module.release_not_found(message) is False

with tempfile.TemporaryDirectory(prefix="bindle-temp-base-test.") as temp_base:
    symlinked_root = Path(temp_base) / "source"
    symlinked_root.mkdir()
    link = Path(temp_base) / "tmp-link"
    link.symlink_to(symlinked_root, target_is_directory=True)
    original_tempdir = module.tempfile.tempdir
    original_mkdtemp = module.tempfile.mkdtemp
    original_prepare = module._prepare
    calls = []
    prepare_calls = []
    before = sorted(item.name for item in symlinked_root.iterdir())

    def forbidden_mkdtemp(**kwargs):
        calls.append(kwargs)
        raise AssertionError("mkdtemp must not run for an in-repository temp base")

    module.tempfile.tempdir = str(link)
    module.tempfile.mkdtemp = forbidden_mkdtemp
    module._prepare = lambda *args: prepare_calls.append(args)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert module.main(["--root", str(symlinked_root),
                                "--repo", owner_repo, "--tag", tag]) == 1
        assert calls == []
        assert prepare_calls == []
        assert sorted(item.name for item in symlinked_root.iterdir()) == before
    finally:
        module.tempfile.tempdir = original_tempdir
        module.tempfile.mkdtemp = original_mkdtemp
        module._prepare = original_prepare

with tempfile.TemporaryDirectory(prefix="bindle-temp-entry-test.") as temp_base:
    temp_base = Path(temp_base)
    symlinked_root = temp_base / "source"
    symlinked_root.mkdir()
    safe_base = temp_base / "safe-base"
    safe_base.mkdir()
    victim = temp_base / "victim"
    victim.mkdir()
    sentinel = victim / "sentinel"
    sentinel.write_bytes(b"external victim must survive\n")
    entry = safe_base.resolve() / "bindle-publication.swap"
    prepare_calls = []
    exec_calls = []
    original_tempdir = module.tempfile.tempdir
    original_mkdtemp = module.tempfile.mkdtemp
    original_prepare = module._prepare
    original_execvp = module.os.execvp

    def swapped_mkdtemp(*, prefix, dir):
        assert prefix == "bindle-publication."
        assert Path(dir) == safe_base.resolve()
        entry.mkdir()
        entry.rmdir()
        entry.symlink_to(victim, target_is_directory=True)
        return str(entry)

    module.tempfile.tempdir = str(safe_base)
    module.tempfile.mkdtemp = swapped_mkdtemp
    module._prepare = lambda *args: prepare_calls.append(args)
    module.os.execvp = lambda *args: exec_calls.append(args)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert module.main(["--root", str(symlinked_root),
                                "--repo", owner_repo, "--tag", tag]) == 1
        assert prepare_calls == []
        assert exec_calls == []
        assert not entry.exists() and not entry.is_symlink()
        assert sentinel.read_bytes() == b"external victim must survive\n"
        assert list(symlinked_root.iterdir()) == []
    finally:
        module.tempfile.tempdir = original_tempdir
        module.tempfile.mkdtemp = original_mkdtemp
        module._prepare = original_prepare
        module.os.execvp = original_execvp

with tempfile.TemporaryDirectory(prefix="bindle-temp-cleanup-test.") as temp_base:
    temp_base = Path(temp_base)
    symlinked_root = temp_base / "source"
    symlinked_root.mkdir()
    safe_base = temp_base / "safe-base"
    safe_base.mkdir()
    victim = temp_base / "victim"
    victim.mkdir()
    sentinel = victim / "sentinel"
    sentinel.write_bytes(b"cleanup must not follow symlink\n")
    original_tempdir = module.tempfile.tempdir
    module.tempfile.tempdir = str(safe_base)
    try:
        temporary = module._temporary_directory(symlinked_root.resolve())
        entry = temporary.path
        shutil.rmtree(entry)
        entry.symlink_to(victim, target_is_directory=True)
        try:
            temporary.cleanup(require_identity=True)
        except module.PublicationError:
            pass
        else:
            raise AssertionError("symlink-swapped cleanup entry was accepted")
        assert not entry.exists() and not entry.is_symlink()
        assert sentinel.read_bytes() == b"cleanup must not follow symlink\n"
    finally:
        module.tempfile.tempdir = original_tempdir
print("test-release-publication: all scenarios passed")
PY
