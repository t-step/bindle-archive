"""structural_graph.redaction -- path normalization and secret redaction.

A build gap, not a reuse. Nothing in bin/ relativizes a path or scrubs a
secret: bin/check-private-info.sh and .gitleaks.toml are detectors that
never rewrite content, and context_graph.evidence rejects an unsafe path
while echoing the raw value straight back to its caller.

Every provider string crosses this module before it reaches a fact, a
finding, a log line, or disk. Findings are built from redacted values only,
so a finding is structurally incapable of carrying a secret.

This module deliberately encodes the same home-directory pattern that
bin/check-private-info.sh scans for, so it carries a skip-list entry there
and an allowlist path in .gitleaks.toml -- the same self-exemption those
two files already hold.
"""

import re

REDACTED = "[redacted:%s]"

# Name -> pattern. Names appear in findings; the matched text never does.
REDACTION_PATTERNS = (
    ("home-path", re.compile(r"/Users/[A-Za-z][A-Za-z0-9._-]*")),
    ("home-path", re.compile(r"/home/[A-Za-z][A-Za-z0-9._-]*")),
    ("vault-path", re.compile(r"iCloud~md~obsidian|Mobile Documents/[^ ]*[Oo]bsidian")),  # private-ok: pattern literal, see the SKIP_FILES entry in Step 5
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("token", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("token", re.compile(r"AKIA[0-9A-Z]{16}")),
)


def normalize_path(value, root):
    """Return value as a repository-relative path, or None if unnormalizable.

    The interchange requires repository-relative paths. An absolute path, a
    Windows drive path, a traversal, or a query string has no safe relative
    form and is refused rather than guessed at -- callers turn a refused
    anchor into a malformed document.

    root bounds what the document may reference: "" means the whole
    repository. A path outside root is unnormalizable, so a document cannot
    smuggle facts about a subtree its coverage never tiled.
    """
    if not isinstance(value, str) or not value:
        return None
    if "?" in value:
        return None
    path = value.replace("\\", "/")
    if path.startswith("/"):
        return None
    if len(path) > 1 and path[1] == ":":
        return None
    if path.startswith("./"):
        path = path[2:]
    if not path:
        return None
    if ".." in path.split("/"):
        return None
    if root:
        if path != root and not path.startswith(root + "/"):
            return None
    return path


def redact(value):
    """Return (scrubbed, matched_names) for an incidental provider string.

    matched_names is a sorted tuple of distinct pattern names, suitable for
    a finding message. The matched text itself is never returned anywhere.
    Redaction is idempotent: a scrubbed string contains no further matches.
    """
    if not isinstance(value, str) or not value:
        return value, ()
    scrubbed = value
    names = set()
    for name, pattern in REDACTION_PATTERNS:
        replacement = REDACTED % name
        scrubbed, count = pattern.subn(replacement, scrubbed)
        if count:
            names.add(name)
    return scrubbed, tuple(sorted(names))
