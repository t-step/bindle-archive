# Font license cheatsheet

Fonts are a common blind spot: they travel as binary files
(`.ttf`/`.otf`/`.woff`/`.woff2`) with no manifest entry, so obligations are
easy to miss. This file covers the license families most likely to appear and
what to flag when evidence is incomplete.

## SIL Open Font License (OFL)

The most common license for free/libre fonts (Google Fonts, most of the
"webfont" ecosystem).

- **Reserved Font Name (RFN):** the OFL lets an author reserve the font's
  name. If the font is modified and redistributed under a Reserved Font Name
  without renaming it, that's a real gap — the OFL requires renaming modified
  versions that carry an RFN.
- **License text must travel with redistribution.** Redistributing the font
  file(s) — bundled in a repo, shipped in an app, included in a build —
  requires including the `OFL.txt` (or `OFL-FAQ.txt`) alongside it. A font
  file with no accompanying license text anywhere in the repo is a gap.
- **Web-embed vs. redistribution:** loading a font at runtime from a
  third-party CDN (e.g. Google Fonts' own hosted URL) is a different situation
  from vendoring the font file into the repo/build. Vendored files trigger the
  license-text-inclusion obligation directly; CDN-loaded fonts still likely
  need attribution/credit per the font's own terms but don't carry a copy of
  the font file into the repo.

## Apache-2.0 / MIT-licensed fonts

Some font families (e.g. certain corporate/brand typefaces) ship under
Apache-2.0 or MIT instead of OFL. Treat these like any other Apache-2.0/MIT
dependency: license text inclusion and copyright-notice preservation apply;
there's no RFN concept, but check for a `NOTICE` file if Apache-2.0.

## Proprietary / commercial fonts

- **Per-seat / per-developer licensing:** many commercial foundries license
  fonts per designer/seat, not per project or per deployment. A font file
  vendored into a repo with no accompanying license/purchase record is a
  strong signal of unclear licensing scope — flag it, don't assume it's fine
  because it's "just used internally."
- **Web-embed limits:** commercial desktop-font licenses frequently exclude
  `@font-face` web embedding entirely, or require a separate web license
  (with its own pageview/domain limits). A commercial font file referenced
  from CSS/`@font-face` with no evidence of a web-license purchase is worth
  flagging distinctly from desktop-only use.
- **No visible license/purchase evidence:** if a commercial-looking font
  (named, polished, not on any known free-font list) has no license file,
  purchase record, or vendor documentation in the repo, record it as unclear
  provenance rather than guessing the terms.

## Icon fonts

Icon fonts (e.g. bundled glyph sets built from Font Awesome, Material Icons,
or a custom icon set compiled into a webfont) mix two things that can have
different licenses: the font-building process and the individual glyphs. A
generated icon font can be OFL for the font wrapper while individual icons
were sourced under different (sometimes incompatible or unknown) terms.
Ambiguity here is common and should be flagged as such rather than resolved by
guessing — note both possible layers of licensing when the source of
individual glyphs isn't documented.

## Detection cues

Look for these signals when inventorying fonts:

- `@font-face` blocks in CSS/SCSS — check the `src` URL/path: vendored file
  (`./fonts/...`) vs. third-party host.
- `fonts.googleapis.com` / `fonts.gstatic.com` URLs — Google Fonts, almost
  always OFL or Apache-2.0 per-family; confirm which family and whether it's
  vendored or CDN-loaded.
- `use.typekit.net` / Adobe Fonts embed snippets — commercial, subscription
  and domain-scoped; flag if the project/domain scope looks stale or unclear.
- `@fontsource/*` npm packages — these repackage Google Fonts (and others)
  for self-hosting; check `package.json` for the specific package name to
  identify the underlying font family and its license (usually OFL, bundled
  by `@fontsource` itself under MIT for the packaging code).
- `next/font/google` or `next/font/local` imports — `next/font/google` pulls
  Google Fonts at build time (same licensing as above, self-hosted output);
  `next/font/local` points at a vendored font file in the repo — treat exactly
  like any other vendored font file above.

## What to flag

- Missing license text for a redistributed/vendored font (OFL, Apache-2.0, or
  commercial license documentation).
- Unclear source: a font file present with no name-to-license mapping
  possible (no metadata, no accompanying license, generic filename).
- RFN modification: a font that appears modified (custom name/weight
  suffixes, edited glyphs) but still carries what looks like a reserved font
  name without renaming.
- Icon-font ambiguity: a compiled icon font with no documentation of
  individual glyph sources/licenses.
