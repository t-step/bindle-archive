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
    "E_SG_FACT_OUTSIDE_ROOT",
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
    # A non-string root (0, False, [], {}, None) is falsy, and
    # document.py used to fold every falsy root into "" with
    # `doc.get("root") or ""` before checking it -- the coercion made a
    # malformed value indistinguishable from the legal empty-string root
    # ("whole repository") and the E_SG_UNNORMALIZABLE_ANCHOR guard never
    # fired. #227's review finding. root is already required above; this
    # is the type check, so it must be isinstance and never truthiness --
    # root == "" is legal and must keep producing no finding here.
    if "root" in doc and not isinstance(doc["root"], str):
        out.append(
            finding(
                "E_SG_MALFORMED_FIELD_SHAPE",
                "root is not a string",
                None,
                "root",
            )
        )
    # provider used to be checked for presence only: a string or list value
    # sailed straight through into facts["provider"] with status="loaded".
    # The JSON Schema constrains provider to an object with required string
    # name/version, so a silent native validator here would let the schema
    # reject documents the native validator accepts -- #227 Task 7 carried
    # finding (Task 5's review).
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
            if not isinstance(provider.get("name"), str):
                out.append(
                    finding(
                        "E_SG_MALFORMED_FIELD_SHAPE",
                        "provider.name is not a string",
                        None,
                        "provider.name",
                    )
                )
            if not isinstance(provider.get("version"), str):
                out.append(
                    finding(
                        "E_SG_MALFORMED_FIELD_SHAPE",
                        "provider.version is not a string",
                        None,
                        "provider.version",
                    )
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
    elif not isinstance(capabilities, list):
        out.append(
            finding(
                "E_SG_MALFORMED_FIELD_SHAPE",
                "capabilities is not a list",
                None,
                "capabilities",
            )
        )
        valid["capabilities"] = []
    else:
        items = []
        for index, item in enumerate(capabilities):
            if isinstance(item, str):
                items.append((index, item))
            else:
                out.append(
                    finding(
                        "E_SG_MALFORMED_FIELD_SHAPE",
                        "capabilities element is not a string",
                        index,
                        "capabilities[]",
                    )
                )
        valid["capabilities"] = items

    for field in _DICT_ELEMENT_FIELDS:
        value = doc.get(field)
        if value is None:
            valid[field] = []
            continue
        if not isinstance(value, list):
            out.append(
                finding(
                    "E_SG_MALFORMED_FIELD_SHAPE",
                    field + " is not a list",
                    None,
                    field,
                )
            )
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
        # failing closed -- #227's review finding. Missing (None) is left
        # alone, same treatment as symbol id above: there is no string to
        # mistype.
        name = symbol.get("name")
        if name is not None and not isinstance(name, str):
            out.append(
                finding(
                    "E_SG_MALFORMED_FIELD_SHAPE",
                    "symbol name is not a string",
                    index,
                    "symbols[].name",
                )
            )
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
        if not isinstance(path_prefix, str):
            out.append(
                finding(
                    "E_SG_MALFORMED_FIELD_SHAPE",
                    "coverage path_prefix is not a string",
                    index,
                    "coverage[].path_prefix",
                )
            )
        capability = entry.get("capability")
        # A capability that isn't a string can't be tested against `declared`
        # (a set): membership on a list/dict operand raises TypeError before
        # any comparison happens. Report the shape problem and skip the
        # membership check rather than let it crash.
        if not isinstance(capability, str):
            out.append(
                finding(
                    "E_SG_MALFORMED_FIELD_SHAPE",
                    "coverage capability is not a string",
                    index,
                    "coverage[].capability",
                )
            )
        elif capability not in declared:
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
            # A missing id is a distinct problem from a duplicated one and
            # must never be compared against `ids`: two symbols that both
            # lack an id are not duplicates of each other, and folding them
            # into E_SG_DUPLICATE_SYMBOL_ID would misreport which problem
            # the document actually has.
            continue
        if not isinstance(symbol_id, str):
            # A non-string id (list, dict, int, ...) can't be hashed into
            # `ids` or tested with `in` without risking TypeError. Report it
            # and leave it out of `ids` -- same treatment as a missing id, so
            # an edge pointing at it is correctly flagged dangling below.
            out.append(
                finding(
                    "E_SG_MALFORMED_FIELD_SHAPE",
                    "symbol id is not a string",
                    index,
                    "symbols[].id",
                )
            )
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
            if value is not None and not isinstance(value, str):
                out.append(
                    finding(
                        "E_SG_MALFORMED_FIELD_SHAPE",
                        "edge " + field + " is not a string",
                        index,
                        "edges[]." + field,
                    )
                )
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
