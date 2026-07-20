"""architecture.project -- authoring and reading the architecture surface's
`config.json` (issue #374 child D, slice D5, epic #141).

THIS IS THE FIRST WRITER OF THAT FILE. Slices D1-D4 shipped `state.py`'s
path helpers and `state.validate_config`, but nothing ever authored the
document they describe: `state.py` validates, it does not create, and
`context_graph.config.init_project` has no architecture counterpart. Every
architecture test before this slice hand-built a config dict in memory, so
a first-ever projection had no configuration to read.

INIT IS NOT A MUTATION VERB. An existing config wins over every
caller-supplied setting and is returned unchanged, with ZERO bytes written.
That is not merely an optimization: the schema's own description records
that apply is read-only on this file because it "carries no marker contract
and no byte-preservation guarantee, so a machine write could silently
reformat or drop hand-maintained exclusions". A re-init that regenerated
defaults would do exactly that damage. For the same reason a malformed
existing config RAISES rather than being repaired or replaced -- the bytes
on disk are the operator's, and this module never rewrites them.

The lock is PROJECT-scoped, not directory-scoped (#228), and taken under
the `arch_init` operation so a lock file's owner metadata says which
surface holds it. A single lock covers `.bindle/context` and
`.bindle/architecture` together; two directory-scoped locks would let a
context apply and an architecture init interleave.

Defaults are deliberately conservative rather than tuned. `max_nodes`
binds CREATION only (see the `caps.over_cap_behavior` description in
`schemas/architecture/v1/config.schema.json`), so a low default strands
nothing -- an over-cap candidate is reported as `over_cap`, never deleted.
Raising the cap later is a config edit, not a migration.
"""
import json
import os
import secrets

from architecture import state
from context_graph import atomic_io
from context_graph import ids as ctx_ids
from context_graph import lock
from context_graph.config import project_dir

# Conservative starting points; every one is an operator-editable field.
DEFAULT_MAX_NODES = 50
DEFAULT_THRESHOLD_HIGH = 0.7
DEFAULT_THRESHOLD_LOW = 0.3
DEFAULT_DIFF_SIZE_CONFIRMATION_LIMIT = 200

# New with this slice. Both describe the ABSENCE or UNREADABILITY of the
# document rather than a property of a well-formed one, which is why
# neither is expressible as a JSON Schema constraint -- see this surface's
# invariant-coverage.json, where both are ledgered as excluded.
E_CONFIG_MISSING = "E_ARCH_CONFIG_MISSING"
E_CONFIG_UNREADABLE = "E_ARCH_CONFIG_UNREADABLE"
E_CONFIG_SLUG_MISMATCH = "E_ARCH_CONFIG_SLUG_MISMATCH"


def _finding(code, message, **extra):
    """Same shape context_graph.validation and architecture.state produce,
    so one CLI renderer serves every surface."""
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d


class ConfigInvalidError(state.ArchStateError):
    """An existing config does not validate, or the caller's settings would
    produce one that does not. Never triggers a repair."""


class ConfigUnreadableError(state.ArchStateError):
    """The config file exists but could not be parsed. Distinct from
    ConfigInvalidError on purpose: unparseable bytes are not a findings
    list about a document, they are the absence of a document to validate,
    and the recovery is an operator looking at the file."""


def config_path(notes_home, project_slug):
    return state.config_path(notes_home, project_slug)


def load_config(path):
    """Return the parsed config, or None when the file does not exist.
    A missing config is a legitimate pre-init state, not an error; only
    unreadable or unparseable bytes raise."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigUnreadableError([_finding(
            E_CONFIG_UNREADABLE, "cannot read %r: %s" % (path, exc))])
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ConfigUnreadableError([_finding(
            E_CONFIG_UNREADABLE, "cannot parse %r: %s" % (path, exc))])


def allocate_project_id():
    return ctx_ids.format_project_id(secrets.token_hex(16))


def _default_config(project_slug, display_name, max_nodes, high, low,
                    diff_size_confirmation_limit):
    cfg = {
        "schema_version": state.SCHEMA_VERSION,
        "projection_schema_version": state.PROJECTION_SCHEMA_VERSION,
        "project_id": allocate_project_id(),
        "project_slug": project_slug,
        "bindings": [],
        "caps": {
            "max_nodes": DEFAULT_MAX_NODES if max_nodes is None else max_nodes,
            # The enum has exactly one member; naming it here rather than
            # indexing OVER_CAP_BEHAVIORS keeps the written document
            # readable next to the schema.
            "over_cap_behavior": "report",
        },
        "thresholds": {
            "high": DEFAULT_THRESHOLD_HIGH if high is None else high,
            "low": DEFAULT_THRESHOLD_LOW if low is None else low,
        },
        "diff_size_confirmation_limit": (
            DEFAULT_DIFF_SIZE_CONFIRMATION_LIMIT
            if diff_size_confirmation_limit is None
            else diff_size_confirmation_limit),
    }
    if display_name:
        cfg["display_name"] = display_name
    return cfg


def init_project(notes_home, project_slug, display_name=None, max_nodes=None,
                 high=None, low=None, diff_size_confirmation_limit=None,
                 contention_timeout=None):
    """Idempotent. Returns (config, created).

    An existing VALID config is returned byte-untouched with created=False,
    ignoring every caller-supplied setting. An existing INVALID one raises.
    A missing one is created with a freshly minted project_id.

    `contention_timeout` is passed through to ProjectLock; None keeps that
    class's own default. It exists because ProjectLock binds its timeout as
    a DEFAULT ARGUMENT, so patching `lock._CONTENTION_TIMEOUT` has no
    effect and a caller that wants to fail fast has no other way in."""
    # Validated before any directory is created: a malformed slug must not
    # leave a stray notes-home directory named after it.
    if not ctx_ids.SLUG_RE.match(project_slug or ""):
        raise ConfigInvalidError([_finding(
            "E_ARCH_CONFIG_MALFORMED_PROJECT_SLUG",
            "project_slug %r is not kebab-case" % (project_slug,),
            field="project_slug")])

    path = state.config_path(notes_home, project_slug)
    pdir = project_dir(notes_home, project_slug)
    os.makedirs(pdir, exist_ok=True)
    lock_kwargs = ({} if contention_timeout is None
                   else {"contention_timeout": contention_timeout})
    with lock.ProjectLock(pdir, "arch_init", **lock_kwargs):
        existing = load_config(path)
        if existing is not None:
            findings = state.validate_config(existing)
            if findings:
                raise ConfigInvalidError(findings)
            # A copied notes-home directory is the failure this catches:
            # the config would otherwise hand a second project the first
            # one's identity, and every judgment recorded under it.
            found = existing.get("project_slug")
            if found != project_slug:
                raise ConfigInvalidError([_finding(
                    E_CONFIG_SLUG_MISMATCH,
                    "config at %r carries project_slug %r but this project "
                    "is %r" % (path, found, project_slug),
                    field="project_slug")])
            return existing, False

        cfg = _default_config(project_slug, display_name, max_nodes, high,
                              low, diff_size_confirmation_limit)
        findings = state.validate_config(cfg)
        if findings:
            raise ConfigInvalidError(findings)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_io.write_json_atomic(path, cfg)
        return cfg, True


def validate(notes_home, project_slug):
    """Read-only. Returns a findings list; empty means valid."""
    path = state.config_path(notes_home, project_slug)
    cfg = load_config(path)
    if cfg is None:
        return [_finding(E_CONFIG_MISSING,
                         "no architecture configuration at %r" % (path,))]
    return state.validate_config(cfg)
