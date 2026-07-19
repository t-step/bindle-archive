"""structural_graph.graphset -- multi-document set load (#227).

One interchange document covers exactly one (binding, commit). A project
with several repository bindings therefore has a set of documents, and this
module loads them into one combined fact view.

Paths and symbol ids are binding-qualified as "<binding_id>::<value>" at
load, so an identical path in two repositories can never merge into one
fact. Aggregation propagates unavailable and unsupported as partial or
unknown and never sums them as zero: a capability nobody could observe is
not a capability observed to be empty.

A partial outage is contained. One binding failing to load leaves every
other binding's facts intact, per FC-4.
"""

from structural_graph import coverage
from structural_graph import document


def load_set(cfg, paths_by_binding):
    """Load one document per configured binding into a combined view.

    paths_by_binding maps binding_id -> document path. A configured binding
    with no entry, or whose document is absent, is reported unavailable.

    Precondition: cfg must already be valid per context_graph.validation's
    rules -- in particular, no two entries in cfg["repositories"] share a
    binding_id (context_graph.validation's E_CONFIG_DUPLICATE_BINDING_ID
    rejects that at config-validation time). This function does not
    re-validate the config; that would duplicate a rule that already lives
    in context_graph.validation, which is the drift #227 spent four review
    rounds unlearning. What it does do is protect its own invariant: it
    keys `bindings` on binding_id, so two configured entries sharing one
    would silently collapse into a single loaded document with no finding
    and no error -- a malformed config passing unnoticed. A project config
    is a caller-supplied argument, not untrusted document content, so under
    the #227 contract (the never-raise guarantee covers document content;
    a malformed argument is caller error) a duplicate here is caller error
    and load_set raises ValueError, the same precedent
    context_graph.evidence.MalformedIdentityError sets for a malformed
    --project-id.

    Findings gain a fifth key here. Inside a document, a finding is the
    four-key {"code", "message", "index", "field"} shape that
    validation.finding builds and validation.py enforces; a set spans
    documents, so a finding is meaningless without saying which binding it
    came from, and this layer adds "binding_id" as it copies each one. That
    is a set-level shape, deliberately one layer above where the four-key
    rule holds -- the per-document findings themselves are never mutated.
    """
    bindings = {}
    files = {}
    symbols = {}
    edges = []
    findings = []

    configured = [
        repo.get("binding_id") for repo in (cfg or {}).get("repositories") or []
    ]
    seen_at = {}
    ordered = []
    for i, binding_id in enumerate(configured):
        if not binding_id:
            continue
        if binding_id in seen_at:
            raise ValueError(
                "load_set: config repositories[%d] has binding_id %r, "
                "already used at repositories[%d] -- caller must pass a "
                "config already valid per context_graph.validation "
                "(E_CONFIG_DUPLICATE_BINDING_ID)"
                % (i, binding_id, seen_at[binding_id])
            )
        seen_at[binding_id] = i
        ordered.append(binding_id)

    for binding_id in sorted(ordered):
        path = (paths_by_binding or {}).get(binding_id)
        if not path:
            bindings[binding_id] = {
                "status": "unavailable",
                "freshness": "freshness_unknown",
                "coverage": [],
                "capabilities": [],
            }
            continue
        result = document.load(path, cfg)
        facts = result["facts"] or {}
        bindings[binding_id] = {
            "status": result["status"],
            "freshness": result["freshness"],
            "coverage": facts.get("coverage") or [],
            "capabilities": facts.get("capabilities") or [],
        }
        for found in result["findings"]:
            entry = dict(found)
            entry["binding_id"] = binding_id
            findings.append(entry)
        if result["status"] != "loaded":
            continue
        for item in facts.get("files") or []:
            files[binding_id + "::" + item["path"]] = dict(item, binding_id=binding_id)
        for item in facts.get("symbols") or []:
            symbols[binding_id + "::" + item["id"]] = dict(item, binding_id=binding_id)
        for item in facts.get("edges") or []:
            edges.append(
                dict(
                    item,
                    binding_id=binding_id,
                    source=binding_id + "::" + item["source"],
                    target=binding_id + "::" + item["target"],
                )
            )

    return {
        "bindings": bindings,
        "facts": {"files": files, "symbols": symbols, "edges": edges},
        "findings": findings,
    }


def aggregate_coverage(result, capability, path):
    """Combine per-binding coverage for capability at path.

    Returns "observed" only when every participating binding observed it,
    "partial" when at least one observed and any other did not, and
    "unknown" when no binding could observe it at all. Never returns a
    count, and never treats unavailable as zero.
    """
    observed = 0
    degraded = 0
    for binding_id in sorted(result.get("bindings") or {}):
        info = result["bindings"][binding_id]
        if info["status"] != "loaded":
            degraded += 1
            continue
        if capability not in (info.get("capabilities") or []):
            degraded += 1
            continue
        status = coverage.status_for(info.get("coverage") or [], capability, path)
        if status == "observed":
            observed += 1
        else:
            degraded += 1
    if observed and not degraded:
        return "observed"
    if observed:
        return "partial"
    return "unknown"
