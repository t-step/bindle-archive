"""context_graph.relationships — the closed v1 relationship vocabulary,
per-relationship directionality, endpoint legality, and coupling
(review_trigger) defaults (issue #180, epic #140).

Owns relationship-*intrinsic* authority metadata only (whether a
relationship may ever be deterministic, whether it always requires
judgment). Whole-object-kind creation-authority checks (does *this* edge
instance actually have its required authority) live in
context_graph.validation, not here — see
docs/design/2026-07-16-context-graph-schema.md section 4.
"""

NODE_CLASSES = frozenset({"project", "semantic", "evidence"})

SEMANTIC_KINDS = frozenset(
    {"decision", "learning", "assumption", "tension", "question"}
)
EVIDENCE_KINDS = frozenset(
    {
        "session",
        "handoff",
        "document_repository",
        "document_project_local",
        "github_issue",
        "github_pr",
    }
)
RESERVED_SEMANTIC_KINDS = frozenset(
    {
        "problem",
        "concept",
        "constraint",
        "solution",
        "pattern",
        "principle",
        "architecture_component",
        "architecture_flow",
        "boundary",
        "test_surface",
    }
)

# Node groups (design section 7).
NODE_GROUPS = {
    "semantic-any": SEMANTIC_KINDS,
    "claim": frozenset({"decision", "learning", "assumption"}),
    "uncertainty": frozenset({"assumption", "tension", "question"}),
    "resolving": frozenset({"decision", "learning"}),
    "evidence-any": EVIDENCE_KINDS,
    "validation-evidence": frozenset(
        {
            "session",
            "handoff",
            "document_repository",
            "document_project_local",
            "github_pr",
        }
    ),
}

RELATIONSHIPS = (
    "contains",
    "supported_by",
    "discussed_in",
    "implemented_by",
    "validated_by",
    "closes",
    "motivates",
    "constrains",
    "depends_on",
    "resolves",
    "supports",
    "contradicts",
    "supersedes",
    "revisits",
)


def _endpoint(node_class, kinds):
    """kinds=None means "any kind valid for this class" (used only where a
    class has exactly one legal kind set, i.e. never for semantic/evidence,
    which always name an explicit group)."""
    return {"class": node_class, "kinds": kinds}


# The closed v1 endpoint matrix (design section 7 / issue body "Closed v1
# endpoint matrix"). Every relationship is total: unknown relationships are
# handled by validate_endpoint_pair returning ok=False, reason="unknown_relationship".
ENDPOINT_MATRIX = {
    "contains": {
        "source": _endpoint("project", None),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": True,
        "judgment_required": False,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "supported_by": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("evidence", NODE_GROUPS["evidence-any"]),
        "deterministic_allowed": True,
        "judgment_required": False,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "discussed_in": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("evidence", NODE_GROUPS["evidence-any"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "implemented_by": {
        "source": _endpoint("semantic", frozenset({"decision"})),
        "target": _endpoint("evidence", frozenset({"github_pr"})),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "validated_by": {
        "source": _endpoint("semantic", NODE_GROUPS["resolving"]),
        "target": _endpoint("evidence", NODE_GROUPS["validation-evidence"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "closes": {
        "source": _endpoint("evidence", frozenset({"github_pr"})),
        "target": _endpoint("evidence", frozenset({"github_issue"})),
        "deterministic_allowed": True,
        "judgment_required": False,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "motivates": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("semantic", frozenset({"decision", "question"})),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "constrains": {
        "source": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption", "tension"})
        ),
        "target": _endpoint(
            "semantic", frozenset({"decision", "assumption", "tension", "question"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "depends_on": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": True,
        "same_kind_required": False,
        "symmetric": False,
    },
    "resolves": {
        "source": _endpoint("semantic", NODE_GROUPS["resolving"]),
        "target": _endpoint(
            "semantic", frozenset({"question", "assumption", "tension"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "supports": {
        "source": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption"})
        ),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
    "contradicts": {
        "source": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption"})
        ),
        "target": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": True,
        "same_kind_required": False,
        "symmetric": True,
    },
    "supersedes": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "deterministic_allowed": True,
        "judgment_required": True,
        "self_edge_forbidden": True,
        "same_kind_required": True,
        "symmetric": False,
    },
    "revisits": {
        "source": _endpoint("semantic", NODE_GROUPS["semantic-any"]),
        "target": _endpoint(
            "semantic", frozenset({"decision", "learning", "assumption", "tension"})
        ),
        "deterministic_allowed": False,
        "judgment_required": True,
        "self_edge_forbidden": False,
        "same_kind_required": False,
        "symmetric": False,
    },
}

REVIEW_TRIGGER_DEFAULT = {
    "constrains": True,
    "depends_on": True,
    "contradicts": True,
    "supersedes": True,
    "supports": False,
    "supported_by": False,
    "discussed_in": False,
    "implemented_by": False,
    "validated_by": False,
    "contains": False,
    "closes": False,
    "motivates": False,
    "resolves": False,
    "revisits": False,
}


def get_review_trigger_default(relationship):
    return REVIEW_TRIGGER_DEFAULT[relationship]


def _kind_matches(spec, node_class, node_kind):
    if node_class != spec["class"]:
        return False
    if spec["kinds"] is None:
        return True
    return node_kind in spec["kinds"]


def validate_endpoint_pair(relationship, source_class, source_kind, target_class, target_kind):
    """Never trusts the relationship name alone. Returns a dict with a
    structured diagnostic payload (design section 7): relationship, actual
    vs allowed source/target class+kind. Reserved/unknown kinds satisfy no
    group and so never match."""
    spec = ENDPOINT_MATRIX.get(relationship)
    if spec is None:
        return {
            "ok": False,
            "reason": "unknown_relationship",
            "relationship": relationship,
        }
    src_ok = _kind_matches(spec["source"], source_class, source_kind)
    tgt_ok = _kind_matches(spec["target"], target_class, target_kind)
    same_kind_ok = True
    if spec.get("same_kind_required", False):
        same_kind_ok = source_kind == target_kind
    ok = src_ok and tgt_ok and same_kind_ok
    return {
        "ok": ok,
        "reason": None if ok else "illegal_endpoint",
        "relationship": relationship,
        "source_class": source_class,
        "source_kind": source_kind,
        "allowed_source_class": spec["source"]["class"],
        "allowed_source_kinds": (
            sorted(spec["source"]["kinds"]) if spec["source"]["kinds"] else None
        ),
        "target_class": target_class,
        "target_kind": target_kind,
        "allowed_target_class": spec["target"]["class"],
        "allowed_target_kinds": (
            sorted(spec["target"]["kinds"]) if spec["target"]["kinds"] else None
        ),
    }


def canonicalize_contradicts_endpoints(source_id, target_id):
    """`contradicts` is symmetric: canonicalize the endpoint pair
    lexicographically before candidate-key or edge-key construction so
    reversed proposals collapse to one subject (design section 10.1)."""
    return tuple(sorted((source_id, target_id)))
