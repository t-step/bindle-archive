"""architecture.matcher — the confidence-gated continuity matcher (issue
#228, epic #141): which of this run's candidates ARE the identities the
project already confirmed, and which are new.

Matching is a BIPARTITE ASSIGNMENT between this run's candidates and the
LIVE confirmed identities, not an independent per-candidate score, and it
has FOUR EXHAUSTIVE OUTCOMES — every candidate reaches exactly one:

  * mint      — no live identity scores above the low threshold. The
                identity is fresh. This is what lets a project whose
                judgments log is empty produce anything at all.
  * reuse     — one identity, uniquely, above the high threshold. An
                ordinary edit reuses; membership delta alone is frozen as
                never identity-churning.
  * contested — two or more candidates claim one identity, or one candidate
                clears the high threshold against two or more identities.
                ALL contestants are demoted to ambiguous and routed. A
                one-to-many claim is a split and a many-to-one claim is a
                merge; picking a winner would silently decide which.
  * routed    — a low/ambiguous match, or a structural match against a
                STALE identity (a reappearance). Never a silent mint,
                stale, or replace.

Three properties of this module are load-bearing and easy to erode:

SCORING IS PROVIDER-INDEPENDENT. Only repo-relative paths, symbol NAMES,
and an opaque neighborhood set participate. Raw provider IDs may be stored
as provenance but are never a matcher signal: their format changes across
provider versions, so scoring on one would route every node to
reconciliation on a patch bump. The candidate shape has no field to carry
one, and an unknown field is a hard abort rather than an ignored key.

THE MATCHER WRITES NOTHING. It runs during preview, before any
confirmation. Minting happens at the confirmed creation event, which is
child D's call into the identity-commit ordering primitive — allocating
here would create an identity nobody confirmed, and that append is
irreversible by design.

LIVENESS COMES FROM THE LOG. The frozen match-scoping rule is stated over a
field that lives in index.json, which #228 forbids as an authority for
meaning. So liveness is derived here from the judgments fold instead:
latest wins by FILE ORDER, a stale record makes an identity stale, and a
reappearance or an explicit operator amendment revives it. That is the
minimum lifecycle interpretation the scoping rule forces on this surface;
everything past it — deciding THAT a split or merge occurred — is child G's.

`routes_to_g` is the honest interim shape. Child G does not exist and is
scheduled a release out, so a routed outcome is a CLASSIFICATION returned to
the caller, not a call into a lifecycle that is not built. It mints nothing,
reuses nothing, and appends no decision: a reuse is a re-observation, and
#228 forbids writing a judgment merely because a projection ran.
"""
from architecture.state import (
    ArchStateError,
    CONFIDENCE_VALUES,
    PROJECTION_TYPES,
)


def _finding(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d

OUTCOMES = ("mint", "reuse", "contested", "routed")

# Weights are module constants, not config. config.thresholds is frozen at
# exactly {high, low} and rejects unknown keys, so making these tunable
# would mean amending a v1 schema for a knob no acceptance criterion
# exercises and no operator has a way to calibrate.
SIGNAL_WEIGHTS = {"source_paths": 0.5, "symbol_names": 0.3, "neighborhood": 0.2}

# Conservative on purpose. While reconciliation is unbuilt an over-route is
# inert — the caller reports it and nothing is lost — whereas an over-reuse
# silently binds new code to an old identity along with its whole history.
DEFAULT_THRESHOLDS = {"high": 0.8, "low": 0.4}

CANDIDATE_REQUIRED = (
    "candidate_key", "projection_type", "source_paths", "symbol_names",
)
CANDIDATE_KNOWN = frozenset(CANDIDATE_REQUIRED + ("neighborhood",))

_SIGNAL_FIELDS = ("source_paths", "symbol_names", "neighborhood")

# Kinds that can move an identity between live and stale. Every other kind
# is a decision about naming or grouping and leaves liveness alone.
_STALING_KINDS = frozenset(["stale"])
_REVIVING_KINDS = frozenset(["reappearance"])


class MatcherInputError(ArchStateError):
    """A candidate or threshold pair the matcher refuses to score.

    Raises rather than returning findings, for the reason the judgments
    reader hard-aborts: a candidate quietly dropped from the assignment is a
    node that never gets an identity, and the next run mints a second one
    for the same code. `.findings` carries the structured detail."""


def identity_signals(fold):
    """Every identity the log knows, with its status and its scoring
    signals, keyed by arch_id:

        {arch_id: {"arch_id", "status": "live"|"stale",
                   "source_paths", "symbol_names", "neighborhood"}}

    Signals are frozensets, taken from the identity's own decision records:
    the allocation carries the confirmed snapshot, and any later record whose
    payload names a signal field supersedes that field. Nothing is read from
    the projection state — a generated note and its provenance both hold the
    same data, and #228 makes the log the sole authority for meaning.

    STALE IDENTITIES ARE RETURNED, NOT FILTERED OUT. Dropping them here
    would turn a reappearance into a mint, which is a second identity for
    code that already has one."""
    signals = {}
    for arch_id, records in fold.get("by_arch_id", {}).items():
        entry = {"arch_id": arch_id, "status": "live"}
        for field in _SIGNAL_FIELDS:
            entry[field] = frozenset()
        for record in records:
            _apply_status(entry, record)
            _apply_signals(entry, record)
        signals[arch_id] = entry
    return signals


def live_identities(fold):
    """`identity_signals` narrowed to the live ones — the only identities a
    candidate may be ASSIGNED to. A stale identity still scores, so that a
    reappearance is detected and routed."""
    return {arch_id: entry
            for arch_id, entry in identity_signals(fold).items()
            if entry["status"] == "live"}


def match(candidates, fold, thresholds=None):
    """Assign `candidates` against the identities in `fold`. Returns

        {"outcomes": [...],   # one per candidate, ordered by candidate_key
         "findings": [...]}   # non-fatal notes about the assignment

    Each outcome is

        {"candidate_key", "outcome", "arch_id", "score", "confidence",
         "reason", "routes_to_g", "contested_with", "contested_by"}

    `arch_id` names the identity the outcome is ABOUT — the one reused, the
    stale one that reappeared, the best sub-threshold match — and is None
    for a mint and for a contest, where naming one would be the winner-pick
    the frozen contest rule forbids. `confidence` is the recorded band:
    high for a reuse, medium for anything routed, None for a mint, whose
    identity is fresh and has no continuity evidence either way. Medium is
    never collapsed into a silent reuse.

    Deterministic throughout: pairs are ranked by (-score, arch_id), and
    outcomes come back ordered by candidate_key, so no result depends on
    mapping iteration order."""
    high, low = _thresholds(thresholds)
    prepared = _prepare(candidates)
    signals = identity_signals(fold)

    scores = {}
    for key, candidate in prepared.items():
        for arch_id, identity in signals.items():
            scores[(key, arch_id)] = _score(candidate, identity)

    high_pairs = sorted(
        (pair for pair, score in scores.items() if score >= high),
        key=lambda pair: (-scores[pair], pair[1], pair[0]))
    components = _components(high_pairs)

    outcomes = [
        _outcome(key, prepared[key], signals, scores, components, low)
        for key in sorted(prepared)
    ]
    return {"outcomes": outcomes, "findings": []}


def _outcome(key, candidate, signals, scores, components, low):
    component = components.get(key)
    if component is not None:
        return _high_outcome(key, component, signals, scores)

    best_id, best_score = _best(key, signals, scores)
    if best_id is None:
        return _record(key, "mint", None, 0.0, None, "empty_authority")
    if best_score < low:
        return _record(key, "mint", None, best_score, None, "no_match")
    if signals[best_id]["status"] == "stale":
        return _record(key, "routed", best_id, best_score, "medium",
                       "stale_reappearance")
    return _record(key, "routed", best_id, best_score, "medium",
                   "low_confidence")


def _high_outcome(key, component, signals, scores):
    """A candidate with at least one high-confidence claim. The frozen
    contest rule decides the algorithm: any connected group of high pairs
    bigger than a single candidate-identity edge is a contest and leaves the
    assignment whole, so what survives is a perfect matching by
    construction and no optimizer — which would resolve contests by picking
    winners — is needed."""
    candidates, identities = component
    if len(candidates) == 1 and len(identities) == 1:
        arch_id = identities[0]
        score = scores[(key, arch_id)]
        if signals[arch_id]["status"] == "stale":
            return _record(key, "routed", arch_id, score, "medium",
                           "stale_reappearance")
        return _record(key, "reuse", arch_id, score, "high", "unique_high")

    best = max(scores[(key, arch_id)] for arch_id in identities)
    return _record(key, "contested", None, best, "medium", "contested_high",
                   contested_with=sorted(identities),
                   contested_by=sorted(k for k in candidates if k != key))


def _record(key, outcome, arch_id, score, confidence, reason,
            contested_with=None, contested_by=None):
    assert outcome in OUTCOMES
    assert confidence is None or confidence in CONFIDENCE_VALUES
    return {
        "candidate_key": key,
        "outcome": outcome,
        "arch_id": arch_id,
        "score": score,
        "confidence": confidence,
        "reason": reason,
        "routes_to_g": outcome in ("contested", "routed"),
        "contested_with": list(contested_with or []),
        "contested_by": list(contested_by or []),
    }


def _best(key, signals, scores):
    """The identity a sub-threshold candidate is closest to. Ties break by
    arch_id: it is the only total, stable, project-scoped order available,
    and an equal-scoring pair must not resolve by mapping order."""
    ranked = sorted(
        ((scores[(key, arch_id)], arch_id) for arch_id in signals),
        key=lambda pair: (-pair[0], pair[1]))
    if not ranked:
        return None, 0.0
    score, arch_id = ranked[0]
    return arch_id, score


def _components(high_pairs):
    """Connected components of the bipartite high-confidence graph, as
    {candidate_key: (sorted candidate keys, sorted arch_ids)}."""
    parent = {}

    def find(node):
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    for key, arch_id in high_pairs:
        union(("candidate", key), ("identity", arch_id))

    groups = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)

    components = {}
    for members in groups.values():
        keys = sorted(name for kind, name in members if kind == "candidate")
        arch_ids = sorted(name for kind, name in members if kind == "identity")
        for key in keys:
            components[key] = (keys, arch_ids)
    return components


def _score(candidate, identity):
    """The weighted mean of per-signal Dice coefficients, in [0, 1].

    Dice rather than Jaccard because membership delta alone is frozen as
    never identity-churning: Jaccard charges a growing component twice for
    each added member, so an ordinary edit that adds a file and a symbol
    would fall under the high threshold and route work that should simply
    reuse its identity.

    A signal absent on BOTH sides is dropped and its weight redistributed
    over the signals that are present. Neighborhood is the live case —
    child C, which will populate it, is not built — and simply losing its
    weight would cap a byte-identical candidate below the high threshold."""
    total_weight = 0.0
    total = 0.0
    for field, weight in SIGNAL_WEIGHTS.items():
        left, right = candidate[field], identity[field]
        if not left and not right:
            continue
        total_weight += weight
        total += weight * _dice(left, right)
    if total_weight == 0.0:
        return 0.0
    return total / total_weight


def _dice(left, right):
    if not left or not right:
        return 0.0
    return 2.0 * len(left & right) / (len(left) + len(right))


def _apply_status(entry, record):
    kind = record.get("kind")
    if kind in _STALING_KINDS:
        entry["status"] = "stale"
    elif kind in _REVIVING_KINDS:
        entry["status"] = "live"
    elif kind == "operator_amendment":
        # The escape hatch says so explicitly or not at all: an amendment
        # about a name must not silently revive a stale identity.
        status = (record.get("payload") or {}).get("status")
        if status in ("live", "stale"):
            entry["status"] = status


def _apply_signals(entry, record):
    payload = record.get("payload") or {}
    for field in _SIGNAL_FIELDS:
        if field in payload:
            entry[field] = frozenset(payload[field] or ())


def _prepare(candidates):
    """Validate and normalize, or abort. Returns {candidate_key: candidate}
    with signal fields as frozensets, leaving the caller's dicts untouched."""
    findings = []
    prepared = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            findings.append(_finding(
                "E_ARCH_CANDIDATE_NOT_AN_OBJECT",
                "a candidate must be an object", index=index))
            continue
        findings.extend(_candidate_findings(candidate, index))
        key = candidate.get("candidate_key")
        if not isinstance(key, str):
            continue
        if key in prepared:
            findings.append(_finding(
                "E_ARCH_CANDIDATE_DUPLICATE_KEY",
                "candidate_key %r appears more than once; two candidates "
                "with one key cannot both be assigned" % (key,),
                index=index, field="candidate_key"))
            continue
        prepared[key] = {
            field: frozenset(candidate.get(field) or ())
            for field in _SIGNAL_FIELDS
        }
    if findings:
        raise MatcherInputError(findings)
    return prepared


def _candidate_findings(candidate, index):
    findings = []
    for field in CANDIDATE_REQUIRED:
        if field not in candidate:
            findings.append(_finding(
                "E_ARCH_CANDIDATE_MISSING_FIELD",
                "a candidate must carry %r" % (field,),
                index=index, field=field))
    for field in sorted(set(candidate) - CANDIDATE_KNOWN):
        findings.append(_finding(
            "E_ARCH_CANDIDATE_UNKNOWN_FIELD",
            "unknown candidate field %r; provider-specific fields are "
            "refused rather than ignored, so no provider value can reach "
            "scoring" % (field,),
            index=index, field=field))
    projection_type = candidate.get("projection_type")
    if "projection_type" in candidate and projection_type not in PROJECTION_TYPES:
        findings.append(_finding(
            "E_ARCH_CANDIDATE_BAD_PROJECTION_TYPE",
            "projection_type must be one of %s, got %r"
            % (", ".join(PROJECTION_TYPES), projection_type),
            index=index, field="projection_type"))
    key = candidate.get("candidate_key")
    if "candidate_key" in candidate and (
            not isinstance(key, str) or not key.strip()):
        findings.append(_finding(
            "E_ARCH_CANDIDATE_MALFORMED_KEY",
            "candidate_key must be a non-empty string, got %r" % (key,),
            index=index, field="candidate_key"))
    for field in _SIGNAL_FIELDS:
        value = candidate.get(field)
        if field in candidate and not _is_string_list(value):
            findings.append(_finding(
                "E_ARCH_CANDIDATE_BAD_SIGNAL",
                "%s must be a list of strings, got %r" % (field, value),
                index=index, field=field))
    return findings


def _thresholds(thresholds):
    """The (high, low) pair to gate on. `None` takes the defaults; anything
    else must satisfy the same constraint config.json froze in slice 2 —
    both in [0, 1], low strictly below high. A pair that does not is a hard
    abort: inverted thresholds would make every score both high and low, and
    the four outcomes would stop being exhaustive."""
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS
    findings = []
    values = {}
    for field in ("high", "low"):
        value = thresholds.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            findings.append(_finding(
                "E_ARCH_THRESHOLDS_BAD_VALUE",
                "thresholds.%s must be a number, got %r" % (field, value),
                field=field))
        elif not 0.0 <= value <= 1.0:
            findings.append(_finding(
                "E_ARCH_THRESHOLDS_OUT_OF_RANGE",
                "thresholds.%s must be within [0, 1], got %r" % (field, value),
                field=field))
        else:
            values[field] = float(value)
    if len(values) == 2 and not values["low"] < values["high"]:
        findings.append(_finding(
            "E_ARCH_THRESHOLDS_BAD_ORDER",
            "thresholds.low must be strictly below thresholds.high, got %r "
            "and %r" % (values["low"], values["high"]),
            field="thresholds"))
    if findings:
        raise MatcherInputError(findings)
    return values["high"], values["low"]


def _is_string_list(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)
