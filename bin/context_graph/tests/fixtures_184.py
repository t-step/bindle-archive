"""Literal builders for #184 reducer + proposal tests — a minimal in-memory
#183 preview and proposal envelopes, so tests need no real notes-home."""

DECISION_A = {"id": "context-node:bindle:aaaa", "class": "semantic",
              "kind": "decision", "label": "Decision A", "status": "active"}
LEARNING_B = {"id": "context-node:bindle:bbbb", "class": "semantic",
              "kind": "learning", "label": "Learning B", "status": "active"}
PR_NODE = {"id": "github-pr:o/r#1", "class": "evidence",
           "kind": "github_pr", "label": "PR 1", "status": "active"}


def preview(nodes=None):
    return {
        "schema_version": 1,
        "project_id": "project:deadbeef",
        "nodes": list(nodes if nodes is not None else [DECISION_A, LEARNING_B, PR_NODE]),
        "edges": [],
        "identity_anchor_candidates": [],
        "conflicts": [],
        "coverage": {},
    }


def edge_proposal(source=DECISION_A["id"], relationship="supports",
                  target=LEARNING_B["id"], basis=None, producer="human",
                  explanation="because", advisory_key=None):
    p = {"source": source, "relationship": relationship, "target": target,
         "basis": basis if basis is not None else [], "explanation": explanation,
         "producer": producer}
    if advisory_key is not None:
        p["advisory_candidate_key"] = advisory_key
    return p
