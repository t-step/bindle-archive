"""architecture.metrics — Bindle's own structural signals over the
interchange (issue #229 child C, slice C1, epic #141).

Fan-in, fan-out, neighborhood and blast radius, computed from #227's
provider-independent facts and nothing else. These are the signals child C's
later slices cluster, name and rank; nothing here decides what becomes a
note.

ABSENCE IS NEVER ZERO, AND THE GUARANTEE IS PER ENTITY. #141 freezes the
failure this exists to prevent: a real 40k-line subsystem whose provider
never advertised `calls` reads as "fan-in: 0, fan-out: 0", falls under a
minimum-evidence threshold, and disappears from the map with no marker
anywhere. So a metric is a MEASUREMENT — `{value, lower_bound, coverage,
band}` — where an exact `value` exists only when every capability the metric
depends on was observed across every binding the entity participates in.
Otherwise the honest answer is a lower bound plus `partial`, or `unknown`
with no number at all. An observed zero stays zero: laundering a real 0 into
"unknown" is the same lie pointing the other way.

COVERAGE IS EVALUATED OVER PARTICIPATING BINDINGS ONLY. graphset's
`aggregate_coverage` answers "did every binding observe this capability at
this path", which reads a path present in one repository as degraded merely
because a second, unrelated repository never mentions it. An entity's
coverage here is combined across the bindings that actually carry a fact for
it, so a partial outage degrades the subtree it touched rather than the
whole map.

BANDS ARE ABSOLUTE CUT POINTS, NOT QUANTILES. #229 freezes that ranking uses
the same banded values as F's churn guard. Under quantiles a band is
relative to the rest of the run, so adding one unrelated file moves other
entities across bands, mints one note and strands another — the churn kept
out of note BYTES re-entering through note EXISTENCE. An absolute cut point
makes a band a pure function of one entity's own metric.

ENTITIES ARE KEYED BY BARE REPOSITORY-RELATIVE PATH, not by graphset's
`<binding_id>::<path>` qualification. #228 freezes that adding or removing a
participating binding never churns identity; a binding-qualified signal
breaks that outright, because re-adding a binding yields a new binding_id,
every signal string changes, and every node routes to reconciliation. Two
bindings sharing a path therefore aggregate into one entity. That is the
deliberate trade: a genuine cross-repository collision is what the matcher's
`contested` outcome exists to surface, and a false identity churn is not
recoverable.

Bands and thresholds are MODULE CONSTANTS. `config.thresholds` is frozen at
exactly {high, low} and rejects unknown keys, so a tunable band would mean
amending a v1 schema for a knob nobody can calibrate — the trade slice 5
made for SIGNAL_WEIGHTS. #229 requires them "enforced and observable", so
they are echoed in the result envelope instead.

The module is pure: the graph arrives loaded, exclusion patterns arrive as
arguments, and nothing here touches a filesystem, a provider or a clock.
"""
from architecture import exclusions
from structural_graph import coverage as sg_coverage

# Absolute cut points: (band name, inclusive floor), ascending.
BANDS = (
    ("none", 0),
    ("low", 1),
    ("moderate", 5),
    ("high", 20),
    ("very_high", 100),
)
BAND_NAMES = tuple(name for name, _floor in BANDS)

UNKNOWN_BAND = "unknown"

COVERAGE_STATUSES = ("observed", "partial", "unknown")

# A depends-on-B relation, whatever its flavour. Distinctness is per PAIR of
# paths, not per edge, so a file that imports and also calls another counts
# once -- otherwise fan-out measures how chatty a provider is.
DEPENDENCY_EDGE_TYPES = ("imports", "depends_on", "calls")

# Structural adjacency for the neighborhood signal. `calls` is deliberately
# excluded: it vanishes entirely without the `calls` capability, and a
# 0.2-weight matcher signal that disappears on a capability toggle is
# exactly PT16's churn failure. `imports`/`depends_on` survive under a
# minimal provider.
NEIGHBORHOOD_EDGE_TYPES = ("imports", "depends_on")


def band(value):
    """The band a metric value falls in; `unknown` when there is no value."""
    if value is None:
        return UNKNOWN_BAND
    name = BANDS[0][0]
    for candidate, floor in BANDS:
        if value >= floor:
            name = candidate
    return name


def measurement(value, coverage):
    """One metric reading.

    `value` is the exact count and exists only under full observation.
    `lower_bound` is what was actually seen — under `partial` it is a floor,
    never the answer. Under `unknown` there is no number at all, because a
    capability nobody could observe has no floor either.
    """
    if coverage == "unknown":
        return {"value": None, "lower_bound": None, "coverage": "unknown",
                "band": UNKNOWN_BAND}
    if coverage == "partial":
        return {"value": None, "lower_bound": value, "coverage": "partial",
                "band": band(value)}
    return {"value": value, "lower_bound": value, "coverage": "observed",
            "band": band(value)}


def aggregate(parts):
    """Combine per-binding measurements without ever summing absence as 0.

    The frozen worked example: a component spanning a binding with fan-in 40
    and a binding that could not observe `calls` aggregates to ">=40,
    partial" — not 40, and not 40+0.
    """
    parts = list(parts or ())
    if not parts:
        return measurement(None, "unknown")
    statuses = [part["coverage"] for part in parts]
    total = sum(part["lower_bound"] or 0 for part in parts)
    if all(status == "unknown" for status in statuses):
        return measurement(None, "unknown")
    if all(status == "observed" for status in statuses):
        return measurement(total, "observed")
    return measurement(total, "partial")


def _combine_statuses(statuses):
    statuses = list(statuses)
    if not statuses or all(status != "observed" for status in statuses):
        return "unknown"
    if all(status == "observed" for status in statuses):
        return "observed"
    return "partial"


def _binding_status(info, capability, path):
    """Whether one binding observed `capability` at `path`.

    Three ways to fail, all of which mean "not observed" rather than
    "observed to be empty": the document never loaded, the provider never
    advertised the capability, or coverage at that path says the subtree was
    unsupported or failed to parse.
    """
    if info.get("status") != "loaded":
        return "unknown"
    if capability not in (info.get("capabilities") or []):
        return "unknown"
    status = sg_coverage.status_for(
        info.get("coverage") or [], capability, path
    )
    return "observed" if status == "observed" else "unknown"


def _entity_coverage(graph, participating, capabilities, path):
    """Coverage for one entity across the bindings that actually carry it."""
    statuses = []
    for binding_id in sorted(participating):
        info = (graph.get("bindings") or {}).get(binding_id) or {}
        for capability in capabilities:
            statuses.append(_binding_status(info, capability, path))
    return _combine_statuses(statuses)


def _resolve(graph):
    """Qualified fact key -> bare repository-relative path."""
    resolved = {}
    facts = graph.get("facts") or {}
    for key, item in (facts.get("files") or {}).items():
        resolved[key] = item.get("path")
    for key, item in (facts.get("symbols") or {}).items():
        resolved[key] = item.get("path")
    return resolved


def _participation(graph):
    """Bare path -> the set of binding ids carrying a fact for it."""
    participating = {}
    facts = graph.get("facts") or {}
    for item in (facts.get("files") or {}).values():
        participating.setdefault(item.get("path"), set()).add(
            item.get("binding_id"))
    for item in (facts.get("symbols") or {}).values():
        participating.setdefault(item.get("path"), set()).add(
            item.get("binding_id"))
    return participating


def _closure(seeds, adjacency):
    """Transitive closure over `adjacency`, excluding the seeds themselves.

    Iterative and visited-guarded: a dependency cycle is ordinary in real
    code and must terminate rather than recurse forever.
    """
    seen = set()
    queue = list(seeds)
    while queue:
        current = queue.pop()
        for neighbor in adjacency.get(current, ()):  # noqa: E501
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return seen


def compute(graph, configured=(), gitignore=(), denylist=(), defaults=True,
            root=""):
    """Structural metrics per surviving repository-relative path.

        {"entities": {path: {"fan_in", "fan_out", "blast_radius",
                             "neighborhood", "bindings"}},
         "excluded": [...],      # what the filter dropped, and why
         "bindings": {...},      # per-binding status, so a silent outage is not silent
         "applied": {...}}       # bands and edge types actually used

    Excluded paths are filtered BEFORE any edge is counted, so an excluded
    path contributes no fan-in, appears in no neighborhood, and cannot reach
    a candidate through a metric.
    """
    facts = graph.get("facts") or {}
    partition = exclusions.partition_paths(
        [item.get("path") for item in (facts.get("files") or {}).values()],
        configured=configured, gitignore=gitignore, denylist=denylist,
        defaults=defaults, root=root,
    )
    kept = set(partition["kept"])

    resolved = _resolve(graph)
    participating = _participation(graph)

    # Distinct (dependent, dependency) path pairs, deduped across edge type.
    dependencies = {}
    dependents = {}
    adjacency = {}
    for edge in facts.get("edges") or ():
        if edge.get("type") not in DEPENDENCY_EDGE_TYPES:
            continue
        source = resolved.get(edge.get("source"))
        target = resolved.get(edge.get("target"))
        if source not in kept or target not in kept or source == target:
            continue
        dependencies.setdefault(source, set()).add(target)
        dependents.setdefault(target, set()).add(source)
        if edge.get("type") in NEIGHBORHOOD_EDGE_TYPES:
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set()).add(source)

    entities = {}
    for path in sorted(kept):
        bindings = participating.get(path) or set()
        status = _entity_coverage(
            graph, bindings, DEPENDENCY_EDGE_TYPES, path
        )
        blast = _closure([path], dependents)
        blast.discard(path)
        entities[path] = {
            "fan_in": measurement(len(dependents.get(path, ())), status),
            "fan_out": measurement(len(dependencies.get(path, ())), status),
            "blast_radius": measurement(len(blast), status),
            "neighborhood": sorted(adjacency.get(path, ())),
            "bindings": sorted(b for b in bindings if b),
        }

    return {
        "entities": entities,
        "excluded": partition["excluded"],
        "bindings": {
            binding_id: {"status": info.get("status"),
                         "freshness": info.get("freshness")}
            for binding_id, info in sorted(
                (graph.get("bindings") or {}).items())
        },
        "applied": {
            "bands": list(BANDS),
            "dependency_edge_types": list(DEPENDENCY_EDGE_TYPES),
            "neighborhood_edge_types": list(NEIGHBORHOOD_EDGE_TYPES),
            "exclusions": partition["applied"],
        },
    }
