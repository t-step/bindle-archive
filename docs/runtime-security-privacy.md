# Runtime security & privacy contract

The contract for **executable and automatic Bindle assets** — anything the
kit installs that runs code, and especially anything that would run
*without a per-run human decision* (session hooks, background steps).
Resolves issue #30; per [product-boundary.md](product-boundary.md),
no automatic runtime behavior may ship before it complies with this doc.

How this relates to the neighboring contracts:

- [privacy-boundaries.md](privacy-boundaries.md) governs **tracked-file
  content** — what may land in Git. Its scanner cannot see runtime
  behavior.
- [ownership-boundaries.md](ownership-boundaries.md) governs **what may be
  touched at all** — owned symlinks, the notes home, never foreign files.
- This doc governs **runtime information flow**: what executes, when, what
  it reads, where its output goes, and how you turn it off.

## Capability classes

Every executable asset is classified by the most sensitive thing it does.
Higher classes need more explicit human involvement.

| Class | May do | Default rule |
|---|---|---|
| C0 read-only local diagnostics | stat/read files, report | may run automatically once documented |
| C1 local mutation of owned surfaces | write owned symlinks, notes home, temp dirs | allowed when documented; anything outside owned surfaces requires per-write confirmation |
| C2 repository mutation | commits, file edits in a repo | never automatic — always a human-initiated action |
| C3 transcript / note access | read session transcripts or note *contents* | never automatic; automatic assets may handle **paths, never contents** |
| C4 network access | any request leaving the machine | never by default; each use documented and approved (see below) |
| C5 external-system mutation | `gh` writes, pushes, publishes | never automatic; explicit per-action human approval |

The single C4 carve-out: read-only queries through a user-authenticated
local CLI (e.g. `gh issue list`) may appear in an automatic asset **only
if** its capability card names the exact command, nothing from the local
machine is sent beyond the query itself, and the asset degrades silently
when the tool is absent, unauthenticated, or offline.

## Capability cards (the shipping gate)

An asset that executes automatically cannot ship without a **capability
card** in its documentation. The card states:

- **trigger** — the exact event (e.g. Claude Code `SessionStart:startup`);
- **inputs** — every piece of information it receives or reads;
- **outputs** — what it emits or writes;
- **storage** — where outputs live (must be an owned surface);
- **retention** — how long outputs persist and who deletes them (plain
  user-owned files; no hidden rotation);
- **failure behavior** — must degrade to the manual workflow, never block
  or corrupt a session;
- **disable / uninstall** — the exact command or edit that turns it off;
- **confirmation** — which of its actions, if any, require per-run
  approval;
- **capability class(es)** from the table above.

No card, no ship. A review of the card is part of the PR that introduces
the asset. (If the capability inventory of issue #29 is adopted, these
fields join its schema; until then the card lives in the asset's doc.)

## Current inventory (2026-07-10)

**Automatic assets: none.** Bindle today ships nothing that runs without a
human starting it. When issue #21 (session hooks) lands, its assets get
the first cards.

Executable-on-request assets, classified:

| Asset | Class | Notes |
|---|---|---|
| `bin/doctor.sh` | C0 | zero writes by design |
| `bin/check.sh`, `bin/check-private-info.sh`, `bin/slugify.sh` | C0 | read/report only (self-tests use temp files) |
| `bin/test-install.sh`, `bin/test-check.sh`, `bin/test-check-frontmatter.sh`, `bin/test-doctor.sh` | C1 | temp fixtures only; never the real environment |
| `bin/install.sh` | C1 | owned symlinks only, per ownership-boundaries |
| `bin/new.sh` | C2 | repo-local scaffolding writes, human-invoked |
| `bin/release-provenance.py` | C1 | reads tagged state and caller evidence; generation writes only caller-selected local assets outside the repo and never mutates Git/GitHub |
| `bin/release-publication.py` | C1/C4/C5 | C1: identity-pinned external temp evidence/upload/download files, removed before final publish; C4: `gh` release view/upload/download traffic; C5: draft creation, asset replacement, and final publication. It never reads transcripts or note contents, so C3 does not apply. The tagged-release workflow is the explicit publication trigger; every pre-publish failure leaves the release unpublished (and any created release as a draft), and the C5 publish edit is the final process replacement after verified cleanup. |
| `bin/notes-home.sh` | C1 | `status` is read-only; `set`/`migrate`/`reset` preview by default and write only on explicit confirmation (`--apply`/TTY yes). Its `~/.claude/settings.json` writes follow rule 7 below verbatim — validate, back up, touch only `env.BINDLE_NOTES_DIR`, show the diff — even though it is not a hook |
| `/session-*`, `/handoff`, `/project-profile`, `/workflow-review`, `/promote-insight`, `/notes-home` commands | C1/C3 | human-invoked; write to the notes home; note *contents* stay out of repos per privacy-boundaries |

Skills and commands are instructions interpreted by the provider, not
programs Bindle executes — but when they direct the agent to run one of
the scripts above, that script's class applies.

## Rules for hooks (the issue #21 gate)

1. **Opt-in only.** Hook installation is its own explicit command — never
   part of default `bin/install.sh`. Installing Bindle must never silently
   add automatic behavior.
2. **Pointers, not payloads.** A hook may pass *paths* to notes, handoffs,
   or transcripts; it must never inject or copy their *contents*. Reading
   contents is the in-session agent's decision, visible to the user.
3. **Transcripts are off-limits.** Even where the provider hands a hook a
   transcript path, Bindle hooks do not open it. Any future exception
   needs its own card naming exactly what is read and why, and remains
   opt-in.
4. **No network, with the C4 carve-out above** (documented, read-only,
   authenticated-CLI queries that fail silent).
5. **Fail open, quietly.** A hook that errors must leave the session fully
   usable and the manual workflow intact — a broken hook may cost the
   convenience, never the session.
6. **Inspectable.** Where the provider stores hook config (Claude Code:
   the `hooks` block of `~/.claude/settings.json`), the installing command
   must show the exact change before making it, and the uninstall path
   must remove exactly that change. `bin/doctor.sh` grows a hooks section
   when hooks exist, so inspection never requires reading provider config
   by hand.
7. **Settings writes are surgical.** Provider settings files are foreign
   territory per ownership-boundaries: back up first, touch only the keys
   named in the card, show a diff, require confirmation.

## Auditing and disabling automatic behavior

- **Inspect:** every automatic asset is listed in this doc's inventory and
  reported by `bin/doctor.sh` (once any exist). If it isn't in both
  places, it's a bug — file it.
- **Disable one asset:** follow its card's disable line (one command or
  one settings edit — cards may not require multi-step teardowns).
- **Disable everything:** removing Bindle's hook entries from the provider
  settings plus `bin/install.sh --prune` must return the machine to
  fully-manual operation with no residue beyond user-owned notes.

## Non-goals

- Securing the underlying model provider: what Claude Code or any
  assistant does with context it already has is governed by that product,
  not by Bindle.
- Formal security certification or sandboxing — this is a personal kit's
  written discipline, enforced by review and tests, not a security
  boundary against a hostile actor.
