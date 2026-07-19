# Structural-graph interchange and reference provider — design

**Issue:** #227 (child of epic #141) · **Date:** 2026-07-18 · **Status:** approved design, pre-implementation

## Context

Epic #141 projects a human-readable architecture map from a structural graph.
Its §7 freezes a **canonical, versioned, provider-neutral local structural-graph
interchange** between any provider and the projection engine: the engine consumes
only the interchange and never imports CodeGraph or any other provider.

#227 builds that seam — the interchange schema plus a reference JSON
reader/provider. It blocks children B, C, D, E, and H, so its contracts are load
bearing for every later child. Nothing else in #141 can start until the shape of
a structural fact is settled.

The interchange carries **raw structural facts only**. Every conclusion — fan-in,
fan-out, blast radius, clustering, ranking — is engine-owned (#141 §4). A
provider's own interpretations enter only as capability-gated hints that never
silently replace engine normalization.

## Decisions

Five decisions were taken during brainstorming; each closes an ambiguity the
issue body leaves open.

1. **Unnormalizable strings split by field role.** Anchors fail closed; incidental
   strings are redacted and kept. See "Redaction".
2. **Surface is library + fixture runner.** No user-facing CLI verb. #231 adds one
   when it has a real caller.
3. **`coverage[]` is `(path_prefix × capability)` and must tile.** Exhaustive over
   the declared root, no gaps, no overlaps. Each document declares a
   `root` — a repository-relative prefix, `""` for the whole repository —
   bounding what its coverage entries must tile and what its facts may reference.
4. **One document per `(binding, commit)`.** The reader loads a *set*.
5. **Parallel package `bin/structural_graph/`**, importing `context_graph`
   one-directionally and never the reverse.

## Architecture

New package `bin/structural_graph/`, six modules, each independently testable.

| Module | Owns |
|---|---|
| `schema.py` | Version constants; frozen vocabularies as module-level tuples (symbol `kind` + `other` escape, edge types, capability names, coverage statuses, document states); the **anchor-field registry**. |
| `redaction.py` | `normalize_path()` → repo-relative or `None`; `redact()` → scrubbed string + finding. Encodes the repo's secret-pattern inventory. |
| `validation.py` | Hand-rolled structural validation. Returns finding lists, never raises. `E_SG_*` codes in a `FINDING_CODES` tuple. |
| `coverage.py` | Tiling verification (exhaustive, non-overlapping, per capability) and `status_for(path, capability)`. |
| `document.py` | Single-document load → normalized facts or an explicit state. |
| `graphset.py` | Set load across bindings; binding-qualified paths and symbols; aggregation. |

Supporting artifacts:

- `schemas/structural-graph/v1/document.schema.json`
- `schemas/structural-graph/v1/invariant-coverage.json`
- `testdata/structural-graph/v1/` with `manifest.json`
- `bin/check-structural-graph-fixtures.py`
- `bin/test-structural-graph.sh`

### Why a parallel package

#141 §4 separates the structural provider's authority (raw observed facts) from
the context graph's authority (semantic identity, confirmed judgment). A parallel
package makes that split checkable as an import rule: `structural_graph` imports
`context_graph.ids` (binding-id grammar) and `context_graph.config` (binding
membership), and `context_graph` never imports `structural_graph`.

Placing these modules inside `context_graph` would merge two authorities into one
package, one `FINDING_CODES` namespace, and one `invariant-coverage.json`.

### House conventions inherited

Verified against the existing package, and followed without exception:

- **No type hints, no dataclasses, no `Enum`.** Every structure is a plain dict;
  enumerated sets are module-level tuples or frozensets mirrored into JSON Schema
  `enum`, the way `relationships.RELATIONSHIPS` mirrors `edge.schema.json`.
- **Runtime validation is hand-rolled**; `jsonschema` is test-only, injected by the
  pre-commit hook.
- **Schema version by directory** (`v1/`), re-asserted in each schema's `$id` and
  as a top-level `schema_version` integer pinned with `const`.
- **Findings are `{code, message, index, field}` dicts** in a fixed order.
- **Determinism asserted, not assumed** — sorted keys, no timestamps in output.

## Redaction

Redaction is a **build gap, not a reuse**. No path-relativization helper and no
secret-scrubbing function exist anywhere in `bin/`. The existing
`check-private-info.sh` and the gitleaks config are *detectors* that never rewrite
content. The only reusable inputs are their regex patterns.

`evidence.normalize` must not be mistaken for prior art: its
`_classify_local_path` rejects an unsafe path and returns a result dict whose
`value` is the **original unmodified atom**, propagating the raw absolute path
into every consumer. That is a leak path, and it is the specific defect this
design guards against.

**Field-role split (frozen in `schema.py`):**

- **Anchors** — file paths, symbol IDs and names, edge endpoints,
  `coverage[].path_prefix`. Unnormalizable → document is `malformed`, nothing
  loads. A redacted anchor is not a degraded fact but an unusable one, and keeping
  it risks a false path-overlap match in the #228 matcher.
- **Incidental** — diagnostics, log lines, provider display labels, route hints,
  everything under `optional_provider_observations`. Unnormalizable → redact in
  place, record a finding, keep the fact.

**Findings never echo the offending value.** They carry the field path and the
reason only. Redaction runs before any finding is constructed, so a finding is
structurally incapable of carrying an unredacted string.

`redaction.py` encodes a home-directory path pattern, which is exactly what the
private-info scanner greps for — the same reason that scanner and the gitleaks
config are already self-exempt. The module therefore needs a `SKIP_FILES` entry
and a gitleaks allowlist path. This is a small, deliberate, reviewed edit to a
privacy gate.

## Data flow

`graphset` iterates configured bindings; `document` runs each through a fixed
order. **The order is part of the contract** — fail-closed must precede everything.

1. Parse JSON. Unparseable → `malformed`.
2. Read `schema_version`. Outside the supported set → `unsupported_version`, **stop
   immediately**. A document from an unknown version cannot be meaningfully
   validated against v1 rules; continuing is how fail-closed degrades into
   best-effort.
3. Structural validation. Blocking findings → `malformed`.
4. `binding_id`: shape via `ids.parse_typed_id` (bad shape → `malformed`), then
   membership against `config["repositories"]` (absent → `deconfigured`).
5. Coverage tiling. Gap or overlap → `malformed`.
6. Redaction pass, field-role aware.
7. Freshness: with `local_checkout_path`, compare `source_commit` to HEAD; without
   one, `freshness_unknown`.

### Result shape

Load outcome and freshness are **orthogonal axes**, not one enum. A stale graph is
readable — FC-4 requires an outage to carry forward rather than delete — so
collapsing freshness into the failure enum would force downstream children to
discard valid facts.

```text
{"status": loaded | malformed | unsupported_version | deconfigured | unavailable,
 "freshness": current | stale | freshness_unknown,
 "findings": [...],
 "facts": {...} | None}
```

A sentinel-string discriminator in a plain dict, matching the `evidence.py`
precedent.

### Aggregation

`graphset` combines per-binding coverage per capability. If any contributing
binding is `unavailable` or `deconfigured`, or reports `unsupported` or
`partial_parse_failure` for a subtree, the aggregate is `unknown` or `partial` —
**never summed as `0`**. Unsupported is not observed-zero.

Paths and symbols are binding-qualified at load, so an identical path in two
repositories cannot merge into one fact.

### Persistence and exceptions

**The reader writes nothing, ever** — no atomic-write import in the package. The
shared `read_json` raises unwrapped, so `document.py` translates
`FileNotFoundError` → `unavailable` and `ValueError` → `malformed` rather than
letting either escape.

Exceptions are reserved for **caller** error — a malformed `project_id` passed in
— mirroring `evidence.MalformedIdentityError`. Everything about the document's own
content is reported in the result dict.

## Testing

`bin/test-structural-graph.sh` runs stdlib `unittest` discovery over
`bin/structural_graph/tests`, the fixture-manifest runner, and corpus-level
assertions. It is registered in the `Makefile` **and** in the pre-commit config
with `language: python` and `additional_dependencies: ["jsonschema"]`.

Both registrations are required: CI runs `pre-commit run --all-files` and never
runs `make test`, so a Makefile-only harness would not execute in CI. The
`jsonschema` dependency is what makes the schema-conformance layer run at all —
it is `skipUnless`-gated and silently skips locally.

`invariant-coverage.json` classifies every `E_SG_*` code as `schema-and-native` or
`native-only`, asserted bidirectionally: every code is classified, and every
`schema-and-native` code has a fixture the JSON Schema genuinely rejects.

### Fixture corpus

At `testdata/structural-graph/v1/`, **exactly one category level deep** — the
conformance test globs one level and would silently miss anything nested.

| Category | Covers |
|---|---|
| `core/` | conforming documents that load |
| `versions/` | unsupported and missing `schema_version` |
| `malformed/` | unparseable, schema violations, bad binding shape |
| `bindings/` | foreign `binding_id`, multi-binding sets, cross-repo same-path and same-symbol collisions |
| `coverage/` | tiling gap, overlap, `unsupported` capability, `partial_parse_failure` subtree |
| `freshness/` | stale commit, missing checkout, absent document |
| `privacy/` | the adversarial set below |

New manifest assertion kinds beyond the existing runner's: `load_status`
(expected status, freshness, and finding codes), `redaction_purity`, `set_load`,
`aggregate_coverage`.

### Privacy fixtures

- absolute path in an **anchor** → `malformed`, nothing loads;
- absolute path in a **diagnostic** → fact survives, string redacted, no finding
  recorded (redaction of an incidental string is the normal, successful path,
  not a defect in the document; only an unredactable *anchor* fails a document
  closed);
- **finding-payload purity** — no finding emitted anywhere in the corpus contains
  a string matching the private-info or gitleaks patterns. This is the regression
  test for the `evidence.normalize` defect.

Authoring constraints:

- `private-ok` markers go on the **same physical line** as the offending string
  (the scanner does a plain per-line substring match).
- Secret-shaped strings stay bearer- or API-key-shaped and are **never PEM
  blocks**. The `detect-private-key` hook honors neither `private-ok` nor the
  scanner's skip list, and would hard-block the commit with no escape but a hook
  exclusion.

## Gate obligations

| Artifact | Obligation |
|---|---|
| every `bin/structural_graph/*.py` | `not_a_capability` ledger entry |
| every `bin/structural_graph/tests/test_*.py` | `not_a_capability` ledger entry |
| `bin/check-structural-graph-fixtures.py` | `not_a_capability` ledger entry |
| this spec | `not_a_capability` ledger entry |
| `bin/test-structural-graph.sh` | auto-excluded from the inventory; add to `Makefile` and pre-commit |
| `schemas/**`, `testdata/**` | none |
| `redaction.py` | private-info skip-list entry + gitleaks allowlist path |

## Scope boundary

Restating #227's own boundary so implementation cannot drift into siblings:

- **Not owned:** bounded candidate selection (#229); provider-specific metric
  algorithms (engine-owned, #229); the CodeGraph adapter (#231).
- **Consumes #140 identities read-only.** Creates no context-graph state, no
  context-graph edge, and no entry in the #184 judgment ledger.
- **Network access is never required.**
- #227's own acceptance is normalized-fact equivalence. **Plan equivalence is a
  combined D+E release gate**, not this child's bar.

Implementation follows superpowers:test-driven-development — this is code, not a
skill, so RED→GREEN per unit rather than a pressure-test campaign.
