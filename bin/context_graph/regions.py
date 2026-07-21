"""The marker-agnostic generated-region core (#230 child D, slice D1).

#185 froze a safe generated-region lifecycle for `context.md`: a BEGIN/END
comment pair bounds the bytes the tool owns, everything outside it belongs to
the user and survives byte-for-byte, and a file whose markers are missing or
duplicated is a conflict rather than something to guess at. A second
surface needs exactly that lifecycle around a *different* marker pair, so the
core lives here and takes the pair as arguments. (The architecture surface
that first needed it was removed in #384; the parameterisation stays, because
collapsing it back into one hard-coded pair is what #185 warned against.)

`projection.py` keeps its own module constants, its context-specific conflict
codes, and its file templates; it now delegates the marker mechanics to this
module so there is ONE scanner. Two copies would let #185's guarantee stop
holding while every test on both sides stayed green -- the same failure mode
#230 warns about for B's primitives.

Pure: no I/O, no clock, no run-only value.
"""


class RegionError(Exception):
    """A splice was attempted against text with no usable marker pair.

    `splice` is the mechanical replacement step and deliberately refuses to
    classify: the caller scans first and owns the vocabulary for what an
    unmanaged or malformed file means on its own surface.
    """


def wrap(body, begin, end):
    """The managed region as it appears on disk: the BEGIN marker, a
    newline, the rendered body, then the END marker.

    Nothing is appended after END -- the caller owns the bytes that follow,
    and a newline injected here would shift every byte of the preserved
    suffix on the first update.
    """
    return begin + "\n" + body + end


def scan(text, begin, end):
    """Classify the `begin`/`end` marker pair in `text`. Returns a
    ("valid", begin_idx, end_idx) / ("unmanaged", None, None) /
    ("malformed", None, None) triple; the offsets are the start offsets of
    the two markers and are meaningful only for "valid".

    - Zero of each -> "unmanaged" (a hand-authored file, or one managed by
      some OTHER marker pair -- this scanner sees only its own).
    - Exactly one of each, BEGIN strictly before END -> "valid".
    - Anything else (unequal counts, END before BEGIN, a duplicated or
      nested pair, only one side present) -> "malformed".
    """
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        return ("unmanaged", None, None)
    if begin_count == 1 and end_count == 1:
        begin_idx = text.index(begin)
        end_idx = text.index(end)
        if begin_idx < end_idx:
            return ("valid", begin_idx, end_idx)
    return ("malformed", None, None)


def splice(existing_text, body, begin, end):
    """Replace the managed region in `existing_text` with `body`, preserving
    every byte outside the marker pair.

    Returns ("noop", None) when the region already holds exactly these bytes
    -- the caller then writes nothing, which is what keeps an unchanged rerun
    byte-stable -- or ("update", new_text) otherwise. Raises `RegionError`
    when `existing_text` carries no valid pair; scan first.
    """
    kind, begin_idx, end_idx = scan(existing_text, begin, end)
    if kind != "valid":
        raise RegionError("text is %s for this marker pair" % (kind,))

    end_stop = end_idx + len(end)
    wrapped_region = wrap(body, begin, end)
    if existing_text[begin_idx:end_stop] == wrapped_region:
        return ("noop", None)
    return ("update",
            existing_text[:begin_idx] + wrapped_region + existing_text[end_stop:])
