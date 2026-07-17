#!/usr/bin/env python3
"""check-context-graph-fixtures.py — thin CLI adapter over
bin/context_graph/ (issue #180, epic #140).

Drives the manifest-registered fixture corpus under
testdata/context-graph/v1/ through context_graph.validation.validate_bundle
(for "validate"-kind fixtures), or compares precomputed candidate_key and
dependency_fingerprint values for relation-kind fixtures (candidate_key_equals,
candidate_key_distinct, dependency_fingerprint_equals,
dependency_fingerprint_distinct). Those precomputed values are expected to have
been computed at fixture-authoring time and are already embedded in each
fixture bundle's candidates list; they are independently cross-checked at
validation time by context_graph.validation._check_candidates for edge-subject
candidates, and pinned byte-exactly by dedicated canonicalization/ fixtures in
the corpus. Reports pass/fail per fixture plus a summary. Contains no
independent copy of ID parsing, endpoint rules, candidate-key logic, or
canonicalization — `validate`-kind fixtures call `context_graph.validation.validate_bundle`; relation-kind fixtures compare package-precomputed values already embedded in the fixture bundles, as described above.

Manifest contract (testdata/context-graph/v1/manifest.json):

  {
    "schema_version": 1,
    "fixtures": [
      {
        "id": "43",
        "path": "endpoint-matrix/43-contains-project-to-semantic.json",
        "assertion": "validate",
        "expect_valid": true,
        "expect_codes": [],
        "match_mode": "exact",
        "coverage_tags": ["endpoint-matrix"],
        "invariant_ids": []
      },
      {
        "id": "75",
        "assertion": "candidate_key_equals",
        "with": ["75-human.json", "75-skill.json", "75-fixture.json"],
        "coverage_tags": ["candidates"]
      }
    ]
  }

`assertion: "validate"` fixtures point at one bundle JSON file (Task 4's
bundle shape) and are checked via validate_bundle; `expect_codes` is the
finding-code list, matched per `match_mode` ("exact" or
"ordered_subset" — the manifest marks which). `assertion:
"candidate_key_equals"`/`"candidate_key_distinct"`/
`"dependency_fingerprint_equals"`/`"dependency_fingerprint_distinct"`
fixtures point at multiple bundle files via `with` and compare a computed
value across them (fixtures 19, 75, 76, 80, 81 — see Tasks 8/12).

Exit codes: 0 all fixtures pass; 1 any fixture's actual result diverges
from its manifest expectation, a fixture has no manifest entry, or a
manifest path does not exist.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from context_graph import validation


def _load_bundle(manifest_dir, relative_path):
    full_path = os.path.join(manifest_dir, relative_path)
    if not os.path.isfile(full_path):
        raise FileNotFoundError(full_path)
    with open(full_path, encoding="utf-8") as fh:
        return json.load(fh)


def _run_validate_fixture(manifest_dir, entry):
    bundle = _load_bundle(manifest_dir, entry["path"])
    findings = validation.validate_bundle(bundle)
    actual_codes = [f["code"] for f in findings]
    actual_valid = len(findings) == 0
    expect_valid = entry["expect_valid"]
    expect_codes = entry.get("expect_codes", [])
    match_mode = entry.get("match_mode", "exact")

    ok = actual_valid == expect_valid
    if ok and not expect_valid:
        if match_mode == "exact":
            ok = actual_codes == expect_codes
        else:  # ordered_subset
            it = iter(actual_codes)
            ok = all(code in it for code in expect_codes)
    return {
        "id": entry["id"], "path": entry["path"], "ok": ok,
        "actual_valid": actual_valid, "actual_codes": actual_codes,
        "expect_valid": expect_valid, "expect_codes": expect_codes,
    }


def _candidate_value(manifest_dir, entry, path):
    bundle = _load_bundle(manifest_dir, path)
    candidates = bundle.get("candidates", [])
    if not candidates:
        raise ValueError("fixture %r has no candidates to compare" % (path,))
    cand = candidates[0]
    if entry["assertion"] in ("candidate_key_equals", "candidate_key_distinct"):
        return cand.get("candidate_key")
    return cand.get("dependency_fingerprint")


def _run_relation_fixture(manifest_dir, entry):
    values = [_candidate_value(manifest_dir, entry, p) for p in entry["with"]]
    if entry["assertion"].endswith("_equals"):
        ok = len(set(values)) == 1
    else:
        ok = len(set(values)) == len(values)
    return {
        "id": entry["id"], "path": ",".join(entry["with"]), "ok": ok,
        "actual_valid": None, "actual_codes": [], "expect_valid": None,
        "expect_codes": [],
    }


def run_manifest(manifest_path):
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    results = []
    seen_ids = set()
    for entry in manifest["fixtures"]:
        if entry["id"] in seen_ids:
            results.append({"id": entry["id"], "path": entry.get("path", ""),
                             "ok": False, "actual_valid": None, "actual_codes": [],
                             "expect_valid": None, "expect_codes": [],
                             "error": "duplicate fixture id"})
            continue
        seen_ids.add(entry["id"])
        try:
            if entry["assertion"] == "validate":
                results.append(_run_validate_fixture(manifest_dir, entry))
            else:
                results.append(_run_relation_fixture(manifest_dir, entry))
        except (FileNotFoundError, ValueError, KeyError) as exc:
            results.append({"id": entry["id"], "path": entry.get("path", ""),
                             "ok": False, "actual_valid": None, "actual_codes": [],
                             "expect_valid": None, "expect_codes": [],
                             "error": str(exc)})
    return results


def render_text(results):
    lines = []
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        lines.append("[%s] fixture %s (%s)" % (status, r["id"], r["path"]))
        if not r["ok"]:
            if r.get("error"):
                lines.append("    error: %s" % r["error"])
            else:
                lines.append(
                    "    expected valid=%s codes=%s; actual valid=%s codes=%s"
                    % (r["expect_valid"], r["expect_codes"], r["actual_valid"],
                       r["actual_codes"])
                )
    passed = sum(1 for r in results if r["ok"])
    lines.append("%d/%d fixtures passed" % (passed, len(results)))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        results = run_manifest(args.manifest)
    except OSError as exc:
        print("check-context-graph-fixtures: cannot read --manifest: %s" % exc,
              file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(render_text(results))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
