"""architecture.loop -- the confirm and apply halves of the projection
loop (issue #374 child D, slice D5c, epic #141).

`preview` builds the plan and writes nothing; `apply.apply` writes but is
handed every input by its caller. This module is the caller, and it is
where the epic's two confirmation rules become executable:

  "A confirmation binds the plan it was given for. Preview emits a plan
   fingerprint; apply recomputes it and aborts if inputs changed between
   preview and apply, rather than writing a plan the user never saw."

  "The confirmation policy is static configuration -- which change classes
   require confirmation, and the note-count and diff-size thresholds."

TWO DIFFERENT QUESTIONS, DELIBERATELY SPLIT ACROSS THE TWO VERBS.

`confirm` answers "is the token I am holding still the current plan, and
does this plan need my explicit approval at all?" It writes nothing and
decides nothing on the operator's behalf: `requires_confirmation` is a
REPORT, and a caller that ignores it can still apply. Making it a refusal
would put a policy veto in a read-only verb and give the operator no way
to approve a large-but-correct refresh.

`apply` answers "write it." It re-plans from scratch inside `apply.apply`
and compares fingerprints there, which is the abort PT25 names. This
module does NOT pre-check the token and skip the call on mismatch: the
authoritative comparison happens under the project lock, and a check out
here would be a second, racier copy of it.

A PREVIEWED arch_id IS PROVISIONAL. Because `apply` rebuilds the plan in
its own process, a first-ever run mints DIFFERENT hexes than the preview
the operator read, and the ones apply mints are the ones committed. That
is safe rather than sloppy: `arch_id` enters no fingerprint term, which is
precisely why the token still matches across the two runs. It is also
unavoidable -- the only thing carried between the two commands is the
token, and persisting a pre-minted identity would append a creation event
nobody confirmed. Every later preview reads the identity back from the log
and is exact.

THE TOKEN IS NEVER PERSISTED. #230 bars the fingerprint from
`apply-state.json` three ways over; it is ephemeral invocation state that
the operator carries from one command to the next. That is why `confirm`
stores nothing and why re-running `preview` is always a legal way to
recover a token.

WHY BOTH VERBS REBUILD THE PREVIEW. Every input apply re-plans from --
`records`, `identities`, `config`, `bindings`, `provider` -- must be the
same one preview planned from, or the re-plan yields a different
fingerprint and the run burns as `stale_preview`. Rebuilding through
`preview.build_preview` is what guarantees that; assembling the inputs a
second way here would be a second implementation of the chain, free to
drift from the one the operator actually read.
"""
from architecture import apply as arch_apply
from architecture import preview as arch_preview
from architecture import project as arch_project

# Codes new with this slice. Both describe an INVOCATION -- a token that
# no longer matches, a plan that could not be built to confirm against --
# rather than a property of a persisted document.
E_CONFIRM_NO_PLAN = "E_ARCH_CONFIRM_NO_PLAN"
E_CONFIRM_STALE_TOKEN = "E_ARCH_CONFIRM_STALE_TOKEN"

# The note states that mean apply would write this entry. `current` is the
# only one that does not.
_WRITING_STATES = ("absent", "changed")


def _finding(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d


def diff_size(preview_result):
    """How many notes this plan would write.

    Counted from `note_state`, which is decided against CURRENT DISK,
    rather than from the plan-level `disposition` -- preview passes
    `previous=()` because nothing on disk reconstructs the prior run's
    rich candidate records, so every disposition reads `mint` and would
    report a full rewrite every run."""
    return sum(1 for entry in preview_result["entries"]
               if entry["note_state"] in _WRITING_STATES)


def confirmation_reasons(preview_result, config):
    """Why this plan needs explicit approval, as a list of reasons.

    The confirmation policy is STATIC CONFIGURATION owned by child B, so
    every threshold here is read from `config.json` and none is invented.
    An empty list means the plan is a straightforward, high-confidence
    refresh -- the class the epic allows to be applied together once the
    user approves the plan."""
    reasons = []
    limit = (config or {}).get("diff_size_confirmation_limit")
    size = diff_size(preview_result)
    if isinstance(limit, int) and size > limit:
        reasons.append({
            "reason": "diff_size_over_limit",
            "detail": "%d note(s) would be written, over the configured "
                      "diff_size_confirmation_limit of %d" % (size, limit),
        })
    if preview_result["over_cap"]:
        reasons.append({
            "reason": "over_cap",
            "detail": "%d candidate(s) rank below the note cap and are "
                      "reported rather than created"
                      % (len(preview_result["over_cap"]),),
        })
    if preview_result["deferred"]:
        reasons.append({
            "reason": "deferred_candidates",
            "detail": "%d candidate(s) are deferred and will not be "
                      "projected" % (len(preview_result["deferred"]),),
        })
    conflicts = [entry for entry in preview_result["entries"]
                 if entry["note_state"] == "conflict"]
    if conflicts:
        reasons.append({
            "reason": "note_conflict",
            "detail": "%d note(s) conflict with what is on disk and will "
                      "not be overwritten" % (len(conflicts),),
        })
    return reasons


def confirm(notes_home, project_slug, graph_paths, fingerprint,
            provider=None, decided_at=None):
    """Check a held token against the current plan. WRITES NOTHING.

    Returns the preview's own shape plus `confirmed`, `requires_confirmation`
    and `confirmation_reasons`. `confirmed` is False -- with
    `E_ARCH_CONFIRM_STALE_TOKEN` -- when the inputs moved since the token
    was printed, which is PT25 caught one step before apply rather than
    after it."""
    result = arch_preview.build_preview(
        notes_home, project_slug, graph_paths, provider=provider,
        decided_at=decided_at)
    out = dict(result)
    out["confirmed"] = False
    out["requires_confirmation"] = False
    out["confirmation_reasons"] = []
    out["expected_fingerprint"] = fingerprint

    if not result["ok"]:
        out["findings"] = list(result["findings"]) + [_finding(
            E_CONFIRM_NO_PLAN,
            "there is no current plan to confirm against; the preview it "
            "would be compared with could not be built")]
        return out

    config = arch_project.load_config(
        arch_project.config_path(notes_home, project_slug))
    reasons = confirmation_reasons(result, config)
    out["requires_confirmation"] = bool(reasons)
    out["confirmation_reasons"] = reasons

    if fingerprint != result["fingerprint"]:
        out["ok"] = False
        out["findings"] = list(result["findings"]) + [_finding(
            E_CONFIRM_STALE_TOKEN,
            "the plan moved since that fingerprint was printed; re-run "
            "`preview` and confirm the plan you can actually read")]
        return out

    out["confirmed"] = True
    return out


def apply_confirmed(notes_home, project_slug, graph_paths, fingerprint,
                    provider=None, decided_at=None, projected_at=None):
    """Rebuild the plan and write it under the held token.

    The fingerprint comparison is NOT made here. `apply.apply` re-plans
    under the project lock and compares there, returning `stale_preview`;
    duplicating the check out here would be a second copy of it racing the
    real one."""
    result = arch_preview.build_preview(
        notes_home, project_slug, graph_paths, provider=provider,
        decided_at=decided_at)
    if not result["ok"]:
        return {"status": "rejected", "ok": False,
                "findings": list(result["findings"]) + [_finding(
                    E_CONFIRM_NO_PLAN,
                    "the plan to apply could not be built; nothing was "
                    "written")],
                "writes": [], "conflicts": [], "orphans": [],
                "resumed": False, "preview": result}

    config = arch_project.load_config(
        arch_project.config_path(notes_home, project_slug))
    applied = arch_apply.apply(
        notes_home, project_slug, result["project_id"], result["records"],
        fingerprint,
        identities=result["identities"],
        identity_records=result["identity_records"],
        config=config,
        bindings=result["bindings"],
        provider=provider,
        projected_at=projected_at)
    out = dict(applied)
    out["preview"] = result
    return out
