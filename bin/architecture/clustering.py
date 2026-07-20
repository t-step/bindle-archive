"""architecture.clustering — monotonically-degrading component grouping and
deterministic naming (issue #229 child C, slice C2, epic #141).

#141 freezes clustering as "deterministic per capability set and
[degrading] monotonically — a lost capability may merge or coarsen
groupings, never silently re-partition them". That rules out the obvious
choice: modularity optimizers are notoriously non-monotonic under edge
removal, so PT16 would become a hope rather than a guarantee, and slice 5
already learned that contract wording ("bipartite assignment") does not
license an optimizer.

THE RULE IS PATH-DOMINANT WITH EDGE REFINEMENT, and monotonicity falls out
of its structure rather than being argued for:

  * a directory QUALIFIES as a component boundary when it holds at least
    MIN_INTERNAL_EDGES edges with both endpoints inside it — which implies
    at least two member files, since an internal edge's endpoints are two
    distinct paths beneath it, so no separate member floor is needed;
  * every file joins its DEEPEST qualifying ancestor directory, or the root
    cluster when none qualifies.

Losing a capability removes edges. Removing edges can only lower an internal
count, which can only un-qualify a directory, which can only move its files
to a SHALLOWER ancestor. Cluster boundaries always fall on directory
boundaries, so a coarser result is always a union of finer ones — never a
re-partition. That is a structural argument a test can check directly, and
test_clustering does.

Edges REFINE rather than merge, which is the direction that makes this work.
Under a merge rule, fewer edges would mean less merging and therefore a
FINER partition — precisely the re-partitioning the contract forbids.

NAMING IS DETERMINISTIC AND ALWAYS EXISTS (R3). The name is the dominant
path segment; colliding names extend leftward one segment at a time until
unique. #141 assigns human-readable naming to OPTIONAL model assistance, so
a cluster that could not name itself would silently make child I
load-bearing — I may only IMPROVE this name, never supply the first one.
"""
from architecture import metrics

# A single internal edge is evidence enough that a directory is a unit. A
# module constant for the same reason bands are: config.thresholds is frozen
# at exactly {high, low} and rejects unknown keys.
#
# There is deliberately no separate member floor. A mutation run proved one
# redundant: an internal edge's two endpoints are distinct paths beneath the
# directory, so any directory clearing this floor already has two members,
# and a `>= 2` member check could never fail. A knob that cannot bind is
# worse than no knob -- it reads as a guard while guarding nothing.
MIN_INTERNAL_EDGES = 1

ROOT_CLUSTER_NAME = "root"


def _ancestors(path):
    """Every directory containing `path`, deepest first, ending at root."""
    out = []
    parts = path.split("/")[:-1]
    while parts:
        out.append("/".join(parts))
        parts = parts[:-1]
    out.append("")
    return out


def _common_directory(left, right):
    """The deepest directory containing both paths."""
    left_parts = left.split("/")[:-1]
    right_parts = right.split("/")[:-1]
    shared = []
    for a, b in zip(left_parts, right_parts):
        if a != b:
            break
        shared.append(a)
    return "/".join(shared)


def _qualifying(pairs):
    """Directories holding enough internal evidence to be a boundary."""
    internal = {}
    for source, target in pairs:
        directory = _common_directory(source, target)
        # `directory + "/x"` makes the directory itself the first ancestor,
        # so an edge inside bin/auth credits bin/auth, bin and the root.
        for ancestor in _ancestors(directory + "/x"):
            internal[ancestor] = internal.get(ancestor, 0) + 1

    return {
        directory
        for directory, count in internal.items()
        if count >= MIN_INTERNAL_EDGES
    }


def _assign(paths, qualifying):
    """Each path to its deepest qualifying ancestor, else the root cluster."""
    assigned = {}
    for path in paths:
        prefix = ""
        for ancestor in _ancestors(path):
            if ancestor in qualifying:
                prefix = ancestor
                break
        assigned.setdefault(prefix, []).append(path)
    return assigned


def _names(prefixes):
    """Dominant path segment per prefix, extended leftward until unique.

    Two `auth` directories in one project are ordinary, and a duplicate name
    would make two notes indistinguishable in the notes home. Extension is
    deterministic and bounded by the prefix itself, so the worst case is the
    full path — legible, and still stable run over run.
    """
    prefixes = list(prefixes)
    depth = {prefix: 1 for prefix in prefixes}

    def render(prefix, levels):
        if prefix == "":
            return ROOT_CLUSTER_NAME
        return "/".join(prefix.split("/")[-levels:])

    for _round in range(max((p.count("/") + 1 for p in prefixes), default=1)):
        rendered = {}
        for prefix in prefixes:
            rendered.setdefault(
                render(prefix, depth[prefix]), []).append(prefix)
        collisions = [group for group in rendered.values() if len(group) > 1]
        if not collisions:
            break
        for group in collisions:
            for prefix in group:
                if depth[prefix] < len(prefix.split("/")):
                    depth[prefix] += 1

    return {prefix: render(prefix, depth[prefix]) for prefix in prefixes}


def _boundary_metric(members, pairs, entities, direction):
    """One cluster-level reading, counting only edges crossing its boundary.

    Summing member fan-in would double-count every internal edge and read a
    cohesive component as a hub. Coverage is combined from the members' own
    readings, so a cluster spanning an unobserved subtree reads partial
    rather than confidently wrong.
    """
    members = set(members)
    external = set()
    for source, target in pairs:
        inside, outside = (target, source) if direction == "in" else (
            source, target)
        if inside in members and outside not in members:
            external.add(outside)
    field = "fan_in" if direction == "in" else "fan_out"
    status = metrics.combine_coverage(
        [entities[path][field]["coverage"] for path in sorted(members)]
    )
    return metrics.measurement(len(external), status)


def cluster(metrics_result, graph):
    """Group the surviving entities into component clusters.

        {"clusters": [{"prefix", "name", "members", "metrics"}, ...],
         "applied": {...}}

    Ordered by prefix, so a diff of two runs is a diff of content rather
    than of iteration order.
    """
    entities = metrics_result["entities"]
    kept = set(entities)
    pairs = metrics.dependency_pairs(graph, kept)

    qualifying = _qualifying(pairs)
    assigned = _assign(kept, qualifying)
    names = _names(sorted(assigned))

    dependents = {}
    for source, target in pairs:
        dependents.setdefault(target, set()).add(source)

    clusters = []
    for prefix in sorted(assigned):
        members = sorted(assigned[prefix])
        blast = set()
        queue = list(members)
        while queue:
            current = queue.pop()
            for dependent in dependents.get(current, ()):
                if dependent in blast:
                    continue
                blast.add(dependent)
                queue.append(dependent)
        blast -= set(members)
        blast_status = metrics.combine_coverage(
            [entities[path]["blast_radius"]["coverage"] for path in members]
        )
        clusters.append({
            "prefix": prefix,
            "name": names[prefix],
            "members": members,
            "metrics": {
                "fan_in": _boundary_metric(members, pairs, entities, "in"),
                "fan_out": _boundary_metric(members, pairs, entities, "out"),
                "blast_radius": metrics.measurement(len(blast), blast_status),
            },
        })

    return {
        "clusters": clusters,
        "applied": {
            "min_internal_edges": MIN_INTERNAL_EDGES,
            "root_cluster_name": ROOT_CLUSTER_NAME,
        },
    }
