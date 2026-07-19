"""structural_graph.validation -- hand-rolled structural validation (#227).

Returns finding lists and never raises, matching context_graph.validation.
Findings are {"code", "message", "index", "field"} dicts and never carry the
offending value: a finding that echoed a provider string back would be the
exact leak structural_graph.redaction exists to close.

Scope is shape and vocabulary membership. Coverage tiling lives in
structural_graph.coverage; binding membership, freshness, and redaction live
in structural_graph.document. Finding order is deterministic: checks run in
registration order, and within a check, by object index.
"""

import re

from structural_graph import schema

FINDING_CODES = (
    "E_SG_MISSING_SCHEMA_VERSION",
    "E_SG_UNSUPPORTED_SCHEMA_VERSION",
    "E_SG_MISSING_FIELD",
    "E_SG_UNKNOWN_FIELD",
    "E_SG_MALFORMED_BINDING_ID",
    "E_SG_MALFORMED_COMMIT",
    "E_SG_MALFORMED_FIELD_SHAPE",
    "E_SG_UNKNOWN_SYMBOL_KIND",
    "E_SG_UNKNOWN_EDGE_TYPE",
    "E_SG_UNKNOWN_CAPABILITY",
    "E_SG_UNKNOWN_COVERAGE_STATUS",
    "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
    "E_SG_DUPLICATE_SYMBOL_ID",
    "E_SG_DANGLING_EDGE_ENDPOINT",
    "E_SG_COVERAGE_GAP",
    "E_SG_COVERAGE_OVERLAP",
    "E_SG_UNNORMALIZABLE_ANCHOR",
    "E_SG_BINDING_NOT_CONFIGURED",
)

_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "binding_id",
    "source_commit",
    "provider",
    "capabilities",
    "root",
    "coverage",
    "files",
    "symbols",
    "edges",
)

_KNOWN_TOP_LEVEL = _REQUIRED_TOP_LEVEL + ("optional_provider_observations", "diagnostics")

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def finding(code, message, index, field):
    """Build a house-shaped finding. Never accepts or stores a value."""
    return {"code": code, "message": message, "index": index, "field": field}


# The whole rest of this module is one rule, applied ~ten times: some value
# must be a string, or some value must be a list, and if it isn't, that's an
# E_SG_MALFORMED_FIELD_SHAPE finding whose message never repeats the type
# name twice (once for the check, once for the wording). `_check_string` and
# `_check_list` are that rule in code: each appends the one finding to `out`
# and reports back whether the value was safe to use, so a call site that
# needs to skip further work on a malformed value can do
# `if not _check_string(...): continue`, and one that doesn't need to skip
# can just call it and move on. `description` is prose ("coverage
# path_prefix"); `field` is the finding's machine-readable field path
# ("coverage[].path_prefix") -- the two differ often enough (list elements,
# loop variables) that collapsing them into one parameter would corrupt one
# or the other at half the call sites.
def _shape_finding(description, shape, index, field):
    return finding(
        "E_SG_MALFORMED_FIELD_SHAPE", description + " is not a " + shape, index, field
    )


def _check_string(out, value, description, index, field):
    """Append a finding and return False unless value is a string."""
    if isinstance(value, str):
        return True
    out.append(_shape_finding(description, "string", index, field))
    return False


def _check_list(out, value, description, index, field):
    """Append a finding and return False unless value is a list."""
    if isinstance(value, list):
        return True
    out.append(_shape_finding(description, "list", index, field))
    return False


def version_findings(doc):
    """Return version-gate findings only. Public on purpose.

    structural_graph.document needs this standalone: the version gate must
    short-circuit before full validation runs, because a document from an
    unknown schema version cannot be meaningfully checked against v1 rules.
    validate_document calls it too, so the rule lives in exactly one place.
    """
    out = []
    if "schema_version" not in doc:
        out.append(
            finding(
                "E_SG_MISSING_SCHEMA_VERSION",
                "document has no schema_version",
                None,
                "schema_version",
            )
        )
    elif doc["schema_version"] not in schema.SUPPORTED_SCHEMA_VERSIONS:
        out.append(
            finding(
                "E_SG_UNSUPPORTED_SCHEMA_VERSION",
                "schema_version is outside the supported set",
                None,
                "schema_version",
            )
        )
    return out


def _shape_findings(doc):
    out = []
    for field in _REQUIRED_TOP_LEVEL:
        if field == "schema_version":
            continue
        if field not in doc:
            out.append(
                finding("E_SG_MISSING_FIELD", "required field is absent", None, field)
            )
    for field in sorted(doc):
        if field not in _KNOWN_TOP_LEVEL:
            out.append(
                finding("E_SG_UNKNOWN_FIELD", "unrecognized top-level field", None, field)
            )
    commit = doc.get("source_commit")
    if commit is not None and not (
        isinstance(commit, str) and _COMMIT_RE.match(commit)
    ):
        out.append(
            finding(
                "E_SG_MALFORMED_COMMIT",
                "source_commit is not a 40-character lowercase hex sha",
                None,
                "source_commit",
            )
        )
    # root is required above; this is its type check, and it tests
    # isinstance rather than truthiness on purpose. root == "" is the legal
    # "whole repository" value and must produce no finding, while every
    # other falsy root (0, False, [], {}, None) is malformed. A truthiness
    # test would collapse the two, and downstream code that then coerced
    # with `or ""` would hand a malformed value to the
    # E_SG_UNNORMALIZABLE_ANCHOR guard disguised as the legal one.
    if "root" in doc:
        _check_string(out, doc["root"], "root", None, "root")
    # The JSON Schema constrains provider to an object with required string
    # name and version. These checks mirror it, so the native validator
    # never accepts a provider the schema would reject.
    if "provider" in doc:
        provider = doc["provider"]
        if not isinstance(provider, dict):
            out.append(
                finding(
                    "E_SG_MALFORMED_FIELD_SHAPE",
                    "provider is not an object",
                    None,
                    "provider",
                )
            )
        else:
            _check_string(out, provider.get("name"), "provider.name", None, "provider.name")
            _check_string(
                out, provider.get("version"), "provider.version", None, "provider.version"
            )
    return out


# Container fields whose elements must be objects. "capabilities" is
# deliberately excluded: its elements are plain strings, not dicts.
_DICT_ELEMENT_FIELDS = ("coverage", "files", "symbols", "edges")


def _field_shape_findings(doc):
    """Verify every container field is a list with well-shaped elements.

    A malformed document is exactly the case this module exists to report
    on, so this runs before any check that calls .get() on an element:
    doc.get(field) or [] silently iterates whatever the field actually is
    (a string yields its characters; an int isn't iterable at all), and an
    unconditional item.get(...) then raises AttributeError on any element
    that isn't a dict. Both are caller-visible crashes this function exists
    to prevent.

    Returns (findings, valid): findings is the E_SG_MALFORMED_FIELD_SHAPE
    list; valid maps each container field name to the (index, item) pairs
    safe for further inspection. A malformed field or element is reported
    and dropped from valid, but never suppresses the checks run on any
    other field or element -- every field is checked independently.
    """
    out = []
    valid = {}

    capabilities = doc.get("capabilities")
    if capabilities is None:
        valid["capabilities"] = []
    elif not _check_list(out, capabilities, "capabilities", None, "capabilities"):
        valid["capabilities"] = []
    else:
        items = []
        for index, item in enumerate(capabilities):
            if _check_string(out, item, "capabilities element", index, "capabilities[]"):
                items.append((index, item))
        valid["capabilities"] = items

    for field in _DICT_ELEMENT_FIELDS:
        value = doc.get(field)
        if value is None:
            valid[field] = []
            continue
        if not _check_list(out, value, field, None, field):
            valid[field] = []
            continue
        items = []
        for index, item in enumerate(value):
            if isinstance(item, dict):
                items.append((index, item))
            else:
                out.append(
                    finding(
                        "E_SG_MALFORMED_FIELD_SHAPE",
                        field + " element is not an object",
                        index,
                        field + "[]",
                    )
                )
        valid[field] = items

    return out, valid


def _vocabulary_findings(valid):
    out = []
    for index, capability in valid["capabilities"]:
        if capability not in schema.CAPABILITIES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_CAPABILITY",
                    "capability is not in the normalized vocabulary",
                    index,
                    "capabilities[]",
                )
            )
    for index, symbol in valid["symbols"]:
        if symbol.get("kind") not in schema.SYMBOL_KINDS:
            out.append(
                finding(
                    "E_SG_UNKNOWN_SYMBOL_KIND",
                    "symbol kind is not in the normalized vocabulary",
                    index,
                    "symbols[].kind",
                )
            )
        # name is an anchor field (schema.ANCHOR_FIELDS): document.py feeds
        # it to redaction.redact, which silently no-ops on a non-string
        # value instead of matching a secret pattern. Without this guard a
        # secret hidden in a list-shaped name produces no
        # E_SG_UNNORMALIZABLE_ANCHOR and the document loads instead of
        # failing closed. Absence and mistyping are separate findings: an
        # absent name is a missing required field, not a shape error.
        name = symbol.get("name")
        if name is None:
            out.append(
                finding(
                    "E_SG_MISSING_FIELD",
                    "symbol has no name",
                    index,
                    "symbols[].name",
                )
            )
        else:
            _check_string(out, name, "symbol name", index, "symbols[].name")
    for index, edge in valid["edges"]:
        if edge.get("type") not in schema.EDGE_TYPES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_EDGE_TYPE",
                    "edge type is not in the normalized vocabulary",
                    index,
                    "edges[].type",
                )
            )
    declared = set(capability for _, capability in valid["capabilities"])
    for index, entry in valid["coverage"]:
        if entry.get("status") not in schema.COVERAGE_STATUSES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_COVERAGE_STATUS",
                    "coverage status is not in the normalized vocabulary",
                    index,
                    "coverage[].status",
                )
            )
        # A non-string path_prefix isn't tested against a set here -- this
        # module never resolves prefixes -- but structural_graph.coverage
        # concatenates it onto strings and calls .startswith() on it, both
        # of which raise TypeError/AttributeError on a non-string. Report
        # the shape problem here so it never reaches that module unguarded.
        path_prefix = entry.get("path_prefix")
        _check_string(
            out, path_prefix, "coverage path_prefix", index, "coverage[].path_prefix"
        )
        capability = entry.get("capability")
        # A capability that isn't a string can't be tested against `declared`
        # (a set): membership on a list/dict operand raises TypeError before
        # any comparison happens. Report the shape problem and skip the
        # membership check rather than let it crash.
        is_string = _check_string(
            out, capability, "coverage capability", index, "coverage[].capability"
        )
        if is_string:
            if capability not in declared:
                out.append(
                    finding(
                        "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
                        "coverage declares a capability the provider did not advertise",
                        index,
                        "coverage[].capability",
                    )
                )
    return out


def _referential_findings(valid):
    out = []
    ids = set()
    for index, symbol in valid["symbols"]:
        symbol_id = symbol.get("id")
        if symbol_id is None:
            # An id is required: structural_graph.graphset keys its merged
            # symbol table on symbols[].id, so a symbol without one has no
            # place in a fact view and must not reach it.
            #
            # A missing id is reported as its own problem and never compared
            # against `ids`: two symbols that both lack an id are not
            # duplicates of each other, and folding them into
            # E_SG_DUPLICATE_SYMBOL_ID would misreport which problem the
            # document actually has.
            out.append(
                finding(
                    "E_SG_MISSING_FIELD",
                    "symbol has no id",
                    index,
                    "symbols[].id",
                )
            )
            continue
        # A non-string id (list, dict, int, ...) can't be hashed into `ids`
        # or tested with `in` without risking TypeError. Report it and leave
        # it out of `ids` -- same treatment as a missing id, so an edge
        # pointing at it is correctly flagged dangling below.
        if not _check_string(out, symbol_id, "symbol id", index, "symbols[].id"):
            continue
        if symbol_id in ids:
            out.append(
                finding(
                    "E_SG_DUPLICATE_SYMBOL_ID",
                    "symbol id appears more than once",
                    index,
                    "symbols[].id",
                )
            )
        else:
            ids.add(symbol_id)
    for index, edge in valid["edges"]:
        for field in ("source", "target"):
            value = edge.get(field)
            # A non-string, non-None endpoint (list, dict, int, ...) can't be
            # tested with `in ids` without risking TypeError. `None` still
            # falls through to the dangling check below: a missing endpoint
            # legitimately names no symbol.
            if value is not None and not _check_string(
                out, value, "edge " + field, index, "edges[]." + field
            ):
                continue
            if value not in ids:
                out.append(
                    finding(
                        "E_SG_DANGLING_EDGE_ENDPOINT",
                        "edge endpoint names no symbol in this document",
                        index,
                        "edges[]." + field,
                    )
                )
    return out


def validate_document(doc):
    """Return findings for a parsed document. [] means structurally valid."""
    if not isinstance(doc, dict):
        return [
            finding(
                "E_SG_MISSING_FIELD", "document is not a JSON object", None, None
            )
        ]
    out = []
    out.extend(version_findings(doc))
    out.extend(_shape_findings(doc))
    field_shape_findings, valid = _field_shape_findings(doc)
    out.extend(field_shape_findings)
    out.extend(_vocabulary_findings(valid))
    out.extend(_referential_findings(valid))
    return out
