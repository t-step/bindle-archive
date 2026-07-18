"""Render the deterministic `context.md` managed region from a final graph
(#185 apply), and plan the file's lifecycle (create/update/conflict; Task 6
adds adopt) around the managed-region marker pair.

The managed region is a *bounded reading surface* over the graph: a fixed
set of section slices, each sorted by a stable key, not a full graph dump
(design doc section 12, "Projection requirements"). It must render
byte-identically across repeated calls on the same `final_graph` — no
timestamp, run id, or other non-graph value may ever appear in it, so two
applies of an unchanged graph never produce a spurious diff.

`final_graph` is shaped like `compiler.compile_preview`'s return
(compiler.py:470-478): `nodes` (`id`/`class`/`kind`/`label`/`status`,
`class` in project|semantic|evidence), `edges` (`key`/`source`/
`relationship`/`target`/`status`/`origin`/`review_trigger`/`basis`/...),
`coverage` (the 7-key map), and `conflicts` (finding dicts). This module
only reads those fields; it never invents new ones.
"""

BEGIN = "<!-- bindle:context-graph:generated:begin -->"
END = "<!-- bindle:context-graph:generated:end -->"

# Relationships whose endpoints are both semantic nodes (relationships.py
# ENDPOINT_MATRIX) -- the structural "decision and learning graph" edges.
# `contains` (project -> semantic membership) is deliberately excluded: the
# compiler admits one per anchored map entry, so rendering it on every
# node would be noise repeated across the whole section rather than a
# reading aid (design doc section 12).
_STRUCTURAL_RELATIONSHIPS = frozenset({
    "motivates", "constrains", "depends_on", "resolves",
    "supports", "contradicts", "supersedes", "revisits",
})

# Relationships that attribute a semantic claim to evidence, or attribute
# delivery evidence to other evidence (relationships.py ENDPOINT_MATRIX):
# `supported_by` (deterministic map pointer), the three judgment-only
# attribution relationships, and `closes` (PR -> issue delivery).
_EVIDENCE_RELATIONSHIPS = frozenset({
    "supported_by", "discussed_in", "implemented_by", "validated_by", "closes",
})

# The 7-key coverage contract (compiler.py:456-466), rendered in this fixed
# order so the section is stable regardless of dict insertion order.
_COVERAGE_KEYS = (
    "project_map", "sessions", "handoffs", "documents",
    "github_issues", "github_prs", "commits",
)


def _node_line(node):
    return "- `%s` (%s, %s): %s" % (
        node["id"], node.get("kind") or node.get("class"), node.get("status", ""),
        node.get("label", ""),
    )


def _edge_line(edge, nodes_by_id, indent=""):
    src = nodes_by_id.get(edge["source"], {})
    tgt = nodes_by_id.get(edge["target"], {})
    return "%s- `%s` (%s) --%s--> `%s` (%s) [%s/%s]" % (
        indent, edge["source"], src.get("label", ""), edge["relationship"],
        edge["target"], tgt.get("label", ""), edge.get("status", ""),
        edge.get("origin", ""),
    )


def _section(heading, lines):
    body = "\n".join(lines) if lines else "(none)"
    return "## %s\n\n%s\n" % (heading, body)


def _render_decision_graph(nodes, edges, nodes_by_id):
    by_source = {}
    for edge in edges:
        if edge["relationship"] in _STRUCTURAL_RELATIONSHIPS:
            by_source.setdefault(edge["source"], []).append(edge)

    lines = []
    for node in nodes:
        if node.get("class") != "semantic":
            continue
        lines.append(_node_line(node))
        for edge in by_source.get(node["id"], []):
            lines.append(_edge_line(edge, nodes_by_id, indent="  "))
    return _section("Decision and learning graph", lines)


def _render_evidence_delivery(edges, nodes_by_id):
    lines = [
        _edge_line(edge, nodes_by_id)
        for edge in edges
        if edge["relationship"] in _EVIDENCE_RELATIONSHIPS
    ]
    return _section("Evidence and delivery", lines)


def _render_review_trigger(edges, nodes_by_id):
    lines = [
        _edge_line(edge, nodes_by_id)
        for edge in edges
        if edge.get("review_trigger")
    ]
    return _section("Review-triggering coupling", lines)


def _render_unconnected(nodes, edges):
    # Only structural + evidence edges count as "incident" here. `contains`
    # is excluded on purpose: the compiler adds one project->node `contains`
    # edge for every anchored semantic node unconditionally (compiler.py
    # ~370-375), so counting it would make every semantic node "incident"
    # and this section could never surface a genuinely isolated entry.
    incident = set()
    for edge in edges:
        if edge["relationship"] not in _STRUCTURAL_RELATIONSHIPS and \
                edge["relationship"] not in _EVIDENCE_RELATIONSHIPS:
            continue
        incident.add(edge["source"])
        incident.add(edge["target"])
    lines = [
        _node_line(node)
        for node in nodes
        if node.get("class") == "semantic" and node["id"] not in incident
    ]
    return _section("Unconnected durable entries", lines)


def _render_coverage(coverage):
    lines = ["- %s: %s" % (key, coverage.get(key, "unsupported")) for key in _COVERAGE_KEYS]
    return _section("Evidence coverage", lines)


def _render_conflicts(conflicts):
    ordered = sorted(conflicts, key=lambda c: (c.get("line") or 0, c.get("code", "")))
    lines = []
    for finding in ordered:
        if finding.get("line"):
            lines.append("- line %s: %s: %s" % (finding["line"], finding["code"], finding["message"]))
        else:
            lines.append("- %s: %s" % (finding["code"], finding["message"]))
    return _section("Conflicts", lines)


def render_managed_region(final_graph):
    """Render the deterministic Markdown body for the managed region of
    context.md from one final graph. Pure: no I/O, no clock, no run-only
    value -- byte-equal output for byte-equal input (design doc section 12).
    """
    nodes = sorted(final_graph.get("nodes", []), key=lambda n: n["id"])
    edges = sorted(final_graph.get("edges", []), key=lambda e: e["key"])
    nodes_by_id = {node["id"]: node for node in nodes}
    coverage = final_graph.get("coverage", {})
    conflicts = final_graph.get("conflicts", [])

    sections = [
        _render_decision_graph(nodes, edges, nodes_by_id),
        _render_evidence_delivery(edges, nodes_by_id),
        _render_review_trigger(edges, nodes_by_id),
        _render_unconnected(nodes, edges),
        _render_coverage(coverage),
        _render_conflicts(conflicts),
    ]
    return "\n".join(sections) + "\n"


def _scan_markers(text):
    """Classify the BEGIN/END marker pair in `text`. Returns a
    ("valid", begin_idx, end_idx) / ("unmanaged", None, None) /
    ("malformed", None, None) triple. `begin_idx`/`end_idx` are the start
    offsets of BEGIN/END respectively, valid only for "valid".

    - Zero of each -> "unmanaged" (a hand-authored file with no managed
      region at all).
    - Exactly one of each, BEGIN strictly before END -> "valid".
    - Anything else (unequal counts, END before BEGIN, a duplicated or
      nested pair, only one side present) -> "malformed".
    """
    begin_count = text.count(BEGIN)
    end_count = text.count(END)
    if begin_count == 0 and end_count == 0:
        return ("unmanaged", None, None)
    if begin_count == 1 and end_count == 1:
        begin_idx = text.index(BEGIN)
        end_idx = text.index(END)
        if begin_idx < end_idx:
            return ("valid", begin_idx, end_idx)
    return ("malformed", None, None)


def plan_context_md(existing_text, managed_body, title="Project"):
    """Plan the create/update/noop/conflict lifecycle transition for
    `context.md` given its current text (or `None` if the file does not
    exist yet) and the freshly rendered managed-region body from
    `render_managed_region`. Pure: no I/O. Content outside the marker pair
    is preserved byte-for-byte on update.
    """
    wrapped_region = BEGIN + "\n" + managed_body + END

    if existing_text is None:
        text = (
            "# %s — context\n" % title
            + wrapped_region
            + "\n## Maintainer notes\n"
            + "(notes below this line are yours -- the tool will never touch them)\n"
        )
        return {"action": "create", "text": text}

    kind, begin_idx, end_idx = _scan_markers(existing_text)
    if kind == "unmanaged":
        return {"action": "conflict", "code": "context_md_unmanaged"}
    if kind == "malformed":
        return {"action": "conflict", "code": "context_md_malformed_markers"}

    end_stop = end_idx + len(END)
    current_region = existing_text[begin_idx:end_stop]
    if current_region == wrapped_region:
        return {"action": "noop"}

    new_text = existing_text[:begin_idx] + wrapped_region + existing_text[end_stop:]
    return {"action": "update", "text": new_text}
