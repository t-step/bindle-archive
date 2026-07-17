"""context_graph.evidence — normalization of typed evidence references
(issue #181, epic #140).

A pure, network-free normalizer for the durable evidence pointers used by
project maps and the future context graph: typed and bare GitHub issue/PR
references, session/handoff/repository-document paths, commit pointers, and
a deliberately narrow whole-value Markdown link wrapper around any of the
above. Delegates canonical identity formatting to context_graph.ids — this
module owns recognition, grammar, and dispatch only.

Two primitives:

  normalize(value, ...)        one evidence atom -> one result dict
  normalize_field(value, ...)  a complete comma-separated field -> either
                                {"status": "field_ok", "results": [...]}
                                or {"status": "field_rejected", "reason": …}

normalize_field owns list tokenization (comma recognition that respects
Markdown-link/backtick spans) and delegates each atom back to normalize().

Result envelope (one of):

  {"status": "normalized", "id": <typed-id>, "class": "evidence",
   "kind": <kind>, ...kind-specific fields...}
  {"status": "unresolved", "kind": <kind>, "reason": <code>, ...}
  {"status": "recognized_unsupported", "kind": "commit_pointer",
   "value": <lowercased-hex>, "reason": "commit_resolution_deferred"}
  {"status": "rejected", "reason": <code>, "value": <original atom>}

Performs no network access, no filesystem reads of evidence targets, and
writes nothing.
"""
import re

from context_graph import ids

GITHUB_ISSUE_URL_RE = re.compile(
    r"^https://github\.com/([^/\s]+)/([^/\s]+)/issues/([0-9]+)(?:[?#].*)?$"
)
GITHUB_PR_URL_RE = re.compile(
    r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/([0-9]+)(?:[?#].*)?$"
)
GITHUB_REPO_PAGE_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/?$")

TYPED_LOCAL_ISSUE_RE = re.compile(r"^(?i:issue)\s+#([0-9]+)$")
TYPED_LOCAL_PR_RE = re.compile(r"^(?i:pr)\s+#([0-9]+)$")
TYPED_QUALIFIED_ISSUE_RE = re.compile(r"^(?i:issue)\s+([^/\s#]+)/([^/\s#]+)#([0-9]+)$")
TYPED_QUALIFIED_PR_RE = re.compile(r"^(?i:pr)\s+([^/\s#]+)/([^/\s#]+)#([0-9]+)$")

BARE_LOCAL_NUMBER_RE = re.compile(r"^#([0-9]+)$")
BARE_QUALIFIED_NUMBER_RE = re.compile(r"^([^/\s#]+)/([^/\s#]+)#([0-9]+)$")

COMMIT_BACKTICK_RE = re.compile(r"^`([^`]+)`$")
COMMIT_PREFIX_RE = re.compile(r"^(?i:commit)\s+(.+)$")
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

KIND_HINT_TO_FORMATTER = {
    "github_issue": ("github_issue", ids.format_github_issue_id),
    "github_pr": ("github_pr", ids.format_github_pr_id),
}


class MalformedIdentityError(ValueError):
    pass


def _require_valid_project_id(project_id):
    if not ids.PROJECT_ID_RE.match(project_id):
        raise MalformedIdentityError(
            "invalid --project-id %r: must be project:<32-lowercase-hex>, "
            "never a repository-shaped identity" % (project_id,)
        )


# --------------------------------------------------------------------------
# GitHub reference classification
# --------------------------------------------------------------------------

def _github_number_result(repository, number, kind_hint):
    if kind_hint in KIND_HINT_TO_FORMATTER:
        kind, formatter = KIND_HINT_TO_FORMATTER[kind_hint]
        owner, repo = repository.split("/", 1)
        return {
            "status": "normalized",
            "id": formatter(owner, repo, number),
            "class": "evidence",
            "kind": kind,
            "repository": repository,
            "number": number,
        }
    return {
        "status": "unresolved",
        "kind": "github_number",
        "repository": repository,
        "number": number,
        "reason": "artifact_type_missing",
    }


def _not_positive_rejection(value):
    return {"status": "rejected", "reason": "artifact_number_not_positive", "value": value}


def _typed_result(is_issue, owner, repo, number):
    formatter = ids.format_github_issue_id if is_issue else ids.format_github_pr_id
    return {
        "status": "normalized",
        "id": formatter(owner, repo, number),
        "class": "evidence",
        "kind": "github_issue" if is_issue else "github_pr",
        "repository": "%s/%s" % (owner, repo),
        "number": number,
    }


def _classify_github(value, repository, kind_hint):
    """Returns a result dict if `value` matches a supported GitHub
    reference shape, else None (not a GitHub-shaped atom at all)."""
    m = TYPED_LOCAL_ISSUE_RE.match(value) or TYPED_LOCAL_PR_RE.match(value)
    if m:
        is_issue = bool(TYPED_LOCAL_ISSUE_RE.match(value))
        number = int(m.group(1))
        if number <= 0:
            return _not_positive_rejection(value)
        if repository is None:
            return {"status": "unresolved",
                     "kind": "github_issue" if is_issue else "github_pr",
                     "number": number, "reason": "repository_not_configured"}
        owner, repo = repository.split("/", 1)
        return _typed_result(is_issue, owner, repo, number)

    m = TYPED_QUALIFIED_ISSUE_RE.match(value) or TYPED_QUALIFIED_PR_RE.match(value)
    if m:
        is_issue = bool(TYPED_QUALIFIED_ISSUE_RE.match(value))
        owner, repo, number_s = m.groups()
        number = int(number_s)
        if number <= 0:
            return _not_positive_rejection(value)
        return _typed_result(is_issue, owner, repo, number)

    m = GITHUB_ISSUE_URL_RE.match(value) or GITHUB_PR_URL_RE.match(value)
    if m:
        is_issue = bool(GITHUB_ISSUE_URL_RE.match(value))
        owner, repo, number_s = m.groups()
        number = int(number_s)
        if number <= 0:
            return _not_positive_rejection(value)
        return _typed_result(is_issue, owner, repo, number)

    if GITHUB_REPO_PAGE_RE.match(value) or value.startswith(("https://github.com/",
                                                              "http://github.com/")):
        return {"status": "rejected", "reason": "github_url_missing_artifact",
                "value": value}

    m = BARE_QUALIFIED_NUMBER_RE.match(value)
    if m:
        owner, repo, number_s = m.groups()
        number = int(number_s)
        if number <= 0:
            return _not_positive_rejection(value)
        return _github_number_result("%s/%s" % (owner, repo), number, kind_hint)

    m = BARE_LOCAL_NUMBER_RE.match(value)
    if m:
        number = int(m.group(1))
        if number <= 0:
            return _not_positive_rejection(value)
        if repository is None:
            return {"status": "unresolved", "kind": "github_number", "number": number,
                     "reason": "repository_not_configured"}
        return _github_number_result(repository, number, kind_hint)

    return None


# --------------------------------------------------------------------------
# Commit pointer classification
# --------------------------------------------------------------------------

def _classify_commit(value):
    m = COMMIT_BACKTICK_RE.match(value) or COMMIT_PREFIX_RE.match(value)
    if not m:
        return None
    candidate = m.group(1)
    if not HEX_RE.match(candidate):
        return {"status": "rejected", "reason": "commit_pointer_invalid_chars",
                "value": value}
    if len(candidate) < 7:
        return {"status": "rejected", "reason": "commit_pointer_too_short",
                "value": value}
    if len(candidate) > 40:
        return {"status": "rejected", "reason": "commit_pointer_too_long",
                "value": value}
    return {
        "status": "recognized_unsupported",
        "kind": "commit_pointer",
        "value": candidate.lower(),
        "reason": "commit_resolution_deferred",
    }


# --------------------------------------------------------------------------
# Local path classification
# --------------------------------------------------------------------------

def _split_fragment(path):
    if "#" in path:
        path, fragment = path.split("#", 1)
        return path, fragment
    return path, None


# A relative path never contains whitespace, Markdown wrapper punctuation,
# or a URL scheme -- excluding those keeps prose, malformed-link remnants,
# and non-GitHub URLs from being misread as generic document paths.
PATH_CANDIDATE_RE = re.compile(r"^[^\s\[\]()<>]+$")


def _looks_like_path(path):
    if path == "":
        return False
    if not PATH_CANDIDATE_RE.match(path):
        return False
    if "://" in path:
        return False
    return True


def _path_is_safe(path):
    if "?" in path:
        return False
    normalized = path.replace("\\", "/")
    if normalized.startswith("/"):
        return False
    if len(normalized) > 1 and normalized[1] == ":":
        return False
    segments = normalized.split("/")
    if ".." in segments:
        return False
    return True


def _classify_local_path(value, project_id, binding_ids):
    path, fragment = _split_fragment(value)
    if not _looks_like_path(path):
        return None
    if not _path_is_safe(path):
        reason = "path_query_string" if "?" in path else (
            "path_absolute" if (path.startswith("/") or (len(path) > 1 and path[1] == ":"))
            else "path_traversal"
        )
        return {"status": "rejected", "reason": reason, "value": value}

    path = path.replace("\\", "/")

    if path.startswith("sessions/") and path.endswith(".md"):
        result = {
            "status": "normalized",
            "id": ids.format_session_id(project_id, path),
            "class": "evidence",
            "kind": "session",
            "path": path,
        }
        if fragment is not None:
            result["fragment"] = fragment
        return result

    if path.startswith("handoffs/") and path.endswith(".md"):
        result = {
            "status": "normalized",
            "id": ids.format_handoff_id(project_id, path),
            "class": "evidence",
            "kind": "handoff",
            "path": path,
        }
        if fragment is not None:
            result["fragment"] = fragment
        return result

    if len(binding_ids) > 1:
        return {"status": "unresolved", "kind": "document", "reason": "binding_ambiguous",
                "value": value}

    if len(binding_ids) == 1:
        result = {
            "status": "normalized",
            "id": ids.format_document_repository_id(project_id, binding_ids[0], path),
            "class": "evidence",
            "kind": "document_repository",
            "binding_id": binding_ids[0],
            "path": path,
        }
    else:
        result = {
            "status": "normalized",
            "id": ids.format_document_project_local_id(project_id, path),
            "class": "evidence",
            "kind": "document_project_local",
            "path": path,
        }
    if fragment is not None:
        result["fragment"] = fragment
    return result


# --------------------------------------------------------------------------
# Markdown link unwrapping
# --------------------------------------------------------------------------

def _find_matching(text, start, open_ch, close_ch):
    """`text[start]` must be open_ch. Returns the index of the matching
    close_ch (depth-aware), or None if unbalanced."""
    depth = 1
    i = start + 1
    while i < len(text):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _parse_single_link(text):
    """text[0] must be '['. Returns (label, destination) if `text` is
    EXACTLY one well-formed inline Markdown link with no trailing/leading
    content, or (None, reason) otherwise."""
    close_bracket = _find_matching(text, 0, "[", "]")
    if close_bracket is None:
        return None, "markdown_wrapper_malformed"
    if close_bracket + 1 >= len(text) or text[close_bracket + 1] != "(":
        if close_bracket + 1 < len(text) and text[close_bracket + 1] == "[":
            return None, "markdown_reference_style"
        return None, "markdown_wrapper_malformed"
    close_paren = _find_matching(text, close_bracket + 1, "(", ")")
    if close_paren is None:
        return None, "markdown_wrapper_malformed"
    if close_paren != len(text) - 1:
        remainder = text[close_paren + 1:]
        if "](" in remainder:
            return None, "markdown_multiple_links"
        return None, "markdown_link_embedded_in_prose"
    label = text[1:close_bracket]
    destination = text[close_bracket + 2:close_paren]
    if destination == "":
        return None, "markdown_destination_empty"
    return (label, destination), None


def _try_unwrap_markdown_link(atom):
    """Returns ("link", label, destination) | ("reject", reason) | ("bare", None)."""
    if atom.startswith("!") and len(atom) > 1 and atom[1] == "[":
        return ("reject", "markdown_image_syntax")

    if not atom.startswith("["):
        return ("bare", None)

    parsed, reason = _parse_single_link(atom)
    if parsed is None:
        return ("reject", reason)
    label, destination = parsed
    return ("link", label, destination)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _classify_bare(value, project_id, repository, binding_ids, kind_hint):
    result = _classify_github(value, repository, kind_hint)
    if result is not None:
        return result
    result = _classify_commit(value)
    if result is not None:
        return result
    result = _classify_local_path(value, project_id, binding_ids)
    if result is not None:
        return result
    reason = "markdown_link_embedded_in_prose" if "](" in value else "unsupported_form"
    return {"status": "rejected", "reason": reason, "value": value}


def normalize(value, project_id, repository=None, binding_ids=(), kind_hint=None):
    """Normalize one evidence atom. `binding_ids` is the zero, one, or many
    `repository-binding:...` identities configured for this project; more
    than one makes any generic repository-document reference ambiguous.
    Raises MalformedIdentityError for a malformed/repository-shaped
    `project_id` -- everything else about the input is reported in the
    result dict, never raised."""
    _require_valid_project_id(project_id)
    binding_ids = list(binding_ids)
    value = value.strip()
    if value == "":
        return {"status": "rejected", "reason": "empty_value", "value": value}

    outcome = _try_unwrap_markdown_link(value)
    if outcome[0] == "reject":
        return {"status": "rejected", "reason": outcome[1], "value": value}
    if outcome[0] == "link":
        _, _label, destination = outcome
        if destination.strip() != destination or destination == "":
            return {"status": "rejected", "reason": "markdown_destination_empty",
                    "value": value}
        return _classify_bare(destination, project_id, repository, binding_ids, kind_hint)

    return _classify_bare(value, project_id, repository, binding_ids, kind_hint)


def tokenize_field(value):
    """Split a complete evidence field into trimmed atoms, respecting
    balanced Markdown-link brackets/parens and backtick spans as
    non-separator regions. Returns (atoms, None) on success or
    (None, reason) on a field-grammar failure (unbalanced wrapper, empty
    member)."""
    tokens = []
    current = []
    bracket_depth = 0
    paren_depth = 0
    in_backtick = False
    for ch in value:
        if ch == "`":
            in_backtick = not in_backtick
            current.append(ch)
            continue
        if not in_backtick:
            if ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth = max(0, bracket_depth - 1)
            elif ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth = max(0, paren_depth - 1)
        if ch == "," and not in_backtick and bracket_depth == 0 and paren_depth == 0:
            tokens.append("".join(current))
            current = []
            continue
        current.append(ch)
    tokens.append("".join(current))

    if in_backtick or bracket_depth != 0 or paren_depth != 0:
        return None, "unbalanced_wrapper"

    stripped = [t.strip() for t in tokens]
    if any(t == "" for t in stripped):
        return None, "empty_atom"
    return stripped, None


def normalize_field(value, project_id, repository=None, binding_ids=()):
    """Normalize a complete comma-separated evidence field. Returns
    {"status": "field_ok", "results": [...]} with one normalize() result
    per atom in order, or {"status": "field_rejected", "reason": ...} when
    the field-level grammar itself cannot be tokenized safely."""
    value = value.strip()
    if value == "":
        return {"status": "field_rejected", "reason": "empty_field"}
    atoms, reason = tokenize_field(value)
    if atoms is None:
        return {"status": "field_rejected", "reason": reason}
    results = [
        normalize(atom, project_id, repository=repository, binding_ids=binding_ids)
        for atom in atoms
    ]
    return {"status": "field_ok", "results": results}


def normalize_batch(records, project_id, repository=None, binding_ids=()):
    """records: an iterable of {"value": <atom>} dicts (JSONL rows).
    Returns a list of normalize() results in input order."""
    return [
        normalize(
            record["value"], project_id, repository=repository, binding_ids=binding_ids
        )
        for record in records
    ]
