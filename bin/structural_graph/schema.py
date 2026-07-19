"""structural_graph.schema -- frozen vocabularies for the #227 interchange.

Owns the versioned value sets every other module in this package validates
against, plus the anchor-field registry that decides whether an
unnormalizable provider string fails a document closed or is redacted in
place (design spec, "Redaction").

Pure constants and pure membership lookup only: no filesystem access, no
network access, no validation beyond membership in a tuple. Cross-object
rules live in structural_graph.validation.

These tuples are mirrored into schemas/structural-graph/v1/document.schema.json
as JSON Schema "enum" values, the way context_graph.relationships mirrors
edge.schema.json. The mirror is asserted by the conformance tests; neither
copy may drift.
"""

SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = (1,)

# Normalized across providers. "other" is the mandatory escape: a provider
# that observes a construct with no normalized equivalent reports "other"
# rather than inventing a kind or dropping the symbol.
SYMBOL_KINDS = (
    "module",
    "class",
    "function",
    "method",
    "field",
    "constant",
    "type_alias",
    "interface",
    "other",
)

EDGE_TYPES = ("contains", "imports", "depends_on", "calls", "tests")

# Capability names are the unit coverage is declared against. A provider
# advertises the subset it supports; an unadvertised capability means the
# facts are unavailable, never observed-zero.
CAPABILITIES = (
    "contains",
    "imports",
    "depends_on",
    "calls",
    "tests",
    "has_export_visibility",
)

COVERAGE_STATUSES = ("observed", "unsupported", "partial_parse_failure")

DOCUMENT_STATUSES = (
    "loaded",
    "malformed",
    "unsupported_version",
    "deconfigured",
    "unavailable",
)

# Orthogonal to DOCUMENT_STATUSES: a stale document still loads.
FRESHNESS_STATES = ("current", "stale", "freshness_unknown")

# Dotted field paths whose values anchor a fact to the repository. An
# unnormalizable anchor makes the whole document malformed; every other
# string is redacted in place and its fact is kept.
ANCHOR_FIELDS = (
    "root",
    "files[].path",
    "symbols[].id",
    "symbols[].name",
    "symbols[].path",
    "edges[].source",
    "edges[].target",
    "coverage[].path_prefix",
)


def is_anchor(field_path):
    """True when field_path names an anchor field.

    Membership is exact against ANCHOR_FIELDS. Anything under
    optional_provider_observations is a provider conclusion, never an
    anchor, and is excluded by construction rather than by a prefix rule.
    """
    return field_path in ANCHOR_FIELDS
