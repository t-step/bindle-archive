# Obligation checklist

Per-obligation checklist used to fill `unmet_obligation`, `evidence`, and
`review_notes` on findings. For each obligation: what to check, what evidence
would demonstrate it's met, and how to phrase a gap as a **risk finding**, not
a legal conclusion. Every "how to phrase it" line below is a template for
`unmet_obligation` / `review_notes` text — keep that framing (likely, appears
to, may) rather than asserting non-compliance as fact.

## Attribution

- **Check:** does anything that's redistributed under a license requiring
  attribution (MIT, BSD, Apache-2.0, most CC-BY variants, many font/asset
  licenses) carry the required credit somewhere reachable by an end user or
  downstream developer?
- **Evidence it's met:** a `NOTICE`/`THIRD_PARTY_NOTICES`/credits file, an
  in-app "about"/credits screen, or a source comment header naming the
  original author, matched to the specific component.
- **Phrase the gap as risk:** "Attribution for `<component>` (`<license>`)
  was not found in any reachable location; this is likely an unmet
  attribution obligation."

## NOTICE completeness

- **Check:** for Apache-2.0 (and similar) dependencies, does the repo's own
  `NOTICE` file (if one exists) include the upstream `NOTICE` content it's
  required to propagate, not just a blank placeholder?
- **Evidence it's met:** the repo's `NOTICE` file contains an entry that
  matches the upstream dependency's own `NOTICE` file content.
- **Phrase the gap as risk:** "The repo has a `NOTICE` file but it does not
  appear to include `<dependency>`'s upstream notice content; the NOTICE
  propagation obligation looks unmet for this dependency."

## License-text inclusion

- **Check:** for each redistributed component whose license requires shipping
  the license text (nearly all common OSS licenses do), is that text present
  somewhere in the repo or build output — not just referenced by name?
- **Evidence it's met:** a copy of the license text under `licenses/`,
  `THIRD_PARTY_LICENSES`, or bundled with the vendored component itself.
- **Phrase the gap as risk:** "No copy of the `<license>` text for
  `<component>` was found in the repo; shipping only the license name/SPDX id
  without the text is likely an unmet inclusion obligation."

## Copyright-notice preservation

- **Check:** where a vendored/copied file retains its original copyright
  header, has that header been preserved rather than stripped or overwritten?
- **Evidence it's met:** the original copyright line is intact in the file, or
  reproduced in an accompanying `LICENSE`/`NOTICE` alongside the vendored code.
- **Phrase the gap as risk:** "`<path>` appears to be vendored from
  `<source>` but no longer carries its original copyright notice; this is
  likely a preservation gap."

## Source-disclosure (copyleft, GPL family)

- **Check:** for a GPL-family dependency, is there a mechanism to obtain
  corresponding source for the combined/derivative work (a public repo,
  written offer, or the dependency itself is clearly isolated/unmodified and
  distributed only in source form)?
- **Evidence it's met:** the combined work's own source is public, or a
  written-offer mechanism is documented, or the dependency is only used at
  build/dev time and never distributed.
- **Phrase the gap as risk:** "`<dependency>` (`<license>`) is
  `<bundled/statically linked>` into the distributed artifact with no
  apparent source-disclosure mechanism; source-disclosure looks likely
  triggered and unmet. Whether it is legally triggered is a human/legal-review
  determination — see `human-review-boundaries.md`."

## Copyleft / share-alike (general)

- **Check:** for any share-alike license (GPL family, CC BY-SA, ODbL), is the
  combined/derivative work distributed under a compatible (often
  same-or-compatible) license as required?
- **Evidence it's met:** the repo's declared license matches or is documented
  as compatible with the share-alike requirement, or the component is kept
  clearly separate/unmodified.
- **Phrase the gap as risk:** "`<component>`'s share-alike terms may require
  `<work>` to be licensed under compatible terms; the repo currently declares
  `<repo license>`, which may not satisfy that — flagged for review, not
  decided here."

## LGPL linking

- **Check:** for an LGPL dependency, is it dynamically linked with the
  ability for an end user to relink a modified version, as the LGPL's
  linking exception assumes — or is it statically linked/bundled into a
  single artifact?
- **Evidence it's met:** dynamic linking is used and swap/relink instructions
  or object files are available, or the dependency is unmodified and
  dynamically loaded.
- **Phrase the gap as risk:** "`<dependency>` (LGPL) appears to be statically
  linked or bundled rather than dynamically linked; this may fall outside the
  LGPL's linking exception. Whether this triggers full obligations is a
  human/legal-review question."

## AGPL network-interaction

- **Check:** is an AGPL-licensed component run as part of a network-accessible
  service (not just distributed as a binary)?
- **Evidence it's met:** the service's own source (matching the running
  version) is offered to users interacting with it over the network.
- **Phrase the gap as risk:** "`<component>` (AGPL) appears to be part of a
  network-accessible service with no apparent offer of corresponding source to
  users of that service; AGPL's network-use trigger may apply. This is a
  human/legal-review determination, not one this tool makes."

## Apache-2.0 patent grant / retaliation

- **Check:** does the repo (or its dependents) engage in patent litigation
  against contributors in a way that could trigger Apache-2.0's patent
  retaliation clause, and is the patent grant itself preserved when
  redistributing?
- **Evidence it's met:** no evidence of patent litigation referenced in repo
  docs/issues, and the Apache-2.0 `LICENSE` text (which carries the patent
  grant) is preserved on redistribution.
- **Phrase the gap as risk:** "No direct evidence found either way; patent
  retaliation/grant questions for `<component>` are flagged for human/legal
  review rather than assessed here — this tool does not evaluate litigation
  posture."

## Trademark / brand limits

- **Check:** does the repo use a project's name, logo, or brand assets in a
  way that goes beyond nominative/referential use (e.g. implying endorsement,
  using a modified logo, using the name in the repo's/product's own branding)?
- **Evidence it's met:** brand assets are absent, or usage is limited to
  unmodified factual reference (e.g. "built with X").
- **Phrase the gap as risk:** "`<name/logo>` usage in `<path>` goes beyond
  simple reference and may exceed the trademark policy's permitted use;
  flagged for human/legal or brand-owner review — trademark scope is never
  decided by this tool."

## CLA / DCO

- **Check:** does the project require a Contributor License Agreement or
  Developer Certificate of Origin, and if so, is there evidence contributions
  comply (a CLA bot, `Signed-off-by` trailers, a `CONTRIBUTING.md` policy)?
- **Evidence it's met:** a documented CLA/DCO process exists and is applied
  (bot check, commit trailers) with no visible gaps.
- **Phrase the gap as risk:** "The repo references a CLA/DCO requirement in
  `<path>` but no enforcement evidence (bot check, `Signed-off-by` trailers)
  was found; flagged as a process gap, not a compliance verdict on any
  specific contribution."

## Dataset provenance / redistribution

- **Check:** for any bundled dataset, is its license/terms documented, and do
  the repo's actual use and redistribution match what those terms allow
  (attribution, share-alike, non-commercial, no-redistribution clauses)?
- **Evidence it's met:** a dataset `LICENSE`/`README`/data-card documents the
  terms, and the repo's usage (internal-only vs. redistributed, commercial vs.
  non-commercial) is consistent with them.
- **Phrase the gap as risk:** "`<dataset>` at `<path>` has `<no documented
  license / ODbL / CDLA / CC-BY-NC / bespoke terms>`; usage in this repo
  `<appears to redistribute / appears commercial>`, which may not align with
  those terms. Confirming the specific dataset terms and repo usage is a
  human-review item, not one this tool resolves."
