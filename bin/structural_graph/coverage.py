"""structural_graph.coverage -- coverage tiling and status lookup (#227).

Coverage is declared per (path_prefix, capability). Tiling is what makes
"unsupported" structurally distinct from "observed to be zero": a subtree a
provider could not parse must say so, and no path may fall outside every
entry.

Exhaustively tiling an unknown filesystem is not decidable from a document
alone, so tiling is realized as root-anchored longest-prefix override:
exactly one entry at root per advertised capability, plus zero or more
strictly-nested entries with distinct prefixes. The root entry covers
everything not otherwise claimed, so a gap is impossible by construction and
a repeated prefix within one capability is the overlap case.

tiling_findings and status_for run downstream of validate_document, which
guarantees entries is a list of dicts with string path_prefix values and
capabilities is a list of strings -- by the time a document reaches this
module, malformed *document content* has already been converted to a
finding rather than left to raise here. That guarantee covers values, not
argument shapes: a caller that hands either function a malformed argument
directly (capabilities as an int, entries as a string) is a programming
mistake, not provider input, and the package already has precedent for
letting that raise -- see context_graph.evidence.MalformedIdentityError on
a bad project_id.
"""

from structural_graph import validation


def _within(path, prefix):
    """True when path is prefix or lies under it on a segment boundary.

    Non-string is not an error here -- that finding belongs to
    validation.py alone -- it is simply never a match. Both operands are
    checked: prefix flows in from a coverage entry (document content), path
    from a caller. Guarding here is what keeps this function's own contract
    ("never raise on a malformed value") true regardless of which operand
    carries the malformed value, including when a test calls it directly
    through tiling_findings or status_for.
    """
    if not isinstance(path, str) or not isinstance(prefix, str):
        return False
    if prefix == "":
        return True
    return path == prefix or path.startswith(prefix + "/")


def _capability_sort_key(capability):
    """Total, deterministic order that never raises.

    Keying on (type name, repr) rather than the value itself sidesteps two
    ways plain sorting can raise on a malformed capabilities list: Python 3
    refuses to compare mutually-incomparable types (e.g. str vs int)
    directly, and this key never needs one element comparable to another's
    native type. repr() also never raises, unlike hashing an unhashable
    value would.
    """
    return (type(capability).__name__, repr(capability))


def _sorted_unique_capabilities(capabilities):
    """Dedupe and sort a capabilities list without hashing or comparing.

    capabilities is a document-derived list, so an individual element can be
    an unhashable value (list, dict) or mutually incomparable with the
    others even while the list itself is well-formed -- `set(...)` would
    raise building the set, and plain `sorted()` would raise comparing them.
    Dedup by an equality scan instead of hashing (these lists are small) and
    sort by the type-qualified key above, so tiling_findings stays raise-free
    on that document content even when exercised directly by its own tests.
    """
    unique = []
    for capability in capabilities or []:
        if capability not in unique:
            unique.append(capability)
    return sorted(unique, key=_capability_sort_key)


def tiling_findings(root, capabilities, entries):
    """Return findings for coverage that fails to tile root.

    Assumes entries is a list of dicts and capabilities is a list of
    strings, per validate_document's guarantee (see module docstring). A
    malformed *value* inside that shape -- a None path_prefix, a capability
    that's a list instead of a string -- is document content and cannot
    raise here. Passing a malformed argument itself (capabilities as an
    int, entries as a string) is caller error and is not guarded against.
    """
    out = []
    entries = entries or []
    for capability in _sorted_unique_capabilities(capabilities):
        prefixes = [
            entry.get("path_prefix")
            for entry in entries
            if entry.get("capability") == capability
        ]
        if root not in prefixes:
            out.append(
                validation.finding(
                    "E_SG_COVERAGE_GAP",
                    "capability has no coverage entry at the document root",
                    None,
                    "coverage[].capability",
                )
            )
        # A list-based membership scan, not a set: path_prefix is document
        # content and can be an unhashable value (list, dict) on a malformed
        # entry -- a set would raise building itself on that value. This
        # function's contract is to never raise on that kind of value;
        # validation.py owns reporting the shape problem itself.
        seen = []
        for index, entry in enumerate(entries):
            if entry.get("capability") != capability:
                continue
            prefix = entry.get("path_prefix")
            if prefix in seen:
                out.append(
                    validation.finding(
                        "E_SG_COVERAGE_OVERLAP",
                        "capability has more than one entry at the same prefix",
                        index,
                        "coverage[].path_prefix",
                    )
                )
            else:
                seen.append(prefix)
            if not _within(prefix, root):
                out.append(
                    validation.finding(
                        "E_SG_COVERAGE_GAP",
                        "coverage entry lies outside the document root",
                        index,
                        "coverage[].path_prefix",
                    )
                )
    return out


def status_for(entries, capability, path):
    """Return the coverage status for path under capability.

    Resolves by longest matching prefix. Returns None when the capability has
    no coverage at all -- the caller must treat that as unknown, never as an
    observed zero.

    Like tiling_findings, this assumes entries is a list of dicts per
    validate_document's guarantee (see module docstring): a malformed value
    inside that shape is document content and cannot raise, but a malformed
    entries argument itself is caller error.
    """
    best_prefix = None
    best_status = None
    for entry in entries or []:
        if entry.get("capability") != capability:
            continue
        prefix = entry.get("path_prefix")
        if not _within(path, prefix):
            continue
        if best_prefix is None or len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_status = entry.get("status")
    return best_status
