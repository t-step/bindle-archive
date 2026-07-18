# Candidate merged #141 parent body (NOT YET APPLIED)

> **What this file is.** A *generated candidate snapshot* of the proposed #141
> issue body, built to recover the requirement sections deleted when the epic
> reframe replaced rather than incorporated the original contract. It is staged
> here for review and diffing. **It has not been written to GitHub.**
>
> **Authority note.** Once the operator applies it, **live #141 is the canonical
> product contract** and this file becomes a historical snapshot. This file never
> outranks the live issue. See the authority split in
> `2026-07-18-141-architecture-projection-epic.md` §0.

Everything below the rule is the proposed body verbatim.

---

# Epic: provider-neutral architecture projection

> **Epic status.** #141 is the parent epic for provider-neutral architecture
> projection. It consumes the completed **#140** context-graph foundation
> (shipped v0.7.0) without restating or weakening it, and preserves the **#142**
> historical-enrichment boundary. Implementation is distributed across children
> A–I; this issue remains the **canonical product contract** — every acceptance
> criterion, pressure test, and frozen cross-child contract is stated here, not
> delegated to a design document.
>
> The decomposition rationale, traceability, and paste-ready child bodies live in
> `docs/design/2026-07-18-141-architecture-projection-epic.md`. That document is a
> **record**, not an authority: where it and this body disagree, this body wins.

## 1. Relationship to #140 and #142

**Upstream contracts consumed (must not be reinvented):**

* opaque project identity from #140 configuration (`project:<32-lowercase-hex>`,
  allocated by #191);
* zero-or-more stable repository bindings, each with a stable `binding_id`
  independent of mutable `owner/repo` coordinates;
* stable context semantic-node identities
  (`context-node:<creation-project-slug>:<32-lowercase-hex>`);
* normalized evidence identities from #181, including binding-qualified
  repository-document identity;
* confirmed context relationships from the final #140 index;
* safe generated-region utilities from #185;
* notes-home ownership and privacy rules;
* provider-neutral preview, confirmation, and idempotence patterns.

All of the above are **closed and shipped**. #140's graduation gate and dogfood
are satisfied.

**#142** (historical inference, backward projection, bulk backfill) remains
separate, blocked, and conditional. No child of #141 performs backfill, and #142
is not part of #141's closure.

## 2. Summary

Create and safely maintain a bounded, human-readable architecture map from a
provider-neutral structural graph.

The structural provider remains the authoritative machine-resolution graph of
files, symbols, dependencies, call paths, and blast radius. Bindle creates a
curated, **rebuildable** projection containing durable architectural concepts:
components, flows, boundaries, hotspots, and test surfaces.

This is not a general structural-graph export and not a visualization feature.
The goal is to make a project's architecture legible without reproducing the
repository's full symbol graph, and without redefining any context-graph meaning.

> *Amended from the original wording* "from CodeGraph or another structural graph
> provider": the engine now consumes a **canonical local structural-graph
> interchange**, and CodeGraph sits behind that interchange as one adapter (§7).

## 3. Intended user experience

A user can run an architecture projection for a structurally indexed repository,
review a proposed set of notes and changes, and approve the write.

The resulting notes home contains a restrained architecture map such as:

```text
Project
├── Codebase Map
├── Components
├── Architectural Flows
├── Boundaries
├── Hotspots
└── Test Surfaces
```

These notes reference existing Bindle context: the project, its semantic nodes,
and normalized evidence identities from the context graph.

The architecture notes are ordinary Markdown with YAML properties. No custom
Obsidian plugin is required, and no local GitHub artifact mirror is created.

**All six branches of that tree are promised outcomes of this epic.** Hotspots may
be *rendered* as bounded temporal status inside durable architecture notes rather
than as a standalone durable note per metric fluctuation (§8, child F4); that is a
rendering choice and does **not** remove hotspots/risk seams from the promise.

## 4. Authority split

Frozen:

* the structural provider is authority **only** for observed structural facts
  exposed by its index or export;
* the context graph is authority for durable project understanding, semantic
  identity, normalized evidence, and confirmed human judgments;
* architecture projection is a downstream, rebuildable reading surface;
* architecture projection cannot silently rewrite context-graph meaning;
* human confirmation is required wherever grouping, naming, splitting, merging,
  renaming, or attribution exceeds structural evidence.

A high-centrality utility module is not automatically an architectural component.
A frequently changed file is not automatically a hotspot. **Metrics are signals,
not truth.**

Architecture projection creates **no** context-graph edge and **no** entry in the
#184 judgment ledger. If architecture work needs a durable semantic relationship
in the context graph, it goes through #140's proposal → #184 validation → human
judgment path, never through projection.

## 5. Frozen contracts and explicit amendments

These hold across every child. A child may extend a contract; none may weaken it.

* **FC-1 Authority separation** — as §4.
* **FC-2 Project-scoped architecture identity** — §6.
* **FC-3 Provider seam / network independence** — §7.
* **FC-4 Source coherence** — every graph is bound to a stable binding, an exact
  commit, a provider name and version, and an interchange schema version. Missing,
  unavailable, or mismatched yields an explicit `unavailable` / `stale` /
  `unsupported_version` / `malformed` / `deconfigured` / `freshness_unknown`
  state. Provider disappearance is **never** deletion or blanket staleness. A
  partial multi-repository outage carries forward the unavailable binding's
  contribution and never stales unaffected notes.
* **FC-5 State authority** — architecture identity, confirmed decisions, **and
  observed provenance** live in an append-only judgments log under the notes home.
  Generated Markdown and the materialized index are rebuildable materializations,
  never authorities, and are never read back to recover identity or meaning.
  Recovery state is metadata only.
* **FC-6 Note safety and byte preservation** — §11.
* **FC-7 Bounded and private** — §9, §12.
* **FC-8 Deterministic core, optional model** — identity, persistence, structural
  normalization, deterministic metrics, candidate keys, confirmation authority,
  and apply behavior are owned by deterministic code. Model assistance is optional
  and non-blocking, entering only through the same reviewable proposal contract
  the deterministic workflow consumes.

### Explicit amendments to the prior contract

Three deviations from #141's earlier wording are **deliberate and recorded here**,
not laundered:

1. **Architecture identity is project-scoped only.** The prior wording scoped
   identity to "stable project identity **and, where relevant, stable
   repository-binding identity**." Amended: repository-binding participation is
   **mutable provenance**, not identity. No single binding ID is embedded in an
   architecture-node ID. Adding, removing, renaming, transferring, or rebinding a
   repository does **not** churn identity. Rationale: a component or flow may span
   repositories, so embedding a binding would churn identity on every
   participation change — the exact failure PT2 tests against. See §6 and AC4.
2. **Provider-independent matcher signals.** The prior identity model listed
   "existing stable provider graph ID, where available" among matching signals.
   Amended: provider structural IDs are **provenance only and never matcher
   signals**. They are opaque and version-unstable — a provider patch release that
   changes ID format would drive overlap to zero at an unchanged commit and churn
   every node. See §6 and PT23.
3. **Last projection timestamp lives in state, not in the note.** The prior
   *Provenance* list required a per-note "last projection timestamp." Amended: it
   lives in state only and advances only on real content change, because a
   timestamp inside a byte-compared generated region would defeat the zero-write
   semantic no-op (AC10, PT8).

## 6. Identity and provenance

Distinguish three identity spaces and never conflate them:

1. **context semantic nodes** — owned by #140/#179; durable project understanding;
2. **provider structural nodes** — owned by the structural provider; files,
   symbols, edges;
3. **projected architecture nodes** — owned by this issue; downstream, rebuildable.

Architecture identity is **scoped to the stable project identity** (amendment 1).
It is opaque, allocated once at the confirmed creation event from command-owned
entropy, and immutable thereafter.

Durable architecture identity must **not** be based on: filename; note title;
`owner/repo`; checkout path; provider display label; Obsidian link text. **A note
filename is presentation, not identity.**

Do not reuse a context semantic-node ID merely because an architecture label
resembles it. A resemblance between an architecture component name and a decision
claim is not identity.

**Continuity is a confidence-gated match, not a hash.** An architecture node names
a *derived cluster* recomputed each run, so there is no stable content to hash.
Identity continues by a multi-signal matcher over the judgments authority, using
**provider-independent** signals (amendment 2): repository-relative path overlap,
symbol *names*, dependency neighborhood, prior projected identity, dominant
anchors, and explicit user confirmation.

Matching is a **bipartite assignment** against *live* identities, with four
exhaustive outcomes:

1. **no match** (including a fresh project with an empty judgments log) → mint a
   new identity at the confirmed creation event;
2. **unique high confidence** → reuse the existing identity, updating membership
   and provenance — an ordinary edit never mints a new node;
3. **contested high confidence** (two candidates claim one identity, or one
   candidate clears the bar against two) → demote to ambiguous and require
   confirmation; a contest is a split or a merge, never a silent winner;
4. **low / ambiguous** → split/merge/rename candidate requiring confirmation.

A **reappearance** matching a *stale* identity requires confirmation and is never
auto-reused: structural overlap alone cannot distinguish a genuine reappearance
from unrelated code later written at the same paths.

Renames update the existing note where confidence is high; ambiguous identity
changes require review. Membership delta alone is never identity.

**Provenance recorded per projected node:**

* stable Bindle projection ID (project-scoped);
* stable project identity;
* participating repository-binding identities (a mutable list);
* projection type;
* source commit per participating binding;
* graph-provider name and version;
* projection schema version;
* source paths (repository-relative, normalized);
* source symbols / provider graph IDs where available (normalized and redacted;
  provenance only, never a matcher signal);
* per-binding status and per-binding coverage;
* confidence;
* prior identities or aliases following a rename, split, or merge, in **both**
  directions (a split records its origin and its products, so a reverted split is
  recoverable);
* last projection timestamp — **in state only** (amendment 3).

## 7. Provider / interchange boundary

A **canonical, versioned, provider-neutral local structural-graph interchange**
sits between any provider and the projection engine. The engine consumes only the
interchange and **never imports CodeGraph or any other provider**. Network access
is never required by the engine or the reference provider.

> *Amended from the original "Adapter boundary".* The prior preferred order was
> "1. stable local export or CLI contract; 2. direct local adapter; 3. MCP-assisted
> discovery." Measurement shows CodeGraph 1.4.1 ships a local CLI but **no bulk
> export verb**; `explore`/`node` emit truncating human-formatted output with no
> `--json`, and `query --json` defaults to a limit of 10. The interchange therefore
> comes **first**, with adapters behind it, and the adapter preference order is:
> direct local adapter → narrow `--json`-capable non-truncating CLI verbs →
> MCP-assisted only where deterministic access is insufficient.

**The interchange carries raw structural facts only; conclusions are engine-owned.**
Files, symbols (with a normalized `kind` enum), tests, and
contains/imports/calls/tests edges are core. Provider *interpretations* —
entry-point and route guesses, resolved dynamic-dispatch hops, clustering and
centrality hints, and export visibility — are **capability-gated optional
observations**, treated as hints and never authoritative.

**Capability degradation is visible, never fabricated.** A missing capability means
the facts are **unavailable**, not empty; "capability not supported" is never
treated as "supported and observed to be zero." This holds **per entity**, not only
per graph: a provider that advertises a capability but fails to parse a subtree
must report that subtree as partial coverage, so a real subsystem can never read as
an observed zero. Cross-binding aggregation propagates `unavailable` as
unknown/partial and never sums it as `0`.

Equivalence between providers is required only over the **intersection of supported
capabilities**, so a provider lacking a capability degrades a projection visibly
rather than diverging silently.

**Plan equivalence is a combined D+E release gate, not E-only acceptance.** A plan
is the planner's artifact, not the interchange's, so the adapter child cannot
produce one alone. E's own acceptance is normalized-fact equivalence; plan
equivalence and the real-CodeGraph end-to-end run gate the release (§14, PT7b).

## 8. Projection and selection model

The projection operates on architectural objects rather than raw code objects.

**Initial supported note types:**

1. Codebase map
2. Component
3. Architectural flow
4. Boundary
5. Hotspot or risk seam
6. Test surface

Individual files, functions, methods, and tests do **not** receive durable notes by
default. They may appear as provenance or evidence within a higher-level
architectural note.

**Selection approach.** Deterministic code:

* discovers entry points and routes;
* identifies cross-module dependency seams;
* calculates fan-in, fan-out, and blast-radius signals;
* detects structural communities or clusters where supported;
* locates test relationships;
* applies configured exclusions and privacy rules;
* produces stable candidate evidence;
* computes deterministic diffs;
* **derives a deterministic default human-readable name for every component.**

> *Amended:* the prior wording assigned "propose human-readable component names" to
> model assistance and to nothing deterministic. Since the deterministic closure set
> renders component notes and a note requires a title, a deterministic default name
> is required — otherwise the optional model layer would be load-bearing. Model
> assistance may **improve** an existing deterministic name, never supply the first.

Model-assisted judgment may: improve component names; group related candidates;
describe architectural responsibility; suggest flows and boundaries; identify
likely split or merge events; rank ambiguous candidates for review.

**No model-generated judgment is written without preview and provenance.**

Clustering must be **deterministic per capability set and degrade monotonically** —
a lost capability may merge or coarsen groupings, never silently re-partition them.

## 9. Bounded projection

Default safeguards:

* a configurable maximum number of projected notes per project;
* minimum evidence thresholds;
* no note-per-symbol or note-per-file behavior;
* prefer updating an existing architectural node over creating a nearby duplicate;
* require confirmation for uncertain new components;
* exclude generated, vendored, dependency, cache, build, gitignored, and explicitly
  private paths;
* prefer durable architectural seams over high raw centrality.

**Over-cap behavior (frozen).** The cap binds **creation**. A previously projected
node that falls out of the ranked set is **retained**, marked below-threshold, and
excluded from further refresh until the operator stales it through the
reconciliation child. It is never auto-deleted and never auto-staled. Ranking uses
**bucketed/banded** metric values, not raw numbers, so a rank oscillation at the cap
boundary cannot strand notes or leak note count over time.

## 10. Confirmation policy

Confirmation is required for:

* creating uncertain architectural nodes;
* renames below a high-confidence threshold;
* splits;
* merges;
* staling a note containing user-authored content;
* replacing manually edited generated regions;
* changes above configured note-count or **diff-size** limits.

Straightforward, high-confidence generated-field refreshes may be applied together
after the user approves the plan.

**The confirmation policy is static configuration** — which change classes require
confirmation, and the note-count and diff-size thresholds — and is owned by child B,
so the first usable release (which ships the confirm loop without the reconciliation
child) has a policy owner.

**A confirmation binds the plan it was given for.** Preview emits a plan
fingerprint; apply recomputes it and aborts if inputs changed between preview and
apply, rather than writing a plan the user never saw.

## 11. Ownership and safe apply

Preserve:

* generated-region ownership, reusing #185's utilities;
* user-authored prose, byte-identical outside generated regions;
* preview before mutation;
* atomic or recoverable apply;
* semantic no-op behavior;
* privacy and path boundaries;
* stale/split/merge/rename review;
* provider-neutral fixtures;
* no requirement for a custom Obsidian plugin;
* no local GitHub artifact mirror.

Refresh must detect hand edits inside generated regions, conflicts between generated
and user-owned fields, missing generation markers, and invalid or duplicated
projection identities. Conflicted notes are classified as uncertain and require
confirmation rather than being silently rewritten.

**Extended apply contract.** #185's apply plans a fixed three-artifact set with
per-file atomicity only. Architecture apply plans a **variable** note manifest, and
therefore adds: a complete planned file manifest with intended bytes/hashes before
the first write; deterministic write ordering; incomplete-apply detection; and
**resume that re-plans against current inputs and disk rather than replaying stored
bytes** — so a hand edit made between an interrupted apply and its resume is
preserved, never clobbered. Zero writes on a semantic no-op. **No false claim of
cross-file filesystem atomicity**: atomicity is per-file; cross-file integrity comes
from the manifest and resume ledger.

### Stale, removed, split, merged

* **Stale or removed:** never delete automatically. Mark `projection_status: stale`
  with last confirmed commit, reason, and replacement link when known.
* **Split:** propose one existing note becoming historical or superseded, plus two
  or more new projected notes with explicit superseded-by links. Requires
  confirmation.
* **Merge:** propose one surviving projected identity, others marked merged into it,
  preserving all user-authored content. Requires confirmation.

## 12. Security and privacy

* Never copy source files wholesale into the notes home.
* Do not include secrets, environment values, or raw configuration contents.
* Redact or normalize absolute local paths; prefer repository-relative paths.
* Cap source excerpts and disable them by default.
* Do not persist raw graph dumps inside notes.
* External links must be allowlisted and previewed.
* **All writes remain below the configured notes home.**
* Respect ignored, generated, vendored, and explicitly private paths.
* Log metadata without logging source contents.

**Normalization and redaction happen at the interchange boundary**, before
persistence or logging, and cover **every** provider-supplied string — paths, symbol
IDs, routes, and any value echoed into a diagnostic or log line — not only source
paths. The notes home is an Obsidian vault, routinely synced and shared, so this is
the threat model rather than a git commit.

## 13. Child DAG

| Child | Scope | Depends on |
|---|---|---|
| **A** | structural-graph interchange, capability model, redaction at the boundary, reference JSON provider, multi-binding fixture corpus | — |
| **B** | architecture identity (**sole allocator**), authority-separated state, provenance, static confirmation policy, continuity matcher, notes-home tree contract, lock contract | A (contract) |
| **C** | deterministic bounded candidate planning, engine-owned metrics, engine-derived entry points, deterministic naming, cross-binding aggregation | A |
| **D** | safe projection loop (preview → confirm → apply → zero-write rerun → changed-only refresh), map + component rendering, notes-home containment, agent-agnostic invocation surface | B, C |
| **E** | CodeGraph adapter behind the interchange + equivalence proof | A (contract), C |
| **F1** | architectural flow notes | D |
| **F2** | boundary notes | F1 |
| **F3** | test-surface notes | F2 |
| **F4** | hotspot / risk-seam rendering | F3 |
| **G** | reconciliation lifecycle: rename, reappearance, split, merge, stale, hand-edit conflicts | D |
| **H** | multi-repository projection breadth | A, B, D (**not** E) |
| **I** | optional model-assisted authoring — **non-blocking** | D |

The graph is acyclic. Topological order:
`A → {B, C} → {D, E} → {F1, G, H, I} → F2 → F3 → F4`.

Only child **B** may allocate an architecture identity. G and H drive lifecycle and
surface collisions respectively, but route every allocation through B.

## 14. Release stages

| Stage | Children | User-facing |
|---|---|---|
| Internal contract milestone | A + B + C + D on the reference provider | No |
| **First usable release** (partial) | A + B + C + D + E | Yes — initial projection, idempotent and changed-only refresh; **not** ongoing-refactor maintenance, which arrives with G |
| Extended note types | F1 → F2 → F3 → F4 | Yes |
| Reconciliation + breadth | G + H | Yes |
| Optional | I | Yes |

The first usable release is gated on a **real-CodeGraph end-to-end run**
(CodeGraph → interchange → bounded candidates → preview → confirm → apply →
zero-write rerun on an actually indexed repository), together with plan
equivalence — a **combined D+E gate**, not fixture equivalence alone.

## 15. Epic closure

**Closure-blocking set: A, B, C, D, E, F1, F2, F3, F4, G, H.**

* All four extended-note phases block closure. #141's promised outcome enumerates
  six initial note types and renders all six in the notes-home tree; flows,
  boundaries, test surfaces, and hotspots/risk seams are all part of that promise.
* **F4 may model hotspots as bounded temporal status inside durable architecture
  notes** rather than creating a durable standalone note per metric fluctuation.
  That rendering choice does **not** remove hotspots/risk seams from closure.
* **I does not block closure.** No acceptance criterion requires model-generated
  content, and deterministic naming (§8) keeps the optional layer off the critical
  path.
* **#142** is not part of this closure and stays separate, blocked, and conditional.

## 16. Acceptance criteria

| # | Criterion | Owner |
|---|---|---|
| AC1 | A structurally indexed local repository produces a previewable architecture projection. | D |
| AC2 | The projection contains a codebase map and a restrained number of selected architectural nodes. | D |
| AC3 | Raw files and symbols do not become notes by default. | C |
| AC4 | Architecture identity is scoped to stable project identity — never to filename, note title, `owner/repo`, checkout path, provider label, or link text alone. Repository-binding participation is recorded as mutable provenance, not identity (amendment 1). | B |
| AC5 | Context semantic-node IDs are never reused merely because an architecture label resembles them. | B |
| AC6 | Architecture notes reference context nodes and normalized evidence without inventing parallel meanings or reinterpreting #140 relationship names. | D |
| AC7 | Architecture projection creates no context-graph judgments and no ledger entries. | D |
| AC8 | Repositoryless projects degrade cleanly; architecture projection may be unavailable. | D |
| AC9 | Multi-repository projects are supported with explicit binding selection. | H |
| AC10 | Re-running against the same commit and configuration produces zero writes. | D |
| AC11 | A changed-only refresh updates affected areas without rebuilding unrelated notes. | D |
| AC12 | A full refresh reconciles the complete projection. | G |
| AC13 | User-authored sections survive every refresh byte-identically. | D |
| AC14 | Renames are preserved where confidence is high. | G |
| AC15 | Ambiguous renames, splits, and merges require confirmation. | G |
| AC16 | Removed nodes are marked stale rather than deleted. | G |
| AC17 | Projection operates without network access. | A |
| AC18 | Both Claude Code and Codex invoke the same provider-neutral workflow with equivalent results. | D |
| AC19 | No custom Obsidian plugin is required. | D |
| AC20 | No local GitHub artifact mirror is created. | D |
| AC21 | No source code is copied wholesale. | D |

**Additional binding requirements** (stated in the prose sections above; numbered
here so children can cite them):

| # | Requirement | Owner |
|---|---|---|
| R1 | The notes home contains the architecture tree of §3 (Codebase Map, Components, Architectural Flows, Boundaries, Hotspots, Test Surfaces); children populate it and may not invent sibling roots. | B (contract), D + F1–F4 (populate) |
| R2 | All writes remain below the configured notes home, verified after symlink resolution; a plan containing an escaping path is rejected whole. | D |
| R3 | Every component has a deterministic human-readable name; model assistance may only improve it. | C |
| R4 | Confirmation fires above configured note-count **and diff-size** limits. | B |
| R5 | External links are allowlisted and previewed. | D |

## 17. Pressure tests

**From the original contract:**

| # | Pressure test | Owner |
|---|---|---|
| PT1 | Multi-repository projects — architecture nodes from two bindings remain distinct and correctly attributed. | H |
| PT2 | Repository rename with stable IDs — rename a binding's coordinates; project ID, binding ID, and projection identities do not churn. | B |
| PT3 | Provider graph unavailable — projection reports unavailable rather than inferring or deleting. | D |
| PT4 | Provider graph stale — detect commit mismatch and refuse or clearly mark the plan stale. | D |
| PT5 | Context node referenced without identity conflation — an architecture label resembling a decision claim does not reuse that decision's semantic ID. | B |
| PT6 | Structural proximity not creating semantic relationships — two modules that call each other produce no context-graph edge. | D |
| PT7a | Equivalent deterministic fixture output — CLI and another adapter produce equivalent **normalized graph fixtures**. | E |
| PT7b | Equivalent **projection plans** across adapters. | D+E release gate |
| PT7 | *(the original single criterion; split into PT7a and PT7b above, because a projection plan is the planner's artifact and the adapter child cannot produce one alone)* | — split — |
| PT8 | Unchanged rerun produces zero writes. | D |
| PT9 | Repositoryless project — projection unavailable, project otherwise intact. | D |
| PT10 | Noise control against repositories with hundreds of modules, generated code, vendored dependencies, monorepo packages, and large test trees; note counts remain bounded. | C |
| PT11 | Rename resilience — rename a component directory and key symbols without changing responsibility; the existing note updates rather than duplicating. | G |
| PT12 | Split and merge — reviewable proposals, user content preserved. | G |
| PT13 | Hand-edited notes — edits to user-owned sections, generated sections, and removed markers produce preservation or conflict classification. | G |
| PT14 | Privacy — secrets, ignored paths, absolute paths, and sensitive identifiers in fixtures never appear in generated notes **or logs**. | A |
| PT15 | Interrupted write — the plan resumes without duplicates or partial corruption. | D |

**Added by the epic decomposition** (not in the original contract; each closes a
gap found by adversarial review):

| # | Pressure test | Owner |
|---|---|---|
| PT16 | Provider/capability toggle at the same commit — clusters coarsen monotonically, identity does not churn. | D |
| PT17 | Partial multi-repository outage — the unavailable binding's content is carried forward, and aggregate metrics are not zero-fabricated. | D (carry-forward) + C (aggregation) |
| PT18 | Hand edit made between an interrupted apply and its resume is preserved, never clobbered by a stale intended byte. | D |
| PT19 | Fresh project with an empty judgments log still produces a projection (the no-match → mint path). | D |
| PT20 | Torn trailing line in the judgments log truncates and reports; corruption elsewhere hard-aborts. | B |
| PT21 | Materialized index deleted while a binding is unavailable — rebuild preserves the carried-forward contribution. | D |
| PT22 | Rank oscillation at the note cap — no orphaned notes, cap observable. | C |
| PT23 | Provider symbol-ID format changes at a fixed commit — identity does not churn. | B |
| PT24 | Provider advertises a capability but fails to parse a subtree — reads as partial, never as observed zero. | A |
| PT25 | Inputs change between preview and confirm — apply aborts, nothing written. | D |
| PT26 | A planned path escapes the notes home (including via symlink) — the whole plan is rejected. | D |
| PT27 | Dirty working tree at a matching source commit — marked partial, never claimed current. | A |
| PT28 | Concurrent context-graph apply and architecture apply are serialized by one project lock. | B |
| PT29 | Interchange asserting a foreign or unconfigured binding ID is rejected. | A |
| PT30 | A user renames a generated note in Obsidian — conflict, not silent re-create. | G |
| PT31 | A commit touching one unrelated file rewrites zero notes. | D |

## 18. Out of scope

The following are excluded and must not reappear:

* creating context-graph nodes, edges, candidates, or ledger judgments;
* activating the reserved semantic kinds `architecture_component`,
  `architecture_flow`, `boundary`, `test_surface` — they stay reserved;
* durable local issue, PR, or commit note trees — GitHub remains authority for
  issue and PR state;
* repository-shaped project identity such as `project:owner/repo`;
* one project equaling one repository;
* Obsidian wikilinks acting as graph authority;
* architecture projection redefining context-graph judgments;
* independently invented semantic identities;
* direct or wholesale source-code copying;
* a general structural-graph export or raw symbol-graph dump;
* a custom Obsidian plugin;
* a local GitHub artifact mirror;
* historical inference, backward projection, or bulk backfill — see **#142**.

## 19. Dependencies

The upstream contracts this epic consumes (§1) are **closed**: #191 (project
identity, configuration, repository bindings), #179/#180 (semantic identities and
schemas), #181 (normalized evidence identities), #183/#184/#185 (deterministic
compilation, judgment authority, generated-region and safe-apply contracts), and
#186 (dogfood and graduation gate). #140 has graduated.

Implementation proceeds through children A–I per §13. Each child issue carries
`Parent: #141`.

**#142** remains separate, blocked, and conditional.
