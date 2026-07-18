"""context_graph.compiler — the deterministic, read-only context-graph
compiler (issue #183, epic #140).

Implements the ten-phase pipeline frozen by
docs/design/2026-07-17-context-graph-foundation.md section 3:

  load configuration (read-only)
  validate roots and ownership
  parse map entries
  normalize evidence through #181
  resolve available sources (sessions, handoffs, documents, GitHub)
  construct deterministic nodes and edges
  validate graph invariants (via context_graph.validation)
  emit deterministic identity-anchor candidates
  classify conflicts and unresolved items
  render preview

Every phase is pure or read-only I/O; none writes. This module stops before
judgment reduction -- it never loads or reduces `judgments.jsonl` (#184's
job) -- and it never infers, proposes, or computes a candidate key for any
semantic (edge) relationship (#184's job too). The only candidates this
module ever produces are deterministic `identity_anchor` candidates for
currently-unanchored map entries.
"""
import os

from context_graph import canonical
from context_graph import config
from context_graph import evidence as evidence_mod
from context_graph import github_adapter as github_adapter_mod
from context_graph import map_parser
from context_graph import relationships as rel
from context_graph import validation

MAP_FILENAME = "map.md"

# All five semantic kinds the compiler ever produces a node for.
_SEMANTIC_KINDS = frozenset({"decision", "learning", "assumption", "tension", "question"})


def _finding(code, message, line=None, **extra):
    d = {"code": code, "message": message, "line": line}
    d.update(extra)
    return d


class CompilerError(Exception):
    """Raised only when graph construction cannot proceed at all --
    missing/malformed configuration or an unreadable map. `.findings` is a
    non-empty list of {"code", "message", ...} dicts, the same shape
    context_graph.config/context_graph.validation already use."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f.get("message", "") for f in findings))


def _map_rel_path(project_slug):
    return "projects/%s/%s" % (project_slug, MAP_FILENAME)


def _map_abs_path(notes_home, project_slug):
    return os.path.join(notes_home, "projects", project_slug, MAP_FILENAME)


def _default_repository(cfg):
    for repo in cfg.get("repositories", []):
        if repo.get("default_for_bare_references"):
            return repo.get("coordinates")
    return None


def _binding_ids(cfg):
    return [r["binding_id"] for r in cfg.get("repositories", []) if r.get("binding_id")]


def _load_configuration(notes_home, project_slug):
    cfg_path = config.config_path(notes_home, project_slug)
    try:
        cfg = config.load_config(cfg_path)
    except config.ConfigError as exc:
        raise CompilerError(exc.findings) from exc
    if cfg is None:
        raise CompilerError([_finding(
            "E_CONFIG_MISSING",
            "no configuration found at %r -- run `context-graph.py init` "
            "(#191) before preview" % (cfg_path,),
        )])
    blocking = config.blocking_findings(cfg)
    if blocking:
        raise CompilerError(blocking)
    return cfg


def _validate_roots(cfg, repo_roots):
    """`--repo-root <alias>=<path>` accepts only aliases this project's
    configuration already knows about -- an unrecognized alias is a
    conflict, never a silently-accepted new binding (repository-binding
    identity and coordinates are #191-owned; #183 never invents one)."""
    conflicts = []
    known = {r.get("alias") for r in cfg.get("repositories", [])}
    for alias in sorted(repo_roots or {}):
        if alias not in known:
            conflicts.append(_finding(
                "unknown-repo-root-alias",
                "--repo-root alias %r is not a configured repository alias" % (alias,),
            ))
    return conflicts


def _read_map(notes_home, project_slug):
    """Returns (text_or_None, coverage). A missing map.md is not a hard
    failure -- knowledge-promotion may simply not have run yet for this
    project -- it degrades project_map coverage to "unavailable" rather
    than aborting the whole preview."""
    path = _map_abs_path(notes_home, project_slug)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), "complete"
    except FileNotFoundError:
        return None, "unavailable"
    except OSError as exc:
        raise CompilerError([_finding(
            "E_MAP_UNREADABLE", "cannot read project map at %r: %s" % (path, exc),
        )]) from exc


def _tokenize_or_empty(raw):
    raw = (raw or "").strip()
    if raw == "":
        return []
    atoms, _reason = evidence_mod.tokenize_field(raw)
    return atoms or []


def _basis_entry(pointer, location):
    return {"kind": "evidence_pointer", "location": location, "pointer": pointer}


def _collect_evidence_contributions(entry, project_id, repository, binding_ids):
    """Returns (contributions, conflicts). `contributions` is a list of
    (normalize() result dict, basis entry dict) pairs across the entry's own
    evidence field and, for a tension, both sides' fields -- #183 never
    tokenizes/splits itself; every field goes through
    evidence.normalize_field unchanged."""
    contributions = []
    conflicts = []

    def handle_field(raw, location):
        raw = (raw or "").strip()
        if raw == "":
            return
        field_result = evidence_mod.normalize_field(
            raw, project_id, repository=repository, binding_ids=binding_ids
        )
        if field_result["status"] == "field_rejected":
            conflicts.append(_finding(
                "unresolved-evidence-field",
                "evidence field could not be tokenized (%s): %r"
                % (field_result["reason"], raw),
                line=entry["line"],
            ))
            return
        atoms = _tokenize_or_empty(raw)
        for atom, result in zip(atoms, field_result["results"]):
            if result["status"] == "normalized":
                contributions.append((result, _basis_entry(atom, location)))
            else:
                conflicts.append(_finding(
                    "unresolved-evidence-pointer",
                    "evidence pointer %r did not resolve (%s: %s)"
                    % (atom, result["status"], result.get("reason")),
                    line=entry["line"],
                ))

    handle_field(entry["evidence_raw"], "entry_evidence")
    for side in entry["sides"] or []:
        handle_field(side["evidence_raw"], "tension_side")

    return contributions, conflicts


def _label_for_evidence(result, github_info):
    kind = result["kind"]
    if kind in ("session", "handoff", "document_repository", "document_project_local"):
        prefix = {"session": "session", "handoff": "handoff",
                  "document_repository": "document", "document_project_local": "document"}[kind]
        return "%s %s" % (prefix, result["path"])
    if kind in ("github_issue", "github_pr"):
        prefix = "Issue" if kind == "github_issue" else "PR"
        base = "%s %s#%s" % (prefix, result["repository"], result["number"])
        if github_info and github_info.get("status") == "ok" and github_info.get("title"):
            return "%s: %s" % (base, github_info["title"])
        return base
    return result["id"]


def _classify_coverage(statuses):
    if not statuses:
        return "unsupported"
    if all(s in ("ok", "missing") for s in statuses):
        return "complete"
    if all(s == "unavailable" for s in statuses):
        return "unavailable"
    return "partial"


def _deterministic_edge(source, relationship, target, det_source_kind, basis=None):
    return {
        "key": "%s|%s|%s" % (source, relationship, target),
        "source": source,
        "relationship": relationship,
        "target": target,
        "status": "confirmed",
        "origin": "deterministic",
        "review_trigger": rel.get_review_trigger_default(relationship),
        "basis": basis or [],
        "deterministic_source": {"kind": det_source_kind},
    }


def _node_class_kind(node):
    return node.get("class"), node.get("kind")


def compile_preview(notes_home, project_slug, repo_roots=None, github_adapter=None):
    """Run the full deterministic preview pipeline and return one preview
    dict. Writes nothing. Raises CompilerError only when configuration is
    missing/malformed or the map cannot be read at all -- every other
    problem (malformed entry, unresolved evidence, illegal edge) is
    reported inside the returned preview's "conflicts", never raised."""
    conflicts = []

    # Phase 1: load configuration (read-only).
    cfg = _load_configuration(notes_home, project_slug)
    project_id = cfg["project_id"]
    binding_ids = _binding_ids(cfg)
    default_repository = _default_repository(cfg)

    # Phase 2: validate roots and ownership.
    conflicts.extend(_validate_roots(cfg, repo_roots))

    # Phase 3: parse map entries.
    map_text, project_map_coverage = _read_map(notes_home, project_slug)
    parsed = {"entries": [], "conflicts": []} if map_text is None else map_parser.parse_project_map(map_text)
    conflicts.extend(parsed["conflicts"])
    map_rel_path = _map_rel_path(project_slug)

    adapter = github_adapter if github_adapter is not None else github_adapter_mod.GitHubAdapter()
    github_info_by_id = {}
    issue_statuses = []
    pr_statuses = []

    nodes_by_id = {}
    project_node = {
        "id": project_id,
        "class": "project",
        "kind": None,
        "label": cfg.get("display_name") or cfg.get("project_slug") or project_slug,
        "status": "current",
    }
    nodes_by_id[project_id] = project_node

    def ensure_evidence_node(result):
        node_id = result["id"]
        if node_id in nodes_by_id:
            return node_id
        github_info = None
        kind = result["kind"]
        if kind in ("github_issue", "github_pr"):
            owner, _, repo_name = result["repository"].partition("/")
            # Phase 5: resolve available sources -- read-only GitHub lookup.
            if kind == "github_issue":
                github_info = adapter.fetch_issue(owner, repo_name, result["number"])
                issue_statuses.append(github_info["status"])
            else:
                github_info = adapter.fetch_pr(owner, repo_name, result["number"])
                pr_statuses.append(github_info["status"])
            github_info_by_id[node_id] = (github_info, owner, repo_name, result["number"])
        nodes_by_id[node_id] = {
            "id": node_id,
            "class": "evidence",
            "kind": kind,
            "label": _label_for_evidence(result, github_info),
            "status": "current",
        }
        return node_id

    # Phase 6a: construct semantic nodes for every anchored entry, and
    # identity-anchor candidates for every unanchored one. Two passes are
    # required because a `supersedes` edge's source (the replacement) may
    # appear before or after its target (the retired tombstone) in the map.
    anchor_candidates = []
    anchored_entries = []
    for entry in parsed["entries"]:
        if not entry["anchored"]:
            fp = canonical.entry_fingerprint(
                project_id, map_rel_path, entry["section"], entry["kind"], entry["entry_bytes"]
            )
            key = canonical.anchor_candidate_key(
                project_id, map_rel_path, entry["section"], entry["kind"], fp
            )
            dep_fp = canonical.anchor_dependency_fingerprint(
                project_id, map_rel_path, entry["section"], entry["kind"], fp
            )
            anchor_candidates.append({
                "subject_type": "identity_anchor",
                "candidate_key": key,
                "candidate_origin": "deterministic_compiler",
                "dependency_fingerprint": dep_fp,
                "validation_status": "valid",
                "project_id": project_id,
                "map_path": map_rel_path,
                "section": entry["section"],
                "entry_kind": entry["kind"],
                "entry_fingerprint": fp,
                "display_claim": entry["label"],
            })
            continue

        node = {
            "id": entry["id"],
            "class": "semantic",
            "kind": entry["kind"],
            "label": entry["label"],
            "status": entry["status"],
        }
        if entry["confidence"] is not None:
            node["confidence"] = entry["confidence"]
        if entry["kind"] == "tension":
            node["sides"] = [
                {"label": s["label"], "evidence": _tokenize_or_empty(s["evidence_raw"])}
                for s in entry["sides"]
            ]
        if entry["id"] in nodes_by_id:
            conflicts.append(_finding(
                "duplicate-semantic-node",
                "map entry id %r already used by another node" % (entry["id"],),
                line=entry["line"],
            ))
            continue
        nodes_by_id[entry["id"]] = node
        anchored_entries.append(entry)

    edges = []

    def try_add_edge(edge, line):
        source_node = nodes_by_id.get(edge["source"])
        target_node = nodes_by_id.get(edge["target"])
        if source_node is None or target_node is None:
            conflicts.append(_finding(
                "illegal-deterministic-edge",
                "edge %r references a node not present in the graph" % (edge["key"],),
                line=line,
            ))
            return
        src_class, src_kind = _node_class_kind(source_node)
        tgt_class, tgt_kind = _node_class_kind(target_node)
        result = rel.validate_endpoint_pair(edge["relationship"], src_class, src_kind, tgt_class, tgt_kind)
        if not result["ok"]:
            conflicts.append(_finding(
                "illegal-deterministic-edge",
                "relationship %r: %s/%s -> %s/%s is not a legal endpoint pair"
                % (edge["relationship"], src_class, src_kind, tgt_class, tgt_kind),
                line=line,
            ))
            return
        edges.append(edge)

    # Phase 6b: deterministic edges -- contains, supported_by, supersedes.
    for entry in anchored_entries:
        try_add_edge(
            _deterministic_edge(project_id, "contains", entry["id"], "project_membership"),
            entry["line"],
        )

        contributions, ev_conflicts = _collect_evidence_contributions(
            entry, project_id, default_repository, binding_ids
        )
        conflicts.extend(ev_conflicts)
        by_evidence_id = {}
        for result, basis in contributions:
            bundle = by_evidence_id.setdefault(result["id"], {"result": result, "basis": {}})
            bundle["basis"][(basis["location"], basis["pointer"])] = basis
        for evidence_id, bundle in sorted(by_evidence_id.items()):
            ensure_evidence_node(bundle["result"])
            basis_list = [bundle["basis"][k] for k in sorted(bundle["basis"])]
            try_add_edge(
                _deterministic_edge(
                    entry["id"], "supported_by", evidence_id, "map_evidence_pointer",
                    basis=basis_list,
                ),
                entry["line"],
            )

        if entry["superseded_by"] and entry["superseded_by"] in nodes_by_id:
            try_add_edge(
                _deterministic_edge(
                    entry["superseded_by"], "supersedes", entry["id"], "map_tombstone",
                ),
                entry["line"],
            )
        elif entry["superseded_by"]:
            conflicts.append(_finding(
                "unresolved-supersedes",
                "bindle:superseded-by %r does not name an anchored node in "
                "this graph" % (entry["superseded_by"],),
                line=entry["line"],
            ))

    # Phase 5 (continued) / closes: for every github_pr evidence node
    # discovered, ask GitHub for its own declared closing references --
    # never inferred from title/body text.
    for node_id, (github_info, owner, repo_name, number) in list(github_info_by_id.items()):
        node = nodes_by_id.get(node_id)
        if node is None or node["kind"] != "github_pr" or github_info.get("status") != "ok":
            continue
        closes_result = adapter.fetch_pr_closes(owner, repo_name, number)
        if closes_result.get("status") != "ok":
            continue
        for issue_number in closes_result.get("closes", []):
            issue_fetch = adapter.fetch_issue(owner, repo_name, issue_number)
            issue_statuses.append(issue_fetch["status"])
            if issue_fetch.get("status") != "ok":
                continue
            issue_id = "github-issue:%s/%s#%d" % (owner, repo_name, issue_number)
            if issue_id not in nodes_by_id:
                nodes_by_id[issue_id] = {
                    "id": issue_id, "class": "evidence", "kind": "github_issue",
                    "label": _label_for_evidence(
                        {"kind": "github_issue", "repository": "%s/%s" % (owner, repo_name),
                         "number": issue_number},
                        issue_fetch,
                    ),
                    "status": "current",
                }
            try_add_edge(
                _deterministic_edge(node_id, "closes", issue_id, "github_closure"), None
            )

    nodes = sorted(nodes_by_id.values(), key=lambda n: n["id"])
    edges = sorted(edges, key=lambda e: e["key"])
    anchor_candidates = sorted(anchor_candidates, key=lambda c: c["candidate_key"])

    # Phase 7: validate graph invariants -- a final integrity pass. Any
    # survivor here indicates a construction bug upstream (every edge was
    # already endpoint-checked before admission), so it is reported rather
    # than silently dropped or allowed to crash the whole preview.
    bundle = {"config": cfg, "nodes": nodes, "edges": edges, "candidates": anchor_candidates, "judgments": []}
    for f in validation.validate_bundle(bundle):
        conflicts.append(_finding(
            "post-construction-invariant-violation",
            "%s: %s" % (f["code"], f["message"]),
        ))

    coverage = {
        "project_map": project_map_coverage,
        "sessions": "complete" if any(n["kind"] == "session" for n in nodes) else "unsupported",
        "handoffs": "complete" if any(n["kind"] == "handoff" for n in nodes) else "unsupported",
        "documents": "complete" if any(
            n["kind"] in ("document_repository", "document_project_local") for n in nodes
        ) else "unsupported",
        "github_issues": _classify_coverage(issue_statuses),
        "github_prs": _classify_coverage(pr_statuses),
        "commits": "unsupported",
    }

    conflicts = sorted(conflicts, key=lambda c: (c.get("line") or 0, c["code"]))

    return {
        "schema_version": 1,
        "project_id": project_id,
        "nodes": nodes,
        "edges": edges,
        "identity_anchor_candidates": anchor_candidates,
        "conflicts": conflicts,
        "coverage": coverage,
    }
