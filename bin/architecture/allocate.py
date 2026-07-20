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
            "payload": {"candidate_key": key},
        })
    return {"identities": identities, "records": records}


def _random_hex():
    """32 lowercase hex chars, mirroring context_graph's allocation sites.
    Random rather than content-derived: a content-derived hex would churn
    the identity on an ordinary edit, which #228 forbids."""
    return secrets.token_hex(16)
