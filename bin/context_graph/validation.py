"""context_graph.validation — validation of each v1 object kind, whole-
object-kind creation-authority checks, cross-object rules, and deterministic
finding ordering (issue #180, epic #140). See Task 4's plan header for the
bundle-validation model and the repositories-as-list decision.

Finding order (design section 14): first by the fixed registration order of
the invariant category (the _CHECKS list below), then by a stable
within-object key (object index, then field). Never dict/set iteration
order, never timestamps.
"""
from context_graph import canonical
from context_graph import ids
from context_graph import relationships as rel

FINDING_CODES = (
    "E_CONFIG_MALFORMED_PROJECT_ID",
    "E_CONFIG_PROJECT_ID_REPO_SHAPED",
    "E_CONFIG_DUPLICATE_ALIAS",
    "E_CONFIG_DUPLICATE_BINDING_ID",
    "E_CONFIG_MULTIPLE_DEFAULT",
    "E_NODE_MALFORMED_ID",
    "E_NODE_RESERVED_KIND",
    "E_NODE_PROJECT_ID_MISMATCH",
    "E_NODE_CONFIDENCE_INVALID_KIND",
    "E_NODE_TENSION_CARDINALITY",
    "E_NODE_TENSION_SIDE_IDENTITY",
    "E_NODE_DUPLICATE_ID",
    "E_EDGE_UNKNOWN_RELATIONSHIP",
    "E_EDGE_RELATIONSHIP_REJECTED",
    "E_EDGE_ENDPOINT_ILLEGAL",
    "E_EDGE_SELF_EDGE_FORBIDDEN",
    "E_EDGE_SUPERSEDES_KIND_MISMATCH",
    "E_EDGE_MISSING_NODE_REF",
    "E_EDGE_DUPLICATE_KEY",
    "E_EDGE_REVIEW_TRIGGER_MISMATCH",
    "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING",
    "E_EDGE_JUDGMENT_REQUIRED_MISSING",
    "E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN",
    "E_CANDIDATE_KEY_CONFLICT",
    "E_CANDIDATE_INVALID_ENDPOINT",
    "E_JUDGMENT_SUBJECT_TYPE_MISMATCH",
)

# Relationships whose deterministic authority is satisfied by a specific
# `deterministic_source.kind` on the edge (design section 8 / issue body
# "Relationship creation authority"). Fixture-representable stand-in for
# the real authoritative sources (#183's map/GitHub reads) that #180 itself
# never touches (non-goal: no map parsing, no GitHub resolution).
_DETERMINISTIC_SOURCE_KIND = {
    "contains": "project_membership",
    "supported_by": "map_evidence_pointer",
    "closes": "github_closure",
    "supersedes": "map_tombstone",
}


def _finding(code, message, index=None, field=None):
    return {"code": code, "message": message, "index": index, "field": field}


def validate_config(config):
    findings = []
    project_id = config.get("project_id", "")
    try:
        parsed = ids.parse_typed_id(project_id)
        if parsed["type"] != "project":
            raise ids.MalformedIdError(project_id, "not a project id")
    except ids.MalformedIdError:
        if "/" in project_id:
            findings.append(
                _finding(
                    "E_CONFIG_PROJECT_ID_REPO_SHAPED",
                    "project_id %r looks repository-shaped (owner/repo); "
                    "project identity is opaque and never derived from "
                    "repository coordinates" % (project_id,),
                    field="project_id",
                )
            )
        else:
            findings.append(
                _finding(
                    "E_CONFIG_MALFORMED_PROJECT_ID",
                    "malformed or missing project_id: %r" % (project_id,),
                    field="project_id",
                )
            )

    repositories = config.get("repositories", [])
    seen_aliases = {}
    seen_bindings = {}
    default_count = 0
    for i, repo in enumerate(repositories):
        alias = repo.get("alias")
        if alias in seen_aliases:
            findings.append(
                _finding(
                    "E_CONFIG_DUPLICATE_ALIAS",
                    "duplicate repository alias %r at index %d (first at %d)"
                    % (alias, i, seen_aliases[alias]),
                    index=i, field="alias",
                )
            )
        else:
            seen_aliases[alias] = i
        binding_id = repo.get("binding_id")
        if binding_id in seen_bindings:
            findings.append(
                _finding(
                    "E_CONFIG_DUPLICATE_BINDING_ID",
                    "duplicate binding_id %r at index %d (first at %d)"
                    % (binding_id, i, seen_bindings[binding_id]),
                    index=i, field="binding_id",
                )
            )
        else:
            seen_bindings[binding_id] = i
        if repo.get("default_for_bare_references"):
            default_count += 1
    if default_count > 1:
        findings.append(
            _finding(
                "E_CONFIG_MULTIPLE_DEFAULT",
                "%d repositories marked default_for_bare_references; at "
                "most one is allowed" % (default_count,),
                field="repositories",
            )
        )
    return findings


def _node_class_kind(node):
    return node.get("class"), node.get("kind")


def _check_nodes(nodes, config):
    findings = []
    seen_ids = {}
    for i, node in enumerate(nodes):
        node_id = node.get("id", "")
        try:
            ids.parse_typed_id(node_id)
        except ids.MalformedIdError as exc:
            findings.append(
                _finding("E_NODE_MALFORMED_ID", str(exc), index=i, field="id")
            )
        kind = node.get("kind")
        if kind in rel.RESERVED_SEMANTIC_KINDS:
            findings.append(
                _finding(
                    "E_NODE_RESERVED_KIND",
                    "reserved future node kind %r is documented but never "
                    "emitted as v1 output" % (kind,),
                    index=i, field="kind",
                )
            )
        if node.get("class") == "project" and config and config.get("project_id"):
            if node_id != config["project_id"]:
                findings.append(
                    _finding(
                        "E_NODE_PROJECT_ID_MISMATCH",
                        "project node id %r differs from configured "
                        "project_id %r" % (node_id, config["project_id"]),
                        index=i, field="id",
                    )
                )
        if node.get("confidence") is not None and kind not in ("assumption", "tension"):
            findings.append(
                _finding(
                    "E_NODE_CONFIDENCE_INVALID_KIND",
                    "confidence is valid only for assumption/tension nodes, "
                    "not %r" % (kind,),
                    index=i, field="confidence",
                )
            )
        if kind == "tension":
            sides = node.get("sides", [])
            if len(sides) != 2:
                findings.append(
                    _finding(
                        "E_NODE_TENSION_CARDINALITY",
                        "tension node must have exactly two sides, found %d"
                        % (len(sides),),
                        index=i, field="sides",
                    )
                )
            for side in sides:
                if "id" in side:
                    findings.append(
                        _finding(
                            "E_NODE_TENSION_SIDE_IDENTITY",
                            "tension side carries its own id %r; sides are "
                            "structured attributes, not addressable nodes"
                            % (side["id"],),
                            index=i, field="sides",
                        )
                    )
        if node_id in seen_ids:
            findings.append(
                _finding(
                    "E_NODE_DUPLICATE_ID",
                    "duplicate node id %r at index %d (first at %d)"
                    % (node_id, i, seen_ids[node_id]),
                    index=i, field="id",
                )
            )
        else:
            seen_ids[node_id] = i
    return findings


def _check_edges(edges, nodes_by_id, judgments):
    findings = []
    accepted_subject_keys = {
        j.get("subject_key") for j in judgments if j.get("decision") == "accepted"
    }
    seen_keys = {}
    for i, edge in enumerate(edges):
        relationship = edge.get("relationship")
        source_id = edge.get("source")
        target_id = edge.get("target")
        if relationship not in rel.RELATIONSHIPS:
            code = (
                "E_EDGE_RELATIONSHIP_REJECTED"
                if relationship == "implements"
                else "E_EDGE_UNKNOWN_RELATIONSHIP"
            )
            findings.append(
                _finding(
                    code,
                    "relationship %r is not in the v1 vocabulary" % (relationship,),
                    index=i, field="relationship",
                )
            )
        else:
            spec = rel.ENDPOINT_MATRIX[relationship]
            source_node = nodes_by_id.get(source_id)
            target_node = nodes_by_id.get(target_id)
            if source_node is None or target_node is None:
                missing = source_id if source_node is None else target_id
                findings.append(
                    _finding(
                        "E_EDGE_MISSING_NODE_REF",
                        "edge references a node not present in the bundle: %r"
                        % (missing,),
                        index=i, field="source" if source_node is None else "target",
                    )
                )
            else:
                src_class, src_kind = _node_class_kind(source_node)
                tgt_class, tgt_kind = _node_class_kind(target_node)
                result = rel.validate_endpoint_pair(
                    relationship, src_class, src_kind, tgt_class, tgt_kind
                )
                if not result["ok"]:
                    findings.append(
                        _finding(
                            "E_EDGE_ENDPOINT_ILLEGAL",
                            "relationship %r: actual source %s/%s not in "
                            "allowed source %s/%s; actual target %s/%s not "
                            "in allowed target %s/%s"
                            % (
                                relationship, src_class, src_kind,
                                result.get("allowed_source_class"),
                                result.get("allowed_source_kinds"),
                                tgt_class, tgt_kind,
                                result.get("allowed_target_class"),
                                result.get("allowed_target_kinds"),
                            ),
                            index=i, field="relationship",
                        )
                    )
                if (
                    spec["same_kind_required"]
                    and src_kind is not None
                    and tgt_kind is not None
                    and src_kind != tgt_kind
                ):
                    findings.append(
                        _finding(
                            "E_EDGE_SUPERSEDES_KIND_MISMATCH",
                            "%r requires source and target of the same kind: "
                            "%r vs %r" % (relationship, src_kind, tgt_kind),
                            index=i, field="relationship",
                        )
                    )
            if spec["self_edge_forbidden"] and source_id == target_id:
                findings.append(
                    _finding(
                        "E_EDGE_SELF_EDGE_FORBIDDEN",
                        "%r forbids a self-edge (source == target == %r)"
                        % (relationship, source_id),
                        index=i, field="target",
                    )
                )
            expected_trigger = rel.get_review_trigger_default(relationship)
            if edge.get("review_trigger") != expected_trigger:
                findings.append(
                    _finding(
                        "E_EDGE_REVIEW_TRIGGER_MISMATCH",
                        "relationship %r must have review_trigger=%r in v1"
                        % (relationship, expected_trigger),
                        index=i, field="review_trigger",
                    )
                )
            origin = edge.get("origin")
            if origin == "deterministic":
                required_kind = _DETERMINISTIC_SOURCE_KIND.get(relationship)
                actual_kind = (edge.get("deterministic_source") or {}).get("kind")
                if required_kind is None or actual_kind != required_kind:
                    findings.append(
                        _finding(
                            "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING",
                            "deterministic %r edge lacks its required source "
                            "authority (expected deterministic_source.kind=%r)"
                            % (relationship, required_kind),
                            index=i, field="deterministic_source",
                        )
                    )
            elif origin == "human_judgment":
                edge_key = edge.get("key")
                if edge_key not in accepted_subject_keys:
                    findings.append(
                        _finding(
                            "E_EDGE_JUDGMENT_REQUIRED_MISSING",
                            "human-judged edge %r has no matching effective "
                            "accepted judgment" % (edge_key,),
                            index=i, field="origin",
                        )
                    )
        edge_key = edge.get("key")
        if edge_key in seen_keys:
            findings.append(
                _finding(
                    "E_EDGE_DUPLICATE_KEY",
                    "duplicate edge key %r at index %d (first at %d)"
                    % (edge_key, i, seen_keys[edge_key]),
                    index=i, field="key",
                )
            )
        else:
            seen_keys[edge_key] = i
    return findings


def _check_candidates(candidates):
    findings = []
    for i, cand in enumerate(candidates):
        subject_type = cand.get("subject_type")
        if subject_type == "identity_anchor" and cand.get("candidate_origin") != "deterministic_compiler":
            findings.append(
                _finding(
                    "E_CANDIDATE_ANCHOR_SYNTHESIS_FORBIDDEN",
                    "identity_anchor candidates may only be produced by the "
                    "deterministic compiler, got candidate_origin=%r"
                    % (cand.get("candidate_origin"),),
                    index=i, field="candidate_origin",
                )
            )
        if subject_type == "edge":
            basis = cand.get("basis", [])
            try:
                recomputed = canonical.candidate_key(
                    cand.get("source"), cand.get("relationship"), cand.get("target"), basis
                )
            except ValueError:
                recomputed = None
            if recomputed is not None and cand.get("candidate_key") != recomputed:
                findings.append(
                    _finding(
                        "E_CANDIDATE_KEY_CONFLICT",
                        "declared candidate_key %r does not match the "
                        "recomputed key %r for this source/relationship/"
                        "target/basis" % (cand.get("candidate_key"), recomputed),
                        index=i, field="candidate_key",
                    )
                )
            relationship = cand.get("relationship")
            if relationship in rel.RELATIONSHIPS:
                result = rel.validate_endpoint_pair(
                    relationship,
                    cand.get("source_class"), cand.get("source_kind"),
                    cand.get("target_class"), cand.get("target_kind"),
                )
                if not result["ok"]:
                    findings.append(
                        _finding(
                            "E_CANDIDATE_INVALID_ENDPOINT",
                            "candidate has an illegal endpoint for %r and "
                            "may never become a review candidate" % (relationship,),
                            index=i, field="relationship",
                        )
                    )
    return findings


def _check_judgments(judgments, candidates_by_key):
    findings = []
    for i, judgment in enumerate(judgments):
        subject_type = judgment.get("subject_type")
        candidate_key = judgment.get("candidate_key")
        candidate = candidates_by_key.get(candidate_key)
        if candidate is not None and candidate.get("subject_type") != subject_type:
            findings.append(
                _finding(
                    "E_JUDGMENT_SUBJECT_TYPE_MISMATCH",
                    "judgment declares subject_type=%r but its candidate %r "
                    "is subject_type=%r" % (
                        subject_type, candidate_key, candidate.get("subject_type")
                    ),
                    index=i, field="subject_type",
                )
            )
    return findings


def validate_bundle(bundle):
    """Validate a fixture bundle (see Task 4's plan header for the shape)
    and return findings ordered per design section 14: fixed invariant-
    category order, then object index."""
    config = bundle.get("config")
    nodes = bundle.get("nodes", [])
    edges = bundle.get("edges", [])
    candidates = bundle.get("candidates", [])
    judgments = bundle.get("judgments", [])

    nodes_by_id = {n.get("id"): n for n in nodes}
    candidates_by_key = {c.get("candidate_key"): c for c in candidates}

    findings = []
    if config is not None:
        findings.extend(validate_config(config))
    findings.extend(_check_nodes(nodes, config))
    findings.extend(_check_edges(edges, nodes_by_id, judgments))
    findings.extend(_check_candidates(candidates))
    findings.extend(_check_judgments(judgments, candidates_by_key))
    return findings
