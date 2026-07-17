"""context_graph.canonical — the two versioned, byte-exact candidate-key
primitives plus the two fingerprint primitives (issue #180, epic #140),
frozen by docs/design/2026-07-16-context-graph-schema.md section 10.

Basis-entry normalization + canonical basis serialization; SHA-256
generation of both the edge candidate key and the identity-anchor
candidate key, plus the anchor entry_fingerprint and
anchor_dependency_fingerprint. Performs no object validation beyond what is
required to canonicalize inputs that were already validated upstream (that
composition lives in context_graph.validation) — this module does not
import context_graph.ids or context_graph.relationships.
"""
import hashlib
import json

# Fixed per-kind field contracts for basis entries (design section 10.1:
# "a fixed allowed field set for its basis kind"; this plan's own decision
# for what the kind set actually is — see the Task 3 docstring above).
BASIS_KINDS = {
    "evidence_pointer": {
        "required": frozenset({"kind", "location", "pointer"}),
        "optional": frozenset(),
        "enum_fields": {"location": frozenset({"entry_evidence", "tension_side"})},
    },
}


def normalize_basis_entry(entry):
    """Normalize one basis entry to a typed JSON object with a fixed
    allowed field set for its kind. Rejects unknown fields, missing
    required fields, unsupported primitive types, and explicit null
    (omitted-vs-null distinction: an omitted optional field is simply
    absent; explicit null is always a rejected primitive). No Unicode
    normalization is applied."""
    if not isinstance(entry, dict):
        raise ValueError("basis entry must be an object, got %r" % (type(entry).__name__,))
    kind = entry.get("kind")
    spec = BASIS_KINDS.get(kind)
    if spec is None:
        raise ValueError("unknown basis kind %r" % (kind,))
    allowed = spec["required"] | spec["optional"]
    extra = set(entry.keys()) - allowed
    if extra:
        raise ValueError(
            "unsupported basis fields %r for kind %r" % (sorted(extra), kind)
        )
    missing = spec["required"] - set(entry.keys())
    if missing:
        raise ValueError(
            "missing required basis fields %r for kind %r" % (sorted(missing), kind)
        )
    normalized = {}
    for field in sorted(allowed):
        if field not in entry:
            continue
        value = entry[field]
        if value is None:
            raise ValueError("basis field %r may not be explicit null" % (field,))
        if not isinstance(value, str):
            raise ValueError(
                "basis field %r must be a string, got %r" % (field, type(value).__name__)
            )
        enum = spec.get("enum_fields", {}).get(field)
        if enum is not None and value not in enum:
            raise ValueError(
                "basis field %r has invalid value %r (expected one of %s)"
                % (field, value, sorted(enum))
            )
        normalized[field] = value
    return normalized


def _serialize(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_basis_bytes(basis_entries):
    """Normalize, deduplicate by exact serialized UTF-8 bytes (basis order
    is semantically irrelevant), sort lexicographically by those bytes, and
    serialize the resulting array with the same json.dumps settings
    (design section 10.1, steps 1-5)."""
    by_bytes = {}
    for entry in basis_entries:
        normalized = normalize_basis_entry(entry)
        key = _serialize(normalized).encode("utf-8")
        by_bytes[key] = normalized
    ordered = [by_bytes[k] for k in sorted(by_bytes.keys())]
    return _serialize(ordered).encode("utf-8")


def candidate_key(source_id, relationship, target_id, basis_entries):
    """Edge candidate key: bindle-context-candidate-v1 (design section
    10.1). For symmetric `contradicts`, the caller is expected to have
    already canonicalized source_id/target_id via
    relationships.canonicalize_contradicts_endpoints — this function
    canonicalizes them again defensively so a caller that forgets still
    gets a collapsed key."""
    if relationship == "contradicts":
        source_id, target_id = sorted((source_id, target_id))
    payload = b"\0".join(
        (
            b"bindle-context-candidate-v1",
            source_id.encode("utf-8"),
            relationship.encode("utf-8"),
            target_id.encode("utf-8"),
            canonical_basis_bytes(basis_entries),
        )
    )
    return "candidate:sha256:" + hashlib.sha256(payload).hexdigest()


def entry_fingerprint(project_id, map_path, section, entry_kind, entry_bytes):
    """Identity-anchor entry fingerprint: bindle-context-entry-fingerprint-v1
    (design section 10.2). `entry_bytes` are the owner-authored entry's
    exact UTF-8 bytes as produced by #183's parser, markers already
    excised — this function applies no further transformation to them."""
    payload = b"\0".join(
        (
            b"bindle-context-entry-fingerprint-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
            entry_bytes,
        )
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def anchor_candidate_key(project_id, map_path, section, entry_kind, entry_fingerprint_value):
    """Identity-anchor candidate key: bindle-context-anchor-candidate-v1
    (design section 10.2). All five frame fields are mandatory; there is
    no basis array for anchors."""
    payload = b"\0".join(
        (
            b"bindle-context-anchor-candidate-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
            entry_fingerprint_value.encode("utf-8"),
        )
    )
    return "anchor-candidate:sha256:" + hashlib.sha256(payload).hexdigest()


def anchor_dependency_fingerprint(
    project_id, map_path, section, entry_kind, entry_fingerprint_value
):
    """Identity-anchor staleness fingerprint:
    bindle-context-anchor-dependency-v1 (design section 10.2) — a direct
    computed field under its own domain literal so its bytes never equal
    the candidate key."""
    payload = b"\0".join(
        (
            b"bindle-context-anchor-dependency-v1",
            project_id.encode("utf-8"),
            map_path.encode("utf-8"),
            section.encode("utf-8"),
            entry_kind.encode("utf-8"),
            entry_fingerprint_value.encode("utf-8"),
        )
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()
