# Release provenance

**Status:** Contract, v1 · **Issue:** thomas-estep/bindle#137

This contract separates release intent, checked-in release state, and
publication evidence. Release Please owns the release PR and the committed
version state; an annotated tag identifies the released source; the provenance
artifact records verification performed after that tag exists. Provenance is
never checked-in version state and Release Captain does not consume it while
recommending a release.

## Authority and lifecycle

- `version.txt` is the sole checked-in version source.
- Release Please owns updates to `version.txt`, the root (`.`) entry in
  `.release-please-manifest.json`, and `CHANGELOG.md` through its release PR.
  The merged release-PR commit is authoritative only when all three agree.
- Publication requires an annotated direct tag named `v<version.txt>`. Its tag
  object's immediate target must be the exact released commit and workflow
  `HEAD`; lightweight tags and tag-to-tag indirection fail.
- The repository must protect release tags against update and deletion and
  operate them as immutable references. Publication verifies the live GitHub
  tag ref before any draft mutation and again at the last possible boundary
  before publication; protection is still required because GitHub does not
  provide an atomic transaction binding those reads to the release edit.
- `bindle-release-provenance.json` and its detached checksum are generated
  after tagging, outside the repository, and attached to the GitHub Release.
- Publication is the final mutation, after the uploaded assets have been
  downloaded and independently verified. Nothing fallible follows it.

The verifier never repairs release state, rewrites a tag, or guesses missing
evidence.

## Source-state gate

Before evidence collection, draft creation, or draft reuse, run:

```bash
python3 bin/release-provenance.py verify-source --tag <tag>
```

It requires all of the following:

1. `git cat-file -t <tag>` reports `tag`.
2. The tag object's immediate `object` is a commit, not another tag.
3. That immediate object equals both `git rev-parse <tag>^{commit}` and the
   recorded 40-lowercase-hex `commit_sha`.
4. Checkout `HEAD` equals that commit.
5. The tag is exactly `v<version.txt>`.
6. `.release-please-manifest.json`'s root package equals `version.txt`.
7. `CHANGELOG.md` contains the released version section.

The publication orchestrator additionally queries GitHub's Git database API
with argv-only `gh api` calls. The live `refs/tags/<URL-encoded-tag>` object
must have type `tag` and the exact locally verified `tag_object_sha`. Fetching
that annotated tag object must report an immediate object of type `commit` and
the exact verified `commit_sha`. Authentication, network, malformed or
duplicate-member JSON, lightweight remote refs, tag-to-tag targets, and every
SHA mismatch fail closed. The same two checks run again after downloaded-asset
verification and temporary cleanup, immediately before the final release edit.

## Exact verification evidence

The evidence document has exactly one record for each required check:

```json
{
  "schema_version": 1,
  "repository": "thomas-estep/bindle",
  "tag": "v0.5.1",
  "commit_sha": "<40 lowercase hex>",
  "checks": [
    {
      "id": "version_state",
      "required": true,
      "command": ["python3", "bin/release-provenance.py", "verify-source", "--tag", "v0.5.1"],
      "status": "passed",
      "exit_code": 0
    }
  ]
}
```

The exact four identifiers and argv templates are:

| id | command |
|---|---|
| `version_state` | `python3 bin/release-provenance.py verify-source --tag <tag>` |
| `release_integrity` | `python3 skills/package-release-integrity/scripts/release_integrity.py publication-check --repo . --tag <tag>` |
| `make_check` | `make check` |
| `make_test` | `make test` |

Each record has `required: true`, exact argv as an array, `status: "passed"`,
and `exit_code: 0`. Allowed statuses are `passed`, `failed`, `unknown`, and
`skipped`; the latter three fail publication. Missing or duplicate identifiers,
an unknown required check, command drift, mismatched repository/tag/commit, or
a missing/nonzero exit code also fails. An aggregate success boolean is not
trusted. Collect the document with `release-provenance.py collect-evidence`.

## Artifact and detached checksum

`release-provenance.py generate` emits two assets outside the checkout. The
JSON object has exactly these keys and no others:

| Key | Meaning |
|---|---|
| `schema_version` | integer `1` |
| `artifact_type` | `bindle-release-provenance` |
| `repository` | tagged source repository in `OWNER/REPO` form |
| `tag` | annotated release tag |
| `tag_object_sha` | annotated tag-object SHA |
| `tagger_timestamp` | annotated tagger date in strict ISO form |
| `commit_sha` | exact directly tagged released commit |
| `version` | tagged `version.txt` value |
| `previous_version` | deterministic preceding SemVer tag, without `v` |
| `changelog` | exact verified released changelog section |
| `capabilities` | sorted tagged capability snapshot |
| `installed_surfaces` | sorted tagged install-manifest snapshot |
| `verification_evidence` | complete validated exact four-check document |
| `tool_versions` | exact `git`, `bash`, `python3`, `shellcheck`, and `shfmt` map |

The exact `commit_sha` is the tagged commit, never its parent. The previous
version is the nearest reachable SemVer-shaped `v*` tag before that commit,
excluding the current tag; absence or ambiguity fails rather than guessing.

### Generation output directory

`generate --output-dir` never creates the output directory. The supplied path
must resolve strictly to a pre-existing real directory, its canonical resolved
path must be outside the repository root, and the generator walks and opens
that canonical directory without following replacement symlinks. Existing
asset targets may be replaced only when they are ordinary entries; either
named asset being a symlink is a hard failure. Writes use unique same-directory
temporary files, atomic replacement, and directory fsync.

The JSON bytes are UTF-8, keys sorted lexicographically, two-space indented,
with exactly one trailing LF. The detached
`bindle-release-provenance.json.sha256` bytes are exactly:

```text
<64 lowercase hex>  bindle-release-provenance.json
```

followed by one LF. The digest covers every JSON byte. Semantic verification
separately checks canonical serialization, schema, evidence, annotated tag,
commit, and version state:

```bash
python3 bin/release-provenance.py verify --tag <tag> \
  --artifact <outside>/bindle-release-provenance.json \
  --checksum <outside>/bindle-release-provenance.json.sha256
```

## Draft creation and exact reuse

The publication orchestrator first runs `gh release view`. Creation is allowed
only when that command exits exactly `1` and stderr is exactly the normalized
missing-release text `release not found` (with no content beyond its accepted
line ending). Every other exit or stderr is a hard failure.

Create a draft for the exact repository and tag. A rerun may reuse only a
release view with this exact field set and values:

- `tagName` equals the requested tag;
- `targetCommitish` equals the verified released commit SHA;
- `name` equals the tag;
- `body` equals the verified provenance artifact's `changelog` string byte for
  byte when UTF-8 encoded (the creation notes file contains exactly those
  bytes, with no added newline);
- `isDraft` is `true`; and
- `isPrerelease` is `false`.

The `assets` array must have unique string names. Its name set must be either
empty or exactly `bindle-release-provenance.json` plus
`bindle-release-provenance.json.sha256`:

- neither present: upload both;
- exactly one of each: replace both deterministically by name, with no
  duplicates, then download and verify the replacements;
- only one present, duplicate names, or any unexpected asset: stop for human
  review without normalizing the draft.

Conflicting metadata and already-published releases also fail closed. A rerun
never edits conflicting state into compliance.

After `gh release create` returns, the orchestrator reads the draft back with
the same exact field set and applies the same strict metadata validation. The
new draft must still be unpublished and have no assets. Server-normalized or
otherwise changed metadata, concurrent publication, or an asset introduced
between creation and read-back stops before upload.

## Publication temporary-directory lease

Publication resolves the system temporary base strictly before doing release
work. That base must be a directory outside the repository. Its newly created
`bindle-publication.*` entry must be an absolute direct child of that canonical
base, a real directory, canonical at its lexical path, and outside the
repository. The orchestrator opens the original directory with
`O_DIRECTORY|O_NOFOLLOW`, retains that descriptor lease, pins its device/inode
identity, and revalidates its lexical type, identity, canonical path, and
external location before each evidence, generation, draft, upload, download,
and verification boundary.

Cleanup recursively walks only the descriptor-pinned original directory with
fd-relative, no-follow operations. It never traverses a replacement at the
lexical pathname. Before the final root `rmdir`, the lexical entry must still
be a real directory with the original device/inode; a mismatch is left
untouched and publication fails. Safe temporary leaks are preferred to deleting
an unknown replacement. The descriptor closes on every path.

On an ordinary failure cleanup leaves any release unpublished (and any release
created by this run as a draft). On success it removes the pinned entry, proves
it did not reappear, rechecks the live remote tag, and only then replaces the
process with the final publish command. No cleanup, status write, or other
fallible operation is scheduled after publication.

## Upload, download, verify, publish

After local semantic and checksum validation, upload both assets to the draft.
Download those exact named assets into a separate directory. Require the
downloaded JSON digest to equal the locally validated upload digest, validate
the downloaded detached checksum against the downloaded JSON bytes, and run
independent semantic verification against the tag and released commit. Only
then clean the pinned temporary directory, repeat the live GitHub tag-ref and
tag-object checks, and publish the draft. The final remote check and release
edit are adjacent commands, but not an atomic GitHub operation; protected,
immutable release tags remain a repository prerequisite. Publishing is the
last command; every earlier failure leaves it unpublished.

## Local provenance path

The local path is read-only with respect to the checkout, Git, GitHub, and all
other remotes. It requires an existing annotated direct tag at `HEAD`, reads
`version.txt` and Release Please state from that tagged commit, requires the
same complete successful evidence, and emits the same two untracked assets
outside the repository. It never changes version/changelog/manifest files,
the index, commits, refs, branches, tags, releases, or any remote state.

## Inspection

Treat the GitHub Release assets as the publication record, not a file in a
checkout. Download both assets, verify the detached checksum, and run semantic
verification against a full-history checkout of the released tag. A green
pre-release recommendation or generic integrity report is not a substitute
for these post-tag checks.
