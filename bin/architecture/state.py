"""architecture.state — the notes-home state layout, the note-path grammar,
the project_id hard abort, and the frozen schemas of the four architecture
state files (issue #228, epic #141).

Path derivation and pure-object validation only. This module reads nothing
and writes nothing: every helper takes the notes home as a parameter,
because that root is user-relocatable (and possibly Obsidian-synced) and is
always read from configuration, never assumed. Persisting these files, and
reading `judgments.jsonl` back with its integrity rules, live elsewhere in
this package.

State is rooted at the NOTES HOME and namespaced by `project_slug`:

  <notes_home>/projects/<project_slug>/.bindle/architecture/
    config.json         projection settings; operator-owned, never machine-written
    judgments.jsonl     append-only DECISIONS ONLY; authority for MEANING
    index.json          durable projection state; authority for OBSERVED
                        PROVENANCE, never for meaning
    observations.jsonl  OPTIONAL, explicitly non-semantic run ledger
    apply-state.json    interrupted-apply recovery metadata ONLY

Never a bare `.bindle/`: one shared directory would put every project's
identity authority in the same file. The architecture directory is a
sibling of the context graph's, under the same `project_dir`, which is why
#228 also puts a single cross-surface lock at the parent — two separate
locks would let a context apply and an architecture apply interleave.

The authority split is the point of the layout, so the schemas enforce it
structurally: `apply-state.json` may carry no semantic field (losing it must
never change what the projection means), and an `index.json` reference
points AT a context identity without carrying any relationship vocabulary
— it is not an edge in the #140 graph.
"""
import os
import re

from architecture.canonical import judgment_record_id, verify_checksum
from architecture.ids import is_arch_node_id, parse_arch_node_id
from context_graph.config import project_dir
from context_graph.ids import (
    BINDING_ID_RE,
    CONTEXT_NODE_ID_RE,
    PROJECT_ID_RE,
    SLUG_RE,
)

SCHEMA_VERSION = 1
PROJECTION_SCHEMA_VERSION = 1

ARCHITECTURE_SUBDIR = os.path.join(".bindle", "architecture")

CONFIG_FILENAME = "config.json"
JUDGMENTS_FILENAME = "judgments.jsonl"
INDEX_FILENAME = "index.json"
APPLY_STATE_FILENAME = "apply-state.json"
OBSERVATIONS_FILENAME = "observations.jsonl"

# The frozen note tree. F1-F4 populate it and may not invent sibling roots.
CODEBASE_MAP_FILENAME = "Codebase Map.md"
NOTE_SUBTREES = (
    "Components",
    "Architectural Flows",
    "Boundaries",
    "Test Surfaces",
    "Hotspots",
)

PROJECTION_TYPES = ("arch_codebase_map", "arch_component")
_SUBTREE_FOR_PROJECTION_TYPE = {"arch_component": "Components"}
_PROJECTION_TYPE_FOR_SUBTREE = {"Components": "arch_component"}

CONFIDENCE_VALUES = ("high", "medium", "low")
PROJECTION_STATUS_VALUES = ("current", "stale", "superseded", "merged", "partial")
PER_BINDING_STATUS_VALUES = ("available", "unavailable", "stale", "deconfigured")
PER_BINDING_COVERAGE_VALUES = ("observed", "unsupported", "partial_parse_failure")
OVER_CAP_BEHAVIORS = ("report",)
APPLY_STATUS_VALUES = ("in_progress", "complete")
APPLY_WRITE_STATES = ("pending", "written")

# The nine decision classes #228 names, plus the operator escape hatch. A
# closed enum: an unknown kind is a validation error, never a silent pass.
JUDGMENT_KINDS = (
    "identity_allocation",
    "naming",
    "grouping",
    "continuity",
    "rename",
    "reappearance",
    "split",
    "merge",
    "stale",
    "operator_amendment",
)

_NOTE_SLUG_RE = SLUG_RE
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}\Z")
_RECORD_ID_RE = re.compile(r"^arch-judgment:sha256:[0-9a-f]{64}\Z")

_JUDGMENT_REQUIRED = (
    "schema_version", "kind", "project_id", "decided_at", "record_id", "checksum",
)
_JUDGMENT_KNOWN = frozenset(_JUDGMENT_REQUIRED + ("arch_id", "payload"))

_CONFIG_REQUIRED = (
    "schema_version", "projection_schema_version", "project_id", "project_slug",
    "bindings", "caps", "thresholds", "diff_size_confirmation_limit",
)
_CONFIG_KNOWN = frozenset(_CONFIG_REQUIRED + ("exclusions", "display_name"))
_BINDING_KNOWN = frozenset(["binding_id", "alias"])

_INDEX_REQUIRED = (
    "schema_version", "projection_schema_version", "project_id", "nodes",
)
_INDEX_KNOWN = frozenset(_INDEX_REQUIRED + ("references",))
_NODE_REQUIRED = (
    "arch_id", "project_id", "note_path", "binding_ids", "projection_type",
    "projection_schema_version", "confidence", "projection_status",
)
_NODE_KNOWN = frozenset(_NODE_REQUIRED + (
    "provider_name", "provider_version", "source_commits", "source_paths",
    "source_symbols", "per_binding_status", "per_binding_coverage",
    "prior_names", "merged_from", "split_from", "split_into", "superseded_by",
    "last_projected_at",
    # #230 slice D4: set when a resume found this note orphaned -- the
    # crashed run wrote it and the fresh re-plan does not contain it. D may
    # neither delete it (never-auto-delete) nor stale it (G's AC16), so the
    # flag IS the outcome and it needs a home in the ledger.
    "orphaned_by_resume",
))
_REFERENCE_KNOWN = frozenset(["arch_id", "context_id"])

_APPLY_REQUIRED = ("schema_version", "project_id", "status", "started_at", "writes")
_APPLY_KNOWN = frozenset(_APPLY_REQUIRED)
_APPLY_WRITE_KNOWN = frozenset(
    ["order", "path", "before_hash", "after_hash", "state"])


def _finding(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d


class ArchStateError(Exception):
    """Base class for architecture-state domain errors. `.findings` is
    always a non-empty list of {"code", "message", "index", "field"} dicts,
    the same shape context_graph.validation produces, so CLI rendering is
    uniform across both surfaces."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f["message"] for f in findings))


class ProjectIdMismatchError(ArchStateError):
    """A state file's project_id disagrees with the project being projected.

    #228 freezes this as a HARD ABORT, and it raises rather than returning
    findings the way context_graph.apply does for its soft aborts: a
    mismatch means a notes-home directory was copied, so the judgments log
    is full of another project's identities. A caller that ignored a return
    value would happily reuse them."""

    def __init__(self, found, expected, source):
        super().__init__([_finding(
            "E_ARCH_PROJECT_ID_MISMATCH",
            "%s carries project_id %r but this project is %r"
            % (source, found, expected),
            field="project_id")])
        self.found = found
        self.expected = expected
        self.source = source


class MalformedNotePathError(ValueError):
    """Raised for any note path outside the frozen tree. `.note_path` and
    `.reason` carry structured detail, mirroring
    architecture.ids.MalformedArchIdError."""

    def __init__(self, note_path, reason):
        super().__init__("malformed note path %r: %s" % (note_path, reason))
        self.note_path = note_path
        self.reason = reason


def architecture_dir(notes_home, project_slug):
    return os.path.join(project_dir(notes_home, project_slug), ARCHITECTURE_SUBDIR)


def config_path(notes_home, project_slug):
    return os.path.join(architecture_dir(notes_home, project_slug), CONFIG_FILENAME)


def judgments_path(notes_home, project_slug):
    return os.path.join(
        architecture_dir(notes_home, project_slug), JUDGMENTS_FILENAME)


def index_path(notes_home, project_slug):
    return os.path.join(architecture_dir(notes_home, project_slug), INDEX_FILENAME)


def apply_state_path(notes_home, project_slug):
    return os.path.join(
        architecture_dir(notes_home, project_slug), APPLY_STATE_FILENAME)


def observations_path(notes_home, project_slug):
    return os.path.join(
        architecture_dir(notes_home, project_slug), OBSERVATIONS_FILENAME)


def format_note_path(projection_type, slug):
    """Build a note path from the projection type and the CREATION-EVENT
    slug. Raises ValueError for an unknown projection type or a slug that
    is not kebab-case."""
    if projection_type == "arch_codebase_map":
        return CODEBASE_MAP_FILENAME
    subtree = _SUBTREE_FOR_PROJECTION_TYPE.get(projection_type)
    if subtree is None:
        raise ValueError("unknown projection_type %r" % (projection_type,))
    if not isinstance(slug, str) or not _NOTE_SLUG_RE.match(slug):
        raise ValueError("slug must be kebab-case: %r" % (slug,))
    return "%s/%s.md" % (subtree, slug)


def parse_note_path(note_path):
    """Parse a vault-relative note path into its subtree, slug, and the
    projection type that owns it. Raises MalformedNotePathError for
    anything outside the frozen tree — including a path that escapes it.

    The path derives from the creation-event slug and is never recomputed
    from a node's current name, so a rename leaves it untouched."""
    if not isinstance(note_path, str) or note_path == "":
        raise MalformedNotePathError(note_path, "not a non-empty string")
    if note_path != note_path.strip():
        raise MalformedNotePathError(note_path, "has leading or trailing whitespace")
    if "\\" in note_path:
        raise MalformedNotePathError(note_path, "uses a backslash separator")
    if note_path.startswith("/") or os.path.isabs(note_path):
        raise MalformedNotePathError(note_path, "is absolute")
    parts = note_path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise MalformedNotePathError(note_path, "escapes the architecture note tree")

    if len(parts) == 1:
        if parts[0] != CODEBASE_MAP_FILENAME:
            raise MalformedNotePathError(
                note_path, "the only note at the tree root is %r"
                % (CODEBASE_MAP_FILENAME,))
        return {"projection_type": "arch_codebase_map",
                "subtree": None,
                "slug": None,
                "note_path": note_path}

    if len(parts) != 2:
        raise MalformedNotePathError(note_path, "is nested below its subtree")
    subtree, filename = parts
    if subtree not in NOTE_SUBTREES:
        raise MalformedNotePathError(
            note_path, "%r is not one of the frozen subtrees" % (subtree,))
    if not filename.endswith(".md"):
        raise MalformedNotePathError(note_path, "is not a .md note")
    slug = filename[: -len(".md")]
    if not _NOTE_SLUG_RE.match(slug):
        raise MalformedNotePathError(note_path, "slug %r is not kebab-case" % (slug,))
    return {"projection_type": _PROJECTION_TYPE_FOR_SUBTREE.get(subtree),
            "subtree": subtree,
            "slug": slug,
            "note_path": note_path}


def is_note_path(note_path):
    """True when note_path lies inside the frozen tree. Never raises."""
    try:
        parse_note_path(note_path)
    except MalformedNotePathError:
        return False
    return True


def require_project_id(document, project_id, source):
    """Assert that a loaded state document belongs to this project. Returns
    None on agreement and raises ProjectIdMismatchError otherwise — a
    missing project_id is a mismatch, not a default."""
    found = document.get("project_id") if isinstance(document, dict) else None
    if found != project_id:
        raise ProjectIdMismatchError(found, project_id, source)
    return None


def _check_required(document, required, code, findings):
    for field in required:
        if field not in document:
            findings.append(_finding(
                code, "missing required field %r" % (field,), field=field))


def _check_unknown(document, known, code, findings, index=None):
    for field in sorted(set(document) - known):
        findings.append(_finding(
            code, "unknown field %r" % (field,), field=field, index=index))


def _check_enum(value, allowed, label, code, findings, index=None):
    if value not in allowed:
        findings.append(_finding(
            code, "%s must be one of %s, got %r" % (label, list(allowed), value),
            field=label, index=index))


def validate_config(document):
    """Structural findings for config.json. Returns a list — empty when the
    document conforms. Never raises for a malformed document; a caller that
    must not proceed raises on the findings itself."""
    findings = []
    if not isinstance(document, dict):
        return [_finding("E_ARCH_CONFIG_NOT_AN_OBJECT",
                         "config.json must be a JSON object")]
    _check_required(document, _CONFIG_REQUIRED,
                    "E_ARCH_CONFIG_MISSING_FIELD", findings)
    _check_unknown(document, _CONFIG_KNOWN,
                   "E_ARCH_CONFIG_UNKNOWN_FIELD", findings)

    if "schema_version" in document and document["schema_version"] != SCHEMA_VERSION:
        findings.append(_finding(
            "E_ARCH_CONFIG_BAD_SCHEMA_VERSION",
            "schema_version must be %d, got %r"
            % (SCHEMA_VERSION, document["schema_version"]),
            field="schema_version"))

    project_id = document.get("project_id")
    if "project_id" in document and (
            not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id)):
        findings.append(_finding(
            "E_ARCH_CONFIG_MALFORMED_PROJECT_ID",
            "project_id must be project:<32-lowercase-hex>, got %r" % (project_id,),
            field="project_id"))

    slug = document.get("project_slug")
    if "project_slug" in document and (
            not isinstance(slug, str) or not SLUG_RE.match(slug)):
        findings.append(_finding(
            "E_ARCH_CONFIG_MALFORMED_PROJECT_SLUG",
            "project_slug must be kebab-case, got %r" % (slug,),
            field="project_slug"))

    findings.extend(_config_binding_findings(document))
    findings.extend(_config_caps_findings(document))
    findings.extend(_config_threshold_findings(document))

    limit = document.get("diff_size_confirmation_limit")
    if "diff_size_confirmation_limit" in document and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        findings.append(_finding(
            "E_ARCH_CONFIG_BAD_DIFF_LIMIT",
            "diff_size_confirmation_limit must be a non-negative integer, got %r"
            % (limit,), field="diff_size_confirmation_limit"))

    exclusions = document.get("exclusions")
    if exclusions is not None and (
            not isinstance(exclusions, list)
            or not all(isinstance(e, str) for e in exclusions)):
        findings.append(_finding(
            "E_ARCH_CONFIG_BAD_EXCLUSIONS",
            "exclusions must be a list of strings, got %r" % (exclusions,),
            field="exclusions"))
    return findings


def _config_binding_findings(document):
    findings = []
    bindings = document.get("bindings")
    if bindings is None:
        return findings
    if not isinstance(bindings, list):
        return [_finding("E_ARCH_CONFIG_BAD_BINDINGS",
                         "bindings must be a list, got %r" % (bindings,),
                         field="bindings")]
    seen_ids = set()
    seen_aliases = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            findings.append(_finding(
                "E_ARCH_CONFIG_BAD_BINDINGS",
                "binding must be an object, got %r" % (binding,), index=index))
            continue
        _check_unknown(binding, _BINDING_KNOWN,
                       "E_ARCH_CONFIG_UNKNOWN_FIELD", findings, index=index)
        binding_id = binding.get("binding_id")
        if not isinstance(binding_id, str) or not BINDING_ID_RE.match(binding_id):
            findings.append(_finding(
                "E_ARCH_CONFIG_MALFORMED_BINDING_ID",
                "binding_id must be repository-binding:<32-lowercase-hex>, got %r"
                % (binding_id,), field="binding_id", index=index))
        elif binding_id in seen_ids:
            findings.append(_finding(
                "E_ARCH_CONFIG_DUPLICATE_BINDING",
                "binding_id %r appears more than once" % (binding_id,),
                field="binding_id", index=index))
        else:
            seen_ids.add(binding_id)
        alias = binding.get("alias")
        if alias in seen_aliases:
            findings.append(_finding(
                "E_ARCH_CONFIG_DUPLICATE_BINDING",
                "alias %r appears more than once" % (alias,),
                field="alias", index=index))
        else:
            seen_aliases.add(alias)
    return findings


def _config_caps_findings(document):
    findings = []
    caps = document.get("caps")
    if caps is None:
        return findings
    if not isinstance(caps, dict):
        return [_finding("E_ARCH_CONFIG_BAD_CAPS",
                         "caps must be an object, got %r" % (caps,), field="caps")]
    _check_unknown(caps, frozenset(["max_nodes", "over_cap_behavior"]),
                   "E_ARCH_CONFIG_UNKNOWN_FIELD", findings)
    max_nodes = caps.get("max_nodes")
    if not isinstance(max_nodes, int) or isinstance(max_nodes, bool) or max_nodes < 1:
        findings.append(_finding(
            "E_ARCH_CONFIG_BAD_CAPS",
            "caps.max_nodes must be a positive integer, got %r" % (max_nodes,),
            field="max_nodes"))
    # Silent enforcement and silent non-enforcement are BOTH forbidden: a
    # lowered cap binds new creation only, and existing over-cap nodes are
    # reported for an explicit operator decision, never retro-staled.
    _check_enum(caps.get("over_cap_behavior"), OVER_CAP_BEHAVIORS,
                "caps.over_cap_behavior", "E_ARCH_CONFIG_BAD_OVER_CAP_BEHAVIOR",
                findings)
    return findings


def _config_threshold_findings(document):
    thresholds = document.get("thresholds")
    if thresholds is None:
        return []
    if not isinstance(thresholds, dict):
        return [_finding("E_ARCH_CONFIG_BAD_THRESHOLDS",
                         "thresholds must be an object, got %r" % (thresholds,),
                         field="thresholds")]
    findings = []
    _check_unknown(thresholds, frozenset(["high", "low"]),
                   "E_ARCH_CONFIG_UNKNOWN_FIELD", findings)
    values = {}
    for key in ("high", "low"):
        value = thresholds.get(key)
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not 0.0 <= value <= 1.0):
            findings.append(_finding(
                "E_ARCH_CONFIG_BAD_THRESHOLDS",
                "thresholds.%s must be a number in [0, 1], got %r" % (key, value),
                field=key))
        else:
            values[key] = value
    if len(values) == 2 and values["low"] >= values["high"]:
        findings.append(_finding(
            "E_ARCH_CONFIG_BAD_THRESHOLDS",
            "thresholds.low (%r) must be below thresholds.high (%r)"
            % (values["low"], values["high"]), field="thresholds"))
    return findings


def validate_index(document):
    """Structural findings for index.json, including the frozen provenance
    enums. Returns a list — empty when the document conforms."""
    findings = []
    if not isinstance(document, dict):
        return [_finding("E_ARCH_INDEX_NOT_AN_OBJECT",
                         "index.json must be a JSON object")]
    _check_required(document, _INDEX_REQUIRED,
                    "E_ARCH_INDEX_MISSING_FIELD", findings)
    _check_unknown(document, _INDEX_KNOWN,
                   "E_ARCH_INDEX_UNKNOWN_FIELD", findings)
    if "schema_version" in document and document["schema_version"] != SCHEMA_VERSION:
        findings.append(_finding(
            "E_ARCH_INDEX_BAD_SCHEMA_VERSION",
            "schema_version must be %d, got %r"
            % (SCHEMA_VERSION, document["schema_version"]),
            field="schema_version"))

    project_id = document.get("project_id")
    nodes = document.get("nodes")
    if nodes is not None and not isinstance(nodes, list):
        findings.append(_finding("E_ARCH_INDEX_BAD_NODES",
                                 "nodes must be a list, got %r" % (nodes,),
                                 field="nodes"))
        nodes = None
    seen_ids = set()
    for index, node in enumerate(nodes or []):
        findings.extend(_index_node_findings(node, project_id, index, seen_ids))
    findings.extend(_index_reference_findings(document, seen_ids))
    return findings


def _index_node_findings(node, project_id, index, seen_ids):
    if not isinstance(node, dict):
        return [_finding("E_ARCH_INDEX_BAD_NODES",
                         "node must be an object, got %r" % (node,), index=index)]
    findings = []
    _check_required(node, _NODE_REQUIRED, "E_ARCH_INDEX_MISSING_FIELD", findings)
    _check_unknown(node, _NODE_KNOWN, "E_ARCH_INDEX_UNKNOWN_FIELD",
                   findings, index=index)

    arch_id = node.get("arch_id")
    if not is_arch_node_id(arch_id):
        findings.append(_finding(
            "E_ARCH_INDEX_MALFORMED_ARCH_ID",
            "arch_id must be arch-node:<project-id>:<32-lowercase-hex>, got %r"
            % (arch_id,), field="arch_id", index=index))
    else:
        if parse_arch_node_id(arch_id)["project_id"] != project_id:
            findings.append(_finding(
                "E_ARCH_INDEX_FOREIGN_PROJECT_ID",
                "arch_id %r embeds a project_id other than the index's %r"
                % (arch_id, project_id), field="arch_id", index=index))
        if arch_id in seen_ids:
            findings.append(_finding(
                "E_ARCH_INDEX_DUPLICATE_NODE",
                "arch_id %r appears more than once" % (arch_id,),
                field="arch_id", index=index))
        seen_ids.add(arch_id)

    if "note_path" in node and not is_note_path(node.get("note_path")):
        findings.append(_finding(
            "E_ARCH_INDEX_MALFORMED_NOTE_PATH",
            "note_path %r is outside the frozen architecture note tree"
            % (node.get("note_path"),), field="note_path", index=index))

    for field, allowed in (("projection_type", PROJECTION_TYPES),
                           ("confidence", CONFIDENCE_VALUES),
                           ("projection_status", PROJECTION_STATUS_VALUES)):
        if field in node:
            _check_enum(node[field], allowed, field, "E_ARCH_INDEX_BAD_ENUM",
                        findings, index=index)

    for field, key, allowed in (
            ("per_binding_status", "status", PER_BINDING_STATUS_VALUES),
            ("per_binding_coverage", "coverage", PER_BINDING_COVERAGE_VALUES)):
        for entry in node.get(field) or []:
            if not isinstance(entry, dict):
                findings.append(_finding(
                    "E_ARCH_INDEX_BAD_ENUM",
                    "%s entry must be an object, got %r" % (field, entry),
                    field=field, index=index))
                continue
            _check_enum(entry.get(key), allowed, "%s.%s" % (field, key),
                        "E_ARCH_INDEX_BAD_ENUM", findings, index=index)

    # The orphan flag is a claim about a note's bytes, so it is boolean and
    # it binds to `partial`. A node reading `current` while carrying the
    # flag would tell a reader the projection stands behind bytes the
    # re-plan just disowned.
    if "orphaned_by_resume" in node:
        if not isinstance(node["orphaned_by_resume"], bool):
            findings.append(_finding(
                "E_ARCH_INDEX_BAD_ORPHAN_FLAG",
                "orphaned_by_resume must be a boolean, got %r"
                % (node["orphaned_by_resume"],),
                field="orphaned_by_resume", index=index))
        elif (node["orphaned_by_resume"]
                and node.get("projection_status") != "partial"):
            findings.append(_finding(
                "E_ARCH_INDEX_ORPHAN_WITHOUT_PARTIAL",
                "orphaned_by_resume requires projection_status 'partial', "
                "got %r" % (node.get("projection_status"),),
                field="orphaned_by_resume", index=index))

    # superseded is defined as "replaced by a confirmed split or merge, and
    # superseded_by[] names the successor(s)" -- without one the lineage is
    # unrecoverable, which is why split records both directions.
    if node.get("projection_status") == "superseded" and not node.get(
            "superseded_by"):
        findings.append(_finding(
            "E_ARCH_INDEX_SUPERSEDED_WITHOUT_SUCCESSOR",
            "projection_status 'superseded' requires a non-empty superseded_by",
            field="superseded_by", index=index))
    return findings


def _index_reference_findings(document, seen_ids):
    references = document.get("references")
    if references is None:
        return []
    if not isinstance(references, list):
        return [_finding("E_ARCH_INDEX_BAD_REFERENCES",
                         "references must be a list, got %r" % (references,),
                         field="references")]
    findings = []
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            findings.append(_finding(
                "E_ARCH_INDEX_BAD_REFERENCES",
                "reference must be an object, got %r" % (reference,), index=index))
            continue
        # A reference records "this note cites <context identity>". It is
        # not an edge in the #140 graph, so it carries no relationship
        # vocabulary -- any extra field is rejected rather than ignored.
        _check_unknown(reference, _REFERENCE_KNOWN,
                       "E_ARCH_INDEX_UNKNOWN_FIELD", findings, index=index)
        arch_id = reference.get("arch_id")
        if arch_id not in seen_ids:
            findings.append(_finding(
                "E_ARCH_INDEX_UNKNOWN_REFERENCE_SOURCE",
                "reference arch_id %r is not a node in this index" % (arch_id,),
                field="arch_id", index=index))
        context_id = reference.get("context_id")
        if not isinstance(context_id, str) or not CONTEXT_NODE_ID_RE.match(
                context_id):
            findings.append(_finding(
                "E_ARCH_INDEX_MALFORMED_REFERENCE",
                "context_id must be a context-node identity, got %r" % (context_id,),
                field="context_id", index=index))
    return findings


def validate_judgment(record):
    """Structural findings for one judgments.jsonl record, including its
    envelope. Returns a list — empty when the record conforms.

    A record that fails here is not merely unusual: judgments.jsonl is the
    sole authority for meaning, so a caller reading the log decides between
    truncate-and-report (a torn TRAILING line) and a hard abort (corruption
    anywhere else) on top of these findings."""
    findings = []
    if not isinstance(record, dict):
        return [_finding("E_ARCH_JUDGMENT_NOT_AN_OBJECT",
                         "a judgment record must be a JSON object")]
    _check_required(record, _JUDGMENT_REQUIRED,
                    "E_ARCH_JUDGMENT_MISSING_FIELD", findings)
    _check_unknown(record, _JUDGMENT_KNOWN,
                   "E_ARCH_JUDGMENT_UNKNOWN_FIELD", findings)
    if "schema_version" in record and record["schema_version"] != SCHEMA_VERSION:
        findings.append(_finding(
            "E_ARCH_JUDGMENT_BAD_SCHEMA_VERSION",
            "schema_version must be %d, got %r"
            % (SCHEMA_VERSION, record["schema_version"]),
            field="schema_version"))
    if "kind" in record:
        _check_enum(record["kind"], JUDGMENT_KINDS, "kind",
                    "E_ARCH_JUDGMENT_BAD_KIND", findings)

    project_id = record.get("project_id")
    if "project_id" in record and (
            not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id)):
        findings.append(_finding(
            "E_ARCH_JUDGMENT_MALFORMED_PROJECT_ID",
            "project_id must be project:<32-lowercase-hex>, got %r" % (project_id,),
            field="project_id"))

    # Identity allocation is the one atomic append that PRECEDES any
    # manifest or file write, so it must name what it allocates.
    if record.get("kind") == "identity_allocation" and "arch_id" not in record:
        findings.append(_finding(
            "E_ARCH_JUDGMENT_MISSING_ARCH_ID",
            "an identity_allocation record must carry the arch_id it allocates",
            field="arch_id"))
    if "arch_id" in record:
        if not is_arch_node_id(record["arch_id"]):
            findings.append(_finding(
                "E_ARCH_JUDGMENT_MALFORMED_ARCH_ID",
                "arch_id must be arch-node:<project-id>:<32-lowercase-hex>, got %r"
                % (record["arch_id"],), field="arch_id"))
        elif parse_arch_node_id(record["arch_id"])["project_id"] != project_id:
            findings.append(_finding(
                "E_ARCH_JUDGMENT_FOREIGN_PROJECT_ID",
                "arch_id %r embeds a project_id other than the record's %r"
                % (record["arch_id"], project_id), field="arch_id"))

    findings.extend(_judgment_envelope_findings(record))
    return findings


def _judgment_envelope_findings(record):
    findings = []
    record_id = record.get("record_id")
    if "record_id" in record and (
            not isinstance(record_id, str)
            or not _RECORD_ID_RE.match(record_id)):
        findings.append(_finding(
            "E_ARCH_JUDGMENT_MALFORMED_RECORD_ID",
            "record_id must be arch-judgment:sha256:<64-lowercase-hex>, got %r"
            % (record_id,), field="record_id"))
    checksum = record.get("checksum")
    if "checksum" in record and (
            not isinstance(checksum, str) or not _HASH_RE.match(checksum)):
        findings.append(_finding(
            "E_ARCH_JUDGMENT_MALFORMED_CHECKSUM",
            "checksum must be sha256:<64-lowercase-hex>, got %r" % (checksum,),
            field="checksum"))
    if findings:
        return findings
    if "checksum" in record and not verify_checksum(record):
        findings.append(_finding(
            "E_ARCH_JUDGMENT_CHECKSUM_MISMATCH",
            "checksum %r does not match the record's content" % (checksum,),
            field="checksum"))
    elif "record_id" in record and record_id != judgment_record_id(record):
        findings.append(_finding(
            "E_ARCH_JUDGMENT_RECORD_ID_MISMATCH",
            "record_id %r does not match the record's content" % (record_id,),
            field="record_id"))
    return findings


def validate_apply_state(document):
    """Structural findings for apply-state.json. Returns a list — empty when
    the document conforms.

    The manifest is recovery metadata ONLY: it records what was to be
    written, in what order, with before and after hashes, and nothing about
    what any of it means. Cross-file atomicity is not claimed — atomicity is
    per file, and cross-file integrity comes from this manifest plus resume."""
    findings = []
    if not isinstance(document, dict):
        return [_finding("E_ARCH_APPLY_STATE_NOT_AN_OBJECT",
                         "apply-state.json must be a JSON object")]
    _check_required(document, _APPLY_REQUIRED,
                    "E_ARCH_APPLY_STATE_MISSING_FIELD", findings)
    _check_unknown(document, _APPLY_KNOWN,
                   "E_ARCH_APPLY_STATE_UNKNOWN_FIELD", findings)
    if "schema_version" in document and document["schema_version"] != SCHEMA_VERSION:
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_BAD_SCHEMA_VERSION",
            "schema_version must be %d, got %r"
            % (SCHEMA_VERSION, document["schema_version"]),
            field="schema_version"))
    if "status" in document:
        _check_enum(document["status"], APPLY_STATUS_VALUES, "status",
                    "E_ARCH_APPLY_STATE_BAD_ENUM", findings)

    writes = document.get("writes")
    if writes is None:
        return findings
    if not isinstance(writes, list):
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_BAD_WRITES",
            "writes must be a list, got %r" % (writes,), field="writes"))
        return findings
    # An empty changed-set writes zero bytes and creates NO apply-state at
    # all, so a manifest with no writes can only be corruption.
    if not writes:
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_EMPTY",
            "apply-state.json exists but plans no writes", field="writes"))
    seen_paths = set()
    for index, write in enumerate(writes):
        findings.extend(_apply_write_findings(write, index, seen_paths))
    return findings


def _apply_write_findings(write, index, seen_paths):
    if not isinstance(write, dict):
        return [_finding("E_ARCH_APPLY_STATE_BAD_WRITES",
                         "write must be an object, got %r" % (write,), index=index)]
    findings = []
    _check_required(write, ("order", "path", "after_hash", "state"),
                    "E_ARCH_APPLY_STATE_MISSING_FIELD", findings)
    _check_unknown(write, _APPLY_WRITE_KNOWN,
                   "E_ARCH_APPLY_STATE_UNKNOWN_FIELD", findings, index=index)

    # Deterministic write ordering is what makes an interrupted apply
    # reconcilable: a gap or a repeat makes "advance after each write"
    # ambiguous, so order must be dense and ascending from zero.
    if write.get("order") != index:
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_BAD_ORDER",
            "write order must be dense and ascending from 0; expected %d, got %r"
            % (index, write.get("order")), field="order", index=index))

    path = write.get("path")
    if not isinstance(path, str) or not path:
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_BAD_PATH",
            "path must be a non-empty relative path, got %r" % (path,),
            field="path", index=index))
    elif path.startswith("/") or ".." in path.split("/"):
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_BAD_PATH",
            "path %r escapes the project's notes tree" % (path,),
            field="path", index=index))
    elif path in seen_paths:
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_DUPLICATE_PATH",
            "path %r is written more than once in one apply" % (path,),
            field="path", index=index))
    else:
        seen_paths.add(path)

    # before_hash is null for a file that does not exist yet.
    before = write.get("before_hash")
    if before is not None and (
            not isinstance(before, str) or not _HASH_RE.match(before)):
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_MALFORMED_HASH",
            "before_hash must be sha256:<64-lowercase-hex> or null, got %r"
            % (before,), field="before_hash", index=index))
    after = write.get("after_hash")
    if "after_hash" in write and (
            not isinstance(after, str) or not _HASH_RE.match(after)):
        findings.append(_finding(
            "E_ARCH_APPLY_STATE_MALFORMED_HASH",
            "after_hash must be sha256:<64-lowercase-hex>, got %r" % (after,),
            field="after_hash", index=index))

    if "state" in write:
        _check_enum(write["state"], APPLY_WRITE_STATES, "state",
                    "E_ARCH_APPLY_STATE_BAD_ENUM", findings, index=index)
    return findings
