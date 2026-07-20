"""architecture.candidates — bounded codebase-map and component candidates
(issue #229 child C, slice C2, epic #141).

What a projection run PROPOSES, before anything is confirmed and before any
identity exists. A candidate is planning state: it carries a
`candidate_key`, which is a per-run join key, and never an `arch_id`, which
only child B may allocate at a confirmed creation event.

THE RECORD IS RICHER THAN THE MATCHER'S, AND THE PROJECTION LIVES HERE.
#228's matcher freezes its input at exactly {candidate_key, projection_type,
source_paths, symbol_names, neighborhood} and HARD ABORTS on any other
field — provider-specific fields are refused rather than ignored. But C must
also carry a name (R3), banded metrics, entry points and binding provenance
for child D to render. So `plan` returns the rich record and `matcher_view`
projects it down. Keeping the projection here means `CANDIDATE_KNOWN` and
its only producer sit in one greppable place, and it lets this slice's own
tests run `matcher.match()` over its output — the only integration guard
available while D does not exist.

ENTRY POINTS ARE ENGINE-DERIVED. #229 allows `is_exported` as a HINT ONLY:
"a provider's entry-point observation is never authoritative". This slice
consumes no hints at all, which is always contract-legal — a provider that
marks every symbol exported cannot manufacture an entry point here. What
remains is provider-independent: a conventional entry filename, and a file
nothing else depends on. The second is gated on observability, because
"nothing depends on it" and "nobody could see what depends on it" are the
absence-vs-zero distinction again, and only the first is an entry point.

THE CODEBASE MAP IS BUILT FROM CLUSTER PREFIXES, NOT FROM EVERY FILE. Its
signals must survive an ordinary edit: a map whose `source_paths` listed
every file in the repository would change on every commit, and that set is
the join key D reuses. Cluster prefixes move only when the project's
structure moves.

`candidate_key` is DOMINANT-PATH DERIVED (`component:<prefix>`), not a hash
of the member set. A member-set hash changes on every ordinary edit, which
makes the changed-set maximal and defeats AC11 and PT31 — "a commit touching
one unrelated file rewrites zero notes".
"""
from architecture import clustering
from architecture import matcher
from architecture import metrics

CODEBASE_MAP_KEY = "codebase-map"
COMPONENT_KEY_PREFIX = "component:"

# The root cluster has no prefix; "." names it in a key and in the map's own
# source_paths, since an empty string reads as a missing value.
ROOT_PREFIX_TOKEN = "."

RECORD_FIELDS = frozenset(matcher.CANDIDATE_KNOWN) | frozenset([
    "name", "metrics", "entry_points", "bindings", "member_count",
])

# Provider-independent filename conventions. Deliberately short: every name
# here is a near-universal program entry, and a speculative addition would
# manufacture entry points on repositories that never meant them.
CONVENTIONAL_ENTRY_NAMES = frozenset([
    "__main__.py",
    "main.py",
    "main.go",
    "main.rs",
    "main.c",
    "main.cpp",
    "index.js",
    "index.ts",
    "index.mjs",
])

ENTRY_REASONS = ("conventional_name", "no_dependents")


def matcher_view(candidate):
    """Project a rich candidate down to exactly the matcher's input shape.

    Lists are copied. The matcher coerces its signals to frozensets and does
    not mutate, but handing a caller a live reference into planning state
    invites a mutation invisible from both sides.
    """
    view = {}
    for field in matcher.CANDIDATE_KNOWN:
        value = candidate.get(field)
        view[field] = (
            list(value) if isinstance(value, (list, tuple)) else value
        )
    return view


def _entry_points(members, entities):
    """Engine-derived entry points for one cluster, sorted, one per path."""
    found = []
    for path in sorted(members):
        if path.split("/")[-1] in CONVENTIONAL_ENTRY_NAMES:
            found.append({"path": path, "reason": "conventional_name"})
            continue
        entity = entities[path]
        fan_in = entity["fan_in"]
        fan_out = entity["fan_out"]
        # Only an OBSERVED zero is evidence. Under partial or unknown
        # coverage the honest reading is "unknown", and claiming an entry
        # point there is the fabricated-zero failure wearing a hat.
        if fan_in["coverage"] != "observed" or fan_in["value"] != 0:
            continue
        # A lower bound is the right question here: "it depends on at least
        # one thing" survives partial coverage, where an exact value does
        # not. Using `value` would make this gate unreachable whenever
        # coverage is partial -- and would leave the fan_in gate above
        # untestable, since both readings share an entity's coverage.
        if (fan_out["lower_bound"] or 0) > 0:
            found.append({"path": path, "reason": "no_dependents"})
    return found


def _symbol_names(graph, members):
    """Symbol NAMES declared in the cluster's own files.

    Names, never provider ids: an id's format changes across provider
    versions, so scoring on one would route every node to reconciliation on
    a patch bump.
    """
    members = set(members)
    names = set()
    for symbol in ((graph.get("facts") or {}).get("symbols") or {}).values():
        if symbol.get("path") in members and symbol.get("name"):
            names.add(symbol["name"])
    return sorted(names)


def _neighborhood(members, entities):
    """Adjacent paths outside the cluster, deduped and sorted."""
    members = set(members)
    hood = set()
    for path in members:
        hood.update(entities[path]["neighborhood"])
    return sorted(hood - members)


def plan(graph, configured=(), gitignore=(), denylist=(), defaults=True,
         root=""):
    """Produce this run's candidate records.

        {"candidates": [...],   # ordered by candidate_key
         "clusters": [...], "entities": {...}, "excluded": [...],
         "bindings": {...}, "applied": {...}}

    Deterministic end to end: identical interchange and configuration
    produce byte-identical output, which is what lets child D's unchanged
    rerun write zero bytes.
    """
    measured = metrics.compute(
        graph, configured=configured, gitignore=gitignore, denylist=denylist,
        defaults=defaults, root=root,
    )
    entities = measured["entities"]
    grouped = clustering.cluster(measured, graph)

    records = []
    for group in grouped["clusters"]:
        members = group["members"]
        records.append({
            "candidate_key": COMPONENT_KEY_PREFIX + (
                group["prefix"] or ROOT_PREFIX_TOKEN),
            "projection_type": "arch_component",
            "source_paths": list(members),
            "symbol_names": _symbol_names(graph, members),
            "neighborhood": _neighborhood(members, entities),
            "name": group["name"],
            "metrics": group["metrics"],
            "entry_points": _entry_points(members, entities),
            "bindings": sorted({
                binding
                for path in members
                for binding in entities[path]["bindings"]
            }),
            "member_count": len(members),
        })

    records.append({
        "candidate_key": CODEBASE_MAP_KEY,
        "projection_type": "arch_codebase_map",
        "source_paths": [group["prefix"] or ROOT_PREFIX_TOKEN
                         for group in grouped["clusters"]],
        "symbol_names": sorted(group["name"] for group in grouped["clusters"]),
        "neighborhood": [],
        "name": CODEBASE_MAP_KEY,
        "metrics": {},
        "entry_points": [],
        "bindings": sorted(measured["bindings"]),
        "member_count": len(grouped["clusters"]),
    })

    return {
        "candidates": sorted(records, key=lambda r: r["candidate_key"]),
        "clusters": grouped["clusters"],
        "entities": entities,
        "excluded": measured["excluded"],
        "bindings": measured["bindings"],
        "applied": {
            "metrics": measured["applied"],
            "clustering": grouped["applied"],
            "conventional_entry_names": sorted(CONVENTIONAL_ENTRY_NAMES),
        },
    }
