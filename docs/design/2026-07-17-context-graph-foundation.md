# Design: context-graph implementation foundation (#182)

Resolves the design half of issue #182 (epic #140), unblocked by #179, #180,
and #181 (all merged). Status: **approved design, not yet implemented** — the
#191, #183, #184, #185, and #186 implementations, and any future amendment,
reference this document and the consolidated issue bodies as the product
source of truth. Where this record and a live issue body diverge, the live
body wins and this record must be corrected; no upstream contract is silently
altered here. This document does not repeat byte-exact algorithms #180
already froze (candidate-key canonicalization, the endpoint matrix, typed-ID
regexes) — it cites them and freezes what #180 explicitly left to #182: exact
command verbs, exact state-file locations under the notes home, the
initialization/compiler/judgment/apply command lifecycle, the schema
amendment #181's shipped output requires, and the go/no-go for the five
remaining children.

**Scope guard.** #182 designs no new schema, no new canonicalization
algorithm, and no new endpoint rule — all three are #180's frozen output,
reused verbatim. #182's job is the seam: how #191/#183/#184/#185/#186 compose,
which files each owns, and what happens under degraded or conflicting input.

---

## 1. Problem and product boundary

### Problem

#140's four already-merged children (#179 identity grammar, #180 schemas +
shared package, #181 evidence normalization) each froze a piece of the
context-graph contract in isolation. Two second-audit structural blockers
stood between that state and implementation: no issue owned explicit
project/context initialization and repository-binding persistence, and the
binding comment amendments scattered across #180/#181/#183/#184/#185 had not
been consolidated into implementation-consumable form. Both are now resolved
— #191 exists and owns initialization; every child issue body (#140, #179,
#180, #181, #183, #184, #185, #186, #191) is marked "Consolidated body," and
this document is the checked-in reconciled artifact the second audit required.
What remained undone was turning the now-coherent boundaries into one
authoritative seam: exact command verbs, exact file locations, exact
compiler/judgment/apply phase ordering, and — surfaced only after #181
shipped — a real schema gap between #181's output vocabulary and #180's
`node.schema.json` enum.

### Product boundary

Reused verbatim from #140 (not restated in full here; see #140's own "Product
boundary" section). In scope: initialization, map parsing, evidence
normalization, deterministic compilation, human judgment, safe apply,
projection, an optional adapter. Out of scope: mirroring GitHub locally,
session-lifecycle coupling, automatic promotion from raw prose, architecture
projection, cross-project synthesis, historical backfill, a general-purpose
graph database, a custom Obsidian plugin.

### Non-goals of this design issue itself

Implementing the compiler, initialization, `context.md` writing, the skill,
or a historical migration; designing architecture projection or cross-project
synthesis. (Per #182's own body.)

---

## 2. Existing contracts reused

This design reuses, without redefinition:

- **#179** — map identity/retirement grammar: marker placement, the
  structured-tension shape, typed tombstones, `bindle:superseded-by`,
  `context-node:<slug>:<32hex>` allocation via `bin/map-entry-id.py`.
- **#180** — the seven schemas, `bin/context_graph/{ids,relationships,
  canonical,validation}.py`, the closed endpoint matrix, the four candidate-key
  canonicalization primitives (byte-exact, §10 of #180's design), the
  schema/native bidirectional-conformance test strategy, the fixture manifest
  convention.
- **#181** — `bin/context_graph/evidence.py` (`normalize`/`normalize_field`/
  `normalize_batch`) and `bin/context-evidence.py`, consumed by #183 as a
  library import, never a subprocess call.
- **#191's own body** — already specifies its command surface, initialization
  lifecycle, and fixture list in full; this design freezes those verbs as
  final (§4) and does not re-derive them.
- **`docs/knowledge-promotion.md`** — the map file, its six sections, entry
  grammar, evidence-pointer syntax, and the promotion ceremony. The context
  graph reads `map.md`; it does not gain a second write path to it.
- **`docs/session-notes-format.md` / `docs/notes-home.md`** — notes-home
  resolution order (`BINDLE_NOTES_DIR` → deprecated `CLAUDE_KIT_NOTES_DIR` →
  `~/.bindle` → deprecated `~/.claude-kit`), the `<project>` slug rule, and
  the existing `projects/<project>/{profile.md,map.md,sessions/,handoffs/}`
  layout, which §5 below extends (not replaces).
- **`docs/ownership-boundaries.md`** — writes stay under the notes home or an
  explicitly-asked repo location; the context graph never mutates Git, GitHub,
  or a project's provider config.
- **`docs/privacy-boundaries.md`** — no secrets, no personal paths, no pasted
  transcripts in any generated artifact; `context.md` and `index.json` are
  notes-home artifacts, private by default like `map.md`.

---

## 3. Architecture

### Data flow

```text
configuration (.bindle/context/config.json)   [#191, read by #183]
project map (map.md)                          [knowledge-promotion, read by #183]
sessions/, handoffs/, committed designs        [read by #183]
GitHub issues/PRs (read-only)                  [read by #183]
        |
        v
   #183 deterministic compiler
        |
        +--> deterministic nodes/edges (direct graph facts)
        +--> identity-anchor candidates (for unanchored map entries)
        |
        v
   preview (writes nothing)
        |
   human-authored / skill-produced semantic proposals -----+
        |                                                   |
        v                                                   v
                  #184 judgment ledger (judgments.jsonl)
                  (validates, computes candidate keys, records
                   accepted/rejected/retired events)
        |
        v
   #185 apply
        |
        +--> index.json   (rebuildable materialized graph)
        +--> context.md   (regenerable reading projection)
        +--> approved identity-anchor markers written into map.md
```

### Deterministic compiler phases (#183)

Frozen pipeline, matching #182's required-decision §6 verbatim:

```text
load configuration (read-only)
validate roots and ownership
parse map entries
normalize evidence through #181 (library import, never a subprocess)
resolve available sources (sessions, handoffs, documents, GitHub — read-only)
construct deterministic nodes and edges
validate graph invariants (via context_graph.validation)
emit deterministic identity-anchor candidates
classify conflicts and unresolved items
render preview
```

All ten phases are pure or read-only I/O; none writes. The compiler **stops
before judgment reduction** — it never loads or reduces `judgments.jsonl`.
That is #184's job; integrating deterministic and effective (judged) state is
#185's job. This ordering is what keeps the epic's dependency graph acyclic
(#140 "Boundary rules that keep the sequence acyclic").

### Producer / validator / authority table

Frozen verbatim from #180 §2 and #182's own required-decision §7 (the two
already agree; this table is the single copy going forward):

| Artifact | Sole producer | Validation / canonicalization | Authority effect |
|---|---|---|---|
| deterministic node or edge | #183 compiler | #180 native validator + schemas | enters rebuilt graph directly; never a candidate, never a judgment |
| identity-anchor candidate | #183 compiler | #184 revalidation before judgment | none until accepted; accepted judgment authorizes #185 marker insertion |
| untrusted semantic proposal | human, #186 skill, or fixture | #184 | none |
| validated semantic (`edge`) candidate | #184 | #184 against current #183 graph + #180 matrix | eligible for human judgment only |
| accepted judgment event | #184 confirm flow after human choice | #184 ledger validation | authority for the effective judged edge or anchor authorization |
| persisted index / projection | #185 apply | full recomputation + validation | rebuildable materialized state |
| project/context configuration | #191 initializer | #180 `config.schema.json` + native validator | authority for project identity and repository operating context |

Non-overlap rules (frozen, from #140/#180/#182 comments, all consistent):
deterministic edges are never candidates; #183 emits no semantic proposals or
semantic candidates; #184 never infers relationships or invents anchor
targets; #184 may aggregate compiler-issued anchor candidates and externally
supplied semantic proposals into one review surface, but aggregation is not
generation authority; semantic proposal producers cannot compute authoritative
candidate keys; #186 emits proposal interchange only, nothing else; #185 never
generates or repairs candidates during apply; direct CLI use supports
human-authored semantic proposals with no skill installed; acceptance recorded
through #184 — never producer confidence — is semantic authority.

### Provider-neutral adapter contract (#186)

#186 is a thin, optional interactive layer. It:

- reads `preview`/`candidates`/`propose` output and renders it for a human —
  `propose`'s output is not incidental here: it is the *only* surface an
  edge candidate and its key ever appear on (§4, §10), since
  `candidates --subject-type edge` has no persisted edge state to read
  (§4). This matches #186's own body, which describes the skill presenting
  both #183-issued anchor candidates *and* #184-validated edge candidates —
  the latter only exist in `propose`'s output, so rendering them requires
  reading it;
- writes semantic proposals in exactly `proposal.schema.json`'s shape (the
  only proposal-interchange format — no second format, no direct
  `judgments.jsonl` write, no direct `config.json` write);
- calls `bin/context-graph.py propose`/`confirm`/`apply` (per #186's own body,
  which explicitly authorizes invoking #185 apply, not just #184 confirm) —
  it never shells past the CLI into the package, and never bypasses the CLI
  to write files directly.

The deterministic compiler must produce equivalent results with no skill
installed — every verb in §4 is a standalone script invocation first, a skill
convenience second.

---

## 4. Command lifecycle

One CLI entry point, `bin/context-graph.py`, thin per #180's adapter
pattern (argument parsing, JSON loading, dispatch to `context_graph`, output
rendering, exit codes — no independent logic). Freezing #191's own proposed
verbs as final and extending them to preview/candidates/propose/confirm/
apply/validate/status, per #182's required command-surface decision:

```text
# #191 — initialization and configuration (mutating unless noted)
bin/context-graph.py init --notes-home <path> --project <slug> [--display-name <name>]
bin/context-graph.py config status   --notes-home <path> --project <slug>            # read-only
bin/context-graph.py config validate --notes-home <path> --project <slug>            # read-only
bin/context-graph.py config add-repository    --notes-home <path> --project <slug> --alias <a> --provider <p> [--coordinates <owner/repo>] [--local-checkout-path <path>] [--default]
bin/context-graph.py config update-repository --notes-home <path> --project <slug> --binding-id <id> [--alias <a>] [--coordinates <c>] [--local-checkout-path <path>] [--default|--no-default]
bin/context-graph.py config remove-repository --notes-home <path> --project <slug> --binding-id <id>
bin/context-graph.py config set-default       --notes-home <path> --project <slug> --binding-id <id>
bin/context-graph.py config break-lock        --notes-home <path> --project <slug> --force   # removes .lock; see §15 — does not itself acquire the lock

# #183 — deterministic compiler (read-only, writes nothing)
bin/context-graph.py preview --notes-home <path> --project <slug> [--repo-root <alias>=<path> ...] [--adopt-context-md]   # --adopt-context-md previews the wrapped context.md diff only, §12

# #184 — candidate review, proposal validation, judgment ledger
bin/context-graph.py candidates --notes-home <path> --project <slug> [--subject-type edge|identity_anchor] [--status pending|accepted|rejected|retired]
bin/context-graph.py propose    --notes-home <path> --project <slug> --input <proposal.json>   # prints the validated candidate and its computed candidate_key to this invocation's own output — the only place a pending edge candidate's key is ever shown, §10/§11
bin/context-graph.py confirm    --notes-home <path> --project <slug> --candidate-key <key> --decision accepted|rejected|retired [--input <proposal.json>]   # --input required for edge candidates on accepted|rejected (re-supplies the proposal propose validated in-memory, §11); omitted for identity_anchor, which #183 regenerates deterministically each run. retired disables a previously-accepted candidate by the same --candidate-key (#184's own body), never allocates or revalidates. #184 allocates the anchor ID internally on identity_anchor acceptance — the caller never supplies one.

# #185 — recompute, validate, write
bin/context-graph.py apply --notes-home <path> --project <slug> [--repo-root <alias>=<path> ...] [--adopt-context-md]   # --adopt-context-md performs the adoption previewed above, refusing only if context.md gained managed-region markers since preview, §12

# Cross-cutting read-only inspection
bin/context-graph.py validate --notes-home <path> --project <slug> --target config|graph|candidates
bin/context-graph.py status   --notes-home <path> --project <slug>   # unresolved conflicts, stale candidates, coverage summary, orphaned temp files, and a present .lock's owner metadata including staleness (§12, §15)
```

`candidates` explicitly discloses `subject_type` and `candidate_origin` on
every row it prints — per #182's own required-decision text, a command named
`candidates` "may not conceal multiple authorities behind one verb." What it
can show differs by `subject_type`, because only one of the two has any
durable state to read: for `identity_anchor`, `--status pending` re-runs
#183's deterministic compiler and lists every currently-unanchored map entry
as a fresh candidate (always reproducible, never persisted, never stale);
for `edge`, there is no persisted "pending" state to list at all — a
validated edge candidate exists only inside the single `propose` invocation
that produced it (§10, §11) and is never written anywhere, so
`candidates --subject-type edge --status pending` always returns empty by
construction, and the operator sees a pending edge candidate's key only in
`propose`'s own output. For **either** subject type, `--status
accepted|rejected|retired` is populated by reading `judgments.jsonl` — real,
persisted ledger state. `candidates` **presents the union** of these
sources (live #183 regeneration plus ledger history); it validates or
generates neither.

Every command accepts `--notes-home`/`--project` explicitly and runs from any
working directory; none requires an active Bindle session or an installed
skill. Optional skill invocation is `/context-graph <verb>` (#186), a pure
pass-through to the same CLI arguments — the skill file itself is Claude-native
and out of scope for this design (per this repo's CLAUDE.md, Phase 1 keeps
Claude assets Claude-native).

`init`, `config *` (mutating forms), `confirm`, and `apply` acquire the
single-writer lock (§15) — `propose` does not: it writes nothing (§11's
in-memory validated-candidate flow), so it never contends for the lock.
`config status`, `config validate`, `preview`, `candidates`, `propose`,
`validate`, and `status` are read-only or write-nothing and never lock.
`config break-lock` is the one exception to both buckets: it removes an
existing `.lock` rather than acquiring one (§15).

---

## 5. State and authority

### Exact layout (extends, does not replace, the existing notes-home contract)

```text
<notes-home>/projects/<project-slug>/
  profile.md                      # existing — session-continuity
  map.md                          # existing — knowledge-promotion
  sessions/, handoffs/            # existing — session-continuity
  context.md                      # NEW — regenerable projection, #185 apply
  .bindle/context/
    config.json                   # NEW — authoritative, #191
    judgments.jsonl                # NEW — append-only ledger, #184
    index.json                     # NEW — rebuildable materialized graph, #185
    .lock                          # NEW — single-writer lock, §15
```

**This resolves the one ambiguity in #182's and #191's own bodies.** #182's
body writes state paths as `<project>/.bindle/context/config.json`; #191's
body writes the same file as
`<notes-home>/projects/<project-slug>/.bindle/context/config.json`. Read
together with #140's "writes remain under the configured notes home" and the
fact that `map.md`/`profile.md` already live at
`<notes-home>/projects/<project-slug>/`, `<project>` in #182's shorthand means
the notes-home project directory, never the Git checkout. This design freezes
that reading as final: **no context-graph state file is ever written into a
project's Git repository.** `docs/session-notes-format.md` and
`docs/notes-home.md` are amended (companion change, landed alongside #191) to
list `context.md` and `.bindle/context/` in the notes-home layout diagram —
this design record identifies that amendment as required; #191's
implementation makes it.

### Authority per file (frozen from #140's "Authority model", restated with file paths)

| State | Authority for | Rebuildable? |
|---|---|---|
| `.bindle/context/config.json` | project identity, repository-binding operating context | no — authoritative, #191-owned |
| `map.md` | promoted claim text and current curated understanding | no — owner-authored |
| current source artifacts (sessions, handoffs, documents, GitHub) | what artifacts presently contain | n/a — external truth |
| GitHub (read-only) | current issue/PR metadata, explicit closure | n/a — external truth |
| `.bindle/context/judgments.jsonl` | explicit human graph judgments | no — append-only, #184-owned |
| `.bindle/context/index.json` | rebuildable materialized view | **yes** — #185 fully recomputes on every apply |
| `context.md` | nothing — presentation only | **yes** — fully regenerable from `index.json` |

The prior `index.json` may retain last-known descriptive metadata during
degraded source access (§13) but may never preserve an otherwise-unsupported
relationship — an outage never grandfathers an invalid edge.

### Which writes are append-only vs. atomic-replace

- **Append-only:** `judgments.jsonl` only. Every write is `open(path, "a")` +
  a single `fsync`'d line; no line is ever edited or removed in place.
- **Atomic replacement:** `config.json`, `index.json`, `context.md`, and any
  written map-entry marker in `map.md` (the identity-anchor insertion). All
  four use write-to-temp-file-in-the-same-directory + `os.replace` (atomic on
  POSIX and Windows), with `fsync` on the temp file before rename and, where
  the platform supports it, an `fsync` on the containing directory after.
  `.lock` is created with `O_CREAT | O_EXCL` (§15), not written-then-renamed.

---

## 6. Project identity, configuration, and repository bindings

**Owned by #191; this section freezes only what #182 must add on top of
#191's already-detailed body** — the exact file location (§5, resolved
above) and the exact command verbs (§4, frozen above). Every other rule in
this space — `project:<32-lowercase-hex>` allocation via
`secrets.token_hex(16)`, idempotent init, malformed-config recovery routing
to an explicit separately-previewed recovery operation, zero/one/multiple
repository bindings, `repository-binding:<32-lowercase-hex>` stable IDs
independent of `owner/repo` coordinates, at-most-one default, bare-reference
resolution only through a unique configured default, `project-local` as a
reserved non-binding-alias discriminator — is #191's own frozen contract,
reused verbatim and not restated here to avoid a second, driftable copy.

One clarification this design adds: **repository resolution order for a
document evidence pointer.** #181's CLI takes `binding_ids` as a plain list
(§8 below); #183, when constructing the compiler's evidence-resolution
context from `config.json`, passes the **full configured `binding_id` list**
(not just the default) to `context_graph.evidence.normalize_field` — the
default-repository selection in `config.json` governs bare
`Issue #NNN`/`PR #NNN` resolution only (#191's contract), never which
repository bindings are available for document-evidence normalization.

---

## 7. Map parsing

**Owned by #179/#180's frozen grammar; #182 freezes the seam to #183's
parser, adding no new grammar.** The binding rule, restated verbatim because
#182's body requires this section to state it explicitly:

> Every owner-curated top-level map entry becomes exactly one semantic node.
> Indented field lines and tension sides are structured content of that node,
> not additional nodes.

Frozen boundaries for #183's parser, reusing #179's grammar and #180's
`node.schema.json` status mapping without modification:

- **Heading-entry boundaries (Decisions, Learnings):** one entry begins at a
  `### <claim>` line and ends immediately before the next `###`/`##` line or
  end of section; its field lines (`why:`/`so:`/`revisit-when:`/`evidence:`)
  are structured content, not separate nodes.
- **Single-bullet Assumption:** one entry is one top-level `-` bullet in
  `## Assumptions & tensions` whose body has no indented sub-bullets.
- **Structured tension:** one entry is one top-level `-` bullet with exactly
  two indented sub-bullets; the parent produces the `tension` node, each side
  becomes an entry in the node's `sides` array (`node.schema.json`'s `sides`
  field, `minItems`/`maxItems` 2) — never a second node.
- **Open question:** one entry is one top-level `-` bullet in
  `## Open questions`; its `(open|parked)` token maps directly to
  `node.schema.json`'s `status` enum (`open`/`parked`).
- **Superseded / typed tombstone:** one entry is one top-level `-` bullet
  under `## Superseded` beginning `<kind>: `; it maps to `status: superseded`
  and carries the **existing** id from `bindle:context-id` (never a new
  allocation) plus, when present, `bindle:superseded-by` as the deterministic
  source for a `supersedes` edge (§3's deterministic-`supersedes` path).
- **Identity-marker placement:** exactly as knowledge-promotion.md's "Stable
  identities" section states — claim heading, top-level bullet, or tension
  parent bullet only. A marker found on a field line, a tension side, or an
  unsupported location is a parse-time conflict, reported and never
  auto-relocated (§13).
- **Missing required sections:** all six `##` sections are contractually
  always present (knowledge-promotion.md); a map missing one is a conflict,
  reported and not silently treated as an empty section — #183 does not write
  to `map.md` to repair it (only the knowledge-promotion write path does
  that, on the next confirmed write).
- **Map size cap:** #183 has no special behavior at the ≤150/200-line budget;
  the budget is a knowledge-promotion write-time concern (§ "Update rules"
  there), not a compiler read-time concern. #183 parses whatever `map.md`
  currently contains, at any size.
- **Malformed cardinality / untyped tombstones / unresolved
  `superseded-by`:** exactly `bin/map-entry-id.py validate`'s existing
  finding set (`duplicate-id`, untyped-tombstone info, malformed/duplicate/
  self-referential/unresolved `superseded-by`, `retirement-in-place` error,
  `legacy-retirement-in-place` info) — #183 calls the same validation logic
  (via `context_graph`, not a `map-entry-id.py` subprocess call) rather than
  re-deriving a second finding set.

No second Markdown grammar is introduced anywhere in this design.

---

## 8. Evidence normalization

**Owned by #181, consumed by #183 as `import context_graph.evidence` per
#180's "never shell out to the CLI" boundary.** One required schema amendment
surfaces from #181's shipped implementation, flagged in #181's post-merge
audit comment and confirmed against the live code in this design's
reconnaissance:

### Required amendment: node/candidate schema `kind` enum

`schemas/context-graph/v1/node.schema.json` and `candidate.schema.json`
(mirrored `source_kind`/`target_kind`) currently enumerate exactly one
document evidence kind, `design_document`. #181's shipped
`context_graph.evidence.normalize()` instead emits two kinds for a
repository-relative document path: `document_repository` (bound to a
`repository-binding:...`) and `document_project_local` (no binding
configured or repositoryless project) — reusing the vocabulary
`context_graph.ids.parse_typed_id` already defines for `document:` IDs
(`document:<project-id>:<binding-id>:<path>` vs.
`document:<project-id>:project-local:<path>`). Neither shipped string equals
`design_document`, and #181's grammar accepts any repository-relative path
(not only `docs/design/*`), so `design_document` is both wrong-named and
narrower than what is actually normalized.

**Decision:** replace `design_document` with `document_repository` and
`document_project_local` in both schemas' `kind` enums (`node.schema.json`
line 13, `candidate.schema.json` lines 40 and 48), **and** in
`bin/context_graph/relationships.py`'s `EVIDENCE_KINDS` (line 19) and its
`validation-evidence` node group (line 44) — both already shipped by #180 and
both hard-coding `design_document` today. This is **not** schema-only: those
two `relationships.py` constants feed `ENDPOINT_MATRIX` directly
(`evidence-any` gates `supported_by`/`discussed_in`'s target;
`validation-evidence` gates `validated_by`'s target), so leaving them
unamended would make `validate_endpoint_pair` reject every deterministic
`supported_by` edge to a `document_repository`/`document_project_local` node
— the compiler's primary evidence-edge path — the moment #181's already-shipped
output starts flowing through it. The native validator,
`bin/context_graph/validation.py`, is **already shipped by #180** (not a
#183 green-field file, correcting an earlier draft of this section) — it
carries no literal `design_document` itself and derives evidence-kind
legality entirely through `relationships.py`'s `validate_endpoint_pair`, so
it inherits this fix automatically once (1) and (2) land; no separate edit
to `validation.py` is required. What *does* require separate edits, because
it hard-codes the old value directly rather than deriving it: the shipped
test `bin/context_graph/tests/test_relationships.py`'s
`test_validated_by_learning_to_design_ok_question_to_issue_fails` (asserts
`design_document` legal against `validation-evidence`, which becomes false
after this amendment) and five shipped `expect_valid: true` fixtures under
`testdata/context-graph/v1/` that contain `design_document` nodes/edges
(`documents/68-…`, `documents/69-…`, `identity-config/68-…`,
`identity-config/69-…`, `endpoint-matrix/47-1-…`) — all five would newly
fail both schema conformance (the enum no longer contains their `kind`) and
native validation (`endpoint-matrix/47-1`'s `validated_by` edge would
trip `E_EDGE_ENDPOINT_ILLEGAL`) if left unmigrated. Classify the amendment in
`invariant-coverage.json` as `schema-and-native` once #183 lands, consistent
with #180's existing methodology (§11 of #180's design). This amendment is
folded back into #180's own frozen contract per that document's own stated
update rule ("the answer is decided in the implementation issue and folded
back into this document") — #180's `docs/design/2026-07-16-context-graph-schema.md`
§6 and the two schema files are both patched in the same PR that implements
#183 (not in this design-only change, which touches no schema file and no
other document — see the Appendix for the complete list of amendments this
design requires but defers to their owning implementation PRs).

### `--binding-id` CLI shape — ratified

#181's audit comment flagged the CLI's repeatable `--binding-id` flag (zero =
repositoryless/project-local; one = the unique binding; more than one =
`status: unresolved`, `reason: binding_ambiguous`) as an unratified
best-fit interpretation pending #191/#182. **Ratified as final** in this
design: the CLI semantics stay exactly as shipped. #183, calling the library
function directly, passes the full `binding_ids` list straight from
`config.json`'s `repositories[].binding_id` (§6) — no change to
`evidence.py`'s public signature is needed. A future richer resolution (e.g.
an evidence-pointer-scoped alias hint) is out of scope for v1 and not
required by any epic acceptance criterion.

### Field-level parsing ownership

Restated per #182's required-decision text: field-level parsing of
comma-separated evidence pointers is owned solely by #181.
`context_graph.evidence.normalize_field` is the only tokenizer; #183 extracts
the raw `evidence:` field string from a parsed map entry (§7) and passes it
unchanged to `normalize_field` — #183 never splits on commas, never unwraps a
Markdown link, and never implements a second evidence grammar, matching
#181's own body: "#183 extracts the complete field and delegates it unchanged
to this normalizer."

---

## 9. GitHub adapter

Owned by #183, thin and read-only (#184 has no role in GitHub access or
closure-edge extraction — `closes` is deterministic-only, produced solely by
#183, per #184's own body, which places it outside the workflow it owns):

- **Issue and PR lookup:** by `owner/repo#number` (from a normalized
  `github_issue:`/`github_pr:` evidence ID, §8), read-only, via whatever
  read-only mechanism the runtime environment already authorizes for GitHub
  access (`gh`/API token) — this design does not introduce a new credential
  path.
- **Explicit closure-edge extraction:** a `closes` edge is deterministic
  (§3's creation-authority table) and is created **only** from GitHub's own
  declared PR→issue closing-reference data — never inferred from issue/PR
  title or body text similarity.
- **Timeout and failure behavior:** a network timeout, rate limit, or
  authentication failure degrades the affected GitHub-sourced coverage state
  to `unavailable` (§13) — it never raises past the compiler boundary, never
  aborts the whole preview, and never silently fabricates issue/PR state.
- **Rate-limit handling:** on a rate-limit response, the adapter stops
  further GitHub calls for the remainder of that run, marks
  `github_issues`/`github_prs` coverage `partial` or `unavailable`
  (depending on whether any calls succeeded), and reports which references
  were not resolved.
- **Missing vs. unavailable:** "missing" (the API confirms no such issue/PR)
  and "unavailable" (the API could not be reached or denied access) are
  distinct coverage states — a missing artifact is real information (a
  broken reference); an unavailable one is uncertainty. Conflating them
  would turn a transient outage into a false claim of a broken reference.
- **Last-known metadata:** on `unavailable`, the prior `index.json`'s
  last-known descriptive fields (title, state) may be retained for display,
  clearly marked `stale`; no edge is invented or preserved past what the
  last successful resolution actually supported (§5's authority table).
- **Test stubbing:** the adapter's read functions are called through one
  narrow interface (`fetch_issue(owner, repo, number)` /
  `fetch_pr(owner, repo, number)` / `fetch_pr_closes(owner, repo, number)`)
  so fixtures and pressure tests substitute a stub returning canned
  responses (including timeout/rate-limit/not-found) — no fixture makes a
  real network call, matching #180's stdlib-only, network-free runtime
  posture for everything except this one adapter boundary.

No GitHub mutation is permitted anywhere in this design — read-only, full
stop.

---

## 10. Candidate-production authority

Covered fully in §3's producer/validator/authority table and non-overlap
rules — this section exists in the required outline to point at that content
rather than duplicate it. The one addition: the exact file/command
transitions the table implies:

```text
map.md (unanchored entry)
   --#183 preview-->  identity-anchor candidate (in-memory, printed by `candidates`)
   --human accepts via `confirm --decision accepted`--> #184 allocates the
   anchor ID internally (via #179's helper) -->
   judgments.jsonl event (decision: accepted, assigned_id, entry_fingerprint)
   --#185 apply-->  map.md marker write (§12) + index.json node

human-authored proposal.json  (or #186-produced)
   --`propose` command--> #184 validates against current #183 graph + #180 matrix
   --valid--> validated `edge` candidate (in-memory, printed by `propose`
   ITSELF — never `candidates`, which has no persisted edge state to show;
   never persisted anywhere — `propose` writes nothing)
   --human accepts via `confirm --decision accepted --input <same proposal.json>`-->
   #184 recomputes the candidate key from the resupplied envelope, confirms
   it matches the key `propose` showed, revalidates endpoint legality and
   basis against the *current* #183 graph (§11's confirm-time revalidation)
   -->
   judgments.jsonl event (decision: accepted)
   --#185 apply--> index.json edge (origin: human_judgment)
```

An edge candidate's validated state genuinely does not survive between
`propose` and `confirm` as separate process invocations — nothing persists
it (§5's layout has no candidate store). `confirm` must therefore be handed
the same proposal envelope again at acceptance time; it is not reconstructed
from the bare `candidate_key` alone. This matches #184's own body, which
requires confirm to "validate the proposal envelope and recompute the
candidate key" for edge acceptance — `--input` is not a convenience, it is
the only way `confirm` can do that.

---

## 11. Candidate and judgment lifecycle

Reduction state machine owned by #184; this design freezes only the file
format and command transitions, not the reducer algorithm itself (#184's
implementation detail, bounded by the rules below which are already frozen
across #140/#180/#184's consolidated bodies):

- **Generation:** identity-anchor candidates only from #183 preview;
  semantic (`edge`) candidates only from #184 validating a proposal.
- **Endpoint-legality gate, then candidate-key construction:** #184
  validates the proposal's (or #183's anchor discovery's) endpoint pair
  against #180's closed matrix *before* computing a candidate key — an
  illegal pair is rejected outright and never reaches #180 §10's
  key-construction algorithm, so no candidate key is ever minted for an
  illegal combination. Legal pairs proceed through exactly #180 §10's two
  byte-exact algorithms — #182 adds no third.
- **Proposal interchange:** `proposal.schema.json`, the only accepted input
  shape for `propose`.
- **Confirm-time revalidation:** `confirm` re-runs the same endpoint-legality
  and basis validation against the *current* #183 graph immediately before
  appending an acceptance event — propose-time validation alone is not
  trusted, since an arbitrary amount of time and graph change can separate
  `propose` from `confirm`. For an `identity_anchor` candidate, `confirm`
  re-derives the candidate directly from a fresh #183 preview (deterministic,
  no input needed). For an `edge` candidate, `confirm --input <proposal.json>`
  requires the operator to resupply the same proposal envelope `propose`
  validated — `confirm` recomputes the candidate key from it, confirms the
  recomputed key matches `--candidate-key`, and only then revalidates (§10's
  flow diagram shows the full transition; nothing about an edge candidate
  persists between separate `propose` and `confirm` invocations, so there is
  no other way for `confirm` to know what it is being asked to accept). A
  candidate that was legal at propose time but is no longer legal at confirm
  time is refused with a `candidate_stale_illegal` diagnostic; the operator
  must re-propose against current state. (This revalidation runs after the
  existing-decision idempotency check in §15's "Idempotence" — an
  already-accepted `candidate_key` short-circuits before revalidation, since
  it performs no new write.)
- **Acceptance / rejection / retirement:** three `judgment.schema.json`
  `decision` values; append-only; a later valid event for the same
  `subject_key` supersedes an earlier one for reduction purposes (the ledger
  itself is never edited or truncated).
- **Ledger-reduction revalidation:** when computing effective state, #184's
  reducer re-checks each accepted event's endpoint pair against the #183
  graph current at reduction time (not the graph current when the event was
  accepted). An accepted event whose endpoint pair has since become illegal
  contributes no effective edge — the ledger event itself is never rewritten
  or removed (append-only, unconditionally), but reduction treats it as
  inert and reports it as a `stale_illegal_judgment` finding rather than
  silently reinstating an invalid edge or silently dropping the audit trail.
- **Candidate-scoped dependency fingerprints:** exactly #180 §9/§10.2 — no
  whole-graph fingerprint ever independently stales a candidate.
- **Unchanged-rejection suppression:** a rejected candidate whose
  `candidate_key` (and therefore its full material content) is unchanged is
  not re-proposed by `candidates`/re-offered by `propose`; a changed
  candidate key (evidence, endpoints, or basis changed) is a new subject,
  always re-offerable.
- **Conflict between multiple accepted edges:** cannot occur for the same
  `candidate_key` (acceptance is idempotent per key), but two *different*
  accepted edges can express contradictory graph meaning (e.g. both
  `A --supports--> B` and `A --contradicts--> B` accepted) — this design
  does not forbid it; `apply` reports it as a `semantic_conflict`
  diagnostic, informational only, never blocking apply. This is distinct
  from an illegal endpoint combination (never approvable — see the
  endpoint-legality gate above): a semantic conflict is two independently
  *legal* edges whose meanings disagree, not an invalid graph record. If an
  accepted edge's endpoint pair has instead become genuinely illegal by
  apply time (caught despite confirm-time and ledger-reduction
  revalidation — e.g. a referenced node's `kind` changed between reduction
  and apply), §12 step 6's whole-state validation aborts the entire apply
  rather than treating it as a mere semantic conflict. The graph is a record
  of human judgment, not an enforcer of judgment consistency — but it is
  never a record of an invalid one.

---

## 12. Projection and apply safety

### Apply pipeline (#185)

```text
1. re-run the full #183 deterministic-compiler pipeline (§3) against current
   sources — never trust the prior preview or the prior index.json
2. load and reduce judgments.jsonl (#184's reducer, §11) into effective
   judged edges and effective identity-anchor authorizations, revalidating
   each accepted **edge** event's endpoint legality against this run's #183
   graph (§11's ledger-reduction revalidation — `identity_anchor` events have
   no endpoint pair and instead revalidate by fingerprint/uniqueness)
3. construct the exact intended `map.md` bytes in memory, with only the
   authorized identity-anchor markers inserted (§7's marker-placement rule)
   — no other byte of the file changes
4. parse the planned `map.md` bytes in memory using the same canonical
   parser #183 uses (never a second, divergent parse path) — this
   guarantees a first-apply anchor for an entry added since preview still
   appears in this run's final outputs, because it is discovered by
   re-parsing the actual planned text, not synthesized separately
5. build the intended final graph — nodes and edges (deterministic +
   effective judged) — from the planned map parsed in step 4
6. validate the complete planned state against #180's full invariant set
   before any write occurs; an endpoint pair that is illegal against this
   planned state aborts the entire apply (§11) — nothing is written
7. write, in this order: (a) map.md marker insertions (atomic replace,
   minimal diff — see below), (b) index.json (atomic replace), (c)
   context.md (atomic replace)
8. release the lock
```

Step 6's whole-state validation before step 7's first write is what makes
apply "construct and validate the complete intended final state... before its
first write" (#140's mutation-lifecycle guarantee).

### `map.md` marker writes

An approved identity-anchor write inserts **only** the
`<!-- bindle:context-id: ... -->` comment onto the entry's existing anchor
line (§7's marker-placement rule) — no other byte of the entry, and no other
line in the file, changes. This is the same "minimal diff, never
regenerate the file, never reorder the owner's prose" discipline
knowledge-promotion.md already establishes for the promotion workflow; apply
reuses it rather than inventing a second write discipline for the same file.

### `context.md` creation vs. update vs. markerless adoption vs. malformed markers

- **First creation:** no `context.md` exists — apply writes it fresh from the
  planned state, wrapped in a managed-region marker
  (`<!-- bindle:context-graph:generated:begin/end -->`, matching the
  HTML-comment marker convention already used for map identities). This
  marker name supersedes the illustrative `bindle:context:start`/`end` shown
  in #185's own body — #185 explicitly defers exact marker rendering to
  #182 (this design), so the two are not in conflict, but a reader
  cross-referencing both documents should expect this document's marker,
  not #185's example, to be the one implemented.
- **Update:** `context.md` exists with a valid managed-region marker — apply
  replaces only the marked region; any owner-added prose outside the markers
  survives untouched (mirrors `map.md`'s "never touch what a proposal doesn't
  name").
- **Markerless adoption:** `context.md` exists with **no** managed-region
  marker (hand-created, or from a version predating this contract) — apply
  refuses to overwrite it. It reports `context_md_unmanaged` and writes
  nothing to that file (the rest of apply — `index.json`, map markers —
  still proceeds). Adoption is a **separately previewed, explicitly
  confirmed operation** (#185's own wording), not a same-invocation flag:
  `preview --adopt-context-md` prints the exact wrapped diff (the existing
  content as it will appear once wrapped in markers) and writes nothing —
  nothing from this preview persists for `apply` to compare against later
  (§5's layout has no preview-state store, deliberately, mirroring why an
  `edge` candidate's validated state doesn't survive between `propose` and
  `confirm` either, §11). A follow-up `apply --adopt-context-md` therefore
  guards against the one genuinely unsafe, cheaply re-checkable transition
  rather than requiring byte-identical content: it re-reads the current
  `context.md` and performs the wrap-and-write only if the file is **still
  markerless** — wrapping current markerless content is non-destructive
  regardless of ordinary prose edits made between preview and apply, since
  the operator already confirmed the general shape via preview and nothing
  outside the wrapper is altered. If the file has instead gained a
  managed-region marker (or malformed one) since preview — meaning apply
  ran, or some other process wrote a `context.md`, in between — adoption
  refuses with `context_md_adopt_state_changed` rather than overwriting it.
- **Malformed markers:** `context.md` exists with malformed, duplicate,
  nested, reversed, or partial managed-region markers — apply treats this as
  a conflict, reported (`context_md_malformed_markers`), and never
  auto-regenerated (the rest of apply still proceeds, exactly as in
  markerless adoption's refusal). There is no automatic-repair path for a
  malformed marker pair; recovery requires the operator to manually fix or
  remove the malformed markers before apply will treat the file as either
  "update" or "markerless adoption" eligible.

### Temporary files, atomic rename, per-file atomicity, and orphan cleanup

Every write in step 7 uses the same temp-file-in-target-directory +
`os.replace` discipline as §5. **Atomicity is honest and per-file, not
cross-file:** apply does not claim that steps 7(a)–7(c) commit as one atomic
transaction. Write ordering is deliberate — map markers first (the
cheapest-to-detect-and-resume step), then `index.json`, then `context.md` —
so an interruption's blast radius is always "some approved markers landed,
some derived state didn't" rather than the reverse (an inconsistent
`index.json` referencing anchor IDs never written to `map.md`).

A crash between a temp file's write/fsync and its `os.replace` rename leaves
an orphaned `*.tmp` file in the target directory. Cleanup is **passive,
never automatic**: `status` (§4) lists any orphaned temp file matching this
design's naming convention under the affected project's `.bindle/context/`
or notes-home project directory, and reports it as a diagnostic; no command
deletes a temp file it did not itself just create and successfully rename in
the same invocation. An operator removes a reported orphan manually,
consistent with this design's general refusal to auto-repair (matches the
no-automatic-lock-breaking and no-automatic-config-repair posture elsewhere
in this document).

### Incomplete-apply detection and safe retry

Detection reuses the single-writer lock (§15) rather than a new hash field:
`apply` holds `.lock` for the duration of steps 1–8, and the lock's owner
metadata (`operation: "apply"`) is released only on normal completion (the
same `try`/`finally` §15 already guarantees). A hard kill (`SIGKILL`, power
loss) during any of steps 1–7 leaves `.lock` stale with `operation: "apply"`
— exactly the signal `config status`/`status` (§4) already surfaces per
§15's stale-lock reporting, with no separate mechanism needed. An
implementation was earlier considered that instead compared a
freshly-recomputed digest of "the planned state" against a value stored in
`index.json` — rejected during this design's own review: because the
planned state is derived from current sources (steps 1–6), any ordinary
edit to `map.md` after a completed apply changes what a fresh recompute
produces, so that approach reports a false "previous apply was interrupted"
on the single most common workflow (edit map, then run `apply` again). The
stale-lock signal has no such false positive — the lock's state reflects
only whether the *apply process itself* exited cleanly, never whether
sources changed since.

Recovery is **always** a safe retry, whether or not a stale lock was
detected: re-running `apply` from scratch (after `config break-lock` if the
lock is stale) re-derives the complete planned state from current sources
(steps 1–6 are side-effect-free) and re-writes only what actually differs
from what's on disk — a map marker already written this way is semantically
idempotent to write again (same bytes), so no rollback machinery is needed.
There is no partial-apply rollback path because there is nothing to roll
back to that retry doesn't already reconstruct. This holds identically on a
project's very first apply (no prior `index.json` exists) — a fresh run
always reconstructs the complete planned state regardless of what, if
anything, partially landed before.

### Semantic no-op

Apply performs a byte-for-byte comparison of each of the three target
artifacts' planned bytes against their current on-disk bytes before writing;
an artifact whose planned bytes exactly match current bytes is not
rewritten (no temp file, no rename, no mtime change) — satisfying #140's "a
second unchanged apply performs zero writes."

---

## 13. Failure and degradation behavior

Coverage states, exactly `index.schema.json`'s enum
(`complete`/`partial`/`uncertain`/`unavailable`/`unsupported`), applied
uniformly across `project_map`, `sessions`, `handoffs`, `documents`,
`github_issues`, `github_prs`, `commits`:

- **`unavailable`** (e.g. GitHub timeout, notes-home unreadable mid-run) never
  deletes previously promoted understanding — the affected nodes/edges keep
  their last-known state, marked stale (§9), and `map.md`/`config.json` are
  never touched by a degraded read.
- **`uncertain`** (e.g. a document evidence pointer's target file exists but
  its content couldn't be confirmed to still match) is reported distinctly
  from `unavailable` — never conflated with artifact absence (#180's own
  wording, reused here for the whole system, not just #180's validator).
- **Missing evidence** (a session/handoff/document/GitHub target genuinely
  does not exist) degrades that one evidence node's status; it does not
  remove the semantic node that cited it, and does not block preview or
  apply for the rest of the graph.
- **Malformed/conflicting `config.json`, malformed map entries, illegal
  endpoint combinations:** all are invariant failures per #180/#191's own
  validation rules (§6), reported with the structured diagnostic each
  contract defines, and never silently repaired or skipped by #183/#184/#185.
- **A hard parse or validation failure that would prevent constructing a
  coherent preview at all** (e.g. `config.json` missing) stops before any
  candidate is emitted and reports "configuration required" — matching
  #191's own preview-time behavior contract.

---

## 14. Security and privacy

- **Allowed notes-home writes:** exactly six paths under
  `<notes-home>/projects/<project-slug>/` — the five new files in §5's layout
  (`context.md`, `config.json`, `judgments.jsonl`, `index.json`, `.lock`)
  plus `map.md` (existing file; identity-anchor marker insertions only,
  §12); nothing is ever written above that directory or into
  `private-denylist.txt`.
- **Repository-relative document paths:** normalized and validated by #181
  (already shipped); §8 adds no new path-handling logic.
- **Absolute path normalization / traversal rejection:** owned by #181's
  `normalize()` (already rejects traversal per its shipped fixture corpus);
  #183/#185 never construct a filesystem path from unvalidated evidence
  output — they only ever join a `context_graph`-validated relative path
  onto a caller-supplied, already-trusted root (`--notes-home`/`--repo-root`).
  Rejecting traversal is a normalization-time concern (#181), not something
  #182 re-implements downstream.
- **External URL handling:** #181 already resolves `https://github.com/...`
  issue/PR/repo-page URL shapes to typed IDs and rejects everything else as
  unsupported; no other URL form is ever fetched or followed by any part of
  this design (no HTML scraping, no arbitrary-URL evidence).
- **Source excerpt policy:** no part of this system ever copies session,
  handoff, or document *content* into `index.json` or `context.md` — only
  identity, label (the map's own claim text, already owner-authored and
  already private-by-default per privacy-boundaries.md), status, and
  relationship metadata. A session/handoff's private body text never crosses
  into a generated artifact.
- **Log redaction:** the CLI's stderr/diagnostic output includes typed IDs,
  file paths under the notes home, and finding codes — never raw session
  content, and never resolved GitHub tokens/credentials (the adapter, §9,
  never logs its auth mechanism).
- **`context.md`/`index.json` are notes-home artifacts**, private by default
  exactly like `map.md` — the repo-bound-content recipe (sanitize, scan with
  `bin/check-private-info.sh`, leave unstaged) applies unchanged if a user
  ever explicitly asks to publish either into a repo; this design's own
  outputs never opt out of that default.

---

## 15. Idempotence, atomicity, and locking

### Single-writer lock

Frozen, shared by #191 init/config-mutation, #184 confirm, and #185 apply —
per #182's required-decision §10, #191's own Locking section, and #184's
Command boundary, all three of which name exactly these three participants
and never `propose`.

- **Location:** `<notes-home>/projects/<project-slug>/.bindle/context/.lock`
  (§5).
- **Acquisition:** atomic `os.open(path, O_CREAT | O_EXCL | O_WRONLY)`; on
  success, write owner metadata as JSON — `{"pid": <int>, "hostname": <str>,
  "operation": "init"|"config"|"confirm"|"apply", "acquired_at":
  <ISO-8601>}` — then `fsync`. `propose` is deliberately absent from this
  enum: it never acquires the lock (§4), so no lock-owner metadata record can
  ever have that value.
- **Contention policy (bounded, documented):** on `EEXIST`, read the existing
  lock's owner metadata; retry acquisition with exponential backoff
  (starting 100ms, capped at 2s per attempt) for up to 10 seconds total; on
  final failure, exit non-zero and print the owner metadata verbatim so the
  operator can diagnose (a live process on this host, a stale lock from a
  crashed run, or a genuinely concurrent second invocation).
- **Read-only visibility:** `status` (§4) reads and reports a present
  `.lock`'s owner metadata whenever it runs — not only on the contention
  path above — including whether the owning `pid` still looks live on
  `hostname`, so an operator can see a stale lock (and diagnose which
  operation left it, per its `operation` field) without first triggering a
  contending acquisition. This is what §12's incomplete-apply detection
  relies on.
- **No automatic breaking:** a live-looking lock is never broken
  automatically, regardless of age.
- **Explicit stale-lock recovery:** `bin/context-graph.py config
  break-lock --notes-home <path> --project <slug> --force` removes the lock
  file after printing its owner metadata and requiring the operator to
  confirm (or pass `--force` non-interactively) — this is the one explicit,
  separately named recovery operation; no other command ever removes
  `.lock`. `config break-lock` does not itself acquire the project lock
  through the normal path — its entire purpose is to act when the lock file
  already exists, so it opens/removes `.lock` directly (after printing owner
  metadata and requiring confirmation) rather than contending for it.
- **Release:** normal completion removes the lock file as its last step,
  inside the same `try/finally` that guarantees release on any raised
  exception during the locked operation, so a clean crash (an unhandled
  Python exception) still releases; only a hard process kill (`SIGKILL`,
  power loss) leaves a stale lock, which is exactly the case
  `break-lock` exists for.
- **Cross-project isolation:** the lock path is project-scoped
  (`.../projects/<project-slug>/...`), so operations on unrelated projects
  never contend.

### Idempotence

Restated from §12: `init` reruns preserve the existing ID and perform zero
writes when config is already valid; `apply` reruns perform zero writes when
nothing changed (byte-for-byte comparison); `confirm` on an already-decided
`candidate_key` with the same decision is a no-op read of the existing
ledger state, not a duplicate append (the CLI checks current effective state
before appending — an unnecessary duplicate acceptance event is refused with
a clear "already accepted" message rather than silently growing the ledger).

---

## 16. Test strategy

Every epic acceptance criterion maps to one of: a deterministic fixture, a
unit/shell test, an integration pressure test, or an explicit manual dogfood
check. This design does not enumerate all ~150 fixtures across five
implementation issues (each issue's own body already does, per §"Required
inputs" review); it freezes the **mapping discipline**:

| Layer | Owner | Convention |
|---|---|---|
| Native unit tests | each of #191/#183/#184/#185/#186 | `bin/context_graph/tests/test_<module>.py`, `python3 -m unittest discover`, mirrors #180/#181's existing pattern |
| Fixture corpus | each issue, own `testdata/` subtree | `testdata/context-graph-<issue-topic>/v1/`, one file per fixture, manifest-driven — mirrors #180 §12/§13 exactly, not reinvented per issue |
| Shell harness | each issue | `bin/test-context-graph-<topic>.sh`, auto-excluded from the inventory (`^bin/test-.*\.sh$`), wired into `make test` |
| Schema conformance | #183 (first consumer of the amended `kind` enum, §8) | extends #180's existing bidirectional conformance test; the `document_repository`/`document_project_local` amendment gets its own fixture pair before #183 merges |
| Cross-boundary endpoint-legality matrix | #183/#184 jointly | one fixture set proving direct CLI, skill-supplied proposal, human-authored proposal file, prior ledger event, and deterministic compiler edge **all** hit the same `validate_endpoint_pair` call at each of §11's checkpoints: before candidate-key construction, at confirm-time revalidation, at ledger-reduction revalidation, at compilation, and at apply's whole-state validation (§12 step 6) — plus one fixture proving a judgment legal at accept-time and illegal by apply-time aborts the entire apply (§12 step 6) rather than silently landing |
| Locking/concurrency | #191 (owns the lock's first implementation) | two-process fixture (subprocess spawn) proving exactly one of two concurrent `init` calls allocates an ID; stale-lock recovery exercised via a fixture lock file with fabricated old `acquired_at`; fixture proving `propose` never creates or waits on `.lock` |
| Apply safety | #185 | fixture proving semantic no-op writes nothing (mtime-comparison assertion); fixture proving a first-apply anchor added since preview appears in that same apply's output via the planned-bytes reparse (§12 step 4); fixture proving a crash between step 7(a) and 7(b) leaves a stale `operation: "apply"` lock reported by `status`, and that a retry after `config break-lock` safely reconstructs full state regardless of exactly which sub-step was interrupted; fixture proving an orphaned temp file is reported by `status`, never auto-deleted; fixture proving `preview --adopt-context-md` then `apply --adopt-context-md` adopts a still-markerless file even after an ordinary prose edit made between preview and apply, and refuses (`context_md_adopt_state_changed`) only if the file gained a managed-region marker in between; fixture proving malformed markers are reported and never auto-regenerated |
| Manual dogfood | #186 graduation | run the full init → preview → propose → confirm → apply cycle against this repo's own `~/.bindle/projects/bindle/` notes home before marking #186 tested, per this repo's own `superpowers:writing-skills` RED→GREEN→REFACTOR discipline |

`make check` and `make test` must stay green after each child lands, exactly
as #180/#181 already established.

---

## 17. Migration and compatibility

- **No historical migration is in scope** (epic non-goal, restated). Every
  existing `map.md` continues to parse: pre-#179 unanchored entries and
  pre-#179 status-flipped-in-place retirements are read as informational,
  never hard errors (§7, reusing #179's existing `legacy-retirement-in-place`
  classification).
- **No existing notes-home file is redefined.** `profile.md`, `map.md`,
  `sessions/*.md`, `handoffs/*.md` keep their exact current shape; this
  design only adds new files beside them (§5).
- **Schema versioning:** this is still `v1` throughout — the §8 `kind` enum
  amendment is a **fix to unreleased-as-implemented v1 schema files** (no
  compiler has shipped against the old `design_document` value yet — #183 is
  the first consumer), not a `v2` bump. #180's versioning rule ("a future v2
  is a new directory... not an edit of these") governs any *future* breaking
  change; amending a not-yet-consumed enum before its first real consumer
  ships is not that case.
- **`docs/session-notes-format.md`/`docs/notes-home.md` amendment:** adding
  `context.md` and `.bindle/context/` to the documented notes-home layout
  (§5) is additive and backward compatible — existing tooling that lists
  `projects/<project>/` contents is unaffected by two new entries.

---

## 18. Final child-issue decomposition

**No new child issue is required.** The existing #140 child chain — #179,
#180, #181 (shipped); #191, #183, #184, #185, #186 (remaining) — is
sufficient, matching #180's own §21 conclusion and every "no new child issue
is required" audit-resolution comment on #140/#181. Splitting further is
warranted only when a child can land independently and materially reduce
integration risk; none of the remaining five meets that bar today (#191 must
precede #183 for the compiler to have real config to read; #183 must precede
#184 for real deterministic graph to validate proposals against; #184 must
precede #185 for real judgments to reduce; #185 must precede #186 for a real
apply to drive from a skill).

Refined scope per child, reflecting this design's decisions:

- **#191** — implements exactly its own already-detailed body, plus this
  design's file-location resolution (§5) and command-verb freeze (§4:
  `init`, `config status|validate|add-repository|update-repository|
  remove-repository|set-default`, `config break-lock`), plus the shared
  lock contract (§15).
- **#183** — implements the ten-phase pipeline (§3), the map parser (§7)
  reusing `context_graph.validation`/`bin/map-entry-id.py` logic (not a
  subprocess call), the GitHub adapter (§9), and lands the `kind`-enum schema
  amendment (§8) in the same PR that first emits a `document_repository`/
  `document_project_local` node.
- **#184** — implements the reducer state machine (§11) including
  confirm-time and ledger-reduction endpoint-legality revalidation and
  validate-before-key-construction ordering, `propose`/`confirm`/
  `candidates` (§4), and the endpoint-legality cross-boundary fixture set
  (§16).
- **#185** — implements `apply` (§12) including the `context.md`
  creation/update/markerless-adoption/malformed-marker behavior, the
  planned-map reparse mechanism (§12 steps 3–5), the semantic-no-op
  comparison, orphaned-temp-file reporting, and stale-lock-based
  incomplete-apply detection (§12) — no schema amendment required for this.
- **#186** — implements the thin skill/adapter (§3's provider-neutral
  contract) and drives graduation dogfood (§16).

---

## 19. Explicit unresolved questions

None block a go decision. Several items are **resolved by this design**
rather than left open, and are addressed in their own sections, not here,
because #182's body requires this section to name only what remains
genuinely open:

- §8's schema amendment (`design_document` → `document_repository`/
  `document_project_local`).
- §5's file-location reading (`<project>` means the notes-home project
  directory).
- §11's three endpoint-legality revalidation checkpoints
  (validate-before-key-construction, confirm-time revalidation,
  ledger-reduction revalidation) and the apply-time abort-on-illegal-late
  behavior (§12 step 6) — added during this design's own adversarial review,
  not carried over from an earlier draft.
- §12's planned-map reparse mechanism (replacing an earlier in-memory
  synthesis approach that risked a second, divergent implementation of "what
  a newly-anchored entry's node looks like"), the `context.md`
  malformed-marker case, stale-lock-based incomplete-apply detection
  (replacing an earlier `source_state_hash` schema-field proposal, rejected
  during this design's own review for a false-positive invariant — see
  §12), orphaned temp-file reporting, and the two-step `--adopt-context-md`
  preview/confirm flow.
- §4's `confirm` command signature (removing the caller-supplied
  `--assigned-id`, since #184 allocates the anchor ID internally; adding
  `--input <proposal.json>` for edge acceptance, since an edge candidate's
  validated state does not otherwise survive between separate `propose` and
  `confirm` invocations — §10, §11) and the corrected single-writer lock
  participant list and owner-metadata `operation` enum (§4, §15 — `propose`
  removed from both; it was never authorized by #182/#191/#184 and is never
  shown writing anything).

One forward-looking item, explicitly out of scope for a go/no-go on
#191–#186:

- The `semantic_conflict` diagnostic (§11, two accepted edges expressing
  contradictory graph meaning — distinct from an illegal endpoint
  combination, which is never approvable) is informational only in v1.
  Whether a future version should surface it more prominently (e.g. a
  dedicated `status` section) is left to #186 graduation dogfood to surface
  as real usage experience, not speculated here.

---

## 20. Go / no-go conclusion

**GO for #191, #183, #184, #185, and #186.**

Both structural blockers the second audit identified are cleared (#191 exists
and owns initialization; every upstream body is consolidated, and this
document is the checked-in reconciled contract the audit required). Checking
against #182's own acceptance criteria:

- Every required design decision (§1 "Required design decisions" 1–15 in
  #182's body) is addressed above: command surface (§4), state ownership
  (§5), map parsing (§7), endpoint legality (§3 reuses #180's matrix; §11/§12
  freeze #182's six required checkpoints (proposal ingestion, candidate-key
  construction, confirmation, ledger reduction, compilation, apply) as five
  concrete mechanisms — validate-before-key-construction (covering both
  proposal ingestion and candidate-key construction with one gate),
  confirm-time revalidation, ledger-reduction revalidation, compilation, and
  apply's whole-state validation with abort-on-illegal-late — project
  identity/bindings (§6, reusing #191), compiler phases (§3),
  candidate-production authority (§3/§10),
  candidate/judgment lifecycle (§11), apply safety (§12), single-writer
  locking (§15), GitHub adapter (§9), projection bounds (§12),
  privacy/path enforcement (§14), provider-neutral adapter (§3), test
  matrix (§16).
- No authority or mutation boundary remains implicit — §3's table and §5's
  authority table are the two single sources of truth going forward.
- Direct script use is fully specified (§4) and does not depend on #186.
- The design reuses #179/#180/#181/#191 without redefinition (§2) and
  introduces no second Markdown grammar, no second evidence grammar, no
  second candidate-key algorithm.
- The complete seven-file v1 schema set has frozen locations (unchanged from
  #180 §3) and one identified, scoped amendment (§8), not a redefinition.
- The dependency sequence among children is acyclic (§18, matching #140's
  own dependency documentation).
- Failure and degraded-source behavior are complete (§13).
- #141 can now identify exactly which completed contracts it will consume:
  the file layout in §5, the CLI surface in §4, and `index.json`/`context.md`
  as its read surface once #185 ships — #141 remains out of this design's
  scope beyond that pointer.
- This design explicitly identifies what it corrects: #180's
  `design_document` enum value (§8), the `<project>` path ambiguity in
  #182's/#191's own bodies (§5), and — surfaced by this design's own
  adversarial review before merge — an earlier draft's single-writer-lock
  scope error and `confirm --assigned-id` authority inversion (§4, §15),
  neither of which ever matched #182/#191/#184's already-consistent frozen
  text.

The go decision authorizes implementation of **#191, #183, #184, #185, and
#186**, in that dependency order. It does not authorize skipping any of §16's
fixture/test obligations, and it does not authorize the §8 schema amendment
landing anywhere other than the #183 PR that first needs it.

---

## Appendix: required upstream amendments

1. **`schemas/context-graph/v1/node.schema.json`** and **`candidate.schema.json`**
   — replace `design_document` with `document_repository` and
   `document_project_local` in every `kind`/`source_kind`/`target_kind` enum
   (§8). Land in the #183 PR.
2. **`bin/context_graph/relationships.py`** — the same replacement in
   `EVIDENCE_KINDS` (line 19) and the `validation-evidence` node group (line
   44), both already shipped by #180 and both feeding `ENDPOINT_MATRIX` (§8)
   — without this, `validate_endpoint_pair` would reject the compiler's
   primary deterministic evidence edge (`supported_by`) the moment #181's
   already-shipped output reaches it. Land in the same PR as (1) — this is
   the amendment that makes (1) actually schema-*and-native* consistent,
   not a second independent change.
3. **Shipped test and fixture migration for (1)/(2)**, all already existing
   and all breaking unmigrated: `bin/context_graph/tests/test_relationships.py`'s
   `test_validated_by_learning_to_design_ok_question_to_issue_fails` (asserts
   `design_document` legal against `validation-evidence` — must be updated to
   assert against `document_repository`/`document_project_local` instead, or
   retired if superseded by a new #183-added fixture pair covering the same
   case); and five `expect_valid: true` fixtures under
   `testdata/context-graph/v1/` containing `design_document` nodes/edges —
   `documents/68-distinct-binding-qualified-documents.json`,
   `documents/69-project-local-document.json`,
   `identity-config/68-distinct-binding-qualified-documents.json`,
   `identity-config/69-project-local-document.json`, and
   `endpoint-matrix/47-1-validated-by-learning-to-design-document.json` —
   each must have its `design_document` kind(s) migrated to the correct
   `document_repository`/`document_project_local` value for that fixture's
   scenario (repository-bound vs. project-local), or the fixture must be
   retired if superseded by §16's already-required new
   `document_repository`/`document_project_local` fixture pair. Land in the
   same PR as (1)/(2) —
   `make check`/`make test` cannot stay green through that PR otherwise.
4. **`docs/design/2026-07-16-context-graph-schema.md`** §6 and
   **`docs/context-graph-schema.md`** (the shipped companion doc, line 56) —
   same enum correction, folded back per the design doc's own stated update
   rule. Land in the same PR as (1)/(2)/(3).
5. **`docs/session-notes-format.md`** and **`docs/notes-home.md`** — add
   `context.md` and `.bindle/context/{config.json,judgments.jsonl,
   index.json,.lock}` to the documented notes-home layout (§5, §17). Land in
   the #191 PR (first to create any of these paths).

`index.schema.json` requires no amendment: incomplete-apply detection (§12)
was redesigned during this document's own review to reuse the existing
single-writer lock's stale-owner-metadata signal (§15) rather than a new
schema field, after the original hash-field approach was found to produce
false positives on ordinary source edits.

`docs/superpowers/plans/2026-07-16-context-graph-schema-implementation.md`
(8 occurrences of `design_document`, verified by full-repo search alongside
every amendment above) is **deliberately excluded** from this list, not
missed: it is #180's already-executed, point-in-time implementation plan —
a historical record of what was built and why, not a live contract this or
any future document reconciles against (unlike `docs/context-graph-schema.md`
and the 2026-07-16 design doc, both still-live references item 4 corrects).
Amending it would misrepresent history rather than correct a contract.

No other upstream issue body (#140, #179, #180, #181, #182, #183, #184,
#185, #186, #191) requires a text change — the single-writer-lock scope
correction and owner-metadata `operation` enum fix (§4, §15), the `confirm
--assigned-id` removal, and the `confirm --input` addition for edge
acceptance (§4, §10, §11) fix errors and gaps in an earlier draft of this
design document itself; they never matched #182/#191/#184's
already-consistent frozen text, so no upstream body needs to change to
agree with the correction.
