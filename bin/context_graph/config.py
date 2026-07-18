"""context_graph.config — project identity and repository-binding
configuration (issue #191, epic #140). Owns config.json's authoritative
lifecycle: allocation, atomic persistence, and repository-binding CRUD.

Read-only semantic checks (project-id shape, duplicate alias/binding-id,
multiple-default) are context_graph.validation.validate_config (shipped by
#180); this module adds config-file-specific structural and local-origin
checks that validate_config cannot do because they need filesystem/git
access outside its pure-object contract. context_graph.config.all_findings
composes both, deliberately NOT adding new codes to validation.FINDING_CODES
(that enum is #180-owned and cross-checked by test_schema_conformance.py).

Every mutating function acquires context_graph.lock.ProjectLock for the
duration of its read-modify-write and releases it (including on exception)
before returning or raising. An existing config that fails validation is
never mutated further — mutation always raises ConfigInvalidError rather
than repairing or replacing it.
"""
import os
import secrets
import subprocess

from context_graph import atomic_io
from context_graph import ids
from context_graph import lock
from context_graph import validation

SCHEMA_VERSION = 1
CONTEXT_SUBDIR = os.path.join(".bindle", "context")
CONFIG_FILENAME = "config.json"

_KNOWN_TOP_LEVEL_FIELDS = frozenset(
    ["schema_version", "project_id", "project_slug", "display_name", "repositories"]
)
_KNOWN_REPOSITORY_FIELDS = frozenset(
    ["alias", "binding_id", "provider", "coordinates", "local_checkout_path",
     "default_for_bare_references"]
)


def _finding(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d


class ConfigError(Exception):
    """Base class for config domain errors. `.findings` is always a
    non-empty list of {"code", "message", ...} dicts — the same shape
    context_graph.validation produces, so CLI rendering is uniform."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f["message"] for f in findings))


class ConfigMissingError(ConfigError):
    def __init__(self, path):
        super().__init__([_finding(
            "E_CONFIG_MISSING", "no configuration found at %r" % (path,))])
        self.path = path


class ConfigInvalidError(ConfigError):
    """Existing or about-to-be-written config fails validation."""


class BindingNotFoundError(ConfigError):
    def __init__(self, binding_id):
        super().__init__([_finding(
            "E_CONFIG_BINDING_NOT_FOUND",
            "no repository binding %r in configuration" % (binding_id,))])
        self.binding_id = binding_id


def project_dir(notes_home, project_slug):
    return os.path.join(notes_home, "projects", project_slug)


def context_dir(notes_home, project_slug):
    return os.path.join(project_dir(notes_home, project_slug), CONTEXT_SUBDIR)


def config_path(notes_home, project_slug):
    return os.path.join(context_dir(notes_home, project_slug), CONFIG_FILENAME)


def allocate_project_id():
    return ids.format_project_id(secrets.token_hex(16))


def allocate_binding_id():
    return ids.format_repository_binding_id(secrets.token_hex(16))


def load_config(path):
    """Return the parsed config dict, or None if no file exists at path.
    Raises ConfigInvalidError (E_CONFIG_UNREADABLE) for a present file that
    is not valid JSON — never silently treated as missing."""
    try:
        return atomic_io.read_json(path)
    except FileNotFoundError:
        return None
    except ValueError as e:
        raise ConfigInvalidError([_finding(
            "E_CONFIG_UNREADABLE", "config at %r is not valid JSON: %s" % (path, e))])


def structural_findings(cfg):
    """Config-file-specific structural checks beyond validate_config's
    semantic checks: unsupported schema_version, unknown top-level/
    repository fields, malformed binding_id shape. Pure, no filesystem
    access."""
    findings = []
    version = cfg.get("schema_version")
    if version != SCHEMA_VERSION:
        findings.append(_finding(
            "E_CONFIG_SCHEMA_VERSION_UNSUPPORTED",
            "unsupported schema_version %r (expected %d)" % (version, SCHEMA_VERSION),
            field="schema_version"))
    for key in cfg:
        if key not in _KNOWN_TOP_LEVEL_FIELDS:
            findings.append(_finding(
                "E_CONFIG_UNKNOWN_FIELD", "unknown top-level field %r" % (key,), field=key))
    for i, repo in enumerate(cfg.get("repositories", [])):
        for key in repo:
            if key not in _KNOWN_REPOSITORY_FIELDS:
                findings.append(_finding(
                    "E_CONFIG_UNKNOWN_FIELD",
                    "unknown repository field %r at index %d" % (key, i),
                    index=i, field=key))
        binding_id = repo.get("binding_id", "")
        try:
            parsed = ids.parse_typed_id(binding_id)
            if parsed["type"] != "repository_binding":
                raise ids.MalformedIdError(binding_id, "not a repository-binding id")
        except ids.MalformedIdError:
            findings.append(_finding(
                "E_CONFIG_MALFORMED_BINDING_ID",
                "malformed binding_id %r at index %d" % (binding_id, i),
                index=i, field="binding_id"))
    return findings


def _git_env():
    """Return a cleaned environment dict with git-related variables stripped.
    This ensures that subprocess.run(["git", ...]) calls are hermetic — they
    operate on the repo specified by -C, not inherited GIT_DIR/GIT_WORK_TREE/etc
    from an ambient git process (e.g. a parent git commit hook). This is needed
    for production code that shells out to git and for tests that create
    temporary git repos, to ensure correctness even when invoked from within
    a git hook or other git-wrapping context."""
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"):
        env.pop(key, None)
    return env


def _coordinates_from_git_url(url):
    """'git@github.com:owner/repo.git' or 'https://github.com/owner/repo.git'
    -> 'owner/repo'. Returns None for a URL shape this cannot parse rather
    than guessing."""
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@"):
        _, _, tail = url.partition(":")
    elif "://" in url:
        _, _, tail = url.partition("://")
        _, _, tail = tail.partition("/")
    else:
        return None
    parts = tail.strip("/").split("/")
    if len(parts) < 2:
        return None
    return "%s/%s" % (parts[-2], parts[-1])


def local_origin_findings(cfg):
    """For each binding with both coordinates and a local_checkout_path
    that exists and is a Git repository, compare its `origin` remote to
    the configured coordinates. A disagreement is reported, never silently
    adopted (issue's Validation section; design fixture 16)."""
    findings = []
    for i, repo in enumerate(cfg.get("repositories", [])):
        coordinates = repo.get("coordinates")
        checkout = repo.get("local_checkout_path")
        if not coordinates or not checkout:
            continue
        if not os.path.isdir(os.path.join(checkout, ".git")):
            continue
        try:
            out = subprocess.run(
                ["git", "-C", checkout, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5, env=_git_env())
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode != 0:
            continue
        origin_coordinates = _coordinates_from_git_url(out.stdout.strip())
        if origin_coordinates and origin_coordinates != coordinates:
            findings.append(_finding(
                "E_CONFIG_LOCAL_ORIGIN_DISAGREEMENT",
                "local checkout %r origin %r disagrees with configured "
                "coordinates %r at index %d" % (checkout, origin_coordinates,
                                                 coordinates, i),
                index=i, field="local_checkout_path"))
    return findings


def _malformed_shape_findings(cfg):
    """Defensive type-shape check: a syntactically valid JSON document can
    still be the wrong *shape* (e.g. a list or string at the top level, or
    a non-object repositories entry). validate_config/structural_findings/
    local_origin_findings all assume cfg and each repositories[i] are
    dicts and will raise AttributeError/TypeError on anything else. Catch
    that here, before any .get/iteration, so malformed shape surfaces as
    an E_CONFIG_MALFORMED_SHAPE finding (-> ConfigInvalidError) instead of
    an unhandled Python exception."""
    if not isinstance(cfg, dict):
        return [_finding(
            "E_CONFIG_MALFORMED_SHAPE",
            "config is not a JSON object (got %s)" % (type(cfg).__name__,))]
    repositories = cfg.get("repositories")
    if repositories is not None:
        if not isinstance(repositories, list):
            return [_finding(
                "E_CONFIG_MALFORMED_SHAPE",
                "repositories is not a list (got %s)" % (type(repositories).__name__,),
                field="repositories")]
        for i, repo in enumerate(repositories):
            if not isinstance(repo, dict):
                return [_finding(
                    "E_CONFIG_MALFORMED_SHAPE",
                    "repository entry at index %d is not an object (got %s)"
                    % (i, type(repo).__name__),
                    index=i)]
    return []


def all_findings(cfg):
    """The union `config validate` reports: shared semantic checks
    (validate_config) plus this module's structural and local-origin
    checks. A malformed top-level/repositories shape short-circuits before
    any of those run, since they all assume dict access."""
    shape_findings = _malformed_shape_findings(cfg)
    if shape_findings:
        return shape_findings
    return (validation.validate_config(cfg)
            + structural_findings(cfg)
            + local_origin_findings(cfg))


def init_project(notes_home, project_slug, display_name=None):
    """Idempotent: an existing valid config is preserved byte-for-byte
    (zero writes) and returned with created=False. A missing config is
    created with a freshly allocated project_id. An existing malformed/
    conflicting config raises ConfigInvalidError rather than being
    repaired or replaced. Returns (config_dict, created: bool)."""
    cdir = context_dir(notes_home, project_slug)
    path = os.path.join(cdir, CONFIG_FILENAME)
    with lock.ProjectLock(cdir, "init"):
        existing = load_config(path)
        if existing is not None:
            findings = all_findings(existing)
            if findings:
                raise ConfigInvalidError(findings)
            return existing, False
        cfg = {
            "schema_version": SCHEMA_VERSION,
            "project_id": allocate_project_id(),
            "project_slug": project_slug,
            "repositories": [],
        }
        if display_name:
            cfg["display_name"] = display_name
        findings = all_findings(cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, cfg)
        return cfg, True


def _load_valid_or_raise(notes_home, project_slug, cdir):
    path = os.path.join(cdir, CONFIG_FILENAME)
    cfg = load_config(path)
    if cfg is None:
        raise ConfigMissingError(path)
    findings = all_findings(cfg)
    if findings:
        raise ConfigInvalidError(findings)
    return path, cfg


def _find_repository(repositories, binding_id):
    for i, repo in enumerate(repositories):
        if repo.get("binding_id") == binding_id:
            return i
    return None


def add_repository(notes_home, project_slug, alias, provider, coordinates=None,
                    local_checkout_path=None, is_default=False):
    cdir = context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "config"):
        path, cfg = _load_valid_or_raise(notes_home, project_slug, cdir)
        entry = {"alias": alias, "binding_id": allocate_binding_id(), "provider": provider}
        if coordinates:
            entry["coordinates"] = coordinates
        if local_checkout_path:
            entry["local_checkout_path"] = local_checkout_path
        repositories = list(cfg["repositories"])
        if is_default:
            repositories = [dict(r, default_for_bare_references=False) for r in repositories]
            entry["default_for_bare_references"] = True
        repositories.append(entry)
        new_cfg = dict(cfg, repositories=repositories)
        findings = all_findings(new_cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, new_cfg)
        return new_cfg, entry


def update_repository(notes_home, project_slug, binding_id, alias=None,
                       coordinates=None, local_checkout_path=None, default=None):
    """`default=True` sets this binding default (unsetting any other);
    `default=False` explicitly unsets it; `default=None` leaves it
    unchanged. Only supplied (non-None) fields change."""
    cdir = context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "config"):
        path, cfg = _load_valid_or_raise(notes_home, project_slug, cdir)
        repositories = [dict(r) for r in cfg["repositories"]]
        idx = _find_repository(repositories, binding_id)
        if idx is None:
            raise BindingNotFoundError(binding_id)
        if alias is not None:
            repositories[idx]["alias"] = alias
        if coordinates is not None:
            repositories[idx]["coordinates"] = coordinates
        if local_checkout_path is not None:
            repositories[idx]["local_checkout_path"] = local_checkout_path
        if default is True:
            for i, r in enumerate(repositories):
                r["default_for_bare_references"] = (i == idx)
        elif default is False:
            repositories[idx]["default_for_bare_references"] = False
        new_cfg = dict(cfg, repositories=repositories)
        findings = all_findings(new_cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, new_cfg)
        return new_cfg, repositories[idx]


def remove_repository(notes_home, project_slug, binding_id):
    cdir = context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "config"):
        path, cfg = _load_valid_or_raise(notes_home, project_slug, cdir)
        repositories = list(cfg["repositories"])
        idx = _find_repository(repositories, binding_id)
        if idx is None:
            raise BindingNotFoundError(binding_id)
        removed = repositories.pop(idx)
        new_cfg = dict(cfg, repositories=repositories)
        findings = all_findings(new_cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, new_cfg)
        return new_cfg, removed


def set_default(notes_home, project_slug, binding_id):
    return update_repository(notes_home, project_slug, binding_id, default=True)
