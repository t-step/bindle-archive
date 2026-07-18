#!/usr/bin/env python3
"""Graduation gate for the optional `context-graph` skill (issue #186).

The skill is a proposal *producer*, never a candidate authority. These checks
prove the invariant the issue makes graduation-blocking: **no producer can
bypass, reinterpret, or silently repair endpoint legality**, because every path
— human, skill, fixture — flows through the same deterministic `propose`/
`confirm` verbs.

Two layers, both against the real deterministic tooling:

1. Real-CLI subprocess: build a notes-home with a decision, a learning, and a
   question node, then drive `bin/context-graph.py propose`/`confirm` with
   proposal envelopes that differ only in `producer`. Proves producer parity,
   the illegal-combo battery, reversed-`contradicts` collapse, uncertainty
   invariance, and that a skill can neither fabricate a candidate nor confirm
   an illegal one.
2. In-process validator: for endpoint kinds that need GitHub evidence
   (`github_pr`/`github_issue`) and so cannot be map-derived offline, call the
   same `context_graph.proposals.validate_edge_proposal` the CLI calls, with an
   in-memory preview. Proves the `issue closes PR` / `learning implemented_by
   PR` illegal combos are rejected by the same authority.

Run: `python3 skills/context-graph/tests/ontology_safety.py <repo-root>`
(bin/test-context-graph-skill.sh is the wrapper wired into `make test`).
"""
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
CLI = os.path.join(REPO_ROOT, "bin", "context-graph.py")
PY = sys.executable

# Node ids baked into the anchored map below (32 hex chars each), matching the
# id grammar the existing bin/test-context-graph-cli.sh fixtures rely on.
DECISION = "context-node:proj:11111111111111111111111111111111"
LEARNING = "context-node:proj:22222222222222222222222222222222"
QUESTION = "context-node:proj:33333333333333333333333333333333"

MAP_TEXT = (
    "## Brief\n\n"
    "## Decisions\n"
    "### A decision (2026-07, settled) "
    "<!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nrevisit-when: z\nevidence:\n\n"
    "## Learnings\n"
    "### A learning (2026-07) "
    "<!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Assumptions & tensions\n\n"
    "## Open questions\n"
    "- An open question (open) — so: still unresolved "
    "<!-- bindle:context-id: %s -->\n\n"
    "## Superseded\n"
) % (DECISION, LEARNING, QUESTION)

_passed = 0
_failed = 0


def check(desc, ok):
    global _passed, _failed
    if ok:
        _passed += 1
        print("  ✓ %s" % desc)
    else:
        _failed += 1
        print("  ✗ %s" % desc)


def proposal(source, relationship, target, producer="skill",
             basis=None, explanation="because", uncertainty=None,
             advisory=None):
    p = {"source": source, "relationship": relationship, "target": target,
         "basis": basis if basis is not None else [],
         "explanation": explanation, "producer": producer}
    if uncertainty is not None:
        p["uncertainty"] = uncertainty
    if advisory is not None:
        p["advisory_candidate_key"] = advisory
    return p


def run(scratch, nh, verb, *args, envelope=None):
    """Run one CLI verb; if `envelope` is given, write it to a temp file and
    pass it as --input. Returns (rc, parsed-json-or-None)."""
    argv = [PY, CLI, verb, "--notes-home", nh, "--project", "proj", *args]
    if envelope is not None:
        path = tempfile.mkstemp(suffix=".json", dir=scratch)[1]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh)
        argv += ["--input", path]
    out = subprocess.run(argv, capture_output=True, text=True)
    try:
        return out.returncode, json.loads(out.stdout)
    except json.JSONDecodeError:
        return out.returncode, None


def finding_codes(result):
    return [f.get("code") for f in (result or {}).get("findings", [])]


def cli_layer(scratch):
    nh = tempfile.mkdtemp(dir=scratch)
    subprocess.run([PY, CLI, "init", "--notes-home", nh, "--project", "proj"],
                   capture_output=True, text=True, check=True)
    with open(os.path.join(nh, "projects", "proj", "map.md"), "w",
              encoding="utf-8") as fh:
        fh.write(MAP_TEXT)

    # Sanity: the three endpoints compile to the intended kinds.
    _, preview = run(scratch, nh, "preview")
    kinds = {n["id"]: n["kind"] for n in (preview or {}).get("nodes", [])}
    check("map yields a decision node", kinds.get(DECISION) == "decision")
    check("map yields a learning node", kinds.get(LEARNING) == "learning")
    check("map yields a question node", kinds.get(QUESTION) == "question")

    # --- Producer parity: same content, producer differs -> same candidate ---
    keys = {}
    for producer in ("human", "skill", "fixture"):
        rc, res = run(scratch, nh, "propose",
                      envelope=proposal(DECISION, "supports", LEARNING,
                                        producer=producer))
        cand = (res or {}).get("candidate")
        keys[producer] = (cand or {}).get("candidate_key"), \
            (res or {}).get("subject_key"), (cand or {}).get("producer")
        check("legal proposal from %s exits 0 with a candidate" % producer,
              rc == 0 and cand is not None)
    check("human/skill/fixture reduce to the SAME candidate_key",
          keys["human"][0] == keys["skill"][0] == keys["fixture"][0]
          and keys["human"][0] is not None)
    check("...and the SAME subject_key",
          keys["human"][1] == keys["skill"][1] == keys["fixture"][1])
    check("...differing ONLY in recorded producer provenance",
          {keys["human"][2], keys["skill"][2], keys["fixture"][2]}
          == {"human", "skill", "fixture"})

    # --- Uncertainty is provenance only: never changes the candidate ---
    _, base = run(scratch, nh, "propose",
                  envelope=proposal(DECISION, "supports", LEARNING))
    _, unc = run(scratch, nh, "propose",
                 envelope=proposal(DECISION, "supports", LEARNING,
                                   uncertainty="I am only 40% sure"))
    check("model uncertainty never changes the candidate_key",
          (base or {}).get("candidate", {}).get("candidate_key")
          == (unc or {}).get("candidate", {}).get("candidate_key"))

    # --- Candidate is reviewable: source/rel/target kinds visible ---
    cand = (base or {}).get("candidate", {})
    check("candidate exposes source_kind/relationship/target_kind for review",
          cand.get("source_kind") == "decision"
          and cand.get("relationship") == "supports"
          and cand.get("target_kind") == "learning")

    # --- Illegal-combo battery: skill path == human path, no candidate ---
    battery = [
        ("reserved implements (decision -> learning)",
         DECISION, "implements", LEARNING),
        ("cross-kind supersedes (decision -> learning)",
         DECISION, "supersedes", LEARNING),
        ("reversed resolves (question -> decision)",
         QUESTION, "resolves", DECISION),
        ("wrong target kind for motivates (decision -> learning)",
         DECISION, "motivates", LEARNING),
    ]
    for desc, s, rel, t in battery:
        rc_s, res_s = run(scratch, nh, "propose",
                          envelope=proposal(s, rel, t, producer="skill"))
        rc_h, res_h = run(scratch, nh, "propose",
                          envelope=proposal(s, rel, t, producer="human"))
        no_cand = (res_s or {}).get("candidate") is None \
            and (res_h or {}).get("candidate") is None
        check("illegal %s: rejected, no candidate minted" % desc,
              rc_s == 1 and rc_h == 1 and no_cand)
        check("illegal %s: skill and human paths give identical findings"
              % desc, finding_codes(res_s) == finding_codes(res_h)
              and finding_codes(res_s) != [])

    # --- Reversed contradicts collapses to one canonical candidate ---
    _, fwd = run(scratch, nh, "propose",
                 envelope=proposal(DECISION, "contradicts", LEARNING))
    _, rev = run(scratch, nh, "propose",
                 envelope=proposal(LEARNING, "contradicts", DECISION))
    check("reversed contradicts collapses to one canonical candidate_key",
          (fwd or {}).get("candidate", {}).get("candidate_key")
          == (rev or {}).get("candidate", {}).get("candidate_key")
          and (fwd or {}).get("candidate") is not None)

    # --- A skill cannot fabricate a candidate via an advisory key ---
    bogus = "candidate:sha256:" + "0" * 64
    rc, res = run(scratch, nh, "propose",
                  envelope=proposal(DECISION, "supports", LEARNING,
                                    producer="skill", advisory=bogus))
    check("skill-supplied mismatched candidate key is rejected, not trusted",
          rc == 1 and (res or {}).get("candidate") is None
          and "E_PROPOSAL_ADVISORY_KEY_MISMATCH" in finding_codes(res))

    # --- An illegal proposal can never be confirmed ---
    rc, res = run(scratch, nh, "confirm", "--candidate-key",
                  "candidate:sha256:" + "a" * 64, "--decision", "accepted",
                  envelope=proposal(DECISION, "implements", LEARNING,
                                    producer="skill"))
    ledger = os.path.join(nh, "projects", "proj", ".bindle", "context",
                          "judgments.jsonl")
    check("confirm refuses an illegal proposal and writes no judgment",
          rc != 0 and not os.path.exists(ledger))


def validator_layer():
    """GitHub-endpoint illegal combos: same authority the CLI uses, in-memory
    preview so no network/repo binding is needed."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "bin"))
    from context_graph import proposals  # noqa: E402

    pr = {"id": "github-pr:o/r#1", "class": "evidence", "kind": "github_pr",
          "label": "PR 1", "status": "active"}
    issue = {"id": "github-issue:o/r#2", "class": "evidence",
             "kind": "github_issue", "label": "Issue 2", "status": "active"}
    dec = {"id": DECISION, "class": "semantic", "kind": "decision",
           "label": "D", "status": "active"}
    lrn = {"id": LEARNING, "class": "semantic", "kind": "learning",
           "label": "L", "status": "active"}
    preview = {"schema_version": 1, "project_id": "project:deadbeef",
               "nodes": [pr, issue, dec, lrn], "edges": [],
               "identity_anchor_candidates": [], "conflicts": [],
               "coverage": {}}

    cases = [
        ("issue closes PR (closes is github_pr -> github_issue)",
         proposal(issue["id"], "closes", pr["id"], producer="skill")),
        ("learning implemented_by PR (implemented_by is decision -> github_pr)",
         proposal(LEARNING, "implemented_by", pr["id"], producer="skill")),
    ]
    for desc, prop in cases:
        res = proposals.validate_edge_proposal(prop, preview)
        check("illegal %s: rejected by the shared validator, no candidate"
              % desc, res["candidate"] is None
              and res["findings"] and res["findings"][0]["code"]
              == "E_PROPOSAL_ILLEGAL_ENDPOINT")

    # Legal counterpart stays reviewable (decision implemented_by PR).
    res = proposals.validate_edge_proposal(
        proposal(DECISION, "implemented_by", pr["id"], producer="skill"),
        preview)
    check("legal decision implemented_by PR remains a reviewable candidate",
          res["candidate"] is not None and res["findings"] == [])


def main():
    if not os.path.exists(CLI):
        print("cannot find CLI at %s" % CLI)
        return 1
    scratch = tempfile.mkdtemp()
    print("== real-CLI subprocess layer ==")
    cli_layer(scratch)
    print("== shared-validator layer (github endpoints) ==")
    validator_layer()
    print()
    print("test-context-graph-skill: %d passed, %d failed" % (_passed, _failed))
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
