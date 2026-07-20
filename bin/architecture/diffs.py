"""architecture.diffs — deterministic diffs and the minimal changed-set
(issue #229 child C, slice C3, epic #141).

C supplies the PRIMITIVE; child D owns the criterion. D's AC11 (changed-only
refresh) and PT31 ("a commit touching one unrelated file rewrites zero
notes") are discharged by D, but neither is reachable unless C can say which
candidates actually moved. That is all this module does.

WHAT IS NOT IN THE FINGERPRINT IS THE POINT. `bindings` is provenance: it
moves when a binding is added or removed, on commits that changed no
architecture at all. Fingerprinting it would mark every candidate changed on
such a commit and defeat PT31 outright. The exclusion is reported in
`applied` rather than left implicit -- a deliberate blind spot a caller
cannot see is indistinguishable from a bug.

METRICS COMPARE AS BANDS ONLY. Identical reasoning to ranking's: a fan-in of
21 -> 22 is a real change to `value` and no change at all to the
architecture, so comparing raw measurements would rewrite notes on ordinary
edits. The band is the churn-guarded reading, so the band is what a diff
sees.

AN UNKNOWN FIELD IS REFUSED, NOT IGNORED. #228's matcher hard-aborts on an
unknown candidate field for the same reason: a fingerprint that silently
dropped a field it did not recognise would compare EQUAL across a real
change, and the failure would surface as a note that stopped updating rather
than as an error.

This module reads no state. `previous` arrives from whatever child D holds;
C never opens `index.json`, which keeps it clear of both B's state schema and
the identity #228 forbids C to touch.
"""
from architecture import candidates

# Provenance -- see the module docstring. Kept as a named tuple rather than a
# subtraction at the call site so that the blind spot has one greppable home.
EXCLUDED_FIELDS = ("bindings",)

FINGERPRINT_FIELDS = tuple(
    sorted(candidates.RECORD_FIELDS - frozenset(EXCLUDED_FIELDS)))


class DiffInputError(Exception):
    """Input a diff cannot compare honestly."""


def _metric_bands(value):
    """Reduce a metrics map to `{signal: band}`."""
    if not isinstance(value, dict):
        return {}
    bands = {}
    for signal, measurement in value.items():
        bands[signal] = (measurement.get("band")
                         if isinstance(measurement, dict) else measurement)
    return bands


def fingerprint(record):
    """The comparable reading of one candidate.

    Keys are exactly `FINGERPRINT_FIELDS`, including for a record that omits
    one -- a missing field must compare as missing rather than shift every
    other field's meaning.
    """
    unknown = set(record) - set(candidates.RECORD_FIELDS)
    if unknown:
        raise DiffInputError(
            "unknown candidate field(s): " + ", ".join(sorted(unknown)))

    printed = {}
    for field in FINGERPRINT_FIELDS:
        value = record.get(field)
        if field == "metrics":
            printed[field] = _metric_bands(value)
        elif isinstance(value, (list, tuple)):
            printed[field] = list(value)
        else:
            printed[field] = value
    return printed


def _by_key(records, side):
    indexed = {}
    for record in records:
        key = record["candidate_key"]
        if key in indexed:
            raise DiffInputError(
                "duplicate candidate_key in %s: %s" % (side, key))
        indexed[key] = fingerprint(record)
    return indexed


def diff(previous, current):
    """Classify every candidate across two runs.

        {"added": [key, ...], "removed": [key, ...],
         "changed": [{"candidate_key", "fields": [...]}, ...],
         "unchanged": [key, ...],
         "applied": {...}}

    Every key lands in exactly one bucket, and every list is sorted --
    identical input must produce byte-identical output, which is what lets
    D's unchanged rerun write nothing.

    `changed` names the fields that moved rather than reporting a bare
    boolean: D compares note BYTES region by region, so it needs to know
    whether a change touched anything it renders. Recomputing that from the
    records would duplicate the fingerprint's exclusion rules in a second
    place, where the two could disagree.
    """
    before = _by_key(previous, "previous")
    after = _by_key(current, "current")

    changed = []
    unchanged = []
    for key in sorted(set(before) & set(after)):
        fields = sorted(field for field in FINGERPRINT_FIELDS
                        if before[key][field] != after[key][field])
        if fields:
            changed.append({"candidate_key": key, "fields": fields})
        else:
            unchanged.append(key)

    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": changed,
        "unchanged": unchanged,
        "applied": {
            "fingerprint_fields": list(FINGERPRINT_FIELDS),
            "excluded_fields": list(EXCLUDED_FIELDS),
            "metric_comparison": "band",
        },
    }
