"""architecture.exclusions — what candidate planning refuses to look at
(issue #229 child C, slice C1, epic #141).

#141's bounded-projection safeguards require the engine to "exclude
generated, vendored, dependency, cache, build, gitignored, and explicitly
private paths" and to normalize to repository-relative form. This module is
that filter, and it runs BEFORE any metric is computed: a path excluded here
contributes no fan-in, appears in no neighborhood, and reaches no candidate.

Three properties are load-bearing.

EXCLUSION IS OBSERVABLE. Every drop is reported with the source that dropped
it and the pattern that matched. "The map is missing that subsystem" and
"the map excluded that subsystem on purpose" are indistinguishable
otherwise, and the second is a configuration answer while the first is a
bug report.

EXCLUSION IS PURE. Patterns arrive as arguments — .gitignore lines and
private-denylist terms are read by the caller, not here. Every module in
this package holds that line (state.py takes the notes home as a parameter
rather than resolving it), and it is what lets the whole filter be tested
from literal data with no filesystem at all.

A PRIVATE MATCH NEVER ECHOES THE TERM. The reason travels onward into
findings and logs. Naming the matched denylist term there would leak
precisely what the denylist exists to suppress, so the reported pattern is a
constant placeholder. Same reasoning as redaction.py: findings are built
from redacted values only.

Precedence between sources is fixed rather than first-match, because the
reported source is diffed run over run: `unnormalizable` (the path has no
safe relative form at all), then `private`, then `default`, `configured`,
`gitignore`. Privacy outranks the pattern sources so that a private path
inside a vendored tree still reads as private.
"""
import re

from structural_graph.redaction import normalize_path, redact

# Sources, in the fixed precedence order above.
EXCLUSION_SOURCES = (
    "unnormalizable", "private", "default", "configured", "gitignore",
)

# What a denylist match reports instead of the term it matched.
PRIVATE_PATTERN = "[redacted:denylist-term]"

# Bare segments match at any depth (a `node_modules` anywhere is a
# dependency tree); `**/`-prefixed globs match at any depth including the
# root, per gitignore's own reading of a leading `**/`.
DEFAULT_EXCLUSION_PATTERNS = (
    # version control and tooling caches
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".gradle",
    ".terraform",
    # dependency trees
    "node_modules",
    "bower_components",
    "vendor",
    "third_party",
    ".venv",
    "venv",
    ".tox",
    # build and coverage output
    "dist",
    "build",
    "target",
    "out",
    "coverage",
    # generated and minified artifacts
    "**/*.pyc",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.generated.*",
    "**/*_generated.go",
    "**/*.pb.go",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/*.lock",
    "**/package-lock.json",
    "**/go.sum",
)


def _translate(pattern):
    """Glob to regex, with `*` bounded to one segment and `**` crossing.

    A single `*` that crossed `/` would make `*.py` exclude the entire
    repository the moment anyone configured it for one top-level script.
    """
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:[^/]+/)*"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return out


def _has_wildcard(pattern):
    return any(ch in pattern for ch in "*?[")


def matches(path, pattern):
    """True when a repository-relative path matches one exclusion pattern.

    Three shapes, following gitignore closely enough that a .gitignore line
    handed straight in behaves the way the operator expects:

      * a bare literal segment (`vendor`, `node_modules`) matches that
        segment at ANY depth, as a file or as a directory;
      * a trailing `/` means directory-only — it matches what lies beneath,
        never a file of the same name;
      * anything containing `/` is anchored at the repository root unless it
        opens with `**/`.
    """
    if not isinstance(pattern, str):
        return False
    pattern = pattern.strip()
    if not pattern or pattern.startswith("#"):
        return False
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern[:-1]
    if not pattern:
        return False

    if "/" not in pattern and not _has_wildcard(pattern):
        segments = path.split("/")
        if dir_only:
            return pattern in segments[:-1]
        return pattern in segments

    expression = _translate(pattern)
    if dir_only:
        expression += "/.*"
    return re.fullmatch(expression, path) is not None


def _gitignore_verdict(path, lines):
    """Last matching .gitignore line wins, and `!` un-excludes.

    Gitignore's own rule. Without it, the common shape of a real ignore file
    — ignore a build tree, then rescue one checked-in artifact inside it —
    silently drops the rescued path.
    """
    verdict = None
    for line in lines or []:
        if not isinstance(line, str):
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        negated = stripped.startswith("!")
        candidate = stripped[1:] if negated else stripped
        if matches(path, candidate):
            verdict = None if negated else candidate
    return verdict


def _reason(source, pattern):
    return {"source": source, "pattern": pattern}


def exclusion_reason(path, configured=(), gitignore=(), denylist=(),
                     defaults=True, root=""):
    """Why `path` is excluded, or None when it survives every filter.

    Returns {"source", "pattern"}. `root` bounds what is in scope: a path
    outside it has no place in this project's map and is refused by
    normalization rather than silently kept.
    """
    normalized = normalize_path(path, root)
    if normalized is None:
        return _reason("unnormalizable", None)

    lowered = normalized.lower()
    for term in denylist or ():
        if not isinstance(term, str):
            continue
        term = term.strip()
        if term and term.lower() in lowered:
            return _reason("private", PRIVATE_PATTERN)

    if defaults:
        for pattern in DEFAULT_EXCLUSION_PATTERNS:
            if matches(normalized, pattern):
                return _reason("default", pattern)

    for pattern in configured or ():
        if matches(normalized, pattern):
            return _reason("configured", pattern)

    ignored = _gitignore_verdict(normalized, gitignore)
    if ignored is not None:
        return _reason("gitignore", ignored)

    return None


def partition_paths(paths, configured=(), gitignore=(), denylist=(),
                    defaults=True, root=""):
    """Split paths into what planning may see and what it dropped.

        {"kept": [...],                       # normalized, unique, sorted
         "excluded": [{"path", "source", "pattern"}, ...],   # sorted by path
         "applied": {...}}                    # the filters that ran

    Output is a pure function of the path SET, not of its order, because
    #229's acceptance requires identical input to produce byte-identical
    output and an interchange document's file order is a provider's choice.

    An unnormalizable path is reported REDACTED. It is the value most likely
    to carry a home directory — that is usually why it failed to normalize —
    and this report is not exempt from FC-7 just because the path was
    rejected.
    """
    kept = set()
    excluded = {}
    for path in paths or ():
        reason = exclusion_reason(
            path, configured=configured, gitignore=gitignore,
            denylist=denylist, defaults=defaults, root=root,
        )
        if reason is None:
            kept.add(normalize_path(path, root))
            continue
        if reason["source"] == "unnormalizable":
            reported = redact(path)[0] if isinstance(path, str) else repr(path)
        else:
            reported = normalize_path(path, root)
        excluded[reported] = dict(reason, path=reported)

    return {
        "kept": sorted(kept),
        "excluded": [excluded[key] for key in sorted(excluded)],
        "applied": {
            "defaults": list(DEFAULT_EXCLUSION_PATTERNS) if defaults else [],
            "configured": list(configured or ()),
            "gitignore": list(gitignore or ()),
            "denylist_terms": len([
                t for t in (denylist or ())
                if isinstance(t, str) and t.strip()
            ]),
            "root": root,
        },
    }
