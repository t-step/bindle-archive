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
    return out


def _vocabulary_findings(doc):
    out = []
    for index, capability in enumerate(doc.get("capabilities") or []):
        if capability not in schema.CAPABILITIES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_CAPABILITY",
                    "capability is not in the normalized vocabulary",
                    index,
                    "capabilities[]",
                )
            )
    for index, symbol in enumerate(doc.get("symbols") or []):
        if symbol.get("kind") not in schema.SYMBOL_KINDS:
            out.append(
                finding(
                    "E_SG_UNKNOWN_SYMBOL_KIND",
                    "symbol kind is not in the normalized vocabulary",
                    index,
                    "symbols[].kind",
                )
            )
    for index, edge in enumerate(doc.get("edges") or []):
        if edge.get("type") not in schema.EDGE_TYPES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_EDGE_TYPE",
                    "edge type is not in the normalized vocabulary",
                    index,
                    "edges[].type",
                )
            )
    declared = set(doc.get("capabilities") or [])
    for index, entry in enumerate(doc.get("coverage") or []):
        if entry.get("status") not in schema.COVERAGE_STATUSES:
            out.append(
                finding(
                    "E_SG_UNKNOWN_COVERAGE_STATUS",
                    "coverage status is not in the normalized vocabulary",
                    index,
                    "coverage[].status",
                )
            )
        if entry.get("capability") not in declared:
            out.append(
                finding(
                    "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
                    "coverage declares a capability the provider did not advertise",
                    index,
                    "coverage[].capability",
                )
            )
    return out


def _referential_findings(doc):
    out = []
    seen = set()
    for index, symbol in enumerate(doc.get("symbols") or []):
        symbol_id = symbol.get("id")
        if symbol_id in seen:
            out.append(
                finding(
                    "E_SG_DUPLICATE_SYMBOL_ID",
                    "symbol id appears more than once",
                    index,
                    "symbols[].id",
                )
            )
        seen.add(symbol_id)
    for index, edge in enumerate(doc.get("edges") or []):
        for field in ("source", "target"):
            if edge.get(field) not in seen:
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
    out.extend(_vocabulary_findings(doc))
    out.extend(_referential_findings(doc))
    return out
