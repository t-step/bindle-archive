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
#
# Order is load-bearing: patterns apply in sequence over the same string, so
# every specific path rule runs before the general absolute-path rule and a
# "/Users/jane/..." string reads as home-path rather than absolute-path.
#
# The absolute-path rule redacts any /-rooted filesystem-path-shaped run,
# because an absolute path names a machine's layout whoever's it is:
# "/opt/acme-internal/secret-project" leaks as surely as a home directory.
# Its leading (?<![\w\]/.~-]) requires the run to start at a path boundary,
# which is what keeps redaction idempotent -- the replacement text
# "[redacted:home-path]/repo" leaves "/repo" preceded by "]" and "/x.py"
# preceded by a word character, so neither is a fresh match on a second pass.
REDACTION_PATTERNS = (
    ("home-path", re.compile(r"/Users/[A-Za-z][A-Za-z0-9._-]*")),
    ("home-path", re.compile(r"/home/[A-Za-z][A-Za-z0-9._-]*")),
    ("vault-path", re.compile(r"iCloud~md~obsidian|Mobile Documents/[^ ]*[Oo]bsidian")),  # private-ok: pattern literal, see the SKIP_FILES entry in Step 5
    (
        "absolute-path",
        re.compile(r"(?<![\w\]/.~-])/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+"),
    ),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("token", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("token", re.compile(r"AKIA[0-9A-Z]{16}")),
)


def normalize_path(value, root):
    """Return value as a repository-relative path, or None if unnormalizable.

    The interchange requires repository-relative paths. An absolute path, a
    home-relative path ("~/x", "~jane/x"), a Windows drive path, a traversal,
    or a query string has no safe relative form and is refused rather than
    guessed at -- callers turn a refused anchor into a malformed document.

    A "~"-prefixed path is refused for a second reason beyond ambiguity: it
    resolves outside the repository and carries a username, and anchors are
    exempt from redaction, so accepting one would persist that username in a
    fact no later pass rewrites.

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
    if path.startswith("~"):
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
