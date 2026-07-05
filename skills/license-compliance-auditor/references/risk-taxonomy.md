# Risk taxonomy

The shared risk enum used by `risk_level` and `compatibility_risk` in
`output-schema.md`: `critical | high | medium | low | info`. Every finding gets
exactly one of these five levels. This file defines what each level means, how
to pick between them, and which situations deserve extra scrutiny before you
settle on a level. Levels describe **risk and likely obligation gaps with
evidence** — never a compliance verdict. See `human-review-boundaries.md` for
what must be escalated instead of decided.

## The five levels

### `critical`

The repo appears to be out of compliance in a way with real legal exposure, or
a license conflict looks irreconcilable on its face.

Examples:

- A copyleft dependency (GPL/AGPL) is bundled or statically linked into a
  product declared under a permissive or proprietary license, with no evidence
  of a compliance mechanism (no offer of source, no dual-license note, no
  isolation boundary).
- The repo's declared license and a dependency's license are directly
  incompatible for the way the dependency is actually used (e.g. an AGPL
  library embedded in closed-source, publicly-served code).
- A vendored file's license header contradicts the repo's declared license and
  the vendored code is compiled/bundled into the shipped artifact.

### `high`

A real obligation is very likely unmet, but there is some mitigating factor
(the linking model is ambiguous, the dependency is dev-only-but-not-clearly-so,
the missing artifact is one that's normally easy to add) or the exposure is
narrower than `critical`.

Examples:

- A copyleft/share-alike obligation is present but linking is dynamic only, or
  the dependency's role in distribution isn't fully confirmed by static
  analysis alone.
- A component that requires shipping its license text (Apache-2.0, MIT, BSD)
  is redistributed with no `LICENSE`/`NOTICE` file for it anywhere in the repo
  or build output.
- An OFL-licensed font is redistributed without its accompanying `OFL.txt`.
- A CC BY-NC asset appears in a repo that looks commercial or is publicly
  distributed.

### `medium`

An obligation gap exists and should be fixed, but the exposure is narrower or
more easily remediated — attribution/notice hygiene rather than a structural
conflict.

Examples:

- A permissively-licensed dependency (MIT/BSD/ISC) is used correctly but its
  copyright notice isn't preserved anywhere reachable (`NOTICE`, `THIRD_PARTY`,
  bundled comment header).
- A code snippet appears to be copied from an external source (e.g. a Stack
  Overflow answer) with no attribution or licensing note, and provenance can't
  be confirmed either way.
- A dataset's license is stated but redistribution/attribution terms aren't
  addressed anywhere in the repo that ships it.

### `low`

A minor, cosmetic gap in an obligation that is otherwise substantially met.

Examples:

- A `NOTICE` file exists and covers the dependency but is missing a
  non-essential detail (e.g. a copyright year, a URL fragment).
- License text is present but not in the most discoverable location (e.g.
  buried in a subdirectory rather than repo root or `THIRD_PARTY_NOTICES`).

### `info`

No obligation gap detected; the finding is informational — a baseline
confirmation, a coverage note, or a clean result worth recording for
completeness.

Examples:

- A dependency's declared license is compatible with the repo's declared
  license and all applicable obligations (attribution, notice, license text)
  are met with clear evidence.
- The repo-wide license baseline itself, recorded as a finding for
  traceability.

## Escalation rule: compatibility conflicts win

When a finding could plausibly be scored at different levels along different
axes — e.g. the obligation itself looks like a `medium` (missing notice) but
the license-compatibility angle looks like `critical` (the dependency's
copyleft terms conflict with the repo's declared license) — **take the
highest applicable severity.** `risk_level` is the finding's overall severity;
it must never be lower than `compatibility_risk` when compatibility risk is
the dominant concern.

## Be especially careful with these cases

These patterns come up often enough, and carry enough exposure, that they
deserve a deliberate second look before assigning a level — usually pushing
toward `high` or `critical` rather than defaulting to `medium`:

- **Permissive repo + copyleft dependency.** A repo declared MIT/BSD/Apache
  that depends on (especially bundles or statically links) a GPL/LGPL/AGPL
  component.
- **AGPL in a network service.** AGPL's source-disclosure trigger extends to
  network use, not just distribution — flag this distinctly from ordinary GPL
  even though the mechanism itself is a legal-review question, not one this
  tool decides.
- **LGPL statically linked or bundled.** LGPL's linking exception assumes
  dynamic linking with re-linking ability preserved; static linking or
  bundling into a single binary/bundle changes the obligation picture.
- **CC BY-SA / BY-NC / BY-ND assets.** Share-alike, non-commercial, and
  no-derivatives terms on images/audio/video/fonts are easy to miss because
  they travel with the asset file, not a manifest.
- **OFL fonts missing their license text, or with reserved-font-name (RFN)
  concerns.** Redistributing an OFL font without `OFL.txt`, or modifying and
  redistributing a font under an RFN without renaming it, are both common
  real-world gaps.
- **Datasets under ODbL / CDLA / CC-BY / NC / SA / bespoke terms.** Dataset
  licenses frequently layer attribution, share-alike, and non-commercial
  clauses together, and bespoke "research use only" or "personal use only"
  terms are common and easy to overlook.
