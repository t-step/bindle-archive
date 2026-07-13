# Delegation profiles

The provider-neutral ladder for **what a delegated worker is authorized to
do**, independent of which model or provider executes it. Resolves issue
[#32](https://github.com/thomas-estep/bindle/issues/32).

Delegation decisions get described in terms of specific model names or
informal strength labels ("use the strong one for this"). Names and relative
capability change; the same model may be safe for one bounded task and unsafe
for another. This contract fixes the vocabulary a workflow, packet, or human
uses to grant authority — **Mechanical, Review, Research, Implementation,
Privileged** — so that vocabulary outlives any particular provider's model
lineup.

This is **not** a model-selection tool, a routing policy, or an evaluation
harness. Choosing which concrete worker satisfies a profile stays a human (or
provider-config) decision, per
[product-boundary.md](product-boundary.md)'s non-goal 2 (no autonomous model
routing) and non-goal 4 (no standalone evaluation platform). It deliberately
references, rather than restates, the neighboring contracts:

- **What executes, when, and where its output may go** is the
  [runtime security & privacy contract](runtime-security-privacy.md). Its
  capability classes (C0–C5) describe *assets*; this doc's mutation columns
  below describe *worker authority* using the same class vocabulary so the
  two line up without duplicating each other.
- **How a bounded unit of delegated work is specified** is the
  [delegated implementation packets](delegated-implementation-packets.md)
  contract. A packet *names* a profile from this doc in its authority
  section; it does not define the ladder.
- **Which workflows apply and how they compose** is issue #31's forthcoming
  composition and precedence contract — out of scope here.

## Two governing rules

1. **Authority is granted by profile, never inferred from capability.** A
   worker's underlying model, tooling, or credentials may exceed what a
   profile permits; the profile is the ceiling regardless. A worker operating
   under Mechanical has exactly Mechanical's authority even if it is also
   configured with push access.
2. **A sub-delegated worker's authority is the intersection of its own
   profile and everything its parent task explicitly granted — never wider
   than either.** A parent may hand a narrower scope to a child than its own
   profile would otherwise allow (e.g. an Implementation-profile task
   spawning a Review-only sub-check); the child may not claim back authority
   the parent didn't pass down, and a profile can only narrow what a task
   inherits, never widen it.
3. **Privileged authority is never inferred from Implementation authority.**
   A worker trusted to edit and commit within a branch is not thereby trusted
   to merge, release, publish, or mutate an external system. Each Privileged
   action requires its own explicit grant naming that exact action — see
   [runtime security & privacy contract](runtime-security-privacy.md)'s C5
   class and rule 2 of the packet contract ("a packet grants no mutation
   authority it does not explicitly state").

## The five profiles

| Profile | Repository mutation | External mutation | Maps to runtime-security-privacy.md class |
|---|---|---|---|
| Mechanical | yes, within an explicit bounded file scope | no | C2, scope-limited |
| Review | no | no | C0/C1 (read-only) |
| Research | no | no (the C4 read-only-CLI carve-out only, if documented) | C0/C1, conditional C4 |
| Implementation | yes, within the branch | conditional — push/PR-open only if explicitly granted | C2, conditional C5 |
| Privileged | as granted | yes | C5 |

### Mechanical

- **Permitted:** bounded edits within an explicitly named file scope; running
  the stated deterministic validation command; reporting its actual result.
- **Prohibited:** any edit outside the named scope; product, architecture, or
  design decisions; inventing verification criteria not already specified.
- **Required inputs & inherited constraints:** an explicit file scope
  (paths or glob), a deterministic verification command with its expected
  result, and the parent task's "do not change" list, inherited verbatim.
- **Required verification/evidence:** the verification command's real
  output — pass or fail — never a narrated summary.
- **Escalation/stop conditions:** verification fails and the fix requires
  judgment beyond the named scope or command — stop and hand back to
  Implementation or a human rather than improvising a fix.

### Review

- **Permitted:** reading the artifact or diff under review; critiquing it
  against named standards (contracts, acceptance criteria, prior decisions).
- **Prohibited:** any write to a tracked file; a finding that doesn't cite
  concrete repository evidence (file, line, or command output).
- **Required inputs & inherited constraints:** the artifact/diff to review
  and the standard it's judged against; the parent task's scope, so a review
  doesn't wander into unrelated files.
- **Required verification/evidence:** every finding traceable to a specific
  file:line or reproducible command output.
- **Escalation/stop conditions:** the review concludes the object under
  review needs redesign, not a fix — stop and report to the human/owner
  rather than silently expanding into Implementation.

### Research

- **Permitted:** gathering evidence and alternatives; reading repository
  history, docs, and (where a runtime-security-privacy.md C4 carve-out
  documents it) read-only authenticated-CLI queries; producing a written
  analysis.
- **Prohibited:** implementation edits; any external mutation; presenting
  inference as fact.
- **Required inputs & inherited constraints:** the question or decision the
  research supports, and which prior decisions are already settled (e.g.
  product-boundary.md), so research doesn't silently relitigate them.
- **Required verification/evidence:** fact and inference labeled distinctly;
  sources cited.
- **Escalation/stop conditions:** the research surfaces that a settled
  decision is actually wrong — stop and report; revising the decision is
  separate work, not something Research authority may act on directly.

### Implementation

- **Permitted:** branch-scoped repository edits per an approved packet;
  running its verification commands; opening or updating a PR **only** if
  the packet's external mutation authority explicitly grants it.
- **Prohibited:** merging, releasing, publishing, or mutating any external
  system; pushing or opening a PR without an explicit grant; touching
  anything in the packet's "do not change" section.
- **Required inputs & inherited constraints:** an approved packet or issue
  with a bounded objective, expected artifacts, a "do not change" list, and
  verification commands — see
  [delegated implementation packets](delegated-implementation-packets.md).
- **Required verification/evidence:** verification commands actually run
  with real output; the diff confined to the expected artifacts.
- **Escalation/stop conditions:** a failed preflight, scope growing beyond
  the bounded objective, or behavior that can't be verified — stop and
  report per the packet contract's stop-conditions section.

### Privileged

- **Permitted:** merge, release, deploy, publish, or external-system
  mutation — exactly, and only, the action explicitly authorized.
- **Prohibited:** exercising any such action on inferred trust ("I have
  implementation access, so I can merge"); acting on a stale or
  differently-scoped prior approval.
- **Required inputs & inherited constraints:** explicit user authorization
  naming the exact action, plus everything a lower profile already verified
  (tests, diff review) for the same change.
- **Required verification/evidence:** the same rule the packet contract
  states for closeout: repository and remote state, not narration — plus a
  record of what was authorized and by whom.
- **Escalation/stop conditions:** the authorization is ambiguous, stale, or
  scoped differently from the action about to be taken — stop and
  reconfirm rather than proceeding on a prior approval.

## Requesting a profile without naming a model

A workflow, packet, or human requests a profile by naming it in prose —
for example, a delegated-implementation-packet's authority section stating
"Profile: Implementation" — never by specifying a model, provider, or agent
tier. Choosing the concrete worker that satisfies a named profile is left to
whoever dispatches the task, using whatever criteria their provider makes
available; this contract defines only what that worker is authorized to do
once dispatched, and every delegated task carries both its own profile and
whatever constraints it inherited from its parent (rule 2 above).

## Examples

### 1. A weaker worker safely handling a bounded, mechanically verified task

A file-scoped edit across a known set of skill directories, verified by a
deterministic script, is Mechanical: the scope is explicit and the pass/fail
condition doesn't require judgment. The #87 knowledge-promotion pressure-test
campaign ran 48 such reps on a mid-tier Claude model, scored only against the
filesystem, and passed at the stated rep counts — evidence that a
comparatively weaker worker is safe here precisely because the profile
bounds the blast radius, not because the worker is unusually capable. This is
the interim decision record product-boundary.md's backlog triage names for
issue #39: recorded evidence, not new routing infrastructure.

### 2. Implementation authority does not imply merge or release authority

The worked example in
[delegated implementation packets](delegated-implementation-packets.md#worked-example)
(issue #71) grants an Implementation-profile worker commit and PR-open
authority but explicitly withholds issue-close and self-merge — "Issue left
open for the owner to merge/close." The worker implemented, tested, and
opened PR #72; merging it remained a Privileged action the packet never
granted, per governing rule 3 above.

### 3. A delegated worker inherits its parent task's constraints

`/promote-knowledge` (Research-shaped: it gathers and digests project
evidence) can spawn a nested `knowledge-scout` subagent to do the same
digesting. The scout inherits the parent's project scope and its
read-only ceiling — it may read candidate evidence but not write to the
project's map — even though the underlying model is capable of writes. Per
governing rule 2, the sub-task's authority is the intersection of its own
(Review-shaped, read-only) profile and what the parent passed down, never
wider than either.

## Provider mapping (illustrative, non-normative)

This contract names no commercial model and ranks none against another. A
provider's own configuration is where a profile gets mapped onto a concrete
model or agent tier, and that mapping is provider-owned, out of scope here,
and expected to change as providers evolve:

- **Claude Code:** a subagent's `model:` frontmatter field (see
  `agents/_template.md`) is where a Claude-native workflow would record a
  profile-to-model choice; Bindle does not prescribe values.
- **Cross-model evidence on file:** the #87 campaign (Example 1 above) is the
  one recorded data point — a specific Claude tier passed a Mechanical/
  Research-shaped task at stated rep counts. It documents what has been
  pressure-tested for that task shape, not a general ranking of one model
  against another.

## Where this fits

- [delegated-implementation-packets.md](delegated-implementation-packets.md)
  is the packet contract that names a profile per task; this doc is what
  that name means.
- [runtime-security-privacy.md](runtime-security-privacy.md) classifies what
  executes and its capability class; this doc classifies who's authorized to
  direct it, using the same class vocabulary for mutation.
- [product-boundary.md](product-boundary.md) is why this stays documentation:
  non-goal 2 (no autonomous routing) and non-goal 4 (no eval platform) bound
  this contract to a decision record, not automation.
