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
"""

from structural_graph import validation


def _within(path, prefix):
    """True when path is prefix or lies under it on a segment boundary.

    Non-string is not an error here -- that finding belongs to
    validation.py alone -- it is simply never a match. Both operands are
    checked: prefix flows in from a coverage entry, path from a caller, and
    either could be malformed independently. Guarding here is what keeps
    this function's own contract ("never raise") true no matter what a
    caller -- including a test calling it directly through tiling_findings
    or status_for -- hands in.
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

    tiling_findings is public and exercised directly by its own tests, so
    it must not raise TypeError on a capabilities list containing an
    unhashable element (list, dict) -- `set(...)` would raise building the
    set -- or mutually-incomparable elements -- plain `sorted()` would raise
    comparing them. Dedup by an equality scan instead of hashing (these
    lists are small) and sort by the type-qualified key above.
    """
    unique = []
    for capability in capabilities or []:
        if capability not in unique:
            unique.append(capability)
    return sorted(unique, key=_capability_sort_key)


def tiling_findings(root, capabilities, entries):
    """Return findings for coverage that fails to tile root."""
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
        # A list-based membership scan, not a set: path_prefix can be an
        # unhashable value (list, dict) on a malformed entry, and this
        # function's contract is to never raise regardless -- validation.py
        # owns reporting the shape problem itself.
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
