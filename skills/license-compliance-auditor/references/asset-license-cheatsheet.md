# Asset license cheatsheet

Covers images, audio, video, icons, and similar non-code assets. Like fonts,
these travel as binary files with no manifest entry, so licensing terms
usually live in a sidecar file, a README credit line, or nowhere at all.

**Core rule: public web availability is not redistribution permission.** An
asset being easy to find, screenshot, or right-click-save does not mean it's
licensed for reuse. Absence of a visible license/copyright notice on a found
asset is itself a finding (unclear provenance), not evidence that it's free
to use.

## Creative Commons family

| License | What it typically requires | Common gap |
| --- | --- | --- |
| CC0 | Nothing — public-domain dedication | Rare to get wrong, but confirm it's actually CC0 and not just "free to use" marketing copy |
| CC BY | Attribution (author, title, source, license link — "TASL") | Attribution missing or incomplete (e.g. no license link) |
| CC BY-SA | Attribution + share-alike (derivatives must carry the same license) | Derivative/adapted asset not re-licensed as BY-SA; attribution missing |
| CC BY-NC | Attribution + non-commercial use only | Used in a commercial product or a repo that is itself commercial/monetized |
| CC BY-NC-SA | Attribution + non-commercial + share-alike | Any of the above three gaps, often stacked |
| CC BY-ND | Attribution + no derivatives (must be used unmodified) | Asset appears cropped/edited/recolored from the original |

## Other data/asset-oriented licenses

- **ODbL (Open Database License):** attribution + share-alike, specific to
  databases/datasets (e.g. OpenStreetMap-derived data). A derived or extracted
  database under ODbL must itself be offered under ODbL, and attribution to
  the source must be preserved.
- **CDLA (Community Data License Agreement — Sharing or Permissive):**
  CDLA-Sharing behaves like a share-alike obligation for the dataset itself;
  CDLA-Permissive has fewer obligations but attribution/notice terms still
  apply per the specific version.
- **Public domain / CC0:** confirm the claim rather than accept it at face
  value — "public domain" claims for images (especially ones sourced from
  stock sites) are sometimes marketing language rather than an actual
  dedication.

## Bespoke and informal terms

Frequently seen in the wild, rarely backed by a real license:

- **"Free for personal use"** — near-universally excludes commercial and
  often excludes any public-distribution use; flag any such asset found in a
  repo that looks commercial or is publicly distributed.
- **"Non-commercial only"** — same NC concern as CC BY-NC above, but without
  a formal license to anchor the interpretation to.
- **Site-specific terms of service** (e.g. a stock-photo site's own ToS
  rather than a named open license) — these vary widely (some allow
  commercial use with attribution, some require a paid license, some forbid
  redistribution of the raw file entirely) and can't be assumed from the file
  alone; flag as unclear-provenance if the specific source/terms aren't
  documented in the repo.

## Priorities — what to flag first

In rough order of how often these turn into real problems:

1. **Missing attribution** where the license requires it (any CC-BY variant,
   ODbL, many bespoke terms).
2. **NC (non-commercial) terms in a repo that looks commercial or is publicly
   distributed** — one of the highest-frequency real gaps.
3. **Share-alike terms** (CC BY-SA, ODbL, CDLA-Sharing) not carried forward to
   the derivative work/dataset.
4. **No-derivatives terms** (CC BY-ND) on an asset that appears modified.
5. **Unclear source** — an asset with no accompanying license, credit, or
   provenance information at all.
6. **Trademark/brand limits** — logos, mascots, or brand marks used beyond
   simple factual reference.
7. **Missing license text or source URL** — even permissive terms (CC BY,
   CC0) benefit from a recorded source URL for future verification; its
   absence makes the finding harder to later confirm as compliant.
8. **Copied assets with no provenance record at all** — no filename hint, no
   credits file entry, no commit message context; the highest-uncertainty
   case, worth calling out explicitly as "provenance unknown" rather than
   silently treating as low-risk.
