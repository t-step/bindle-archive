"""architecture.planner — the projection plan and its fingerprint
(issue #230 child D, slice D3, epic #141).

A CONFIRMATION BINDS THE PLAN IT WAS GIVEN FOR. The epic freezes it: preview
emits a plan fingerprint, and apply recomputes it and aborts as
`stale_preview` if it differs, "rather than writing a plan the user never
saw". Without it a `git pull` between preview and apply writes a plan nobody
confirmed and mints identities nobody reviewed. `plan_context_md` detects
FILE-side drift only, never input-side drift, so it cannot serve here.

THE FINGERPRINT TRAVELS AS A TOKEN, NOT AS STATE. Nothing in this module
writes anything. `apply-state.json` is barred from carrying it three ways
over -- FC-5 gives that file "interrupted-apply recovery metadata only" and
"any semantic role whatsoever" as its explicit non-role, its schema is
`additionalProperties: false`, and B's native validator admits no optional
keys -- and a sixth file under the architecture directory would extend
child B's frozen notes-home tree contract. So preview prints the digest and
apply is handed it back, matching this repo's `--approval-token` idiom:
ephemeral invocation state, not a persisted marker.

THE DIGEST READS BANDS, NOT RAW MEASUREMENTS. The candidate term is
`diffs.fingerprint`, which excludes `bindings` and compares metrics as
bands. Digesting raw records would abort a legitimately confirmed plan every
time a fan-in moved 21 -> 22, and would re-import through the fingerprint
exactly the `bindings` churn that C3 excluded to keep PT31 reachable. The
binding term carries source commits separately and explicitly, so provenance
movement is still detected -- it is just detected where it means something.

THE CONFIG TERM IS THE VALIDATED DOCUMENT, NOT THE FILE BYTES. Reformatting
`config.json`, or an editor appending a newline, changes no input to the
plan; aborting on it would burn an operator's confirmation for nothing. A
config that does not validate is refused outright rather than digested,
because a fingerprint over a malformed document compares equal to itself and
would carry the malformation into apply.

DETERMINISM, NOT EQUIVALENCE. This module asserts that an identical
interchange yields a byte-identical plan. It does NOT assert that two
adapters yield equivalent plans: PT7b is a combined D+E release gate, child
E (#231) is unstarted, and a plan cannot be compared against a producer that
does not exist. Determinism is PT7b's precondition and is testable today
against the reference provider alone; equivalence is discharged at the
release gate, with E, and is not claimed here.

THE CAP MARKS, IT DOES NOT DROP. An over-cap candidate appears in the plan
as an explicit no-op entry rather than being omitted, so preview can report
it. `epic` freezes that such a node is retained, never auto-deleted and
never auto-staled -- omitting it from the plan would leave a note on disk
that no surface mentions, waiting on child G (#236, unstarted) to stale it.
Same reasoning #230 settled on for `orphaned_by_resume`: classification is
the honest MVP outcome.

Ranking spells the flag `over_cap` and so does this module. #372 settled that
as the authoritative spelling, declared on the `caps.over_cap_behavior`
description in `schemas/architecture/v1/config.schema.json`; the retired
`below_cap_threshold` named the same flag, not another one.
"""
import hashlib
import json

from architecture import candidates
from architecture import diffs
from architecture import ranking
from architecture import state
from context_graph import containment

PLAN_FINGERPRINT_PREFIX = "arch-plan:sha256:"

# Domain-separated from every other digest in the kit. A plan is not a
# judgment record, and an untagged digest could be presented as one.
_PLAN_TAG = b"bindle-arch-plan-fingerprint-v1"

# Exactly the terms #230 freezes for the fingerprint. Sorted so the tuple
# reads the same way the digest payload does.
FINGERPRINT_TERMS = ("bindings", "candidates", "config", "manifest", "provider")

# `noop` covers both "nothing moved" and "over cap": neither writes bytes,
# and preview distinguishes them by the `over_cap` flag on the entry.
DISPOSITIONS = ("mint", "refresh", "noop")


class PlanInputError(Exception):
    """Input a plan cannot be built from honestly."""


def _binding_term(bindings):
    """Per-binding source commits, keyed and ordered by binding id."""
    if bindings is None:
        return {}
    if not isinstance(bindings, dict):
        raise PlanInputError("bindings term must be a mapping, got %r"
                             % (type(bindings),))
    term = {}
    for binding_id, observed in sorted(bindings.items()):
        if isinstance(observed, dict):
            term[binding_id] = observed.get("source_commit")
        else:
            term[binding_id] = observed
    return term


def _provider_term(provider):
    """Provider name and version, and nothing else about it."""
    if provider is None:
        return {}
    if not isinstance(provider, dict):
        raise PlanInputError("provider term must be a mapping, got %r"
                             % (type(provider),))
    return {"name": provider.get("name"), "version": provider.get("version")}


def _config_term(config):
    """The validated config document. Refuses one that does not conform --
    see the module docstring on why a malformed document is not digested."""
    if config is None:
        return {}
    findings = state.validate_config(config)
    if findings:
        raise PlanInputError(
            "config does not validate; refusing to fingerprint it: %s"
            % ("; ".join(sorted(f.get("code", "?") for f in findings)),))
    return config


def _candidate_term(records):
    """Band-level readings of every candidate, ordered by candidate_key."""
    if records is None:
        return []
    try:
        readings = [diffs.fingerprint(record) for record in records]
    except diffs.DiffInputError as exc:
        raise PlanInputError("candidate term is not comparable: %s" % (exc,))
    return sorted(readings, key=lambda reading: reading["candidate_key"])


def plan_fingerprint(terms):
    """Digest over the inputs a confirmation binds.

    `terms` carries exactly FINGERPRINT_TERMS. An unknown or missing term is
    refused rather than defaulted: a digest that silently dropped a term it
    did not recognise would compare EQUAL across a real change, and the
    failure would surface as an apply that wrote a plan nobody confirmed.
    """
    if not isinstance(terms, dict):
        raise PlanInputError("terms must be a mapping, got %r" % (type(terms),))
    present = frozenset(terms)
    expected = frozenset(FINGERPRINT_TERMS)
    unknown = sorted(present - expected)
    if unknown:
        raise PlanInputError("unknown fingerprint term(s): %s"
                             % (", ".join(unknown),))
    missing = sorted(expected - present)
    if missing:
        raise PlanInputError("missing fingerprint term(s): %s"
                             % (", ".join(missing),))

    payload = {
        "bindings": _binding_term(terms["bindings"]),
        "candidates": _candidate_term(terms["candidates"]),
        "config": _config_term(terms["config"]),
        "manifest": sorted(terms["manifest"] or []),
        "provider": _provider_term(terms["provider"]),
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    digest = hashlib.sha256(b"\0".join((_PLAN_TAG, serialized))).hexdigest()
    return PLAN_FINGERPRINT_PREFIX + digest


def _note_path(candidate_key, projection_type, identity):
    """The vault-relative path for one candidate.

    An identity may carry its own `note_path` -- the creation-event path,
    which a rename never recomputes. Only a candidate without one has its
    path formatted here, from the projection type the RECORD carries and the
    creation-event slug the identity supplies. The planner never derives a
    slug itself: that is a creation event, and creation events belong to
    child B's identity allocation.
    """
    if not isinstance(identity, dict):
        raise PlanInputError("identity for %r must be a mapping, got %r"
                             % (candidate_key, type(identity)))
    carried = identity.get("note_path")
    if carried is not None:
        return carried
    try:
        return state.format_note_path(projection_type, identity.get("slug"))
    except ValueError as exc:
        raise PlanInputError("cannot place %r: %s" % (candidate_key, exc))


def _cap_from(config):
    if not isinstance(config, dict):
        return None
    caps = config.get("caps")
    if not isinstance(caps, dict):
        return None
    return caps.get("max_nodes")


def plan(records, previous=(), config=None, identities=None, notes_root="",
         bindings=None, provider=None):
    """Build this run's projection plan.

        {"entries": ({"candidate_key", "projection_type", "note_path",
                      "disposition", "rank", "over_cap"}, ...),
         "fingerprint": "arch-plan:sha256:...",
         "over_cap": (candidate_key, ...),
         "applied": {...}}

    Entries are ordered by `candidate_key`, so the plan is a pure function of
    its inputs and not of the order they arrived in.
    """
    identities = identities or {}
    records = list(records or ())

    try:
        ranked = ranking.rank(records, cap=_cap_from(config))
    except ranking.RankingInputError as exc:
        raise PlanInputError("cannot rank candidates: %s" % (exc,))
    ranking_by_key = {row["candidate_key"]: row for row in ranked["ranked"]}

    previous_readings = {}
    for record in previous or ():
        try:
            reading = diffs.fingerprint(record)
        except diffs.DiffInputError as exc:
            raise PlanInputError("previous candidate is not comparable: %s"
                                 % (exc,))
        previous_readings[reading["candidate_key"]] = reading

    entries = []
    for record in sorted(records, key=lambda r: r["candidate_key"]):
        key = record["candidate_key"]
        identity = identities.get(key, {})
        row = ranking_by_key.get(key, {})
        over_cap = bool(row.get("over_cap"))
        projection_type = record.get("projection_type")

        if over_cap:
            disposition = "noop"
        elif key not in previous_readings:
            disposition = "mint"
        else:
            try:
                current = diffs.fingerprint(record)
            except diffs.DiffInputError as exc:
                raise PlanInputError("candidate %r is not comparable: %s"
                                     % (key, exc))
            disposition = ("noop" if current == previous_readings[key]
                           else "refresh")

        entries.append({
            "candidate_key": key,
            "projection_type": projection_type,
            "note_path": _note_path(key, projection_type, identity),
            "disposition": disposition,
            "rank": row.get("rank"),
            "over_cap": over_cap,
        })

    verdict, offenders = containment.check_plan(
        notes_root, [entry["note_path"] for entry in entries])
    if verdict != "contained":
        raise PlanInputError(
            "planned path(s) escape the notes home; the whole plan is "
            "rejected: %s" % ("; ".join(path for path, _ in offenders),))

    manifest = [entry["note_path"] for entry in entries
                if entry["disposition"] != "noop"]
    fingerprint = plan_fingerprint({
        "bindings": bindings,
        "candidates": records,
        "config": config,
        "manifest": manifest,
        "provider": provider,
    })

    return {
        "entries": tuple(entries),
        "manifest": tuple(manifest),
        "fingerprint": fingerprint,
        "over_cap": tuple(ranked["over_cap"]),
        "applied": {
            "cap": ranked["cap"],
            "cap_exempt_keys": tuple(ranking.CAP_EXEMPT_KEYS),
            "fingerprint_excluded_fields": tuple(diffs.EXCLUDED_FIELDS),
            "fingerprint_terms": FINGERPRINT_TERMS,
        },
    }
