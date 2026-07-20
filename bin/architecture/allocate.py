"""architecture.allocate — mint identity for candidates the matcher could
not continue (issue #374, epic #141).

`matcher.match` reports `outcome="mint", arch_id=None` and allocates
nothing by design: it runs during preview, and an identity minted there
would be one nobody confirmed. `apply()` requires `identities[key]
["arch_id"]`, and the planner requires a kebab-case `slug` to place the
note. This module is the only thing that produces either.

TWO HALVES, ONLY ONE OF THEM FREE.

The hex enters no fingerprint term — `planner.FINGERPRINT_TERMS` is
("bindings", "candidates", "config", "manifest", "provider") — so it may be
random, mirroring `context_graph.review`'s `secrets.token_hex(16)`. The
SLUG IS NOT FREE: `manifest` is the list of planned `note_path`s and a note
path derives from the slug, so a slug that differed between preview and
apply would abort every first-ever projection as `stale_preview`.
Derivation is therefore a pure function of the candidate's name.

Two candidates deriving one slug would claim one note path, and nothing
downstream dedupes `note_path`. That is refused here, naming both
candidates, rather than disambiguated with a suffix: a suffix is a silent
rename that moves a note path on an unrelated edit. The refusal is
provisional in the sense that no repository has yet hit it; the reason it
is a refusal and not a suffix is above.

THE ALLOCATION RECORD IS THE CREATION EVENT, so it carries everything a
later run needs to CONTINUE the identity rather than mint a second one --
the slug, the projection type, and the matcher's scoring signals. See
`_payload`. The record shape is additive: `judgment.schema.json` declares
`payload` an open object and requires only `arch_id` on an
identity_allocation, so records written before this slice stay valid and
simply continue to be unplaceable and unscoreable.
"""
import re
import secrets

from architecture import ids
from architecture import state

_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


class SlugError(ValueError):
    """A name no legal kebab-case slug can be derived from."""


class SlugCollisionError(ValueError):
    """Two candidates derived the same slug, so they would claim the same
    note path. `.slug` and `.candidate_keys` carry structured detail."""

    def __init__(self, slug, candidate_keys):
        keys = sorted(set(candidate_keys))
        super().__init__(
            "slug collision %r: %s -- rename one upstream, or map it "
            "explicitly" % (slug, ", ".join(keys)))
        self.slug = slug
        self.candidate_keys = keys


def derive_slug(name):
    """Derive the creation-event slug from a candidate's display name.

    Pure and deterministic: the same name always yields the same slug, which
    is what keeps a preview fingerprint valid at apply. Raises SlugError
    when no legal slug survives."""
    if not isinstance(name, str):
        raise SlugError("name must be a string: %r" % (name,))
    slug = _SEPARATOR_RE.sub("-", name.lower()).strip("-")
    if not state._NOTE_SLUG_RE.match(slug or ""):
        raise SlugError("no kebab-case slug can be derived from %r" % (name,))
    return slug


def allocate(project_id, candidates, decided_at, mint_hex=None):
    """Mint an identity for each candidate. Returns

        {"identities": {candidate_key: {"arch_id", "slug"}},
         "records":    [identity_allocation, ...]}   ordered by candidate_key

    ready to hand to `apply()` as `identities` and `identity_records`. The
    records are unstamped — `judgments.append_judgment` supplies `record_id`
    and `checksum`.

    Every slug is derived and checked for collision BEFORE the first hex is
    minted, so a refused batch allocates nothing at all."""
    mint = mint_hex if mint_hex is not None else _random_hex

    slugs = {}
    by_slug = {}
    for candidate in candidates:
        key = candidate["candidate_key"]
        slug = derive_slug(candidate["name"])
        slugs[key] = slug
        # A repeated candidate_key lands here twice and is refused by the
        # collision check below: two candidates, one note path.
        by_slug.setdefault(slug, []).append(key)

    for slug, keys in sorted(by_slug.items()):
        if len(keys) > 1:
            raise SlugCollisionError(slug, sorted(keys))

    by_key = {candidate["candidate_key"]: candidate
              for candidate in candidates}
    identities = {}
    records = []
    for key in sorted(slugs):
        arch_id = ids.format_arch_node_id(project_id, mint())
        identities[key] = {"arch_id": arch_id, "slug": slugs[key]}
        records.append({
            "schema_version": state.SCHEMA_VERSION,
            "kind": "identity_allocation",
            "project_id": project_id,
            "decided_at": decided_at,
            "arch_id": arch_id,
            "payload": _payload(key, slugs[key], by_key[key]),
        })
    return {"identities": identities, "records": records}


def _payload(candidate_key, slug, candidate):
    """The creation event, recorded so the LOG ALONE can continue it.

    #228 makes the log the sole authority for meaning, and two later
    readers take it at its word:

    * `matcher.identity_signals` scores a candidate against the signals in
      an identity's own records and reads nothing from the projection
      state. An allocation carrying no signals scores zero against every
      candidate, so the next run reports `mint` and allocates a SECOND
      identity for code that already has one.
    * `planner._note_path` places a reuse from a path the identity carries.
      A reuse supplies no slug -- its creation event was an earlier run --
      and index.json was the only record of that path, so a crash between
      this append and the index write stranded the identity permanently
      (#374's unplaceable-reuse question).

    `slug` and `projection_type` together re-derive the creation-event
    path EXACTLY, through the same `state.format_note_path` that produced
    it -- as opposed to re-deriving the slug from the candidate's current
    name, which a rename would silently move.

    Every signal is sorted: the payload is content-digested into
    `record_id`, so an unordered set would give one decision two identities.
    """
    payload = {"candidate_key": candidate_key, "slug": slug}
    projection_type = candidate.get("projection_type")
    if projection_type:
        payload["projection_type"] = projection_type
    for field in ("source_paths", "symbol_names", "neighborhood"):
        payload[field] = sorted(candidate.get(field) or ())
    return payload


def _random_hex():
    """32 lowercase hex chars, mirroring context_graph's allocation sites.
    Random rather than content-derived: a content-derived hex would churn
    the identity on an ordinary edit, which #228 forbids."""
    return secrets.token_hex(16)
