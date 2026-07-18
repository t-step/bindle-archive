"""context_graph.review -- orchestration for #184's propose/confirm/candidates.
Glues the #183 deterministic preview, proposal validation, and the append-only
ledger. `propose` writes nothing and never locks; `confirm` takes the
single-writer lock and appends exactly one judgment event."""
import secrets
from datetime import datetime, timezone

from context_graph import canonical, compiler, config, ids, ledger, lock, proposals

ANCHOR_KEY_PREFIX = "anchor-candidate:sha256:"
_DECISIONS = ("accepted", "rejected", "retired")


class ReviewError(Exception):
    """Raised only when the current graph itself cannot be compiled (missing
    or malformed #191 configuration, an unreadable map). `.findings` mirrors
    `compiler.CompilerError.findings` so the CLI can render it uniformly with
    every other findings-shaped error."""

    def __init__(self, message, findings=None):
        super().__init__(message)
        self.findings = findings or [{"code": "E_REVIEW", "message": message}]


def _preview(notes_home, slug, repo_roots, github_adapter):
    try:
        return compiler.compile_preview(
            notes_home, slug, repo_roots=repo_roots, github_adapter=github_adapter)
    except compiler.CompilerError as exc:
        raise ReviewError("cannot compile current graph", findings=exc.findings) from exc


def propose(notes_home, slug, proposal, repo_roots=None, github_adapter=None):
    """Validate an edge proposal against a FRESH #183 preview. Returns
    {"candidate": dict|None, "subject_key": str|None, "findings": [dict]}.
    Writes nothing; takes no lock (design section 4, L266-272)."""
    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    return proposals.validate_edge_proposal(proposal, preview)


def _now_iso(now):
    return now if now is not None else datetime.now(timezone.utc).isoformat()


def _anchor_by_key(preview, candidate_key):
    """Recompute anchor_candidate_key over every fresh preview's anchor
    candidate and return the one matching candidate_key, or None."""
    for c in preview.get("identity_anchor_candidates", []):
        recomputed = canonical.anchor_candidate_key(
            c["project_id"], c["map_path"], c["section"], c["entry_kind"],
            c["entry_fingerprint"])
        if recomputed == candidate_key:
            return c
    return None


def confirm(notes_home, slug, candidate_key, decision, proposal=None,
            repo_roots=None, github_adapter=None, now=None):
    """Revalidate `candidate_key` against the CURRENT graph and append
    exactly one judgment event under the single-writer "confirm" lock.
    Returns {"event": dict|None, "idempotent": bool, "findings": [dict]}.

    Propose-time validation is never trusted here (design section 11):
    an edge decision re-runs validate_edge_proposal against a fresh
    preview and an identity_anchor decision re-locates the candidate in a
    fresh preview's identity_anchor_candidates -- either can legitimately
    have gone stale between propose and confirm."""
    if decision not in _DECISIONS:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "E_CONFIRM_INVALID_DECISION",
                              "message": "decision %r not one of %s"
                              % (decision, _DECISIONS)}]}

    cdir = config.context_dir(notes_home, slug)
    path = ledger.judgments_path(notes_home, slug)
    is_anchor = candidate_key.startswith(ANCHOR_KEY_PREFIX)

    with lock.ProjectLock(cdir, "confirm"):
        existing = ledger.load_judgments(path)
        reduced = ledger.reduce_judgments(existing)

        # Idempotency short-circuit (design section 11): an already-effective
        # accepted candidate_key appends nothing.
        if decision == "accepted":
            for cur in reduced["effective"].values():
                if cur["candidate_key"] == candidate_key:
                    return {"event": None, "idempotent": True, "findings": []}

        if is_anchor:
            return _confirm_anchor(notes_home, slug, candidate_key, decision,
                                    repo_roots, github_adapter, path, now)
        return _confirm_edge(notes_home, slug, candidate_key, decision, proposal,
                              repo_roots, github_adapter, path, now)


def _confirm_edge(notes_home, slug, candidate_key, decision, proposal,
                   repo_roots, github_adapter, path, now):
    if decision == "retired":
        # Retirement names a prior candidate_key and never revalidates or
        # allocates (issue body).
        subject_key = _edge_subject_from_key_only(candidate_key, path)
        if subject_key is None:
            return {"event": None, "idempotent": False,
                    "findings": [{"code": "E_CONFIRM_UNKNOWN_CANDIDATE",
                                  "message": "no prior event names %s" % candidate_key}]}
        event = {"schema_version": 1, "subject_type": "edge",
                 "subject_key": subject_key, "candidate_key": candidate_key,
                 "decision": "retired", "decided_at": _now_iso(now)}
        ledger.append_judgment(path, event)
        return {"event": event, "idempotent": False, "findings": []}

    if proposal is None:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "E_CONFIRM_INPUT_REQUIRED",
                              "message": "edge %s requires --input" % decision}]}

    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    result = proposals.validate_edge_proposal(proposal, preview)
    if result["candidate"] is None:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "candidate_stale_illegal", "message": f["message"]}
                             for f in result["findings"]]}

    recomputed_key = result["candidate"]["candidate_key"]
    if recomputed_key != candidate_key:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "E_CONFIRM_KEY_MISMATCH",
                              "message": "recomputed %s != --candidate-key %s"
                              % (recomputed_key, candidate_key)}]}

    c = result["candidate"]
    event = {"schema_version": 1, "subject_type": "edge",
             "subject_key": result["subject_key"], "candidate_key": candidate_key,
             "decision": decision, "decided_at": _now_iso(now)}
    if decision == "accepted":
        # Embedded edge content -- needed by reduction-time revalidation and
        # #185's materialization, neither of which re-reads the proposal.
        event.update({"source": c["source"], "relationship": c["relationship"],
                      "target": c["target"], "basis": c["basis"]})
    ledger.append_judgment(path, event)
    return {"event": event, "idempotent": False, "findings": []}


def _edge_subject_from_key_only(candidate_key, path):
    """Retirement names only a candidate_key; recover its subject_key from
    ledger history (the most recent event naming that key)."""
    subject_key = None
    for ev in ledger.load_judgments(path):
        if (ev.get("subject_type") == "edge"
                and ev.get("candidate_key") == candidate_key
                and "subject_key" in ev):
            subject_key = ev["subject_key"]
    return subject_key


def _prior_anchor_acceptance(path, candidate_key):
    """The most recent accepted identity_anchor event naming candidate_key,
    or None. `retired` of an anchor names a prior acceptance by the SAME
    candidate_key (the map slot's bytes have not changed), mirroring
    `_edge_subject_from_key_only`."""
    prior = None
    for ev in ledger.load_judgments(path):
        if (ev.get("subject_type") == "identity_anchor"
                and ev.get("candidate_key") == candidate_key
                and ev.get("decision") == "accepted"):
            prior = ev
    return prior


def _confirm_anchor(notes_home, slug, candidate_key, decision, repo_roots,
                     github_adapter, path, now):
    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    c = _anchor_by_key(preview, candidate_key)
    prior = _prior_anchor_acceptance(path, candidate_key)

    if c is not None:
        subject_key = canonical.anchor_subject_key(
            c["project_id"], c["map_path"], c["section"], c["entry_kind"])
        entry_fp = c["entry_fingerprint"]
    elif prior is not None:
        subject_key = prior.get("subject_key")
        entry_fp = prior.get("entry_fingerprint")
    else:
        return {"event": None, "idempotent": False,
                "findings": [{"code": "candidate_stale_illegal",
                              "message": "no current or prior anchor for %s" % candidate_key}]}

    if decision == "accepted" and c is None:
        # A fresh acceptance always needs a live candidate to revalidate
        # against; a prior acceptance alone (candidate now gone from the
        # current graph) cannot ground a NEW acceptance.
        return {"event": None, "idempotent": False,
                "findings": [{"code": "candidate_stale_illegal",
                              "message": "no current anchor candidate for %s" % candidate_key}]}

    event = {"schema_version": 1, "subject_type": "identity_anchor",
             "subject_key": subject_key, "candidate_key": candidate_key,
             "decision": decision, "decided_at": _now_iso(now)}

    if decision == "accepted":
        # Allocate the opaque id internally -- never accepted from the
        # caller (schema-required assigned_id + entry_fingerprint).
        event["assigned_id"] = ids.format_context_node_id(slug, secrets.token_hex(16))
        event["entry_fingerprint"] = entry_fp
    else:
        # rejected/retired: judgment.schema.json requires assigned_id and
        # entry_fingerprint on every identity_anchor event regardless of
        # decision. `retired` names a prior acceptance, so its assigned_id
        # comes from that acceptance. A `rejected` of a candidate that was
        # never accepted has no id to carry -- "" is schema-valid (the
        # property is an unconstrained string) and documents "no id was
        # ever allocated" rather than fabricating one.
        event["assigned_id"] = (prior or {}).get("assigned_id", "")
        event["entry_fingerprint"] = entry_fp or (prior or {}).get("entry_fingerprint", "")

    ledger.append_judgment(path, event)
    return {"event": event, "idempotent": False, "findings": []}


def list_candidates(notes_home, slug, subject_type=None, status=None,
                    repo_roots=None, github_adapter=None):
    """Union of live #183 anchor regeneration and persisted ledger history.
    Read-only: validates/generates nothing new, takes no lock (design
    section 4, L241-257). Returns {"rows": [dict], "findings": [dict]}."""
    rows = []
    want_pending = status in (None, "pending")
    want_ledger = status in (None, "accepted", "rejected", "retired")

    if want_pending and subject_type in (None, "identity_anchor"):
        preview = _preview(notes_home, slug, repo_roots, github_adapter)
        for c in preview.get("identity_anchor_candidates", []):
            rows.append({"subject_type": "identity_anchor", "status": "pending",
                         "candidate_origin": c["candidate_origin"],
                         "candidate_key": c["candidate_key"],
                         "display_claim": c.get("display_claim")})
    # Pending edge candidates never persist -> nothing to list (by construction).

    if want_ledger:
        path = ledger.judgments_path(notes_home, slug)
        events = ledger.load_judgments(path)
        reduced = ledger.reduce_judgments(events)
        # rejected_keys/retired_keys are monotonic sets on the reducer (never
        # pruned -- relied on elsewhere for propose-time suppression), so a
        # naive per-event walk would emit a stale rejected/retired row
        # alongside a later re-acceptance of the same candidate_key, or one
        # row per repeated identical decision. Project ledger history down to
        # AT MOST ONE row per candidate_key: that key's most-recent event in
        # append order (last event wins), keeping first-seen order for the
        # row list.
        latest_by_key = {}
        key_order = []
        for ev in events:
            key = ev.get("candidate_key")
            if key not in latest_by_key:
                key_order.append(key)
            latest_by_key[key] = ev
        for key in key_order:
            ev = latest_by_key[key]
            st = _ledger_row_status(ev, reduced)
            if st is None or (status is not None and st != status):
                continue
            if subject_type is not None and ev.get("subject_type") != subject_type:
                continue
            rows.append({"subject_type": ev.get("subject_type"), "status": st,
                         "candidate_origin": "validated_proposal"
                         if ev.get("subject_type") == "edge" else "deterministic_compiler",
                         "candidate_key": ev.get("candidate_key")})
    return {"rows": rows, "findings": []}


def _ledger_row_status(ev, reduced):
    key = ev.get("candidate_key")
    if ev.get("decision") == "accepted":
        for cur in reduced["effective"].values():
            if cur["candidate_key"] == key:
                return "accepted"
        return None  # superseded/revoked acceptance is not a current row
    if ev.get("decision") == "rejected" and key in reduced["rejected_keys"]:
        return "rejected"
    if ev.get("decision") == "retired" and key in reduced["retired_keys"]:
        return "retired"
    return None
