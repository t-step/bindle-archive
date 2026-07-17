"""context_graph.ids — typed-ID parsing and formatting for the v1
context-graph interchange contract (issue #180, epic #140).

Pure string parsing/formatting only: no filesystem or network access, no
validation beyond an ID's own regex shape. Semantic/cross-object validation
(does this project_id match the configured one, does this node exist) lives
in context_graph.validation.

Typed-ID formats (frozen by docs/design/2026-07-16-context-graph-schema.md
section 5):

  project:<32-lowercase-hex>
  context-node:<creation-project-slug>:<32-lowercase-hex>   (#179 form)
  repository-binding:<32-lowercase-hex>
  session:<project-id>:sessions/<filename>.md
  handoff:<project-id>:handoffs/<filename>.md
  document:<project-id>:<binding-id>:<repository-relative-path>
  document:<project-id>:project-local:<project-relative-path>
  github-issue:<owner>/<repo>#<n>
  github-pr:<owner>/<repo>#<n>
  candidate:sha256:<64-lowercase-hex>
  anchor-candidate:sha256:<64-lowercase-hex>

All hex components are exactly 32 (id) or 64 (candidate-key digest)
lowercase hexadecimal characters; any other length is malformed.
"""
import re

HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PROJECT_ID_RE = re.compile(r"^project:([0-9a-f]{32})$")
CONTEXT_NODE_ID_RE = re.compile(
    r"^context-node:([a-z0-9]+(?:-[a-z0-9]+)*):([0-9a-f]{32})$"
)
BINDING_ID_RE = re.compile(r"^repository-binding:([0-9a-f]{32})$")
SESSION_ID_RE = re.compile(r"^session:(project:[0-9a-f]{32}):(sessions/.+\.md)$")
HANDOFF_ID_RE = re.compile(r"^handoff:(project:[0-9a-f]{32}):(handoffs/.+\.md)$")
DOCUMENT_REPO_ID_RE = re.compile(
    r"^document:(project:[0-9a-f]{32}):(repository-binding:[0-9a-f]{32}):(.+)$"
)
DOCUMENT_LOCAL_ID_RE = re.compile(
    r"^document:(project:[0-9a-f]{32}):project-local:(.+)$"
)
GITHUB_ISSUE_ID_RE = re.compile(r"^github-issue:([^/#]+)/([^/#]+)#([0-9]+)$")
GITHUB_PR_ID_RE = re.compile(r"^github-pr:([^/#]+)/([^/#]+)#([0-9]+)$")
CANDIDATE_KEY_RE = re.compile(r"^candidate:sha256:([0-9a-f]{64})$")
ANCHOR_CANDIDATE_KEY_RE = re.compile(r"^anchor-candidate:sha256:([0-9a-f]{64})$")

PROJECT_LOCAL_LITERAL = "project-local"


class MalformedIdError(ValueError):
    """Raised by parse_typed_id for any string that is not a well-formed v1
    typed ID. `.id_str` and `.reason` carry structured detail for the
    caller's finding message."""

    def __init__(self, id_str, reason):
        super().__init__("malformed typed ID %r: %s" % (id_str, reason))
        self.id_str = id_str
        self.reason = reason


def parse_typed_id(id_str):
    """Parse any v1 typed-ID string into a dict with a "type" discriminator
    plus type-specific fields. Raises MalformedIdError for anything that does
    not match one of the frozen v1 formats exactly (repository-shaped
    project IDs, short hex, unknown prefixes, empty strings)."""
    if not isinstance(id_str, str) or id_str == "":
        raise MalformedIdError(id_str, "not a non-empty string")

    m = PROJECT_ID_RE.match(id_str)
    if m:
        return {"type": "project", "id": id_str, "hex": m.group(1)}

    m = CONTEXT_NODE_ID_RE.match(id_str)
    if m:
        return {
            "type": "context_node",
            "id": id_str,
            "creation_project_slug": m.group(1),
            "hex": m.group(2),
        }

    m = BINDING_ID_RE.match(id_str)
    if m:
        return {"type": "repository_binding", "id": id_str, "hex": m.group(1)}

    m = SESSION_ID_RE.match(id_str)
    if m:
        return {
            "type": "session",
            "id": id_str,
            "project_id": m.group(1),
            "relative_path": m.group(2),
        }

    m = HANDOFF_ID_RE.match(id_str)
    if m:
        return {
            "type": "handoff",
            "id": id_str,
            "project_id": m.group(1),
            "relative_path": m.group(2),
        }

    m = DOCUMENT_REPO_ID_RE.match(id_str)
    if m:
        return {
            "type": "document_repository",
            "id": id_str,
            "project_id": m.group(1),
            "binding_id": m.group(2),
            "repository_relative_path": m.group(3),
        }

    m = DOCUMENT_LOCAL_ID_RE.match(id_str)
    if m:
        return {
            "type": "document_project_local",
            "id": id_str,
            "project_id": m.group(1),
            "project_relative_path": m.group(2),
        }

    m = GITHUB_ISSUE_ID_RE.match(id_str)
    if m:
        return {
            "type": "github_issue",
            "id": id_str,
            "owner": m.group(1),
            "repo": m.group(2),
            "number": int(m.group(3)),
        }

    m = GITHUB_PR_ID_RE.match(id_str)
    if m:
        return {
            "type": "github_pr",
            "id": id_str,
            "owner": m.group(1),
            "repo": m.group(2),
            "number": int(m.group(3)),
        }

    m = CANDIDATE_KEY_RE.match(id_str)
    if m:
        return {"type": "candidate_key", "id": id_str, "hex": m.group(1)}

    m = ANCHOR_CANDIDATE_KEY_RE.match(id_str)
    if m:
        return {"type": "anchor_candidate_key", "id": id_str, "hex": m.group(1)}

    raise MalformedIdError(id_str, "matches no known v1 typed-ID format")


def format_project_id(hex32):
    if not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "project:%s" % hex32


def format_context_node_id(creation_project_slug, hex32):
    if not SLUG_RE.match(creation_project_slug):
        raise ValueError(
            "invalid creation_project_slug %r" % (creation_project_slug,)
        )
    if not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "context-node:%s:%s" % (creation_project_slug, hex32)


def format_repository_binding_id(hex32):
    if not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "repository-binding:%s" % hex32


def format_session_id(project_id, relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not relative_path.startswith("sessions/") or not relative_path.endswith(".md"):
        raise ValueError(
            "session relative_path must be 'sessions/<name>.md': %r" % (relative_path,)
        )
    return "session:%s:%s" % (project_id, relative_path)


def format_handoff_id(project_id, relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not relative_path.startswith("handoffs/") or not relative_path.endswith(".md"):
        raise ValueError(
            "handoff relative_path must be 'handoffs/<name>.md': %r" % (relative_path,)
        )
    return "handoff:%s:%s" % (project_id, relative_path)


def format_document_repository_id(project_id, binding_id, repository_relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not BINDING_ID_RE.match(binding_id):
        raise ValueError("invalid binding_id %r" % (binding_id,))
    return "document:%s:%s:%s" % (project_id, binding_id, repository_relative_path)


def format_document_project_local_id(project_id, project_relative_path):
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    return "document:%s:%s:%s" % (
        project_id,
        PROJECT_LOCAL_LITERAL,
        project_relative_path,
    )


def format_github_issue_id(owner, repo, number):
    return "github-issue:%s/%s#%d" % (owner, repo, number)


def format_github_pr_id(owner, repo, number):
    return "github-pr:%s/%s#%d" % (owner, repo, number)
