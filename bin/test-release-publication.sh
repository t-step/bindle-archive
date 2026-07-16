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

def value(flag):
    return argv[argv.index(flag) + 1]

verb = argv[2]
if verb == "view":
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
    notes = Path(value("--notes-file")).read_text()
    state["release"] = {
        "tagName": argv[3], "targetCommitish": value("--target"),
        "name": value("--title"), "body": notes, "isDraft": True,
        "isPrerelease": False, "assets": [],
    }
elif verb == "upload":
    files = [Path(item) for item in argv[4:]
             if not item.startswith("--") and item not in (value("--repo"),)]
    if "--clobber" in argv:
        replacing = {item.name for item in files}
        state["release"]["assets"] = [
            item for item in state["release"]["assets"]
            if item["name"] not in replacing]
    for source in files:
        shutil.copy2(source, Path(state["assets_dir"]) / source.name)
        state["release"]["assets"].append({"name": source.name})
elif verb == "download":
    destination = Path(value("--dir"))
    patterns = [argv[index + 1] for index, item in enumerate(argv)
                if item == "--pattern"]
    for name in patterns:
        shutil.copy2(Path(state["assets_dir"]) / name, destination / name)
    corruption = state["download_corruption"]
    if corruption == "json":
        (destination / "bindle-release-provenance.json").write_text("corrupt\n")
    elif corruption == "checksum":
        (destination / "bindle-release-provenance.json.sha256").write_text("corrupt\n")
elif verb == "edit":
    assert argv[4:] == ["--draft=false", "--repo", value("--repo")]
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
    template_assets = tmp / "template-assets"
    template_assets.mkdir()

    def invoke(initial_release, *, corruption=None, inspection=None):
        case = tmp / f"case-{len(list(tmp.glob('case-*')))}"
        case.mkdir()
        assets = case / "assets"
        assets.mkdir()
        for item in template_assets.iterdir():
            shutil.copy2(item, assets / item.name)
        state_path = case / "state.json"
        log_path = case / "gh.log"
        log_path.write_text("")
        state = {"release": initial_release, "assets_dir": str(assets),
                 "download_corruption": corruption,
                 "inspection_error": inspection}
        state_path.write_text(json.dumps(state))
        env = dict(base_env, GH_STATE=str(state_path), GH_LOG=str(log_path),
                   GH_ASSETS=str(assets), TMPDIR=str(case))
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
    result, state, logs, leftovers = invoke(None)
    assert result.returncode == 0, result.stderr
    assert {key: state["release"][key] for key in (
        "tagName", "targetCommitish", "name", "body", "isPrerelease"
    )} == {"tagName": tag, "targetCommitish": commit_sha, "name": tag,
           "body": body, "isPrerelease": False}
    assert state["release"]["isDraft"] is False
    assert [item["name"] for item in state["release"]["assets"]] == sorted(asset_names)
    assert logs[0] == ["gh", "release", "view", tag, "--repo", owner_repo,
                       "--json",
                       "tagName,targetCommitish,name,body,isDraft,isPrerelease,assets"]
    create = next(call for call in logs if call[2] == "create")
    assert create[:10] == ["gh", "release", "create", tag, "--draft",
                           "--verify-tag", "--target", commit_sha,
                           "--title", tag]
    downloads = [call for call in logs if call[2] == "download"]
    assert len(downloads) == 1
    assert downloads[0].count("--pattern") == 2
    assert set(downloads[0][index + 1] for index, value in enumerate(downloads[0])
               if value == "--pattern") == asset_names
    assert logs[-1] == final
    assert leftovers == []
    for asset in asset_names:
        shutil.copy2(Path(state["assets_dir"]) / asset, template_assets / asset)

    matching = {"tagName": tag, "targetCommitish": commit_sha, "name": tag,
                "body": body, "isDraft": True, "isPrerelease": False,
                "assets": []}
    result, state, logs, _ = invoke(matching)
    assert result.returncode == 0, result.stderr
    assert not any(call[2] == "create" for call in logs)
    assert logs[-1] == final

    exact = dict(matching, assets=[{"name": name} for name in sorted(asset_names)])
    result, state, logs, _ = invoke(exact)
    assert result.returncode == 0, result.stderr
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
        result, state, logs, _ = invoke(release)
        assert result.returncode != 0
        assert not any(call[2] in ("upload", "edit") for call in logs), (release, logs)

    for corruption in ("json", "checksum"):
        result, state, logs, _ = invoke(matching, corruption=corruption)
        assert result.returncode != 0
        assert not any(call[2] == "edit" for call in logs)

    for inspection in ("auth", "network", "parsing"):
        result, state, logs, _ = invoke(None, inspection=inspection)
        assert result.returncode != 0
        assert not any(call[2] in ("create", "upload", "edit") for call in logs)

spec = importlib.util.spec_from_file_location("release_publication", orchestrator)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.release_not_found("release not found\n") is True
for message in (" release not found\n", "release not found: v0.5.1\n",
                "authentication required\n", "network error\n", ""):
    assert module.release_not_found(message) is False
print("test-release-publication: all scenarios passed")
PY
