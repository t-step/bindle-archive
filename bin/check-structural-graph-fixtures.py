#!/usr/bin/env python3
"""Manifest-driven fixture runner for the #227 structural-graph interchange.

Contains no independent copy of validation, coverage, redaction, or load
logic: every assertion runs the real structural_graph modules, so a fixture
can never pass against a reimplementation that drifted from the library.

Mirrors bin/check-context-graph-fixtures.py in shape and exit contract.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from structural_graph import document
from structural_graph import graphset
from structural_graph.redaction import REDACTION_PATTERNS


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def assert_load_status(fixture, base, config):
    # document.load (not load_json + load_object) so a fixture path that
    # does not exist on disk -- the deliberate absent-document case -- is
    # classified "unavailable" by the real module instead of crashing the
    # runner on an uncaught FileNotFoundError.
    result = document.load(os.path.join(base, fixture["path"]), config)
    problems = []
    if result["status"] != fixture["expect_status"]:
        problems.append(
            "status %s, expected %s" % (result["status"], fixture["expect_status"])
        )
    expected_freshness = fixture.get("expect_freshness")
    if expected_freshness and result["freshness"] != expected_freshness:
        problems.append(
            "freshness %s, expected %s" % (result["freshness"], expected_freshness)
        )
    actual = sorted(set(f["code"] for f in result["findings"]))
    expected = sorted(set(fixture.get("expect_codes") or []))
    if actual != expected:
        problems.append("codes %s, expected %s" % (actual, expected))
    return problems


def assert_set_load(fixture, base, config):
    paths = dict(
        (binding, os.path.join(base, rel))
        for binding, rel in fixture["documents"].items()
    )
    result = graphset.load_set(config, paths)
    problems = []
    for binding, expected in (fixture.get("expect_binding_status") or {}).items():
        actual = result["bindings"].get(binding, {}).get("status")
        if actual != expected:
            problems.append(
                "binding %s status %s, expected %s" % (binding, actual, expected)
            )
    expected_files = fixture.get("expect_file_count")
    if expected_files is not None and len(result["facts"]["files"]) != expected_files:
        problems.append(
            "file count %d, expected %d"
            % (len(result["facts"]["files"]), expected_files)
        )
    expected_file_keys = fixture.get("expect_file_keys")
    if expected_file_keys is not None:
        actual_file_keys = sorted(result["facts"]["files"].keys())
        if actual_file_keys != sorted(expected_file_keys):
            problems.append(
                "file keys %s, expected %s"
                % (actual_file_keys, sorted(expected_file_keys))
            )
    expected_symbol_keys = fixture.get("expect_symbol_keys")
    if expected_symbol_keys is not None:
        actual_symbol_keys = sorted(result["facts"]["symbols"].keys())
        if actual_symbol_keys != sorted(expected_symbol_keys):
            problems.append(
                "symbol keys %s, expected %s"
                % (actual_symbol_keys, sorted(expected_symbol_keys))
            )
    return problems


def assert_aggregate_coverage(fixture, base, config):
    paths = dict(
        (binding, os.path.join(base, rel))
        for binding, rel in fixture["documents"].items()
    )
    result = graphset.load_set(config, paths)
    actual = graphset.aggregate_coverage(
        result, fixture["capability"], fixture["query_path"]
    )
    if actual != fixture["expect_aggregate"]:
        return ["aggregate %s, expected %s" % (actual, fixture["expect_aggregate"])]
    return []


def _iter_corpus_documents(base):
    """Yield every fixture document path under base, manifest.json excluded.

    Discovers from disk rather than from manifest entries, so a fixture
    file referenced only inside another fixture's "documents" map (or not
    referenced at all) still gets scanned. Walk order is sorted so output
    stays deterministic between runs.
    """
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for filename in sorted(filenames):
            if filename == "manifest.json" or not filename.endswith(".json"):
                continue
            yield os.path.join(dirpath, filename)


def _secret_hits(blob):
    """Return the sorted, distinct REDACTION_PATTERNS names matched in blob.

    Runs the real compiled regexes -- the same ones redaction.redact uses
    to scrub a document -- so this check cannot drift from what the
    redactor actually does. A legitimately-redacted value reads
    "[redacted:<name>]", which contains none of the pattern shapes it
    replaced (no "/Users/", "@", "ghp_", "sk-", "AKIA", ...), so scanning
    the serialized output directly does not flag its own redaction marks.
    """
    return sorted(set(name for name, pattern in REDACTION_PATTERNS if pattern.search(blob)))


def _record_leaks(problems, source, result):
    for label in ("findings", "facts"):
        blob = json.dumps(result[label] or {})
        for name in _secret_hits(blob):
            problems.append(
                "%s: %s contains unredacted %s" % (source, label, name)
            )


def assert_redaction_purity(fixture, base, config):
    """No finding or fact anywhere in the corpus may carry a raw secret.

    This is the regression test for the context_graph.evidence defect, where
    an unsafe path was rejected and then echoed back verbatim in the result.

    Corpus-wide means two things: every fixture document on disk under
    testdata/structural-graph/v1/ is scanned through document.load (not
    only ones with a top-level manifest "path" entry), and every
    set_load/aggregate_coverage fixture's aggregated graphset.load_set
    result is scanned too, so the multi-binding merge/qualification path
    is policed as well as the single-document path.
    """
    problems = []

    for target in _iter_corpus_documents(base):
        result = document.load(target, config)
        _record_leaks(problems, os.path.relpath(target, base), result)

    manifest = load_json(os.path.join(base, "manifest.json"))
    for entry in manifest["fixtures"]:
        if entry.get("assertion") not in ("set_load", "aggregate_coverage"):
            continue
        paths = dict(
            (binding, os.path.join(base, rel))
            for binding, rel in entry["documents"].items()
        )
        result = graphset.load_set(config, paths)
        _record_leaks(problems, "graphset:%s" % entry["id"], result)

    return problems


ASSERTIONS = {
    "load_status": assert_load_status,
    "set_load": assert_set_load,
    "aggregate_coverage": assert_aggregate_coverage,
    "redaction_purity": assert_redaction_purity,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(args.manifest))
    manifest = load_json(args.manifest)
    config = manifest["config"]

    seen = set()
    failures = 0
    for fixture in manifest["fixtures"]:
        fixture_id = fixture["id"]
        if fixture_id in seen:
            print("  ✗ duplicate fixture id %s" % fixture_id)
            failures += 1
            continue
        seen.add(fixture_id)
        handler = ASSERTIONS.get(fixture["assertion"])
        if handler is None:
            print("  ✗ %s: unknown assertion %s" % (fixture_id, fixture["assertion"]))
            failures += 1
            continue
        problems = handler(fixture, base, config)
        if problems:
            failures += 1
            source = fixture.get("path") or fixture["assertion"]
            print("  ✗ %s (%s)" % (fixture_id, source))
            for problem in problems:
                print("      %s" % problem)

    total = len(manifest["fixtures"])
    if failures:
        print("fixtures: %d of %d failed" % (failures, total))
        return 1
    print("fixtures: all %d passed" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
