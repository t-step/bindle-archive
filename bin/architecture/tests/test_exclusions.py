"""Exclusion and privacy filtering for candidate planning (#229 child C,
slice C1, epic #141).

The frozen contract this exercises: candidate generation must exclude
generated, vendored, dependency, cache, build, gitignored and explicitly
private paths, and must normalize to repository-relative form. An excluded
path never appears in a candidate, in a metric, or in a finding.

Two properties beyond "the filter filters":

EXCLUSION IS OBSERVABLE. A dropped path is reported with the source that
dropped it and the pattern that matched, because "the map is missing a
subsystem" and "the map excluded a subsystem on purpose" are the same
picture without it.

EXCLUSION IS PURE. Patterns arrive as arguments. Nothing here opens
.gitignore, reads a denylist file, or shells out to git -- the same rule
state.py holds by taking the notes home as a parameter.

The corpus below is literal hand-authored data. A corpus, a validator and a
writer that all route through one implementation prove agreement, not
correctness.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import exclusions

# ---------------------------------------------------------------- corpus

# Ordinary source that must always survive every filter.
KEPT = [
    "bin/auth/session.py",
    "bin/auth/tokens.py",
    "bin/render/html.py",
    "src/main.rs",
    "README.md",
]

# One representative of each default-excluded class.
VENDORED = "vendor/github.com/pkg/errors/errors.go"
DEPENDENCY = "node_modules/left-pad/index.js"
CACHE = "bin/__pycache__/session.cpython-311.pyc"
BUILD = "dist/bundle.js"
GENERATED = "api/service_pb2.py"


class BuiltInExclusions(unittest.TestCase):
    def test_ordinary_source_is_kept(self):
        for path in KEPT:
            self.assertIsNone(exclusions.exclusion_reason(path))

    def test_vendored_is_excluded_as_default(self):
        reason = exclusions.exclusion_reason(VENDORED)
        self.assertIsNotNone(reason)
        self.assertEqual(reason["source"], "default")

    def test_dependency_tree_is_excluded(self):
        self.assertIsNotNone(exclusions.exclusion_reason(DEPENDENCY))

    def test_cache_is_excluded_at_any_depth(self):
        self.assertIsNotNone(exclusions.exclusion_reason(CACHE))

    def test_build_output_is_excluded(self):
        self.assertIsNotNone(exclusions.exclusion_reason(BUILD))

    def test_generated_code_is_excluded(self):
        self.assertIsNotNone(exclusions.exclusion_reason(GENERATED))

    def test_defaults_can_be_disabled(self):
        self.assertIsNone(exclusions.exclusion_reason(VENDORED, defaults=False))

    def test_reason_names_the_pattern_that_matched(self):
        reason = exclusions.exclusion_reason(DEPENDENCY)
        self.assertIn("pattern", reason)
        self.assertIn("node_modules", reason["pattern"])

    def test_every_default_pattern_is_a_string(self):
        self.assertTrue(exclusions.DEFAULT_EXCLUSION_PATTERNS)
        for pattern in exclusions.DEFAULT_EXCLUSION_PATTERNS:
            self.assertIsInstance(pattern, str)


class PatternSemantics(unittest.TestCase):
    def test_star_does_not_cross_a_segment_boundary(self):
        self.assertIsNone(
            exclusions.exclusion_reason(
                "src/app.py", configured=["*.py"], defaults=False
            )
        )

    def test_star_matches_within_one_segment(self):
        self.assertIsNotNone(
            exclusions.exclusion_reason(
                "app.py", configured=["*.py"], defaults=False
            )
        )

    def test_double_star_crosses_segment_boundaries(self):
        self.assertIsNotNone(
            exclusions.exclusion_reason(
                "src/deep/nested/app.py", configured=["**/*.py"], defaults=False
            )
        )

    def test_directory_pattern_matches_everything_beneath_it(self):
        self.assertIsNotNone(
            exclusions.exclusion_reason(
                "docs/design/notes.md", configured=["docs/"], defaults=False
            )
        )

    def test_directory_pattern_does_not_match_a_prefix_of_a_name(self):
        self.assertIsNone(
            exclusions.exclusion_reason(
                "docsite/index.md", configured=["docs/"], defaults=False
            )
        )

    def test_bare_segment_matches_at_any_depth(self):
        self.assertIsNotNone(
            exclusions.exclusion_reason(
                "a/b/node_modules/c/d.js",
                configured=["node_modules"],
                defaults=False,
            )
        )


class ConfiguredAndGitignore(unittest.TestCase):
    def test_configured_exclusion_is_sourced_as_configured(self):
        reason = exclusions.exclusion_reason(
            "bin/auth/session.py", configured=["bin/auth/"]
        )
        self.assertEqual(reason["source"], "configured")

    def test_gitignore_exclusion_is_sourced_as_gitignore(self):
        reason = exclusions.exclusion_reason(
            "bin/auth/session.py", gitignore=["bin/auth/"]
        )
        self.assertEqual(reason["source"], "gitignore")

    def test_gitignore_negation_rescues_a_path(self):
        self.assertIsNone(
            exclusions.exclusion_reason(
                "bin/auth/session.py",
                gitignore=["bin/auth/", "!bin/auth/session.py"],
                defaults=False,
            )
        )

    def test_gitignore_comments_and_blanks_are_ignored(self):
        self.assertIsNone(
            exclusions.exclusion_reason(
                "bin/auth/session.py",
                gitignore=["# bin/auth/", "", "   "],
                defaults=False,
            )
        )

    def test_source_precedence_is_deterministic(self):
        # A path matching several sources reports one reason, always the
        # same one, so a diff of exclusion output is stable.
        reason = exclusions.exclusion_reason(
            VENDORED, configured=["vendor/"], gitignore=["vendor/"]
        )
        self.assertEqual(reason["source"], "default")


class Privacy(unittest.TestCase):
    def test_denylist_term_excludes_the_path(self):
        reason = exclusions.exclusion_reason(
            "bin/rivendell/secret.py", denylist=["rivendell"]
        )
        self.assertEqual(reason["source"], "private")

    def test_denylist_match_is_case_insensitive(self):
        self.assertIsNotNone(
            exclusions.exclusion_reason(
                "bin/Rivendell/secret.py", denylist=["rivendell"]
            )
        )

    def test_denylist_reason_never_echoes_the_term(self):
        # The reason travels into findings and logs. Naming the private term
        # there would leak exactly what the denylist exists to suppress.
        reason = exclusions.exclusion_reason(
            "bin/rivendell/secret.py", denylist=["rivendell"]
        )
        self.assertNotIn("rivendell", repr(reason).lower())

    def test_privacy_outranks_every_other_source(self):
        reason = exclusions.exclusion_reason(
            "vendor/rivendell/x.go", denylist=["rivendell"]
        )
        self.assertEqual(reason["source"], "private")

    def test_empty_denylist_term_matches_nothing(self):
        self.assertIsNone(
            exclusions.exclusion_reason(
                "bin/auth/session.py", denylist=["", "   "], defaults=False
            )
        )


class Normalization(unittest.TestCase):
    def test_absolute_path_is_refused_as_unnormalizable(self):
        reason = exclusions.exclusion_reason(
            "/Users/someone/repo/app.py"  # private-ok: synthetic fixture
        )
        self.assertEqual(reason["source"], "unnormalizable")

    def test_home_relative_path_is_refused(self):
        reason = exclusions.exclusion_reason("~/repo/app.py")
        self.assertEqual(reason["source"], "unnormalizable")

    def test_traversal_is_refused(self):
        reason = exclusions.exclusion_reason("bin/../../etc/passwd")
        self.assertEqual(reason["source"], "unnormalizable")

    def test_dot_slash_prefix_is_normalized_not_refused(self):
        self.assertIsNone(exclusions.exclusion_reason("./bin/auth/session.py"))

    def test_normalization_happens_before_pattern_matching(self):
        reason = exclusions.exclusion_reason(
            "./vendor/pkg/errors.go", defaults=True
        )
        self.assertEqual(reason["source"], "default")

    def test_root_bounds_what_is_in_scope(self):
        reason = exclusions.exclusion_reason("other/app.py", root="src")
        self.assertEqual(reason["source"], "unnormalizable")


class Partition(unittest.TestCase):
    def test_kept_paths_are_normalized_sorted_and_unique(self):
        result = exclusions.partition_paths(
            ["./b.py", "a.py", "b.py"], defaults=False
        )
        self.assertEqual(result["kept"], ["a.py", "b.py"])

    def test_excluded_entries_carry_path_source_and_pattern(self):
        result = exclusions.partition_paths(KEPT + [VENDORED])
        self.assertEqual(len(result["excluded"]), 1)
        entry = result["excluded"][0]
        self.assertEqual(entry["path"], VENDORED)
        self.assertEqual(entry["source"], "default")
        self.assertIn("pattern", entry)

    def test_excluded_entries_are_sorted_by_path(self):
        result = exclusions.partition_paths([DEPENDENCY, BUILD, VENDORED])
        paths = [entry["path"] for entry in result["excluded"]]
        self.assertEqual(paths, sorted(paths))

    def test_an_excluded_path_never_appears_in_kept(self):
        result = exclusions.partition_paths(KEPT + [VENDORED, DEPENDENCY])
        self.assertEqual(result["kept"], sorted(KEPT))

    def test_unnormalizable_path_is_excluded_never_kept(self):
        result = exclusions.partition_paths(
            ["/Users/someone/x.py", "a.py"]  # private-ok: synthetic fixture
        )
        self.assertEqual(result["kept"], ["a.py"])
        self.assertEqual(result["excluded"][0]["source"], "unnormalizable")

    def test_unnormalizable_entry_reports_a_redacted_path(self):
        # The rejected value is the one most likely to carry a home
        # directory, and it travels onward as an exclusion report.
        result = exclusions.partition_paths(
            ["/Users/someone/x.py"]  # private-ok: synthetic fixture
        )
        self.assertNotIn("someone", repr(result["excluded"][0]))

    def test_partition_is_byte_identical_across_input_orderings(self):
        forward = exclusions.partition_paths(KEPT + [VENDORED, DEPENDENCY])
        reverse = exclusions.partition_paths(
            list(reversed(KEPT + [VENDORED, DEPENDENCY]))
        )
        self.assertEqual(forward, reverse)

    def test_applied_exclusions_are_echoed_for_observability(self):
        result = exclusions.partition_paths(KEPT, configured=["x/"])
        self.assertIn("applied", result)
        self.assertIn("configured", result["applied"])
        self.assertEqual(result["applied"]["configured"], ["x/"])

    def test_empty_input_is_not_an_error(self):
        result = exclusions.partition_paths([])
        self.assertEqual(result["kept"], [])
        self.assertEqual(result["excluded"], [])


if __name__ == "__main__":
    unittest.main()
