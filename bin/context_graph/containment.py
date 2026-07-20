"""context_graph.containment — notes-home containment for planned writes
(#230 slice D2, epic #141 R2/PT26).

Every planned path must resolve BELOW the configured notes home AFTER
symlink resolution, and a plan containing any escaping path is rejected
WHOLE — never partially applied. This module answers that question and
nothing else: it performs no writes, creates no directories, and reports
rather than raises, so a caller can surface every offender at once.

It lives in context_graph/ rather than architecture/ for the reason
regions.py does: architecture already imports context_graph, and
projection.py writes into the same notes home, so both get one enforcement
point instead of two implementations that can drift.

Three properties are load-bearing, and each is a case a lexical path check
gets WRONG:

- Resolution happens on both sides. The notes home is user-relocatable and
  is commonly an Obsidian vault reached through a symlink; comparing a
  resolved path against an unresolved root would call every write an
  escape.
- Containment is a PATH-SEGMENT relation, not a string prefix. A sibling
  directory named `<root>-evil` shares the root's name as a prefix while
  living entirely outside it.
- A planned path does not exist yet. Resolution must therefore work
  through the deepest existing ancestor and treat the missing remainder
  lexically, which is exactly os.path.realpath's non-strict behavior — a
  symlinked ANCESTOR still escapes even when the leaf is absent.

Verdicts, never exceptions:

    check_path(root, path)  -> ("contained", None)
                            |  ("escapes", <resolved destination>)
    check_plan(root, paths) -> ("contained", ())
                            |  ("rejected", ((path, resolved), ...))

A malformed path (non-string, empty, or containing a NUL byte) is an
escape rather than an error: it cannot be shown to resolve below the root,
and the whole-plan rejection is the same either way.
"""
import os

__all__ = ["check_path", "check_plan"]


def _resolved_root(root):
    return os.path.realpath(root)


def _is_below(root_real, resolved):
    """Segment-wise containment. Equality is NOT containment — writes must
    land below the notes home, not at it."""
    if resolved == root_real:
        return False
    return resolved.startswith(root_real.rstrip(os.sep) + os.sep)


def check_path(root, path):
    """Report whether `path` resolves strictly below `root`.

    A relative path is interpreted against `root`, which is where planned
    note paths are rooted; an absolute path is taken as given.
    """
    if not isinstance(path, str) or not path or "\x00" in path:
        return ("escapes", None)

    root_real = _resolved_root(root)
    candidate = path if os.path.isabs(path) else os.path.join(root_real, path)
    resolved = os.path.realpath(candidate)

    if _is_below(root_real, resolved):
        return ("contained", None)
    return ("escapes", resolved)


def check_plan(root, paths):
    """Verdict for a whole plan: every path or none.

    Returns ("contained", ()) or ("rejected", ((path, resolved), ...)) with
    EVERY offender in plan order — an operator fixing one escaping path
    should not have to re-run to discover the next.
    """
    offenders = []
    for path in paths:
        verdict, resolved = check_path(root, path)
        if verdict != "contained":
            offenders.append((path, resolved))
    if offenders:
        return ("rejected", tuple(offenders))
    return ("contained", ())
