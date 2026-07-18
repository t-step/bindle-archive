"""Render the rebuildable per-project index.json from a final graph.

Pure and deterministic: nodes sorted by id, edges by key, no run-only
timestamp is included so byte-equality holds across identical runs
(design doc section 12, "Semantic no-op").
"""

SCHEMA_VERSION = 1


def render_index(final_graph):
    """final_graph: a compile_preview-shaped dict extended by apply with
    unresolved_evidence / suppressed_rejections. Returns a schema-conformant
    index.json object. Writes nothing."""
    nodes = sorted(final_graph.get("nodes", []), key=lambda n: n["id"])
    edges = sorted(final_graph.get("edges", []), key=lambda e: e["key"])
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": final_graph["project_id"],
        "nodes": nodes,
        "edges": edges,
        "coverage": final_graph.get("coverage", {}),
        "conflicts": final_graph.get("conflicts", []),
        "unresolved_evidence": final_graph.get("unresolved_evidence", []),
        "suppressed_rejections": final_graph.get("suppressed_rejections", []),
    }
