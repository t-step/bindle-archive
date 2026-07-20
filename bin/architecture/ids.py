"""architecture.ids — typed-ID parsing and formatting for architecture
projection identity (issue #228, epic #141).

Pure string parsing/formatting only: no filesystem or network access, no
validation beyond an ID's own regex shape. Allocation of a new arch-node ID
is a state-and-judgment concern and lives elsewhere in this package; this
module only says whether a string is a well-formed identity and what its
parts are.

Frozen format (issue #228):

  arch-node:<project-id>:<32-lowercase-hex>

where `<project-id>` is the FULL `project:<32-lowercase-hex>` token from
#140's identity space, not a bare hex digest — a consumer can hand
`parse_arch_node_id(...)["project_id"]` straight to `context_graph.ids`
without reassembling it.

This parser lives HERE and never in `context_graph.ids`. Teaching that
module the `arch-node:` grammar would make an architecture identity pass
`context_graph.validation`'s node-id check, legalizing architecture
identity inside the #140 graph. The separation is a frozen contract of
#228, and `architecture.tests.test_ids` guards it as a regression test.

The dependency runs one way only: architecture may read context-graph
identity, never the reverse.
"""
import re

from context_graph.ids import HEX32_RE, PROJECT_ID_RE

# `\Z`, not `$`: `$` also matches just before a trailing newline, so a
# newline-terminated line read from a JSONL file would parse as valid and
# then be written back with the newline baked into the identity.
ARCH_NODE_ID_RE = re.compile(
    r"^arch-node:(project:[0-9a-f]{32}):([0-9a-f]{32})\Z"
)


class MalformedArchIdError(ValueError):
    """Raised by parse_arch_node_id for any string that is not a well-formed
    arch-node ID. `.id_str` and `.reason` carry structured detail for the
    caller's finding message, mirroring context_graph.ids.MalformedIdError."""

    def __init__(self, id_str, reason):
        super().__init__("malformed arch-node ID %r: %s" % (id_str, reason))
        self.id_str = id_str
        self.reason = reason


def parse_arch_node_id(id_str):
    """Parse an arch-node ID string into a dict with a "type" discriminator
    plus its project ID and node hex. Raises MalformedArchIdError for
    anything that does not match the frozen format exactly."""
    if not isinstance(id_str, str) or id_str == "":
        raise MalformedArchIdError(id_str, "not a non-empty string")

    match = ARCH_NODE_ID_RE.match(id_str)
    if not match:
        raise MalformedArchIdError(
            id_str, "does not match arch-node:<project-id>:<32-lowercase-hex>"
        )

    return {
        "type": "arch_node",
        "id": id_str,
        "project_id": match.group(1),
        "hex": match.group(2),
    }


def is_arch_node_id(id_str):
    """True when id_str is a well-formed arch-node ID. Never raises — for
    call sites classifying an untrusted string rather than consuming it."""
    return isinstance(id_str, str) and ARCH_NODE_ID_RE.match(id_str) is not None


def format_arch_node_id(project_id, hex32):
    """Build an arch-node ID from a full `project:<hex>` token and a 32-char
    lowercase hex node digest. Raises ValueError on either component."""
    if not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id %r" % (project_id,))
    if not isinstance(hex32, str) or not HEX32_RE.match(hex32):
        raise ValueError("hex32 must be exactly 32 lowercase hex chars: %r" % (hex32,))
    return "arch-node:%s:%s" % (project_id, hex32)
