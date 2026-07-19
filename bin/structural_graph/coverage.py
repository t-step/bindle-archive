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
    """True when path is prefix or lies under it on a segment boundary."""
    if prefix == "":
        return True
    return path == prefix or path.startswith(prefix + "/")


def tiling_findings(root, capabilities, entries):
    """Return findings for coverage that fails to tile root."""
    out = []
    entries = entries or []
    for capability in sorted(set(capabilities or [])):
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
        seen = set()
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
            seen.add(prefix)
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
