# Design: provider-neutral context-graph schemas and fixtures (v1)

Resolves the design half of issue #180 (epic #140), unblocked by #179 (PR #195).
Status: **approved design, not yet implemented** — the #180 implementation and
every downstream child (#181, #182, #183, #184, #185, #186, #191) reference this
document and the consolidated issue bodies as the product source of truth. When
an implementation question is not answered here, the answer is decided in the
implementation issue and folded back into this document, not improvised
silently.

This design freezes the twenty-two decision areas #180 requires. It reconciles
the consolidated bodies of #140, #179, #180, #181, #182, #183, #184, #185, #186,
and #191, all of which are now marked "Consolidated body" — comments remain audit
history only. Where this record and a live issue body diverge, the live body
wins and this record must be corrected; no upstream contract is silently altered
here.

**Scope guard.** #180 designs and delivers *contracts, fixtures, and a
stdlib-only fixture validator*. It parses no maps, resolves no GitHub, calls no
model, allocates no identity, and writes nothing to any notes home. Identity
*allocation and persistence* is owned by **#191**, not #180 — a correction to
any earlier framing that implied #182 or a #180-local initializer owns it.

---

## 1. Problem and goals

### Problem

#140 connects several independently authoritative surfaces — the authoritative
context configuration, the owner-curated project map, sessions and handoffs,
committed design documents, GitHub issues and PRs, human-confirmed semantic
relationships, and generated projections. Without a single checked-in contract,
the deterministic compiler (#183), the judgment ledger (#184), the apply phase
(#185), the optional skill (#186), the initializer (#191), and future
architecture/cross-project work would each invent slightly different identity,
relationship, confidence, and authority rules. A closed relationship vocabulary
alone is insufficient: every advertised relationship needs an explicit creation
path, relationship names alone must never establish validity, and ontologically
illegal endpoints must be invariant failures rather than human-approvable
candidates.

### Goals

Freeze a minimal v1 interchange contract that is model- and provider-neutral and
that:

- defines opaque project identity and stable repository-binding identity;
- separates semantic nodes from evidence nodes, and deterministic edges from
  judged edges;
- uses typed, directed relationships governed by a **closed endpoint matrix**;
- assigns every v1 relationship one or more explicit creation authorities;
- distinguishes untrusted semantic proposals, validated edge candidates,
  deterministic identity-anchor candidates, append-only judgments, and derived
  effective state;
- freezes a versioned, byte-exact candidate-key canonicalization primitive that
  #183 and #184 both call and neither reimplements;
- keeps the JSON Schema files and the native Python validator in sync through a
  bidirectional conformance test rather than code generation or runtime schema
  loading;
- is compact enough to inspect and test, with canonical fixtures covering every
  node class, semantic kind, evidence kind, and relationship, plus every named
  invalid case.

### Non-goals

Allocating/persisting project identity (#191); parsing project maps (#183);
resolving GitHub (#183/#184); building `index.json` from live sources (#185);
writing `context.md` (#185); implementing preview/confirm/apply (#184/#185);
creating a model-assisted proposal skill (#186); architecture projection or
cross-project synthesis (later); emitting or interpreting the deferred semantic
`implements` relationship (never in v1).

---

## 2. Authorities and ownership boundaries

The runtime authority is the **native Python package** (`bin/context_graph/`).
The seven JSON Schema files are **documentation and interchange contracts** for
other-language consumers; they never execute at Bindle runtime.

Producer / validator / authority split (frozen; mirrors #182's required table
and #180's candidate-generation section):

| Artifact | Sole producer | Validation / canonicalization | Authority effect |
|---|---|---|---|
| deterministic node or edge | #183 compiler | #180 native validator + schemas | enters rebuilt graph directly; never a candidate, never a judgment |
| identity-anchor candidate | #183 compiler | #184 revalidation before judgment | none until accepted; accepted judgment authorizes #185 marker insertion |
| untrusted semantic proposal | human, #186 skill, or fixture | #184 | none |
| validated semantic (`edge`) candidate | #184 | #184 against current #183 graph + #180 matrix | eligible for human judgment only |
| accepted judgment event | #184 confirm flow after human choice | #184 ledger validation | authority for the effective judged edge or anchor authorization |
| persisted index / projection | #185 apply | full recomputation + validation | rebuildable materialized state |
| project/context configuration | #191 initializer | #180 `config.schema.json` + native validator | authority for project identity and repository operating context |

Authority table for the whole system (from #180, frozen verbatim in intent):
configuration → project identity and repository operating context; project map →
promoted claim text and current curated understanding; judgment ledger →
explicit human graph judgments; current source evidence → what artifacts
presently contain; GitHub → current issue/PR metadata and GitHub-declared
closure; index → rebuildable materialized view; generated Markdown → regenerable
presentation only. The prior index may retain last-known descriptive metadata
during degraded source access but may **not** preserve an otherwise unsupported
relationship.

**Hard boundaries this design enforces on the implementation.** The CLI is a
thin adapter (§4). The package is standard-library only. The package never loads
a JSON Schema file at runtime and never adds a runtime `jsonschema` dependency.
#183 and #184 never shell out to the CLI; they `import context_graph`. No issue
maintains an independent candidate-key, endpoint, ID, or canonicalization
implementation — all of it lives in the shared package.

---

## 3. Exact file layout

The frozen target layout for the #180 implementation (this design record itself
lives at `docs/design/2026-07-16-context-graph-schema.md` and is not part of
that layout):

```text
docs/
  context-graph-schema.md            # shipped human contract (companion to the schemas)

schemas/context-graph/v1/
  config.schema.json
  node.schema.json
  edge.schema.json
  proposal.schema.json
  candidate.schema.json
  judgment.schema.json
  index.schema.json
  invariant-coverage.json            # not a *.schema.json; the invariant→classification ledger

bin/
  context_graph/
    __init__.py                      # docstring + SCHEMA_VERSION only; no API re-exports
    ids.py
    relationships.py
    canonical.py
    validation.py
  check-context-graph-fixtures.py    # thin CLI adapter over the package
  test-context-graph-schema.sh       # test harness (auto-excluded from the inventory)

testdata/context-graph/v1/
  manifest.json                      # authoritative execution + reporting order
  core/
  map-shape/
  endpoint-matrix/
  identity-config/
  candidates/
  canonicalization/
  documents/
```

Decisions, with the repository evidence that fixes them:

- **`relationships.py`, not `matrix.py`** — the module owns the whole
  relationship contract (names, directionality, endpoint kinds, payload
  constraints, intrinsic relationship-level authority), of which the endpoint
  matrix is one part; `matrix.py` would under-name it. (Rejected in §20.)
- **`validation.py`, not `validate.py`** — matches the noun-form naming of the
  sibling modules and reads as "the validation contract," not an imperative
  script.
- **`__init__.py` stays minimal** — a package docstring and a
  `SCHEMA_VERSION = 1` constant only. It does **not** re-export the package API;
  callers use explicit paths (`from context_graph.ids import parse_typed_id`).
  Broad re-exports are rejected in §20.
- **No `models.py`** — plain dicts plus explicit validators are sufficient for a
  stdlib-only interchange contract; no repository evidence shows dataclasses are
  needed. Introducing it prematurely is rejected in §20. It may be revisited
  only if a concrete implementation obstacle proves dicts insufficient.
- **`docs/context-graph-schema.md` is a #180 implementation deliverable**, the
  human-readable companion contract that ships beside the schemas. It is *not*
  produced by this design task (which produces only this `docs/design/` record).

---

## 4. Module responsibilities

The package is the single home for all runtime contract logic. Public entry
points (explicit imports, exactly as the downstream issues will call them):

```python
from context_graph.ids import parse_typed_id
from context_graph.relationships import validate_endpoint_pair
from context_graph.canonical import candidate_key
from context_graph.validation import validate_candidate
```

**`ids.py`** — parsing and formatting of every typed ID, and the exact regexes:
- project ID `project:<32-lowercase-hex>`;
- semantic-node ID `context-node:<slug>:<32-lowercase-hex>` (the #179 form;
  regex `^context-node:([a-z0-9]+(?:-[a-z0-9]+)*):([0-9a-f]{32})$`, reused, not
  re-derived);
- repository-binding ID `repository-binding:<32-lowercase-hex>`;
- evidence IDs (`session:…`, `handoff:…`, `document:…`, `github-issue:…`,
  `github-pr:…`) per §5;
- candidate key `candidate:sha256:<64-lowercase-hex>` and judgment
  subject/candidate key shapes.
- No filesystem or network access.

**`relationships.py`** — the closed relationship vocabulary; per-relationship
directionality; source/target endpoint classes and kinds; the endpoint-matrix
rules (§7); edge-specific payload constraints; the symmetric-`contradicts`
canonical-ordering rule and the per-relationship default `review_trigger` value
(§7 coupling). It owns relationship-*intrinsic* authority metadata only
(deterministic-eligible vs judgment-required per relationship). Object-kind
creation-authority rules do **not** live here (see `validation.py`).

**`canonical.py`** — basis-entry normalization; canonical basis serialization;
candidate-key domain separation and framing; SHA-256 candidate-key generation
(§10); deterministic ordering and byte-exact deduplication. It performs no object
validation beyond what is required to canonicalize inputs that were already
validated upstream.

**`validation.py`** — validation of each object kind (config, node, edge,
proposal, candidate, judgment, index); object-kind creation-authority checks
(e.g. "a deterministic edge lacking its required source authority is invalid";
"a human-judged edge without a matching effective accepted judgment is
invalid"); composition of ID, relationship/endpoint, lifecycle, and cross-object
rules; native invariant findings with a deterministic finding order (§14).
Creation-authority rules that apply to a *whole object kind* live here, not as
scattered rules in `relationships.py`.

**`check-context-graph-fixtures.py`** (CLI) — a thin adapter, responsible only
for: argument parsing; loading JSON from disk; selecting the appropriate
validator entry point from the package; rendering machine-readable and
human-readable output; exit codes. It contains **no** independent copy of ID
parsing, endpoint rules, schema invariants, candidate-key logic, or
canonicalization — every such call goes to the package.

---

## 5. Typed-ID formats

All hex components are exactly 32 lowercase hexadecimal characters; a
16-character component is malformed (fixture 70).

```text
project:<32-lowercase-hex>
context-node:<creation-project-slug>:<32-lowercase-hex>        # #179 semantic node
repository-binding:<32-lowercase-hex>                          # stable binding_id

session:<project-id>:sessions/<filename>.md
handoff:<project-id>:handoffs/<filename>.md
document:<project-id>:<binding-id>:<repository-relative-path>   # repo-committed doc
document:<project-id>:project-local:<project-relative-path>     # project-owned, no repo

github-issue:<owner>/<repo>#<n>
github-pr:<owner>/<repo>#<n>
```

Frozen rules:

- `project_id` is opaque and never derived from GitHub coordinates, Git remotes,
  slug, display name, notes path, checkout path, map contents, or model output.
  The project node's `id` is exactly the configured `project_id`. A
  repository-shaped project ID such as `project:owner/repo` is invalid v1 output
  (fixture 65).
- `project-local` is a reserved literal discriminator, not a binding alias, and
  may never collide with a `binding_id` (fixture 69).
- Two configured repositories with the same relative path yield distinct
  binding-qualified document identities (fixture 68).
- `github-issue:` and `github-pr:` IDs stay distinct even when GitHub assigns the
  same number (fixture 2).
- Project-local session/handoff identity is stable across repository rename,
  rebinding, slug rename, and notes-directory move (this is why they key on
  `project_id`, never on a repository coordinate).

---

## 6. Schema contracts

Seven `*.schema.json` files, each a documentation/interchange contract; the
native validator is authoritative (§11).

- **`config.schema.json`** — immutable `project_id`; mutable `project_slug`;
  optional `display_name`; a `repositories` map of alias → binding; each binding
  carries a stable `binding_id`, `provider`, optional `coordinates`, optional
  local checkout path, and optional `default_for_bare_references`; explicit
  `schema_version`. Rejects: malformed/missing `project_id`, duplicate aliases,
  duplicate `binding_id`s, more than one default, and repository-shaped project
  IDs. It does **not** allocate identity (that is #191).
- **`node.schema.json`** — `id`, `class` ∈ {project, semantic, evidence},
  `kind`, `label`, `status`, `source`, optional `confidence` (valid only for
  `assumption`/`tension`). Semantic kinds: decision, learning, assumption,
  tension, question. Evidence kinds: session, handoff, design_document,
  github_issue, github_pr. Reserved future kinds are documented but rejected as
  emitted v1 output (fixture 30).
- **`edge.schema.json`** — `key`, `source`, `relationship`, `target`, `status`,
  `origin` ∈ {deterministic, human_judgment}, `review_trigger`, `basis`. No
  generic `related_to`. `implements` is rejected (fixture 24).
- **`proposal.schema.json`** — untrusted: proposed source, relationship, target,
  material basis, explanation, uncertainty, producer metadata, and an *optional
  advisory* `candidate_key`. It must forbid externally synthesized
  `identity_anchor` targets, entry fingerprints, assigned IDs, and any
  authoritative candidate key.
- **`candidate.schema.json`** — a discriminated union on `subject_type`:
  validated `edge` candidates (#184) and deterministic `identity_anchor`
  candidates (#183). Envelope: `subject_type`, `candidate_key`,
  `candidate_origin` ∈ {deterministic_compiler, validated_proposal},
  candidate-scoped `dependency_fingerprint`, optional diagnostic whole-graph
  fingerprint, producer metadata (non-authoritative), material basis, validation
  status. Rejects a proposal-supplied conflicting precomputed candidate key.
- **`judgment.schema.json`** — append-only event: `schema_version`,
  `subject_type`, `subject_key`, `candidate_key`, `decision` ∈ {accepted,
  rejected, retired}, `decided_at`; `identity_anchor` judgments add
  `assigned_id` and `entry_fingerprint`. Timestamps never participate in semantic
  equality.
- **`index.schema.json`** — the rebuildable materialized view: nodes, edges,
  per-source coverage (§ coverage), and effective-state provenance; presentation
  only, always regenerable.

Two subject types exist in v1 and no more: `edge` (every human-confirmed
relationship candidate, semantic- or evidence-targeted; **not** `semantic_edge`)
and `identity_anchor`. A judgment for one subject type never authorizes the
other (fixture 79).

---

## 7. Relationship endpoint matrix

Relationship validity depends on relationship type **plus** legal endpoint
classes/kinds — never the name alone. Node groups:

```text
semantic-any        = decision | learning | assumption | tension | question
claim               = decision | learning | assumption
uncertainty         = assumption | tension | question
resolving           = decision | learning
evidence-any        = session | handoff | design_document | github_issue | github_pr
validation-evidence = session | handoff | design_document | github_pr
```

Reserved future node kinds satisfy no v1 group (fixture 54).

| Relationship | Source | Target | Rules |
|---|---|---|---|
| `contains` | `project` | `semantic-any` | Deterministic only. No project→evidence containment in v1. |
| `supported_by` | `semantic-any` | `evidence-any` | Deterministic only, from an explicit map evidence pointer. |
| `discussed_in` | `semantic-any` | `evidence-any` | Judgment required. |
| `implemented_by` | `decision` | `github_pr` | Judgment required. Sole v1 implementation attribution. |
| `validated_by` | `decision` or `learning` | `validation-evidence` | Judgment required. |
| `closes` | `github_pr` | `github_issue` | Deterministic only, from GitHub-declared closure. |
| `motivates` | `semantic-any` | `decision` or `question` | Judgment required. |
| `constrains` | `decision`/`learning`/`assumption`/`tension` | `decision`/`assumption`/`tension`/`question` | Judgment required. |
| `depends_on` | `semantic-any` | `semantic-any` | Judgment required. No self-edges. Cycles allowed but visible. |
| `resolves` | `decision` or `learning` | `question`/`assumption`/`tension` | Judgment required. |
| `supports` | `decision`/`learning`/`assumption` | `semantic-any` | Judgment required. |
| `contradicts` | `decision`/`learning`/`assumption` | `decision`/`learning`/`assumption` | Judgment required. No self-edges. Symmetric → canonical endpoint ordering. |
| `supersedes` | one `semantic-any` kind | the **same** kind | Deterministic from a typed tombstone, else judgment. Distinct nodes; no self-edges. |
| `revisits` | `semantic-any` | `decision`/`learning`/`assumption`/`tension` | Judgment required. |

`tension` is an emitted v1 kind and participates wherever the groups include it.
`implements` is not in v1 and validators reject it as emitted output; use
`decision --implemented_by--> github_pr`.

Validation and identity rules (frozen): endpoint legality is revalidated at
**every** boundary — proposal ingestion, candidate-key construction,
confirmation, ledger reduction, compilation, apply, and skill-assisted execution
— never trusting a name. An illegal endpoint is a schema/invariant failure, never
an approvable/rejectable candidate; accepted history cannot grandfather a now-
illegal edge. Every semantic self-edge is invalid. `contradicts` canonicalizes
its two endpoint IDs lexicographically before both candidate-key and edge-key
construction so reversed proposals collapse to one subject (fixture 52); every
other relationship preserves declared direction. The diagnostic names the
relationship, actual source class/kind, allowed source group, actual target
class/kind, and allowed target group.

Coupling (`review_trigger`) defaults, stored explicitly and rejected when a known
relationship contradicts the default absent an explicit override mechanism:
review-triggering = `constrains`, `depends_on`, `contradicts`, `supersedes`;
contextual = `supports`, `supported_by`, `discussed_in`, `implemented_by`,
`validated_by`, `contains`, `closes`, `motivates`, `resolves`, `revisits`.
Shared evidence is neither an edge nor coupling.

---

## 8. Creation-authority rules

Every emitted relationship names one permitted `origin` and satisfies its
authority rule.

- **Deterministic (`origin: deterministic`, #183 only):** `contains` from
  configured project membership; `supported_by` from an explicit map evidence
  pointer; `closes` from GitHub-declared PR→issue closure; `supersedes` when the
  typed tombstone explicitly names the replacement identity. A deterministic edge
  lacking its required source authority is invalid (fixture 26).
- **Human-confirmed (`origin: human_judgment`, #184 accepted judgment):** the
  semantic-to-semantic set (`motivates`, `constrains`, `depends_on`, `resolves`,
  `supports`, `contradicts`, `supersedes`, `revisits`) and the semantic-to-
  evidence set (`discussed_in`, `implemented_by`, `validated_by`). A human-judged
  edge without a matching effective accepted judgment is invalid (fixture 25).
- **`supersedes` has both paths** (deterministic from the map, or human-confirmed
  as a reviewed candidate); both produce identical edge semantics but retain
  distinct `origin` (fixtures 12, 13).
- **No creation by implication:** shared evidence, map proximity, similar
  wording, a Markdown link label, common GitHub participation, or model
  confidence never create an edge. An explicit map evidence pointer creates
  `supported_by` only — never the judgment-required `discussed_in`,
  `implemented_by`, or `validated_by`.

These whole-object-kind authority checks live in `validation.py`, not in
`relationships.py`.

---

## 9. Candidate and judgment contracts

**Proposal → validated candidate → judgment → effective edge** and, in parallel,
**deterministic anchor candidate → judgment → authorized marker write.** The five
strata are never interchangeable: deterministic graph facts (#183, not
candidates), deterministic identity-anchor candidates (#183 only), untrusted
semantic proposals (human/#186/fixture), validated `edge` candidates (#184 only),
and effective judged edges (reduction of accepted #184 judgments). #185, #186, a
provider adapter, and a model may never mint an authoritative candidate key.

**Judgments** are append-only. Every event names `subject_key` and
`candidate_key`; later valid events supersede earlier ones for the same subject;
rejection suppresses only the *unchanged* candidate key; changed evidence or
endpoints yield a new candidate key; no event edits or deletes a prior line;
timestamps do not participate in semantic equality. The exact reducer state
machine (effective acceptance; rejection suppression; retirement; append-only
history) is owned by **#184**; #180 freezes only the event envelope and the
subject/candidate vocabulary.

**Candidate staleness** is candidate-scoped, stored as a canonical
`dependency_fingerprint`. A whole-graph fingerprint is diagnostic only and may
never independently stale a candidate (fixtures 80, 81). For `identity_anchor`:
project ID, stable map-source identity / project-relative path, normalized
section, entry kind, exact owner-authored entry fingerprint excluding Bindle
markers, and unique-current-match / unanchored state. For `edge`: canonical
source/target IDs, current endpoint classes/kinds, relationship + endpoint-matrix
validity, canonical material basis, and only source/target metadata explicitly
declared material by that basis. Explanations, producer metadata, review
ordering, timestamps, and whole-graph diagnostics never participate.

---

## 10. Candidate-key canonicalization algorithm (`bindle-context-candidate-v1`)

A single versioned, byte-exact primitive in `canonical.py`, called by #183 (anchor
keys) and #184 (edge keys and anchor-key recomputation). No issue maintains an
independent implementation.

**Basis normalization.** Each basis entry is normalized to a typed JSON object
with a **fixed allowed field set for its basis kind**. Unknown fields, missing
required fields, and unsupported primitive types are rejected. Numbers, booleans,
and `null` are **forbidden by default** inside a basis entry unless a specific
field contract explicitly allows them; entries are string-valued typed records.
Omitted and explicit-`null` are distinct: `null` is a rejected primitive, an
omitted optional field is simply absent. No Unicode normalization is applied
unless a field contract explicitly requires it.

**Per-entry serialization** (identical settings everywhere):

```python
json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

**Canonical basis bytes.** For the normalized entries:

1. Encode each serialized entry as UTF-8.
2. Deduplicate by exact serialized UTF-8 bytes — basis order is **semantically
   irrelevant** and duplicates collapse (fixture 42; §7 evidence-basis).
3. Sort entries lexicographically by those bytes.
4. Serialize the resulting array with the same `json.dumps` settings.
5. The UTF-8 encoding of that array serialization is `canonical_basis_bytes`.

**Payload framing** (exactly versioned, null-byte domain-separated):

```python
payload = b"\0".join((
    b"bindle-context-candidate-v1",
    source_id.encode("utf-8"),
    relationship_type.encode("utf-8"),
    target_id.encode("utf-8"),
    canonical_basis_bytes,
))
```

For symmetric `contradicts`, `source_id` and `target_id` are the lexicographically
ordered pair before framing. **Key format:** `candidate:sha256:<64-lowercase-hex>`
= `"candidate:sha256:" + sha256(payload).hexdigest()`.

Explicitly frozen: basis order is irrelevant; duplicates collapse; UTF-8 is
exact; no Unicode normalization by default; omitted ≠ null; numbers/booleans/null
forbidden by default; version string is `bindle-context-candidate-v1`. The
identity-anchor candidate-key contract is defined by #184 under this same
framing/domain-separation envelope.

**Ownership.** #180 defines and implements the shared primitive. #183 computes
deterministic anchor-candidate keys through it. #184 recomputes and verifies
anchor keys, then computes semantic-candidate keys, through the same module. The
`canonicalization/` fixtures carry exact expected `canonical_basis_bytes` and
digests so any reimplementation drift is caught.

---

## 11. JSON Schema versus native-validation synchronization

The native Python validator is the runtime authority; the seven schemas are
documentation/interchange contracts for other-language consumers. They are kept
in sync by **bidirectional conformance testing**, not code generation and not
runtime schema loading.

Test strategy:

1. Run native Python validation against every canonical fixture; compare result
   (valid/invalid) and finding codes against `manifest.json`.
2. Run a real JSON Schema validator against the same fixtures. This is a
   **development/test-only** dependency (Python `jsonschema`), gated exactly like
   the repo's existing shellcheck/shfmt pattern: *skipped with a notice when
   absent locally, installed and enforced in CI.* It is never imported by the
   runtime package and never becomes a runtime dependency. (CI is currently
   billing-blocked; the skip-if-absent gate keeps local `make check`/`make test`
   green in the meantime.)
3. Require native and JSON Schema validation to agree on valid vs invalid for
   every invariant representable in JSON Schema.
4. Maintain `schemas/context-graph/v1/invariant-coverage.json`, classifying each
   invariant as exactly one of `schema-and-native`, `native-only`, or
   `schema-only-documentation`. `schema-only-documentation` is normally empty and
   each entry requires explicit justification.

Native-only invariants (not representable in JSON Schema, so validated only in
Python): cross-object endpoint-matrix checks, global ID uniqueness, unresolved
references, self-referential references, candidate-key computation, canonical
ordering/deduplication, and creation-authority lifecycle rules.

The conformance check compares **more than** required fields and enums — it also
covers accepted property names, `additionalProperties`, primitive types, nested
object structure, array cardinality, string patterns, omitted-vs-nullable, and
enums/constants.

---

## 12. Fixture manifest contract

`testdata/context-graph/v1/manifest.json` is the single authoritative registry;
**manifest order is the execution and reporting order** (numeric filename
prefixes are presentation only). Each entry carries, at minimum: a stable fixture
ID; relative path; subject / validator entry point; expected valid-or-invalid
result; exact expected finding code(s); coverage tags; invariant IDs; optional
issue references. Candidate-key and canonicalization fixtures additionally carry
exact expected outputs.

Expected-finding matching: **exact-match** for isolated single-invariant fixtures;
**ordered-subset-match** only for the small, explicitly labeled aggregate
multiple-findings set (§13). The manifest marks which mode each fixture uses.

CI (via `make check`/`make test` locally) fails if: a fixture has no manifest
entry; a manifest path does not exist; fixture IDs are duplicated; an invariant
lacks a coverage classification; a native-required field or enum is absent from
the matching schema; a schema-required field or enum is not enforced natively;
schema and native validation unexpectedly disagree; or a schema/native contract
changes without fixture coverage.

---

## 13. Fixture directory and naming conventions

One file per fixture, grouped by contract category under
`testdata/context-graph/v1/`: `core/`, `map-shape/`, `endpoint-matrix/`,
`identity-config/`, `candidates/`, `canonicalization/`, `documents/`. **Not**
organized by issue number; **not** one giant JSON per subject; **not** a single
flat directory.

Filenames are descriptive and may carry a numeric prefix for human navigation,
e.g. `43-contains-project-to-semantic.json`; the prefix is presentation only.
Most invalid fixtures isolate exactly one invariant failure. A small explicit
multiple-findings set verifies that all independent findings are reported, that
finding order is deterministic, and that validation does not stop at the first
error. No test-only metadata (`_expected_error` etc.) is embedded in contract
fixture JSON — expectations live in `manifest.json`.

Candidate-key and canonicalization fixtures use paired files: `.input.json`,
`.expected.txt` (exact key string / hash), and `.expected.json` (exact canonical
JSON bytes represented as JSON where appropriate).

The #180 body's fixtures 1–81 map onto these directories: core graph/edge/
authority cases → `core/`; the map-projection shapes (33–42) → `map-shape/`; the
endpoint matrix (43–54) → `endpoint-matrix/`; identity/config (55–70) →
`identity-config/` with the two document-identity cases (68, 69) also exercised
under `documents/`; candidate/staleness/authority-separation (71–81) →
`candidates/`; and the byte-exact key/basis vectors → `canonicalization/`.

---

## 14. Deterministic finding taxonomy and ordering

`validation.py` emits **native invariant findings** in a deterministic order,
each a stable machine code plus a human message. Findings do not stop at the
first error — a fixture with N independent failures reports all N. Determinism
rule: findings are ordered first by the manifest/registration order of the
invariant, then by a stable within-object key (object index, then field path),
never by dict iteration, set iteration, or timestamp. Endpoint-legality findings
carry the structured payload from §7 (relationship; actual vs allowed source
class/kind and group; actual vs allowed target class/kind and group). Every
finding code that any fixture expects appears in the manifest, giving a closed,
tested code set.

---

## 15. Compatibility and versioning rules

This is `v1`, pinned by the `schemas/context-graph/v1/` path and
`schema_version: 1` in every versioned record and in `SCHEMA_VERSION`. Reserved
future node kinds and the deferred `implements` relationship are documented but
rejected as emitted v1 output, so a later version can introduce them without a
silent meaning shift. The candidate-key domain string is versioned
(`bindle-context-candidate-v1`); any change to the canonicalization algorithm is
a new version string and a new key namespace, never an in-place redefinition.
Accepted ledger history never grandfathers a record that is illegal under the
active schema version (§7). A future `v2` is a new directory and new schema files
beside `v1`, not an edit of these.

---

## 16. Inventory and capability-classification plan

`bin/check-inventory.py` recursively scans tracked `.py` and `.sh` under `bin/`
(via `git ls-files bin`) and tracked `.md` under `docs/`. `AUTO_EXCLUDE` covers
only `^bin/test-.*\.sh$`, `^docs/design/`, and `^docs/plans/`. Every other non-
test surface must be classified in `capabilities.json` (`script`/`contract`) or
in the `not_a_capability` ledger.

**Evidence recorded (verified against `bin/check-inventory.py` at this commit):**

- `bin/test-context-graph-schema.sh` **is auto-excluded** — it matches
  `AUTO_EXCLUDE[0] = re.compile(r"^bin/test-.*\.sh$")` (check-inventory.py
  ~line 346). No classification needed. This is the *only* auto-excluded new
  surface.
- The five package modules and the fixture CLI are **not** auto-excluded (they
  are `.py` under `bin/`, caught by the recursive `git ls-files bin` scan in
  `check_completeness_fuzzy`) and must each be classified.

Classification plan for the #180 implementation (mirrors existing machinery rows
like `bin/check-inventory.py`, `bin/lib/manifest.sh`, `bin/check-private-info.sh`,
all in `not_a_capability`):

| Path | Classification | Rationale |
|---|---|---|
| `bin/context_graph/__init__.py` | `not_a_capability` | package marker / version constant; library machinery, not an agent-invoked capability |
| `bin/context_graph/ids.py` | `not_a_capability` | shared library module imported by the validator and #183/#184; not invoked directly |
| `bin/context_graph/relationships.py` | `not_a_capability` | shared library module; same rationale |
| `bin/context_graph/canonical.py` | `not_a_capability` | shared library module; same rationale |
| `bin/context_graph/validation.py` | `not_a_capability` | shared library module; same rationale |
| `bin/check-context-graph-fixtures.py` | `not_a_capability` | fixture validator invoked by the test harness / `make check`; machinery, exactly like `bin/check-inventory.py` |
| `bin/test-context-graph-schema.sh` | (none — auto-excluded) | matches `^bin/test-.*\.sh$` |
| `docs/context-graph-schema.md` | `contract` capability row | shipped provider-neutral contract, like `docs/knowledge-promotion.md`; needs a `capabilities.json` row (type `contract`, `mutation: []`) and a `version_introduced` matching its release |

This is a required mechanical plan item, not an open question. The #180
implementation must land these `not_a_capability` entries and the one `contract`
row in the same change that adds the files, or `make check` fails.

This design record itself (`docs/design/2026-07-16-context-graph-schema.md`) is
auto-excluded by `^docs/design/` and needs no inventory row — which is why this
design-only change keeps `make check` green with no `capabilities.json` edit.

---

## 17. Test strategy

- `bin/test-context-graph-schema.sh` is the harness (auto-excluded from the
  inventory; added to the `make test` list). It drives
  `bin/check-context-graph-fixtures.py` over the manifest and asserts each
  fixture's expected result and finding codes.
- Native validation runs against every fixture; results and finding codes are
  compared to `manifest.json` (§12).
- The JSON Schema conformance pass (§11) runs the test-only `jsonschema`
  validator over the same fixtures, skip-if-absent locally, enforced in CI, and
  asserts native/schema agreement on every representable invariant, plus the
  `invariant-coverage.json` completeness check.
- Byte-exact vectors in `canonicalization/` pin `canonical_basis_bytes` and
  digests so candidate-key drift in any consumer is caught.
- Determinism reps: multiple-findings and ordering fixtures (31, 80/81, and the
  aggregate set) assert stable output across repeated runs.
- `make check` and `make test` must pass. This mirrors the repo's existing
  stdlib-only, self-tested `bin/test-*.sh` convention (e.g.
  `bin/test-map-entry-id.sh`).

---

## 18. Failure behavior

The fixture validator reports **precise** invariant failures and exits non-zero
when any fixture's actual result or finding set diverges from its manifest
expectation. It never stops at the first finding within an object. Endpoint
failures name relationship and actual-vs-allowed endpoint groups. The validator
mutates nothing — no notes, no GitHub, no repository state, no schema files. A
missing/malformed manifest, a fixture without a manifest entry, or a coverage gap
is itself a hard failure (§12). Degraded-source coverage states (`unavailable`,
`uncertain`) are never conflated with artifact absence.

---

## 19. Non-goals

Per §1 and #180's Non-goals: no identity allocation/persistence (#191); no map
parsing (#183); no GitHub resolution; no live `index.json` construction (#185);
no `context.md` writing (#185); no preview/confirm/apply (#184/#185); no
model-assisted skill (#186); no architecture projection or cross-project
synthesis; and no emission or interpretation of the deferred `implements`
relationship.

---

## 20. Rejected alternatives

- **One self-contained validator script** — would force a copy of ID/endpoint/
  canonicalization logic per consumer; violates the single-authority package
  boundary (§2, §4).
- **Copying rules into #183 and #184** — guarantees drift; the shared package
  exists precisely so both `import context_graph` (§2).
- **Subprocess-based reuse (#183/#184 shelling out to the CLI)** — brittle,
  slow, and hides the contract behind text I/O; explicitly forbidden. Consumers
  import the package.
- **Runtime JSON Schema loading** — the package never reads schema files at
  runtime; the native validator is authoritative (§11).
- **Runtime `jsonschema` dependency** — forbidden; `jsonschema` is test-only and
  skip-if-absent (§11).
- **A homemade generic schema engine** — rejected; native invariants are written
  as explicit Python checks, and schema conformance uses a real off-the-shelf
  validator, not a hand-rolled engine.
- **Generated Python validators from JSON Schema** — rejected; the native rules
  express cross-object invariants JSON Schema cannot, so generation would lose
  authority and add a build step.
- **Generated JSON Schema from the Python implementation** — rejected; the
  schemas are hand-authored interchange contracts kept honest by the bidirectional
  conformance test, not a derived artifact.
- **One large fixture document per subject** — rejected; one file per fixture
  keeps failures isolated and diffs legible (§13).
- **Flat fixture directory** — rejected in favor of category subdirectories
  (§13).
- **Issue-number-based fixture layout** — rejected; fixtures are grouped by
  contract category, and the manifest (not the tree) owns order (§12, §13).
- **Free-form string basis hashing** — rejected; basis entries are typed JSON
  objects with fixed field sets and byte-exact canonical serialization (§10). No
  `str()`/tuple/`set`/locale/line-ending-dependent hashing.
- **Implementation-defined canonicalization** — rejected; §10 fixes
  serialization settings, dedup, ordering, encoding, and domain separation
  exactly, with byte-exact fixtures.
- **No automated schema/native sync check** — rejected; §11 mandates the
  bidirectional conformance test and `invariant-coverage.json`.
- **`matrix.py` as the module name** — rejected for `relationships.py`, which
  names the whole relationship contract, not just the matrix (§3).
- **Broad exports from `__init__.py`** — rejected; `__init__.py` carries only a
  docstring and `SCHEMA_VERSION`; callers use explicit import paths (§3, §4).
- **Adding `models.py` prematurely** — rejected; plain dicts + explicit
  validators suffice, and no repository evidence proves otherwise (§3).

---

## 21. Implementation issue list / child-chain sufficiency

The existing #140 child chain remains **sufficient**; #180 needs no new child
issue.

- **#179** — map identity + retirement grammar (merged, PR #195).
- **#180** — this contract: schemas, fixtures, stdlib-only validator, shared
  candidate-key/endpoint/ID/canonicalization package.
- **#181** — evidence normalization (owns the comma-separated evidence field and
  repository-document identity), consuming this contract.
- **#182** — seam approval + complete design mapping; freezes exact file
  locations and command transitions but may not omit/redefine these contracts.
- **#183** — deterministic compiler + identity-anchor candidate producer;
  imports the package; never reduces judgments.
- **#184** — proposal validation, candidate-key computation, judgment ledger +
  reducer state machine.
- **#185** — apply / index / `context.md` projection; preserves identity, never
  allocates.
- **#186** — optional skill: proposal producer + interaction layer only.
- **#191** — initialization + repository-binding persistence (the write authority
  #182 named as a structural blocker). Its existence, plus the fully consolidated
  issue bodies, **discharges both** of #182's standing go-decision blockers.

---

## 22. Go / no-go conclusion

**GO for #180 implementation.**

Every stop condition is checked and clear:

- The live #180 body does not contradict any frozen authority in #140, #179,
  #183, #184, #185, or #191 — it is the reconciled consolidated contract, and
  this record follows it.
- The seven schema names and the two subject types (`edge`, `identity_anchor`)
  express every live contract coherently (§6).
- The repository does **not** forbid a development/test-only schema-validation
  dependency: it has an established skip-if-absent-locally / enforce-in-CI pattern
  (shellcheck, shfmt) that `jsonschema` reuses, while the runtime validator stays
  stdlib-only (§11).
- Candidate-key basis kinds are sufficiently defined to freeze canonicalization:
  basis entries are typed JSON objects with fixed field sets, and §10 fixes the
  whole algorithm byte-exactly.
- Endpoint rules are unambiguous after reading the complete bodies — the closed
  matrix (§7) is total over the emitted node kinds.
- The proposed package location (`bin/context_graph/`) is consistent with the
  inventory mechanics: the modules classify as `not_a_capability`,
  `docs/context-graph-schema.md` as a `contract` row, and the test harness is
  auto-excluded (§16). No installation or inventory conflict.
- Resolving this design required no implementation of #181 or later work; #191
  supplies the initialization authority #180 depends on but does not itself
  implement.

The go decision authorizes implementation of **#180 only** — the schemas,
fixtures, validator, and shared package. It does not authorize #181, #182, #183,
#184, #185, #186, or #191. #182 remains the gate that issues the go/no-go for
#183–#186 after adopting this contract.

---

## Appendix: required upstream issue amendments

**None.** This design is fully expressible within the consolidated live bodies of
#140, #179, #180, #181, #182, #183, #184, #185, #186, and #191 as written. No
upstream issue contract is altered by this record. The one framing correction —
that project/context **initialization and repository-binding persistence is owned
by #191**, not by #182 or a #180-local initializer — is already reflected in the
live consolidated bodies (#180 Non-goals name #191; #191 exists with that
ownership), so it requires no new amendment text.
