"""Candidate records, entry points and the matcher projection (#229 child C,
slice C2, epic #141).

The frozen contract this exercises: bounded codebase-map + component
candidates, deterministic ordering, candidate provenance, and ENGINE-DERIVED
entry points from PROVIDER-INDEPENDENT facts with `is_exported` as a hint
only -- never authoritative.

THE INTEGRATION GUARD IS THE POINT OF THIS MODULE'S TESTS. #228's matcher
hard-aborts on any unknown candidate field, and child D -- the code that
would connect the two -- does not exist. So C tests that its own output
survives `matcher.match()` directly. Without it, a wrong guess about the
candidate shape is absorbed silently and surfaces only when D is built.

The corpus is literal hand-authored data. A corpus, a validator and a writer
that all route through one implementation prove agreement, not correctness.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import candidates
from architecture import matcher
from architecture import state

B1 = "binding:" + "1" * 32
FULL_CAPS = ["contains", "imports", "depends_on", "calls", "tests"]


def _binding(capabilities):
    return {
        "status": "loaded",
        "freshness": "current",
        "capabilities": list(capabilities),
        "coverage": [{"path_prefix": "", "capability": c, "status": "observed"}
                     for c in capabilities],
    }


def _q(value):
    return B1 + "::" + value


def _file(path):
    return {"path": path, "binding_id": B1}


def _symbol(name, path, kind="function", exported=None):
    entry = {"id": "sym:" + name, "name": name, "kind": kind, "path": path,
             "binding_id": B1}
    if exported is not None:
        entry["is_exported"] = exported
    return entry


def _edge(kind, source, target):
    return {"type": kind, "source": _q(source), "target": _q(target),
            "binding_id": B1}


PATHS = [
    "bin/auth/session.py",
    "bin/auth/tokens.py",
    "bin/render/html.py",
    "bin/render/markdown.py",
    "main.py",
]

GRAPH = {
    "bindings": {B1: _binding(FULL_CAPS)},
    "facts": {
        "files": {_q(p): _file(p) for p in PATHS},
        "symbols": {
            _q("sym:SessionStore"): _symbol(
                "SessionStore", "bin/auth/session.py", "class"),
            _q("sym:issue_token"): _symbol("issue_token", "bin/auth/tokens.py"),
            _q("sym:render_html"): _symbol("render_html", "bin/render/html.py"),
            _q("sym:render_md"): _symbol(
                "render_md", "bin/render/markdown.py"),
            _q("sym:main"): _symbol("main", "main.py"),
        },
        "edges": [
            _edge("imports", "bin/auth/session.py", "bin/auth/tokens.py"),
            _edge("imports", "bin/render/html.py", "bin/render/markdown.py"),
            _edge("imports", "main.py", "bin/auth/session.py"),
        ],
    },
    "findings": [],
}


def _plan(graph=None, **kwargs):
    return candidates.plan(graph or GRAPH, **kwargs)


def _by_key(result):
    return {c["candidate_key"]: c for c in result["candidates"]}


class Shape(unittest.TestCase):
    def setUp(self):
        self.result = _plan()

    def test_exactly_one_codebase_map_candidate(self):
        maps = [c for c in self.result["candidates"]
                if c["projection_type"] == "arch_codebase_map"]
        self.assertEqual(len(maps), 1)

    def test_one_component_candidate_per_cluster(self):
        components = [c for c in self.result["candidates"]
                      if c["projection_type"] == "arch_component"]
        self.assertEqual(len(components), len(self.result["clusters"]))

    def test_every_projection_type_is_frozen_vocabulary(self):
        for candidate in self.result["candidates"]:
            self.assertIn(candidate["projection_type"], state.PROJECTION_TYPES)

    def test_candidate_keys_are_unique(self):
        keys = [c["candidate_key"] for c in self.result["candidates"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_candidates_are_ordered_by_key(self):
        keys = [c["candidate_key"] for c in self.result["candidates"]]
        self.assertEqual(keys, sorted(keys))

    def test_every_candidate_carries_a_deterministic_name(self):
        for candidate in self.result["candidates"]:
            self.assertTrue(candidate["name"])

    def test_records_carry_only_known_fields(self):
        for candidate in self.result["candidates"]:
            self.assertEqual(
                set(candidate) - candidates.RECORD_FIELDS, set()
            )

    def test_output_is_identical_across_input_orderings(self):
        graph = {
            "bindings": GRAPH["bindings"],
            "facts": dict(
                GRAPH["facts"],
                files=dict(reversed(list(GRAPH["facts"]["files"].items()))),
                edges=list(reversed(GRAPH["facts"]["edges"])),
            ),
            "findings": [],
        }
        self.assertEqual(_plan(graph), self.result)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.result = _plan()
        self.auth = _by_key(self.result)["component:bin/auth"]

    def test_source_paths_are_the_cluster_members(self):
        self.assertEqual(
            self.auth["source_paths"],
            ["bin/auth/session.py", "bin/auth/tokens.py"],
        )

    def test_symbol_names_come_from_member_files_only(self):
        self.assertEqual(
            self.auth["symbol_names"], ["SessionStore", "issue_token"]
        )

    def test_symbol_names_are_names_never_provider_ids(self):
        # Scoring on a provider id routes every node to reconciliation on a
        # provider patch bump; the matcher has no field to carry one.
        for name in self.auth["symbol_names"]:
            self.assertFalse(name.startswith("sym:"))

    def test_neighborhood_excludes_the_cluster_s_own_members(self):
        for path in self.auth["neighborhood"]:
            self.assertNotIn(path, self.auth["source_paths"])

    def test_neighborhood_names_adjacent_paths(self):
        self.assertEqual(self.auth["neighborhood"], ["main.py"])

    def test_bindings_are_recorded_as_provenance(self):
        self.assertEqual(self.auth["bindings"], [B1])

    def test_no_excluded_path_reaches_any_candidate(self):
        graph = {
            "bindings": GRAPH["bindings"],
            "facts": dict(
                GRAPH["facts"],
                files=dict(GRAPH["facts"]["files"],
                           **{_q("vendor/x/y.go"): _file("vendor/x/y.go")}),
            ),
            "findings": [],
        }
        for candidate in _plan(graph)["candidates"]:
            self.assertNotIn("vendor/x/y.go", candidate["source_paths"])
            self.assertNotIn("vendor/x/y.go", candidate["neighborhood"])


class KeyStability(unittest.TestCase):
    def test_an_ordinary_edit_does_not_change_a_candidate_key(self):
        # The key is the join for the changed-set and feeds D's
        # preview->confirm fingerprint. A key that moves on every edit makes
        # the changed-set maximal and defeats AC11/PT31.
        graph = {
            "bindings": GRAPH["bindings"],
            "facts": dict(
                GRAPH["facts"],
                files=dict(GRAPH["facts"]["files"],
                           **{_q("bin/auth/recovery.py"):
                              _file("bin/auth/recovery.py")}),
            ),
            "findings": [],
        }
        self.assertIn("component:bin/auth", _by_key(_plan(graph)))

    def test_an_ordinary_edit_does_not_change_the_codebase_map_signals(self):
        # A map whose source_paths listed every file would change on every
        # commit, and that set is the join key D reuses for the changed-set.
        graph = {
            "bindings": GRAPH["bindings"],
            "facts": dict(
                GRAPH["facts"],
                files=dict(GRAPH["facts"]["files"],
                           **{_q("bin/auth/recovery.py"):
                              _file("bin/auth/recovery.py")}),
            ),
            "findings": [],
        }
        before = _by_key(_plan())[candidates.CODEBASE_MAP_KEY]
        after = _by_key(_plan(graph))[candidates.CODEBASE_MAP_KEY]
        self.assertEqual(after["source_paths"], before["source_paths"])
        self.assertEqual(after["symbol_names"], before["symbol_names"])

    def test_the_key_is_derived_from_the_dominant_path(self):
        self.assertIn("component:bin/render", _by_key(_plan()))

    def test_the_key_is_not_an_identity(self):
        # arch_id is B's to allocate at a confirmed creation event; a
        # candidate key must never look like one.
        for candidate in _plan()["candidates"]:
            self.assertFalse(candidate["candidate_key"].startswith("arch-node:"))


class EntryPoints(unittest.TestCase):
    def test_a_conventional_entry_name_is_derived(self):
        root = _by_key(_plan())["component:."]
        reasons = {e["path"]: e["reason"] for e in root["entry_points"]}
        self.assertEqual(reasons.get("main.py"), "conventional_name")

    def test_an_externally_uncalled_file_is_an_entry_point(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": {_q(p): _file(p) for p in
                          ["svc/run.py", "svc/lib.py"]},
                "symbols": {},
                "edges": [_edge("imports", "svc/run.py", "svc/lib.py")],
            },
            "findings": [],
        }
        entries = _by_key(_plan(graph))["component:svc"]["entry_points"]
        self.assertIn(
            ("svc/run.py", "no_dependents"),
            [(e["path"], e["reason"]) for e in entries],
        )

    def test_no_dependents_is_not_claimed_without_observability(self):
        # Absence-vs-zero again: with no dependency capability, "nothing
        # depends on it" is unknown, not observed.
        graph = {
            "bindings": {B1: _binding(["contains"])},
            "facts": {
                "files": {_q(p): _file(p) for p in
                          ["svc/run.py", "svc/lib.py"]},
                "symbols": {},
                "edges": [],
            },
            "findings": [],
        }
        for candidate in _plan(graph)["candidates"]:
            for entry in candidate["entry_points"]:
                self.assertNotEqual(entry["reason"], "no_dependents")

    def test_no_dependents_is_not_claimed_under_partial_coverage(self):
        # The gate that matters: the file HAS an observed dependency, so it
        # looks like an entry point, but its dependents could not be fully
        # observed. "Nothing depends on it" is then unknown, not zero.
        binding = _binding(FULL_CAPS)
        binding["coverage"] = binding["coverage"] + [
            {"path_prefix": "svc", "capability": "imports",
             "status": "partial_parse_failure"}
        ]
        graph = {
            "bindings": {B1: binding},
            "facts": {
                "files": {_q(p): _file(p) for p in
                          ["svc/run.py", "svc/lib.py"]},
                "symbols": {},
                "edges": [_edge("imports", "svc/run.py", "svc/lib.py")],
            },
            "findings": [],
        }
        for candidate in _plan(graph)["candidates"]:
            for entry in candidate["entry_points"]:
                self.assertNotEqual(entry["reason"], "no_dependents")

    def test_is_exported_is_never_authoritative(self):
        # A provider claiming everything is exported must not manufacture
        # entry points; the hint is not consumed at all in this slice.
        graph = {
            "bindings": {B1: _binding(FULL_CAPS + ["has_export_visibility"])},
            "facts": {
                "files": {_q(p): _file(p) for p in
                          ["svc/run.py", "svc/lib.py"]},
                "symbols": {
                    _q("sym:helper"): _symbol(
                        "helper", "svc/lib.py", exported=True),
                },
                "edges": [_edge("imports", "svc/run.py", "svc/lib.py")],
            },
            "findings": [],
        }
        entries = _by_key(_plan(graph))["component:svc"]["entry_points"]
        self.assertNotIn("svc/lib.py", [e["path"] for e in entries])

    def test_entry_points_are_sorted(self):
        for candidate in _plan()["candidates"]:
            paths = [e["path"] for e in candidate["entry_points"]]
            self.assertEqual(paths, sorted(paths))


class MatcherProjection(unittest.TestCase):
    def setUp(self):
        self.result = _plan()

    def test_the_view_carries_exactly_the_matcher_s_known_fields(self):
        for candidate in self.result["candidates"]:
            view = candidates.matcher_view(candidate)
            self.assertEqual(set(view), set(matcher.CANDIDATE_KNOWN))

    def test_the_view_keeps_every_required_field(self):
        for candidate in self.result["candidates"]:
            view = candidates.matcher_view(candidate)
            for field in matcher.CANDIDATE_REQUIRED:
                self.assertIn(field, view)

    def test_the_matcher_accepts_this_slice_s_own_output(self):
        # The integration guard. An unknown field is a hard abort, so this
        # failing is how a shape drift announces itself while D is unbuilt.
        views = [candidates.matcher_view(c)
                 for c in self.result["candidates"]]
        outcome = matcher.match(views, {"by_arch_id": {}})
        self.assertEqual(len(outcome["outcomes"]), len(views))

    def test_an_empty_log_mints_every_candidate(self):
        views = [candidates.matcher_view(c)
                 for c in self.result["candidates"]]
        outcome = matcher.match(views, {"by_arch_id": {}})
        self.assertEqual(
            sorted({o["outcome"] for o in outcome["outcomes"]}), ["mint"]
        )

    def test_the_view_drops_the_rich_fields(self):
        candidate = self.result["candidates"][0]
        view = candidates.matcher_view(candidate)
        for field in ("name", "metrics", "entry_points", "bindings"):
            self.assertNotIn(field, view)

    def test_the_view_is_a_copy_not_a_live_reference(self):
        candidate = _by_key(self.result)["component:bin/auth"]
        view = candidates.matcher_view(candidate)
        view["source_paths"].append("injected.py")
        self.assertNotIn("injected.py", candidate["source_paths"])


if __name__ == "__main__":
    unittest.main()
