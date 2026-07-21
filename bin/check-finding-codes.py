#!/usr/bin/env python3
"""check-finding-codes.py — every finding code a validator can emit is either
classified in its surface's invariant-coverage.json or explicitly excluded
with a reason.

An invariant-coverage.json decides how a code is asserted: `schema-and-native`
codes must be rejected by BOTH the JSON Schema and the hand-rolled validator,
`native-only` codes by the validator alone. The conformance suites read it to
pick the direction. What nothing checked until now is whether the file is
COMPLETE — a code a validator emits but nobody classified is simply absent
from that reasoning, and both the schema suite and the unit suite stay green
while the invariant it names goes unasserted in one direction.

That gap was noticed and carried for five consecutive sessions across #228 and
#229 without being filed, because each individual slice had a defensible local
answer ("matcher codes aren't state codes"). This check makes the answer
explicit instead of implicit: a code is classified, or it is excluded WITH A
REASON, and there is no third option.

Scope is data-driven. Each invariant-coverage.json declares the source trees
it governs in a `sources` list, so adding a package means either adding it to
a surface or giving it a surface — neither of which can happen silently.
Codes under a `tests/` directory are not emissions; a test naming a code is
asserting about it, not producing it.

Usage: check-finding-codes.py [--root DIR]
Exit: 0 all accounted for · 1 a gap, a stale entry, or a malformed file
"""
import argparse
import json
import os
import re
import sys

CODE_RE = re.compile(r"""["'](E_[A-Z][A-Z0-9_]*)["']""")

# Surfaces that declare themselves not-yet-governed, reported on success so
# a clean run still says what it did NOT cover.
_NOTICES = []
COVERAGE_NAME = "invariant-coverage.json"


def _iter_coverage_files(root):
    schemas = os.path.join(root, "schemas")
    for dirpath, _dirnames, filenames in os.walk(schemas):
        if COVERAGE_NAME in filenames:
            yield os.path.join(dirpath, COVERAGE_NAME)


def _emitted_codes(root, sources):
    """code -> sorted repo-relative files that name it, tests excluded."""
    found = {}
    for source in sources:
        base = os.path.join(root, source)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "tests"]
            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    with open(path, encoding="utf-8") as handle:
                        text = handle.read()
                except OSError:
                    continue
                for code in CODE_RE.findall(text):
                    found.setdefault(code, set()).add(
                        os.path.relpath(path, root))
    return {code: sorted(paths) for code, paths in found.items()}


def _classified_codes(data):
    """The set of classified codes, whichever shape the file uses.

    Returns None when neither shape is present — a file that classifies
    nothing is malformed, not empty.
    """
    codes = data.get("codes")
    if isinstance(codes, dict):
        return set(codes)
    invariants = data.get("invariants")
    if isinstance(invariants, list):
        return {
            entry.get("code")
            for entry in invariants
            if isinstance(entry, dict) and entry.get("code")
        }
    return None


def _check_surface(root, path, problems):
    rel = os.path.relpath(path, root)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        problems.append("%s: unreadable (%s)" % (rel, exc))
        return 0, 0

    sources = data.get("sources")
    if not isinstance(sources, list):
        problems.append(
            '%s: no "sources" list — a coverage file must declare the source '
            "trees it governs, or it silently governs nothing" % rel)
        return 0, 0

    # An empty sources list is legitimate, but only when the file SAYS it
    # governs nothing yet and why. A surface whose codes have not been
    # triaged is a real state — context-graph's runtime and CLI codes were
    # never in scope for its schema-conformance file — and the choice is
    # between recording that in data or leaving it to be rediscovered every
    # few sessions, which is the habit this whole check exists to break.
    if not sources:
        note = data.get("ungoverned_reason")
        if not isinstance(note, str) or not note.strip():
            problems.append(
                '%s: "sources" is empty and no "ungoverned_reason" explains '
                "why — an ungoverned surface must be declared, not implied"
                % rel)
            return 0, 0
        _NOTICES.append("%s: not yet governed — %s" % (rel, note.strip()))
        return 0, 0

    # Two shapes are legitimate: a {code: classification} object, and a
    # list of {code, classification} records (what context-graph uses).
    # Supporting only one would leave a surface silently ungoverned, which is
    # the failure this check exists to prevent — so the shape is read, not
    # dictated. Both shapes stay supported now that the object-shaped surfaces
    # are gone (#384), because the next surface may use either.
    codes = _classified_codes(data)
    if codes is None:
        problems.append(
            '%s: no "codes" object and no "invariants" list' % rel)
        return 0, 0

    excluded = data.get("excluded_codes") or {}
    if not isinstance(excluded, dict):
        problems.append('%s: "excluded_codes" must be an object' % rel)
        return 0, 0

    for code, reason in sorted(excluded.items()):
        if not isinstance(reason, str) or not reason.strip():
            problems.append(
                "%s: %s is excluded with no reason — an exclusion without one "
                "is indistinguishable from an oversight" % (rel, code))
        if code in codes:
            problems.append(
                "%s: %s is both classified and excluded; it must be one or "
                "the other" % (rel, code))

    emitted = _emitted_codes(root, sources)
    accounted = codes | set(excluded)

    for code in sorted(set(emitted) - accounted):
        problems.append(
            "%s: %s is emitted by %s but is neither classified nor excluded"
            % (rel, code, ", ".join(emitted[code])))

    for code in sorted(accounted - set(emitted)):
        problems.append(
            "%s: %s is listed but no source under %s emits it (stale entry)"
            % (rel, code, ", ".join(sources)))

    return len(codes), len(excluded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)

    coverage_files = sorted(_iter_coverage_files(root))
    if not coverage_files:
        print("no %s found under schemas/ — nothing could be checked, which "
              "is a failure rather than a pass" % COVERAGE_NAME)
        return 1

    del _NOTICES[:]
    problems = []
    classified = excluded = 0
    for path in coverage_files:
        surface_classified, surface_excluded = _check_surface(
            root, path, problems)
        classified += surface_classified
        excluded += surface_excluded

    if problems:
        for problem in problems:
            print("  %s" % problem)
        return 1

    print("finding codes accounted for (%d classified, %d explicitly "
          "excluded, %d surface(s))"
          % (classified, excluded, len(coverage_files)))
    for notice in _NOTICES:
        print("  - %s" % notice)
    return 0


if __name__ == "__main__":
    sys.exit(main())
