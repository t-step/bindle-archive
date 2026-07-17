# Context-graph v1 schema reference

Companion reference to the frozen design record at
`docs/design/2026-07-16-context-graph-schema.md` (issue #180, epic #140).
This document describes the *shipped* contract as implemented in
`bin/context_graph/` and `schemas/context-graph/v1/`; the design record is
the historical decision log and stays unedited going forward — if the two
ever diverge, this file and the code are authoritative and the design
record is corrected to match, not the reverse.

## What this contract is

A provider-neutral interchange contract for the context-graph epic (#140):
opaque project/repository identity, semantic and evidence nodes, typed
directed edges governed by a closed endpoint matrix, untrusted proposals,
validated candidates, append-only judgments, and derived index state. The
native Python package (`bin/context_graph/`) is the runtime authority; the
seven `schemas/context-graph/v1/*.schema.json` files are documentation and
interchange contracts for other-language consumers, kept in sync via a
bidirectional conformance test (`bin/test-context-graph-schema.sh`), never
via code generation or runtime schema loading.

## Package layout

| Module | Owns |
|---|---|
| `context_graph.ids` | Typed-ID parsing/formatting only. No I/O. |
| `context_graph.relationships` | Closed relationship vocabulary, endpoint matrix, `review_trigger` defaults. Relationship-intrinsic authority metadata only. |
| `context_graph.canonical` | Basis-entry normalization, canonical basis serialization, the two candidate-key primitives, the two fingerprint primitives. No object validation beyond canonicalization needs. |
| `context_graph.validation` | Per-object-kind validation, whole-object-kind creation-authority checks, cross-object rules, deterministic finding order. |

Callers use explicit import paths
(`from context_graph.ids import parse_typed_id`); `context_graph/__init__.py`
carries only a docstring and `SCHEMA_VERSION`.

## Typed-ID formats

```text
project:<32-lowercase-hex>
context-node:<creation-project-slug>:<32-lowercase-hex>
repository-binding:<32-lowercase-hex>
session:<project-id>:sessions/<filename>.md
handoff:<project-id>:handoffs/<filename>.md
document:<project-id>:<binding-id>:<repository-relative-path>
document:<project-id>:project-local:<project-relative-path>
github-issue:<owner>/<repo>#<n>
github-pr:<owner>/<repo>#<n>
candidate:sha256:<64-lowercase-hex>
anchor-candidate:sha256:<64-lowercase-hex>
```

## Node classes and kinds

Classes: `project`, `semantic`, `evidence`. Semantic kinds: `decision`,
`learning`, `assumption`, `tension`, `question`. Evidence kinds: `session`,
`handoff`, `design_document`, `github_issue`, `github_pr`. Reserved future
semantic kinds (documented, never emitted in v1):
`problem`, `concept`, `constraint`, `solution`, `pattern`, `principle`,
`architecture_component`, `architecture_flow`, `boundary`, `test_surface`.

`confidence` is valid only on `assumption` and `tension` nodes. A `tension`
node carries exactly two `sides`, each `{label, evidence}` — sides are
structured attributes, never independently addressable nodes.

## Relationship endpoint matrix

Fourteen v1 relationships, each with one closed source/target
class+kind constraint (`bin/context_graph/relationships.py:ENDPOINT_MATRIX`
is authoritative — this table is a summary):

| Relationship | Source | Target | Authority |
|---|---|---|---|
| `contains` | project | semantic-any | deterministic |
| `supported_by` | semantic-any | evidence-any | deterministic |
| `discussed_in` | semantic-any | evidence-any | judgment |
| `implemented_by` | decision | github_pr | judgment |
| `validated_by` | decision/learning | validation-evidence | judgment |
| `closes` | github_pr | github_issue | deterministic |
| `motivates` | semantic-any | decision/question | judgment |
| `constrains` | decision/learning/assumption/tension | decision/assumption/tension/question | judgment |
| `depends_on` | semantic-any | semantic-any | judgment (no self-edges) |
| `resolves` | decision/learning | question/assumption/tension | judgment |
| `supports` | decision/learning/assumption | semantic-any | judgment |
| `contradicts` | decision/learning/assumption | (same set) | judgment (symmetric, canonical ordering) |
| `supersedes` | any semantic-any kind | same kind | deterministic or judgment (no self-edges) |
| `revisits` | semantic-any | decision/learning/assumption/tension | judgment |

`implements` is not part of v1 — validators reject it. Implementation
attribution uses `decision --implemented_by--> github_pr`.

## Candidate-key canonicalization

Two versioned, byte-exact primitives plus two fingerprint primitives, all
in `context_graph.canonical`:

- **Edge candidates** (`bindle-context-candidate-v1`,
  `candidate:sha256:<hex>`): basis entries are typed JSON objects with a
  fixed field set per kind (v1 defines one kind, `evidence_pointer`:
  `location` ∈ {`entry_evidence`, `tension_side`}, `pointer` free text),
  deduplicated and sorted by serialized UTF-8 bytes before framing.
- **Identity-anchor candidates** (`bindle-context-anchor-candidate-v1`,
  `anchor-candidate:sha256:<hex>`): five mandatory direct frame fields
  (`project_id`, `map_path`, `section`, `entry_kind`, `entry_fingerprint`),
  no basis array. Built from `entry_fingerprint`
  (`bindle-context-entry-fingerprint-v1`) and staleness uses
  `anchor_dependency_fingerprint` (`bindle-context-anchor-dependency-v1`).

See `docs/design/2026-07-16-context-graph-schema.md` §10 for the full
worked byte-exact example (reproduced as a `canonicalization/` fixture).

## Validation model and finding codes

`context_graph.validation.validate_bundle(bundle)` is the entry point: a
bundle is `{config?, nodes?, edges?, candidates?, judgments?}`. A bundle may
also carry a `proposals` key (untrusted semantic proposals), but
`validate_bundle` does not read or validate it — proposal validation is
#184's future responsibility, not #180's.
Findings are returned in a fixed, deterministic order (registration order
of the invariant category, then object index) and never stop at the first
error. The full closed set of finding codes lives in
`context_graph.validation.FINDING_CODES` and is classified in
`schemas/context-graph/v1/invariant-coverage.json` as
`schema-and-native`, `native-only`, or `schema-only-documentation`.

## Fixture corpus

`testdata/context-graph/v1/manifest.json` is the single authoritative
registry — execution order, expected results, and finding codes all come
from the manifest, never from filename or directory position. Fixtures are
grouped by contract category: `core/`, `map-shape/`, `endpoint-matrix/`,
`identity-config/`, `candidates/`, `canonicalization/`, `documents/`. Run
`bin/test-context-graph-schema.sh` to execute the whole corpus plus the
JSON-Schema/native conformance pass.

## Non-goals (owned elsewhere)

This contract does not parse project maps (#183), resolve GitHub (#183/
#184), allocate or persist project identity (#191), build `index.json` from
live sources or write `context.md` (#185), implement preview/confirm/apply
(#184/#185), or create a model-assisted proposal skill (#186).
