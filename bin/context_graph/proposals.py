"""context_graph.proposals — validate an untrusted edge proposal into a
schema-valid edge candidate (issue #184). Pure: no I/O, no ledger, no lock.

Enforces design section 11's ordering: resolve endpoints against the current
#183 graph, validate the endpoint pair under #180's closed matrix, and ONLY
for a legal pair compute the candidate key + dependency fingerprint. An illegal
or unknown pair is a validation failure and no key is ever minted for it.
"""
from context_graph import canonical, relationships as rel

E_PROPOSAL_MALFORMED = "E_PROPOSAL_MALFORMED"
E_PROPOSAL_UNKNOWN_ENDPOINT = "E_PROPOSAL_UNKNOWN_ENDPOINT"
E_PROPOSAL_ILLEGAL_ENDPOINT = "E_PROPOSAL_ILLEGAL_ENDPOINT"
E_PROPOSAL_BASIS_INVALID = "E_PROPOSAL_BASIS_INVALID"
E_PROPOSAL_ADVISORY_KEY_MISMATCH = "E_PROPOSAL_ADVISORY_KEY_MISMATCH"

_REQUIRED = ("source", "relationship", "target", "basis", "explanation", "producer")
_PRODUCERS = frozenset({"human", "skill", "fixture"})


def nodes_by_id(preview):
    return {n["id"]: n for n in preview.get("nodes", [])}


def _fail(code, message):
    return {"candidate": None, "subject_key": None,
            "findings": [{"code": code, "message": message}]}


def validate_edge_proposal(proposal, preview):
    """Validate one proposal dict against a compile_preview() result.
    Returns {"candidate", "subject_key", "findings"}; candidate is non-None
    only when findings is empty."""
    if not isinstance(proposal, dict):
        return _fail(E_PROPOSAL_MALFORMED, "proposal must be an object")
    missing = [k for k in _REQUIRED if k not in proposal]
    if missing:
        return _fail(E_PROPOSAL_MALFORMED, "missing fields %r" % (sorted(missing),))
    if proposal["producer"] not in _PRODUCERS:
        return _fail(E_PROPOSAL_MALFORMED, "producer %r not one of %s"
                     % (proposal["producer"], sorted(_PRODUCERS)))
    if not isinstance(proposal["basis"], list):
        return _fail(E_PROPOSAL_BASIS_INVALID, "basis must be an array")

    source_id = proposal["source"]
    target_id = proposal["target"]
    relationship = proposal["relationship"]

    index = nodes_by_id(preview)
    src = index.get(source_id)
    tgt = index.get(target_id)
    if src is None or tgt is None:
        return _fail(E_PROPOSAL_UNKNOWN_ENDPOINT,
                     "endpoint(s) not in current graph: %r"
                     % ([e for e, n in ((source_id, src), (target_id, tgt)) if n is None],))

    # Endpoint-legality gate — BEFORE any key construction (design section 11).
    verdict = rel.validate_endpoint_pair(
        relationship, src["class"], src["kind"], tgt["class"], tgt["kind"])
    if not verdict["ok"]:
        return _fail(E_PROPOSAL_ILLEGAL_ENDPOINT,
                     "%s illegal for %s/%s -> %s/%s (%s)"
                     % (relationship, src["class"], src["kind"],
                        tgt["class"], tgt["kind"], verdict["reason"]))

    # Basis validation reuses the frozen canonicalizer (raises ValueError on any
    # unknown kind / bad field), so an invalid basis never reaches key bytes.
    try:
        canonical.canonical_basis_bytes(proposal["basis"])
    except ValueError as exc:
        return _fail(E_PROPOSAL_BASIS_INVALID, str(exc))

    # For symmetric contradicts, canonicalize endpoint order for the key.
    key_source, key_target = source_id, target_id
    if relationship == "contradicts":
        key_source, key_target = rel.canonicalize_contradicts_endpoints(source_id, target_id)

    candidate_key = canonical.candidate_key(
        key_source, relationship, key_target, proposal["basis"])

    advisory = proposal.get("advisory_candidate_key")
    if advisory is not None and advisory != candidate_key:
        return _fail(E_PROPOSAL_ADVISORY_KEY_MISMATCH,
                     "advisory key %r != recomputed %r" % (advisory, candidate_key))

    dependency_fingerprint = canonical.edge_dependency_fingerprint(
        source_id, src["class"], src["kind"], relationship,
        target_id, tgt["class"], tgt["kind"], proposal["basis"])
    subject_key = canonical.edge_subject_key(key_source, relationship, key_target)

    # The emitted candidate's own source/target (and their class/kind) must
    # match whichever endpoint order the key was minted over -- for symmetric
    # contradicts that's the canonicalized (key_source, key_target) pair, not
    # the raw proposal order, so a future consumer recomputing candidate_key
    # from the embedded endpoints gets the same key back. Directional
    # relationships have key_source == source_id / key_target == target_id,
    # so this is a no-op for them.
    key_src_node = index[key_source]
    key_tgt_node = index[key_target]

    candidate = {
        "subject_type": "edge",
        "candidate_key": candidate_key,
        "candidate_origin": "validated_proposal",
        "dependency_fingerprint": dependency_fingerprint,
        "producer": proposal["producer"],
        "validation_status": "valid",
        "source": key_source,
        "relationship": relationship,
        "target": key_target,
        "basis": proposal["basis"],
        "source_class": key_src_node["class"],
        "source_kind": key_src_node["kind"],
        "target_class": key_tgt_node["class"],
        "target_kind": key_tgt_node["kind"],
        "explanation": proposal["explanation"],
    }
    return {"candidate": candidate, "subject_key": subject_key, "findings": []}
