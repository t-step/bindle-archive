"""architecture.ranking — bounded note counts and over-cap retention
(issue #229 child C, slice C3, epic #141).

RANKING IS BANDED, NOT RAW. #229 freezes it: "RANKING USES THE SAME
BUCKETED/BANDED METRIC VALUES as F's churn guard, not raw numbers --
otherwise a rank swap at the cap boundary mints one note and strands another
every few commits, and churn excluded from note BYTES re-enters through note
EXISTENCE." A fan-in of 21 -> 22 is invisible here by construction, because
both read "high".

THE CAP BINDS CREATION, IT DOES NOT DELETE. An over-cap candidate stays in
`ranked` and is merely marked `over_cap`. Nothing in this module drops a
record: never-auto-delete is child G's to relax, and auto-staling is G's
AC16. Marking is the honest MVP outcome -- the same shape #230 settled on
for `orphaned_by_resume`.

THE FLAG IS RUN-SCOPED, NOT PERSISTED STATE. Child B's `index.json` node is a
closed schema with no home for this, and correctly so: the classification is
recomputed from banded metrics and the cap on every run, so it is a property
of the run rather than a durable bit. The epic assigns the flag to D's
preview layer, which is where it lands. THE SPELLING IS SETTLED: `over_cap`
is authoritative per #372, declared on the `caps.over_cap_behavior`
description in `schemas/architecture/v1/config.schema.json`. The retired
second spelling `below_cap_threshold` (once carried by #229's and G's issue
bodies) named the same flag, not another one; do not produce or consume it.

`unknown` RANKS LOWEST. An unobserved metric must never win a cap slot over
an observed zero: that is the fabricated-zero failure inverted, absence read
as strength rather than as zero.

THE CODEBASE MAP IS EXEMPT and does not consume a cap slot. It is the one
note the epic's first release promises unconditionally, so a `max_nodes` of
1 must not be able to spend the only slot on it and strand every component --
nor evict the map itself. The exemption is echoed in `applied` rather than
left implicit, because "silent enforcement and silent non-enforcement are
both forbidden".

Ranking reads no configuration and touches no filesystem: `cap` arrives as an
argument, which keeps this module a pure function of its input the way C1 and
C2 are. Child D reads `config.caps.max_nodes` and passes it in.
"""
from architecture import candidates
from architecture import metrics

# Weakest first, so a band's index is its strength. `unknown` sits below
# `none` deliberately -- see the module docstring.
BAND_ORDER = (metrics.UNKNOWN_BAND,) + tuple(metrics.BAND_NAMES)

# Ordered: blast_radius decides, fan_in breaks its ties, fan_out breaks
# those. Blast radius leads because the cap exists to bound NOTE COUNT
# against a large repository, and reach is what makes a component worth a
# note -- a change that propagates further matters more than one that does
# not.
RANK_SIGNALS = ("blast_radius", "fan_in", "fan_out")

CAP_EXEMPT_KEYS = (candidates.CODEBASE_MAP_KEY,)


class RankingInputError(Exception):
    """A cap that cannot be enforced as written."""


def _band(record, signal):
    """The banded reading of one signal, `unknown` when unmeasured.

    A candidate with no metrics at all -- the codebase map -- reads unknown
    across the board rather than zero, for the same reason an unobserved
    metric does.
    """
    measurement = (record.get("metrics") or {}).get(signal)
    if not isinstance(measurement, dict):
        return metrics.UNKNOWN_BAND
    return measurement.get("band") or metrics.UNKNOWN_BAND


def _strength(record, signal):
    band = _band(record, signal)
    if band not in BAND_ORDER:
        return 0
    return BAND_ORDER.index(band)


def _sort_key(record):
    """Strongest first, then `candidate_key` ascending.

    The tie-break is the candidate key rather than input order because C2
    already froze the key as stable across ordinary edits; ordering on
    arrival would make the output depend on how D happened to build its list.
    """
    return tuple(
        -_strength(record, signal) for signal in RANK_SIGNALS
    ) + (record["candidate_key"],)


def rank(records, cap=None):
    """Rank candidates and mark the ones the cap excludes from creation.

        {"ranked": [{"candidate_key", "rank", "over_cap", "exempt"}, ...],
         "over_cap": [candidate_key, ...],   # sorted; agrees with `ranked`
         "cap": int | None,
         "applied": {...}}

    `ranked` is in rank order and holds EVERY input candidate. `over_cap` is
    that same marking read as a sorted set, for a caller that wants the
    exclusion list without walking the ranking.
    """
    if cap is not None:
        if isinstance(cap, bool) or not isinstance(cap, int):
            raise RankingInputError("cap must be an integer or None")
        if cap < 0:
            raise RankingInputError("cap must not be negative: %r" % (cap,))

    ranked = []
    slots_used = 0
    for position, record in enumerate(sorted(records, key=_sort_key)):
        key = record["candidate_key"]
        exempt = key in CAP_EXEMPT_KEYS
        over_cap = False
        if not exempt:
            # Slots are consumed in rank order, so the mark falls on the
            # weakest candidates and a swap at the boundary moves the mark
            # rather than the membership (PT22).
            if cap is not None and slots_used >= cap:
                over_cap = True
            else:
                slots_used += 1
        ranked.append({
            "candidate_key": key,
            "rank": position,
            "over_cap": over_cap,
            "exempt": exempt,
        })

    return {
        "ranked": ranked,
        "over_cap": sorted(entry["candidate_key"] for entry in ranked
                           if entry["over_cap"]),
        "cap": cap,
        "applied": {
            "band_order": list(BAND_ORDER),
            "rank_signals": list(RANK_SIGNALS),
            "exempt_keys": sorted(CAP_EXEMPT_KEYS),
        },
    }
