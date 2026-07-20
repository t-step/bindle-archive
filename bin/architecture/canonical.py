"""architecture.canonical — the judgments-record envelope: the canonical
byte serialization a judgment record is digested over, its content-derived
`record_id`, and its integrity `checksum` (issue #228, epic #141).

Pure functions over plain dicts: no filesystem access, no clock, no
randomness. Reading, appending, and recovering `judgments.jsonl` are a
later concern; this module only says what a record's envelope fields are
so they can be computed identically by a writer and a verifier.

Why an envelope at all. `context_graph.atomic_io.append_line_atomic` is
`open(path,"a")` + `write` + `flush` + `fsync`: durability, NOT crash
atomicity. A SIGKILL or ENOSPC mid-write leaves a truncated trailing line,
and #228 forbids recovering identity from `index.json` or from the notes —
both of which still hold the data. Per-record integrity is what lets a
reader tell a torn tail (truncate and report) from mid-file corruption
(hard abort) without guessing.

Two digests, two domain tags (issue #228):

  record_id  arch-judgment:sha256:<hex>  over the record MINUS record_id
                                         and checksum
  checksum   sha256:<hex>                over the record MINUS checksum,
                                         so it covers record_id too

Excluding both from `record_id` keeps it a stable function of the decision
itself: stamping a record cannot fold the stamp into the identity, so
`stamp` is idempotent and a duplicate append is detectable as an exact
`record_id` repeat. The digests carry distinct domain tags so the two can
never collide or be substituted for one another.

The canonical form is compact, key-sorted JSON — not the bytes as written.
Hashing the written line would couple every historical record to
`append_line_atomic`'s exact serializer settings, so changing `indent` or
`sort_keys` later would silently invalidate the whole log.
"""
import hashlib
import json

RECORD_ID_PREFIX = "arch-judgment:sha256:"
CHECKSUM_PREFIX = "sha256:"

_RECORD_ID_TAG = b"bindle-arch-judgment-record-v1"
_CHECKSUM_TAG = b"bindle-arch-judgment-checksum-v1"

_RECORD_ID_EXCLUDE = ("record_id", "checksum")
_CHECKSUM_EXCLUDE = ("checksum",)


def canonical_record_bytes(record, exclude=()):
    """Serialize a judgment record to its canonical digest input: compact,
    key-sorted UTF-8 JSON with the named top-level keys removed. Raises
    TypeError for a non-dict or a value JSON cannot represent."""
    if not isinstance(record, dict):
        raise TypeError("judgment record must be a dict, got %r" % (type(record),))
    trimmed = {k: v for k, v in record.items() if k not in exclude}
    return json.dumps(
        trimmed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(tag, record, exclude):
    payload = b"\0".join((tag, canonical_record_bytes(record, exclude=exclude)))
    return hashlib.sha256(payload).hexdigest()


def judgment_record_id(record):
    """Content-derived record ID for a judgment record. Ignores any
    record_id/checksum already present, so it is stable across restamping
    and identical for two appends of the same decision."""
    return RECORD_ID_PREFIX + _digest(_RECORD_ID_TAG, record, _RECORD_ID_EXCLUDE)


def judgment_checksum(record):
    """Integrity checksum over the record minus its own checksum field —
    covering record_id, so a tampered ID fails verification."""
    return CHECKSUM_PREFIX + _digest(_CHECKSUM_TAG, record, _CHECKSUM_EXCLUDE)


def stamp(record):
    """Return a copy of record carrying its record_id and checksum. Never
    mutates the argument, and is idempotent: stamping a stamped record
    reproduces it exactly."""
    stamped = dict(record)
    stamped["record_id"] = judgment_record_id(stamped)
    stamped["checksum"] = judgment_checksum(stamped)
    return stamped


def verify_checksum(record):
    """True when record carries a checksum matching its own content. Never
    raises — a reader classifies untrusted lines with it, including junk
    that is not a record at all."""
    if not isinstance(record, dict):
        return False
    present = record.get("checksum")
    if not isinstance(present, str) or not present:
        return False
    try:
        expected = judgment_checksum(record)
    except (TypeError, ValueError):
        return False
    return present == expected
